"""GameState movement tracking: types, direction, arrival, pushes and callbacks."""

import logging
import threading
import time
from unittest.mock import patch

import pytest

from empire_core.combat import commander_bonuses
from empire_core.commanders.models.roster import Commander, CommanderEffect
from empire_core.enums import MapItemType, MovementType, NPCOwner
from empire_core.gamedata import GameData
from empire_core.movements.tracked import Movement
from empire_core.state.manager import GameState
from tests.state.state_helpers import arrive, gam_payload, later, login, push_payload, wait_for


class TestAttackCallbacks:
    def test_new_attack_fires_callback_once(self, state):
        login(state)
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)

        state.update_from_packet("gam", gam_payload(100))
        assert wait_for(lambda: len(fired) == 1)

        # Refreshes of the SAME movement must not re-fire the callback
        state.update_from_packet("gam", gam_payload(100))
        state.update_from_packet("gam", gam_payload(100))
        time.sleep(0.1)
        assert len(fired) == 1

    def test_own_outgoing_attack_does_not_fire(self, state):
        # Establish the local player
        state.update_from_packet("gbd", {"gpi": {"PID": 999, "PN": "me"}})
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)

        # Movement owned by the local player (OID=999) => own attack
        state.update_from_packet("gam", gam_payload(101, oid=999))
        time.sleep(0.2)
        assert fired == []

    def test_non_attack_movement_does_not_fire(self, state):
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        state.update_from_packet("gam", gam_payload(102, movement_type=1))  # 1 = DEFENCE (support)
        time.sleep(0.2)
        assert fired == []

    def test_callbacks_survive_multiple_dispatch_cycles(self, state):
        login(state)
        # Executor is created lazily and must keep working after shutdown+reuse
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        state.update_from_packet("gam", gam_payload(103))
        assert wait_for(lambda: len(fired) == 1)

        state.shutdown()

        # New packets after a shutdown (e.g. after reconnect) recreate the pool
        state.update_from_packet("gam", gam_payload(104))
        assert wait_for(lambda: len(fired) == 2)

    def test_npc_attack_fires(self, state):
        login(state)
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        state.update_from_packet("gam", gam_payload(105, movement_type=11))  # 11 = NPC_ATTACK
        assert wait_for(lambda: len(fired) == 1)

    def test_returning_attack_does_not_fire(self, state):
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        state.update_from_packet("gam", gam_payload(106, extra={"D": 1}))
        time.sleep(0.2)
        assert fired == []


class TestWithdrawnAttacks:
    """mrm before arrival on an announced attack: CastleArmyData.parse_MRM vs updateMapmovements."""

    @staticmethod
    def watch(state: GameState) -> tuple[list[str], list[Movement]]:
        events: list[str] = []
        withdrawn: list[Movement] = []
        state.on_movement_removed(lambda mid: events.append("removed"))

        def on_withdrawn(mov: Movement) -> None:
            events.append("withdrawn")
            withdrawn.append(mov)

        state.on_incoming_attack_withdrawn(on_withdrawn)
        return events, withdrawn

    def test_an_announced_attack_removed_before_arrival_is_withdrawn(self, state):
        login(state)
        events, withdrawn = self.watch(state)
        state.update_from_packet("gam", gam_payload(150))
        with later(300):
            state.update_from_packet("mrm", {"MID": 150})
        assert wait_for(lambda: events == ["removed", "withdrawn"])
        assert [mov.movement_id for mov in withdrawn] == [150]
        assert withdrawn[0].source_player_name == "Attacker"

    def test_an_attack_removed_at_its_arrival_time_is_not_withdrawn(self, state):
        # No packet in between, so state has not yet seen the arrival time pass
        login(state)
        events, _ = self.watch(state)
        state.update_from_packet("gam", gam_payload(151))
        with later(600):
            state.update_from_packet("mrm", {"MID": 151})
        assert wait_for(lambda: events == ["removed"])
        time.sleep(0.1)
        assert events == ["removed"]

    def test_an_attack_removed_just_before_its_estimate_is_not_withdrawn(self, state):
        # estimated_arrival can run a second late, so this may be the landing
        login(state)
        events, _ = self.watch(state)
        state.update_from_packet("gam", gam_payload(156))
        with later(state.movements[156].estimated_arrival - time.time() - 0.5):
            state.update_from_packet("mrm", {"MID": 156})
        assert wait_for(lambda: events == ["removed"])
        time.sleep(0.1)
        assert events == ["removed"]

    def test_an_arrived_attack_is_not_withdrawn(self, state):
        login(state)
        events, _ = self.watch(state)
        state.update_from_packet("gam", gam_payload(152))
        arrive(state, 152)
        state.update_from_packet("mrm", {"MID": 152})
        assert wait_for(lambda: events == ["removed"])
        time.sleep(0.1)
        assert events == ["removed"]

    def test_an_attack_state_no_longer_tracks_is_not_withdrawn(self, state):
        login(state)
        events, _ = self.watch(state)
        state.update_from_packet("gam", gam_payload(153))
        state.reset()
        state.update_from_packet("mrm", {"MID": 153})
        state.update_from_packet("mrm", {"MID": 9999})
        assert wait_for(lambda: events == ["removed", "removed"])
        time.sleep(0.1)
        assert events == ["removed", "removed"]

    @pytest.mark.parametrize(
        "payload",
        [gam_payload(154, oid=1), gam_payload(154, movement_type=1), gam_payload(154, extra={"D": 1})],
        ids=["own attack", "support", "on its way home"],
    )
    def test_a_movement_never_announced_is_not_withdrawn(self, state, payload):
        login(state)
        events, _ = self.watch(state)
        state.update_from_packet("gam", payload)
        state.update_from_packet("mrm", {"MID": 154})
        assert wait_for(lambda: events == ["removed"])
        time.sleep(0.1)
        assert events == ["removed"]

    def test_a_removed_callback_no_longer_fires(self, state):
        login(state)
        withdrawn: list[Movement] = []
        state.on_incoming_attack_withdrawn(withdrawn.append)
        state.remove_incoming_attack_withdrawn_callback(withdrawn.append)
        state.update_from_packet("gam", gam_payload(155))
        state.update_from_packet("mrm", {"MID": 155})
        time.sleep(0.1)
        assert withdrawn == []
        with pytest.raises(ValueError):
            state.remove_incoming_attack_withdrawn_callback(withdrawn.append)


class TestUpdatedAttacks:
    """Later packets for an announced attack, compared field by field."""

    @staticmethod
    def wrapper(mid: int, extra: dict | None = None, **blocks) -> dict:
        payload = gam_payload(mid, extra=extra)
        payload["M"][0].update(blocks)
        return payload

    @staticmethod
    def watch(state: GameState) -> list[tuple[Movement, Movement]]:
        updates: list[tuple[Movement, Movement]] = []
        state.on_incoming_attack_updated(lambda old, new: updates.append((old, new)))
        return updates

    @staticmethod
    def settle(state: GameState) -> None:
        marker = threading.Event()
        state._dispatch_callback(marker.set)
        assert marker.wait(2)

    def test_the_army_becoming_visible_fires_once(self, state):
        login(state)
        updates = self.watch(state)
        state.update_from_packet("gam", self.wrapper(170, GS=1200))
        state.update_from_packet("gam", self.wrapper(170, GA={"L": [[1, 5]], "M": [[2, 7]]}))
        state.update_from_packet("gam", self.wrapper(170, GA={"L": [[1, 5]], "M": [[2, 7]]}))
        self.settle(state)
        [(old, new)] = updates
        assert (old.units, old.estimated_size) == ({}, 1200)
        assert new.units == {1: 5, 2: 7}

    def test_the_size_estimate_appearing_fires(self, state):
        login(state)
        updates = self.watch(state)
        state.update_from_packet("gam", self.wrapper(171))
        state.update_from_packet("gam", self.wrapper(171, GS=800))
        self.settle(state)
        assert [(old.estimated_size, new.estimated_size) for old, new in updates] == [(0, 800)]

    def test_each_change_of_arrival_fires_once(self, state):
        login(state)
        updates = self.watch(state)
        state.update_from_packet("gam", self.wrapper(172))
        state.update_from_packet("gam", self.wrapper(172, extra={"TT": 300}))
        state.update_from_packet("gam", self.wrapper(172, extra={"TT": 300}))
        state.update_from_packet("gam", self.wrapper(172, extra={"TT": 100}))
        self.settle(state)
        assert [round(old.estimated_arrival - new.estimated_arrival) for old, new in updates] == [300, 200]

    def test_time_passing_between_packets_is_not_a_change(self, state):
        login(state)
        updates = self.watch(state)
        state.update_from_packet("gam", self.wrapper(173))
        with later(30.9):
            state.update_from_packet("gam", self.wrapper(173, extra={"PT": 30}))
        self.settle(state)
        assert updates == []

    def test_a_new_target_fires(self, state):
        login(state)
        updates = self.watch(state)
        state.update_from_packet("gam", self.wrapper(174, extra={"TA": [1, 10, 20, 5, 1]}))
        state.update_from_packet("gam", self.wrapper(174, extra={"TA": [1, 30, 40, 6, 1]}))
        self.settle(state)
        [(old, new)] = updates
        assert ((old.target_x, old.target_y), (new.target_x, new.target_y)) == ((10, 20), (30, 40))

    def test_the_commander_gear_arriving_fires(self, state):
        login(state)
        updates = self.watch(state)
        commander = {"L": {"ID": 4, "EQ": [[901, 2, 2, 3, 0, [[242, [25.0]]]]], "AE": [[426, [10.0], "GE"]]}}
        state.update_from_packet("gam", self.wrapper(175))
        state.update_from_packet("gam", self.wrapper(175, UM=commander))
        state.update_from_packet("gam", self.wrapper(175))
        self.settle(state)
        [(old, new)] = updates
        assert old.commander is None and new.commander is not None
        assert [item.equipment_id for item in new.commander.equipment] == [901]
        assert state.movements[175].commander == new.commander

    def test_nothing_fires_for_a_movement_never_announced(self, state):
        login(state)
        updates = self.watch(state)
        for payload in (gam_payload(176, oid=1), gam_payload(177, movement_type=1)):
            state.update_from_packet("gam", payload)
            payload["M"][0]["M"]["TT"] = 100
            state.update_from_packet("gam", payload)
        self.settle(state)
        assert updates == []

    def test_nothing_fires_once_the_attack_has_arrived(self, state):
        login(state)
        updates = self.watch(state)
        state.update_from_packet("gam", self.wrapper(178))
        arrive(state, 178)
        state.update_from_packet("gam", self.wrapper(178, extra={"TT": 900}))
        self.settle(state)
        assert updates == []

    def test_the_announcement_comes_first_and_fires_once(self, state):
        login(state)
        events: list[str] = []
        state.on_incoming_attack(lambda mov: events.append("incoming"))
        state.on_incoming_attack_updated(lambda old, new: events.append("updated"))
        state.update_from_packet("gam", self.wrapper(179))
        state.update_from_packet("gam", self.wrapper(179, GS=50))
        self.settle(state)
        assert events == ["incoming", "updated"]

    def test_a_removed_callback_no_longer_fires(self, state):
        login(state)
        updates: list[tuple[Movement, Movement]] = []

        def callback(old: Movement, new: Movement) -> None:
            updates.append((old, new))

        state.on_incoming_attack_updated(callback)
        state.remove_incoming_attack_updated_callback(callback)
        state.update_from_packet("gam", self.wrapper(180))
        state.update_from_packet("gam", self.wrapper(180, GS=50))
        self.settle(state)
        assert updates == []
        with pytest.raises(ValueError):
            state.remove_incoming_attack_updated_callback(callback)


class TestOccupationCallbacks:
    """Occupations: SiegeMapmovementVO (bundle line 33173), shown by FilterAttack and FilterAllianceIncoming."""

    ME, ALLY, ENEMY, OUTSIDER, CLAN = 1, 2, 3, 4, 301

    @staticmethod
    def watch(state: GameState) -> list[tuple[str, Movement | None]]:
        events: list[tuple[str, Movement | None]] = []
        state.on_incoming_attack(lambda mov: events.append(("attack", mov)))
        state.on_incoming_attack_updated(lambda old, new: events.append(("attack updated", new)))
        state.on_incoming_attack_withdrawn(lambda mov: events.append(("attack withdrawn", mov)))
        state.on_occupation_started(lambda mov: events.append(("occupation", mov)))
        state.on_occupation_updated(lambda old, new: events.append(("occupation updated", new)))
        state.on_occupation_ended(lambda mov, captured: events.append(("captured" if captured else "broken", mov)))
        state.on_movement_arrived(lambda mid, mov: events.append(("arrived", mov)))
        state.on_movement_removed(lambda mid, mov: events.append(("removed", mov)))
        return events

    @staticmethod
    def settle(state: GameState) -> None:
        marker = threading.Event()
        state._dispatch_callback(marker.set)
        assert marker.wait(2)

    @staticmethod
    def names(events: list[tuple[str, Movement | None]]) -> list[tuple[str, int | None]]:
        return [(name, mov.movement_id if mov else None) for name, mov in events]

    @pytest.mark.parametrize("movement_type", [MovementType.SIEGE, MovementType.OCCUPY_FACTION])
    def test_an_occupation_of_mine_is_announced_once_and_not_as_an_attack(self, state, movement_type):
        login(state)
        events = self.watch(state)
        state.update_from_packet("gam", gam_payload(400, movement_type=movement_type))
        state.update_from_packet("gam", gam_payload(400, movement_type=movement_type))
        self.settle(state)
        assert self.names(events) == [("occupation", 400)]

    def test_an_occupation_of_the_daimyo_township_is_announced(self, state):
        # getOwnerInfoVO (bundle line 138994) gives the township your own owner info
        login(state)
        events = self.watch(state)
        state.update_from_packet("gam", gam_payload(401, movement_type=MovementType.SIEGE, tid=-815))
        self.settle(state)
        assert [name for name, _ in events] == ["occupation"]

    @pytest.mark.parametrize("owner", [ENEMY, -202])
    def test_an_occupation_of_an_alliance_member_is_announced_whoever_sends_it(self, state, owner):
        login(state, self.ME, self.CLAN)
        events = self.watch(state)
        payload = gam_payload(402, movement_type=MovementType.SIEGE, oid=owner, tid=self.ALLY)
        payload["O"] = [{"OID": self.ALLY, "AID": self.CLAN, "N": "ally"}]
        state.update_from_packet("gam", payload)
        self.settle(state)
        assert [name for name, _ in events] == ["occupation"]

    @pytest.mark.parametrize(
        "payload",
        [
            gam_payload(403, movement_type=MovementType.SIEGE, oid=1),
            gam_payload(403, movement_type=MovementType.SIEGE, extra={"D": 1}),
            gam_payload(403, movement_type=MovementType.SIEGE, tid=OUTSIDER),
            gam_payload(403, movement_type=MovementType.DEFENCE),
        ],
        ids=["own occupation", "on its way home", "of an outsider", "support"],
    )
    def test_an_occupation_not_of_us_is_neither_announced_nor_ended(self, state, payload):
        login(state, self.ME, self.CLAN)
        events = self.watch(state)
        payload["O"].append({"OID": self.OUTSIDER, "AID": 99, "N": "outsider"})
        state.update_from_packet("gam", payload)
        state.update_from_packet("mrm", {"MID": 403})
        self.settle(state)
        assert [name for name, _ in events] == ["removed"]

    def test_a_changed_occupation_is_updated(self, state):
        login(state)
        events = self.watch(state)
        state.update_from_packet("gam", gam_payload(404, movement_type=MovementType.SIEGE))
        state.update_from_packet("gam", gam_payload(404, movement_type=MovementType.SIEGE, extra={"TT": 300}))
        state.update_from_packet("gam", gam_payload(404, movement_type=MovementType.SIEGE, extra={"TT": 300}))
        self.settle(state)
        assert [name for name, _ in events] == ["occupation", "occupation updated"]

    def test_an_occupation_whose_army_changes_is_updated(self, state):
        # SiegeMapmovementVO.parseArmy (bundle line 33176) reads the wrapper's A block
        login(state)
        events = self.watch(state)
        for army in ([[216, 5]], [[216, 9]]):
            payload = gam_payload(408, movement_type=MovementType.SIEGE)
            payload["M"][0]["A"] = army
            state.update_from_packet("gam", payload)
        self.settle(state)
        assert [(name, mov.units if mov else None) for name, mov in events] == [
            ("occupation", {216: 5}),
            ("occupation updated", {216: 9}),
        ]

    def test_an_occupation_removed_before_its_end_is_broken(self, state):
        login(state)
        events = self.watch(state)
        state.update_from_packet("gam", gam_payload(405, movement_type=MovementType.SIEGE))
        with later(300):
            state.update_from_packet("mrm", {"MID": 405})
        self.settle(state)
        assert self.names(events) == [("occupation", 405), ("removed", 405), ("broken", 405)]
        assert events[-1][1] is not None and events[-1][1].source_player_name == "Attacker"

    def test_an_occupation_whose_time_runs_out_is_captured_once(self, state):
        login(state)
        events = self.watch(state)
        state.update_from_packet("gam", gam_payload(406, movement_type=MovementType.SIEGE))
        arrive(state, 406)
        with later(900):
            state.get_all_movements()
            state.update_from_packet("mrm", {"MID": 406})
        self.settle(state)
        assert self.names(events) == [("occupation", 406), ("arrived", 406), ("captured", 406), ("removed", None)]

    @pytest.mark.parametrize("before_end", [0.5, -60], ids=["just before its estimate", "after it"])
    def test_an_occupation_removed_at_its_end_is_captured(self, state, before_end):
        # No packet in between, so state has not yet seen the arrival time pass
        login(state)
        events = self.watch(state)
        state.update_from_packet("gam", gam_payload(409, movement_type=MovementType.SIEGE))
        with later(state.movements[409].estimated_arrival - time.time() - before_end):
            state.update_from_packet("mrm", {"MID": 409})
        self.settle(state)
        assert self.names(events) == [("occupation", 409), ("removed", 409), ("captured", 409)]

    def test_an_occupation_state_no_longer_tracks_does_not_end(self, state):
        login(state)
        events = self.watch(state)
        state.update_from_packet("gam", gam_payload(410, movement_type=MovementType.SIEGE))
        state.reset()
        state.update_from_packet("mrm", {"MID": 410})
        self.settle(state)
        assert self.names(events) == [("occupation", 410), ("removed", None)]

    def test_an_occupation_is_not_announced_again_after_a_reconnect(self, state):
        login(state)
        events = self.watch(state)
        state.update_from_packet("gam", gam_payload(407, movement_type=MovementType.SIEGE))
        state.reset()
        login(state)
        state.update_from_packet("gam", gam_payload(407, movement_type=MovementType.SIEGE))
        self.settle(state)
        assert [name for name, _ in events] == ["occupation"]

    def test_removed_callbacks_no_longer_fire(self, state):
        login(state)
        fired: list[object] = []

        def one(mov: Movement) -> None:
            fired.append(mov)

        def two(old: Movement, new: Movement) -> None:
            fired.append(new)

        def ended(mov: Movement, captured: bool) -> None:
            fired.append(mov)

        state.on_occupation_started(one)
        state.on_occupation_updated(two)
        state.on_occupation_ended(ended)
        state.remove_occupation_started_callback(one)
        state.remove_occupation_updated_callback(two)
        state.remove_occupation_ended_callback(ended)
        state.update_from_packet("gam", gam_payload(408, movement_type=MovementType.SIEGE))
        state.update_from_packet("gam", gam_payload(408, movement_type=MovementType.SIEGE, extra={"TT": 100}))
        state.update_from_packet("mrm", {"MID": 408})
        self.settle(state)
        assert fired == []


class TestMovementDirection:
    ME = 1

    @pytest.fixture
    def me(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": self.ME, "PN": "me"}})
        return state

    def test_own_attack_is_outgoing_not_incoming(self, me):
        me.update_from_packet("gam", gam_payload(700, oid=self.ME, tid=555))
        mov = me.get_movement_by_id(700)
        assert mov is not None and mov.is_mine and mov.is_outgoing
        assert not mov.is_incoming
        assert me.get_incoming_attacks() == []
        assert [m.movement_id for m in me.get_outgoing_movements()] == [700]

    def test_attack_on_me_is_incoming(self, me):
        me.update_from_packet("gam", gam_payload(701, oid=555, tid=self.ME))
        assert [m.movement_id for m in me.get_incoming_attacks()] == [701]
        assert me.get_outgoing_movements() == []

    def test_npc_attack_on_me_is_incoming(self, me):
        me.update_from_packet("gam", gam_payload(702, movement_type=11, oid=-1, tid=self.ME))
        assert [m.movement_id for m in me.get_incoming_attacks()] == [702]

    def test_support_to_me_is_incoming_but_not_an_attack(self, me):
        me.update_from_packet("gam", gam_payload(703, movement_type=1, oid=555, tid=self.ME))
        assert [m.movement_id for m in me.get_incoming_movements()] == [703]
        assert me.get_incoming_attacks() == []

    @pytest.mark.parametrize("movement_type", [MovementType.SIEGE, MovementType.OCCUPY_FACTION])
    @pytest.mark.parametrize("tid", [ME, NPCOwner.DAIMYO_TOWNSHIP])
    def test_occupation_of_my_area_is_not_incoming(self, me, movement_type, tid):
        # SiegeMapmovementVO keeps BasicMapmovementVO.isAttackingMovement (bundle line 19438): false
        me.update_from_packet("gam", gam_payload(709, movement_type=movement_type, oid=555, tid=tid))
        mov = me.get_movement_by_id(709)
        assert mov is not None and mov.is_occupation and not mov.is_incoming
        assert me.get_incoming_movements() == []
        assert me.get_incoming_attacks() == []

    def test_returning_army_is_neither_incoming_nor_outgoing(self, me):
        me.update_from_packet("gam", gam_payload(704, oid=self.ME, tid=555, extra={"D": 1}))
        me.update_from_packet("gam", gam_payload(705, oid=555, tid=self.ME, extra={"D": 1}))
        for mid in (704, 705):
            mov = me.get_movement_by_id(mid)
            assert mov is not None and mov.is_returning
        assert me.get_incoming_movements() == []
        assert me.get_outgoing_movements() == []

    def test_travel_between_own_castles_is_outgoing_only(self, me):
        me.update_from_packet("gam", gam_payload(706, movement_type=2, oid=self.ME, tid=self.ME))
        mov = me.get_movement_by_id(706)
        assert mov is not None and mov.is_travel and mov.is_outgoing and not mov.is_incoming

    def test_attack_on_someone_else_is_not_incoming(self, me):
        me.update_from_packet("gam", gam_payload(707, oid=555, tid=666))
        assert me.get_incoming_attacks() == []

    def test_without_a_local_player_nothing_is_incoming(self, state):
        state.update_from_packet("gam", gam_payload(708, tid=1))
        assert state.get_incoming_attacks() == []
        assert state.get_outgoing_movements() == []


class TestMovementTypes:
    @pytest.mark.parametrize("t", [0, 11, 17, 18, 19, 20, 21, 23, 24, 25, 27, 28, 29, 30, 31, 33, 34])
    def test_attack_types(self, t):
        mov = Movement(movement_type=t)
        assert mov.is_attack and not mov.is_support and not mov.is_occupation

    @pytest.mark.parametrize("t", [1, 26, 32])
    def test_support_types(self, t):
        mov = Movement(movement_type=t)
        assert mov.is_support and not mov.is_attack

    @pytest.mark.parametrize("t", [5, 15])
    def test_occupation_types(self, t):
        assert Movement(movement_type=t).is_occupation

    def test_single_value_types(self):
        assert Movement(movement_type=2).is_travel
        assert Movement(movement_type=3).is_spy
        assert Movement(movement_type=4).is_transport
        assert not Movement(movement_type=2).is_transport

    @pytest.mark.parametrize("t", [2, 3, 4, 6, 14])
    def test_non_combat_types_are_not_attacks(self, t):
        assert not Movement(movement_type=t).is_attack

    def test_names_follow_the_client(self):
        assert Movement(movement_type=1).movement_type_name == "DEFENCE"
        assert Movement(movement_type=11).movement_type_name == "NPC_ATTACK"
        assert Movement(movement_type=99).movement_type_name == "UNKNOWN_99"

    def test_a_type_the_client_lacks_has_no_enum(self):
        movement = Movement(movement_type=-1)
        assert movement.movement_type_enum is None
        assert not (movement.is_attack or movement.is_support or movement.is_occupation)
        assert Movement(movement_type=11).movement_type_enum is MovementType.NPC_ATTACK

    def test_target_type_reads_as_an_area_type(self):
        assert Movement(target_type=1).target_type_enum is MapItemType.CASTLE
        assert Movement(target_type=43).target_type_enum is MapItemType.ARE_PORTAL
        assert Movement(target_type=32).target_type_enum is None
        assert Movement().target_type_enum is None

    def test_direction_flag_marks_returns_for_any_type(self):
        assert Movement(movement_type=11, direction=0).is_returning is False
        assert Movement(movement_type=4, direction=1).is_returning


class TestMovementLifecycle:
    def test_update_preserves_created_at_and_names(self, state):
        state.update_from_packet("gam", gam_payload(200))
        first = state.get_movement_by_id(200)
        assert first is not None
        created = first.created_at
        assert first.source_player_name == "Attacker"

        time.sleep(0.02)
        # Update without owner info
        state.update_from_packet("abr", {"A": {"M": {"MID": 200, "T": 0, "PT": 60, "TT": 600, "D": 0, "OID": 999}}})
        updated = state.get_movement_by_id(200)
        assert updated is not None
        assert updated.created_at == created
        assert updated.source_player_name == "Attacker"

    def test_arrival_removes_movement(self, state):
        arrived: list[int] = []
        state.on_movement_arrived(arrived.append)
        state.update_from_packet("gam", gam_payload(201))
        assert state.get_movement_by_id(201) is not None

        arrive(state, 201)
        assert state.get_movement_by_id(201) is None
        assert wait_for(lambda: arrived == [201])

    def test_arrival_fires_once(self, state):
        arrived: list[int] = []
        state.on_movement_arrived(arrived.append)
        state.update_from_packet("gam", gam_payload(206))
        arrive(state, 206)
        state.get_all_movements()
        state.update_from_packet("xyz", {})
        time.sleep(0.15)
        assert arrived == [206]

    def test_any_packet_advances_arrivals(self, state):
        arrived: list[int] = []
        state.on_movement_arrived(arrived.append)
        state.update_from_packet("gam", gam_payload(207))
        # A packet state has no handler for still drives arrivals
        with later(601):
            state.update_from_packet("xyz", {})
        assert 207 not in state.movements
        assert wait_for(lambda: arrived == [207])

    def test_mrm_removes_movement_without_calling_it_a_recall(self, state):
        removed: list[int] = []
        recalled: list[int] = []
        state.on_movement_removed(removed.append)
        state.on_movement_recalled(recalled.append)
        state.update_from_packet("gam", gam_payload(202))
        state.update_from_packet("mrm", {"MID": 202})
        assert state.get_movement_by_id(202) is None
        assert wait_for(lambda: removed == [202])
        time.sleep(0.1)
        assert recalled == []

    def test_mcm_replaces_the_movement_with_its_way_home(self, state):
        recalled: list[Movement] = []
        state.on_movement_recalled(lambda mid, mov: recalled.append(mov))
        state.update_from_packet("gam", gam_payload(208))
        state.update_from_packet(
            "mcm", {"A": {"M": {"MID": 208, "T": 0, "PT": 0, "TT": 300, "D": 1, "OID": 999, "TID": 1}}}
        )
        mov = state.get_movement_by_id(208)
        assert mov is not None and mov.is_returning
        assert mov.source_player_name == "Attacker", "recall lost the owner metadata"
        assert wait_for(lambda: len(recalled) == 1)
        assert recalled[0].is_returning

    def test_mfc_marks_movement_force_cancelable(self, state):
        state.update_from_packet("gam", gam_payload(209))
        state.update_from_packet("mfc", {"MID": 209})
        state.update_from_packet("gam", gam_payload(209))
        mov = state.get_movement_by_id(209)
        assert mov is not None and mov.force_cancelable
        state.update_from_packet("mfc", {"MID": 9999})  # unknown: ignored

    def test_missed_arrival_dropped_on_next_packet(self, state):
        state.update_from_packet("gam", gam_payload(203))
        with later(10_000):
            state.update_from_packet("gam", gam_payload(204))
        assert state.get_movement_by_id(203) is None
        assert state.get_movement_by_id(204) is not None

    def test_queries_return_snapshots(self, state):
        state.update_from_packet("gam", gam_payload(205))
        movements = state.get_all_movements()
        assert len(movements) == 1
        # Mutating the snapshot must not affect internal state
        movements.clear()
        assert len(state.get_all_movements()) == 1


class TestMovementPushes:
    def test_abr_attack_on_me_fires_incoming_attack(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 1, "PN": "me"}})
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        payload = push_payload(210, oid=555)
        payload["O"] = [{"OID": 555, "N": "Raider", "AN": "Raiders"}]
        state.update_from_packet("asr", payload)
        assert wait_for(lambda: len(fired) == 1)
        assert fired[0].source_player_name == "Raider"
        assert [m.movement_id for m in state.get_incoming_attacks()] == [210]

    def test_push_reads_the_wrapper_not_the_payload(self, state):
        # abr carries the wrapper under A; a top-level M must not be parsed
        state.update_from_packet("abr", {"M": {"MID": 211, "T": 0, "TT": 600}})
        assert state.movements == {}


class TestStationedMovements:
    """Supports stay at their target for UM.TWD seconds after arriving and
    keep appearing in gam with PT > TT while they do."""

    @staticmethod
    def stationed_gam(mid: int, pt: int, tt: int, pwd: int, twd: int = 3600) -> dict:
        payload = gam_payload(mid, movement_type=1, extra={"PT": pt, "TT": tt})
        payload["M"][0]["UM"] = {"PWD": pwd, "TWD": twd}
        return payload

    def test_support_arrives_once_and_stays_stationed(self, state):
        arrived: list[int] = []
        state.on_movement_arrived(arrived.append)
        state.update_from_packet("gam", self.stationed_gam(220, pt=0, tt=300, pwd=0))
        arrive(state, 220)
        assert wait_for(lambda: arrived == [220])

        with later(301):
            mov = state.get_movement_by_id(220)
            assert mov is not None and mov.is_stationed

        # Later polls list it with PT past TT; that is not a new arrival
        state.update_from_packet("gam", self.stationed_gam(220, pt=364, tt=300, pwd=64))
        state.update_from_packet("gam", self.stationed_gam(220, pt=384, tt=300, pwd=84))
        time.sleep(0.15)
        assert arrived == [220]
        assert state.get_movement_by_id(220) is not None

    def test_support_already_stationed_when_first_seen_is_not_an_arrival(self, state):
        arrived: list[int] = []
        state.on_movement_arrived(arrived.append)
        for _ in range(3):
            state.update_from_packet("gam", self.stationed_gam(221, pt=325, tt=261, pwd=64))
        time.sleep(0.15)
        assert arrived == []
        mov = state.get_movement_by_id(221)
        assert mov is not None and mov.is_stationed

    def test_stationed_support_leaves_state_when_its_wait_is_over(self, state):
        state.update_from_packet("gam", self.stationed_gam(222, pt=325, tt=261, pwd=64))
        with later(3600):
            assert state.get_movement_by_id(222) is None

    def test_attack_first_seen_after_landing_does_not_alert(self, state):
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        state.update_from_packet("gam", gam_payload(223, extra={"PT": 700, "TT": 600}))
        time.sleep(0.15)
        assert fired == []
        assert state.get_movement_by_id(223) is None


class TestMovementTime:
    def test_time_remaining_advances_with_wall_clock(self):
        mov = Movement(movement_id=1, movement_type=0, progress_time=0, total_time=100, direction=0)
        mov.last_updated = time.time() - 30
        # 100s total, packet 30s ago => ~70s remaining
        assert 65 <= mov.time_remaining <= 71
        assert not mov.has_arrived()

    def test_has_arrived_after_eta_passes(self):
        mov = Movement(movement_id=2, movement_type=0, progress_time=90, total_time=100, direction=0)
        mov.last_updated = time.time() - 60  # 10s remained, 60s ago
        assert mov.time_remaining == 0
        assert mov.has_arrived()

    def test_resources_total_includes_special(self):
        from empire_core.movements.tracked import MovementResources

        res = MovementResources(mead=5, aquamarine=2, coal=1, oil=4)
        assert (res.aquamarine, res.coal, res.oil) == (2, 1, 4)
        assert res.total == 12
        assert not res.is_empty


class TestMovementWrapperBlocks:
    @staticmethod
    def stored(state: GameState, **blocks) -> Movement:
        payload = gam_payload(900)
        payload["M"][0].update(blocks)
        state.update_from_packet("gam", payload)
        mov = state.get_movement_by_id(900)
        assert mov is not None
        return mov

    def test_full_army_is_read_before_army(self, state):
        mov = self.stored(state, FA={"M": [[1, 5]], "RW": [[2, 1]]}, GA={"M": [[9, 9]]})
        assert mov.units == {1: 5, 2: 1}

    def test_full_army_alone_gives_units(self, state):
        assert self.stored(state, FA={"L": [[3, 2]], "R": [[3, 1]]}).units == {3: 3}

    def test_hidden_army_only_has_a_size(self, state):
        mov = self.stored(state, GS=1164)
        assert mov.units == {} and mov.estimated_size == 1164

    def test_travel_units_and_loot(self, state):
        # Live capture of a return home
        mov = self.stored(state, A=[[216, 500]], G=[["W", 8], ["S", 7], ["F", 21], ["C1", 28]])
        assert mov.units == {216: 500}
        assert (mov.resources.wood, mov.resources.stone, mov.resources.food) == (8, 7, 21)
        assert ("C1", 28) in mov.goods

    def test_market_cargo(self, state):
        mov = self.stored(state, MM={"C": 3, "G": [["A", 40], ["O", 5]]})
        assert mov.market_carriages == 3
        assert (mov.resources.aquamarine, mov.resources.oil) == (40, 5)

    def test_attack_flags_and_advisor(self, state):
        mov = self.stored(
            state,
            ATT=0,
            SM=1,
            FC=1,
            AST=[651, 652],
            ASCT=2,
            UM={
                "PWD": 0,
                "TWD": 30,
                "AAT": 1,
                "AAC": 3,
                "AAN": 3,
                "AAL": 1,
                "L": {"ID": 4, "EQ": [[901, 2, 2, 3, 0, [[242, [25.0]]]]], "AE": [[426, [10.0], "GE"], "junk"]},
            },
        )
        assert (mov.attack_type, mov.is_shadow, mov.force_cancelable) == (0, True, True)
        assert (mov.support_tool_ids, mov.auto_skip_cooldown_type) == ([651, 652], 2)
        assert (mov.advisor_type, mov.advisor_movement_count, mov.advisor_movement_number) == (1, 3, 3)
        assert mov.advisor_is_last
        assert mov.commander is not None
        [item] = mov.commander.equipment
        assert (item.equipment_id, item.slot) == (901, 2)
        assert [(b.effect_id, b.values) for b in item.bonuses] == [(242, [25.0])]
        assert mov.commander.area_effects == [CommanderEffect(effect_id=426, values=[10.0], source="GE")]
        assert mov.battle_time == pytest.approx(mov.estimated_arrival + 30)

    def test_one_unreadable_block_does_not_drop_the_attack(self, state):
        login(state)
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        mov = self.stored(state, AST="junk", GA={"M": [[1, 2]]})
        assert mov.units == {1: 2} and mov.support_tool_ids == []
        assert wait_for(lambda: len(fired) == 1)

    def test_the_spy_details_are_kept(self, state):
        # SpyMapmovementVO.parseSpyInfo; the live csm reply's S block
        mov = self.stored(state, S={"SC": 2, "ST": 0, "SA": 100, "SR": 26})
        assert mov.spy is not None
        assert (mov.spy.spy_type, mov.spy.accuracy_or_damage, mov.spy.spy_count, mov.spy.risk) == (0, 100, 2, 26)

    def test_a_movement_without_spies_has_no_spy_details(self, state):
        assert self.stored(state, GA={"M": [[1, 2]]}).spy is None

    def test_unreadable_commander_keeps_the_wait(self, state):
        mov = self.stored(state, UM={"PWD": 5, "TWD": 30, "L": {"EQ": "junk"}})
        assert (mov.wait_passed, mov.wait_total) == (5, 30)
        assert mov.commander is None


class TestStaleMovementPruning:
    """Arrival packets get missed (socket errors, disconnect windows), so every
    mutation and query path must prune — not just the gam handler."""

    def test_pruned_on_pushed_mov_packet(self, state):
        state.update_from_packet("abr", push_payload(300, tt=1))

        with later(10_000):
            state.update_from_packet("abr", push_payload(301))
        assert 300 not in state.movements
        assert 301 in state.movements

    def test_pruned_on_query_without_any_gam(self, state):
        # A consumer driven purely by push callbacks never calls gam
        state.update_from_packet("gbd", {"gpi": {"PID": 1, "PN": "me"}})
        state.update_from_packet("abr", push_payload(302, tt=1))

        with later(10_000):
            assert state.get_incoming_attacks() == []
            assert state.get_all_movements() == []
            assert state.get_incoming_movements() == []
            assert state.get_outgoing_movements() == []
            assert state.get_movement_by_id(302) is None
        assert state.movements == {}, "movements dict grows without bound"

    def test_refreshed_movement_is_not_resurrected_as_new(self, state):
        login(state)
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        state.update_from_packet("abr", push_payload(304, tt=1))
        assert wait_for(lambda: len(fired) == 1)

        # The server pushes a fresh update for the same movement (it was
        # overdue, not gone). Pruning must not drop it just before the update
        # is stored, or the consumer gets a duplicate attack alert.
        with later(10_000):
            state.update_from_packet("abr", push_payload(304, tt=900))

        time.sleep(0.15)
        assert len(fired) == 1, "stale-then-refreshed movement re-alerted as new"
        assert 304 in state.movements

    def test_arrival_is_not_delayed(self, state):
        # There is no arrival packet to wait for: once travel time is up the
        # movement has arrived.
        state.update_from_packet("abr", push_payload(303, tt=1))

        with later(10):
            assert state.get_movement_by_id(303) is None
            assert state.get_all_movements() == []


class _CountingDict(dict):
    scans = 0

    def items(self):
        type(self).scans += 1
        return super().items()


class TestArrivalScheduling:
    """Movements are scanned only once one is due, and then in the order state first saw them."""

    def test_a_packet_with_nothing_due_does_not_scan_the_movements(self, state):
        for mid in range(400, 450):
            state.update_from_packet("abr", push_payload(mid, tt=600))
        state.movements = _CountingDict(state.movements)
        _CountingDict.scans = 0
        for _ in range(20):
            state.update_from_packet("sne", {"MSG": []})
        state.get_all_movements()
        assert _CountingDict.scans == 0
        with later(601):
            state.update_from_packet("sne", {"MSG": []})
        assert _CountingDict.scans == 1
        assert state.movements == {}

    def test_arrivals_fire_in_the_order_the_movements_were_first_seen(self, state):
        arrived: list[int] = []
        state.on_movement_arrived(arrived.append)
        state.update_from_packet("abr", push_payload(460, tt=300))
        state.update_from_packet("abr", push_payload(461, tt=100))
        state.update_from_packet("abr", push_payload(462, tt=200))
        with later(301):
            state.update_from_packet("sne", {"MSG": []})
        assert wait_for(lambda: len(arrived) == 3)
        assert arrived == [460, 461, 462]

    def test_an_update_that_brings_the_arrival_forward_is_seen(self, state):
        arrived: list[int] = []
        state.on_movement_arrived(arrived.append)
        state.update_from_packet("abr", push_payload(463, tt=900))
        state.update_from_packet("abr", push_payload(463, tt=10))
        with later(11):
            state.update_from_packet("sne", {"MSG": []})
        assert wait_for(lambda: arrived == [463])

    def test_a_removed_movement_seen_again_can_arrive(self, state):
        arrived: list[int] = []
        state.on_movement_arrived(arrived.append)
        # Stationed when first seen, so its arrival is behind it; then removed and sent again
        state.update_from_packet("gam", TestStationedMovements.stationed_gam(464, pt=325, tt=261, pwd=64))
        state.update_from_packet("mrm", {"MID": 464})
        state.update_from_packet("gam", TestStationedMovements.stationed_gam(464, pt=0, tt=300, pwd=0))
        arrive(state, 464)
        assert wait_for(lambda: arrived == [464])


class TestMovementParseFailures:
    """Schema drift must not silently swallow every incoming attack."""

    BAD = {"A": {"M": {"MID": "not-an-int", "T": 1}}}

    def test_parse_failure_is_visible_at_default_level(self, state, caplog):
        with caplog.at_level(logging.DEBUG, logger="empire_core.state.movements"):
            state.update_from_packet("abr", self.BAD)

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1, "movement parse failure invisible at INFO"
        assert warnings[0].exc_info is not None, "no traceback: schema drift undiagnosable"
        assert state.movements == {}

    def test_repeated_failures_do_not_flood(self, state, caplog):
        with caplog.at_level(logging.DEBUG, logger="empire_core.state.movements"):
            for _ in range(25):
                state.update_from_packet("abr", self.BAD)

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1, f"log flooded with {len(warnings)} warnings"

    def test_next_warning_after_window_reports_suppressed_count(self, state, caplog):
        with caplog.at_level(logging.DEBUG, logger="empire_core.state.movements"):
            for _ in range(5):
                state.update_from_packet("abr", self.BAD)
            # The rate-limit window expires; the next failure must warn again
            # and account for the four failures suppressed in between.
            with patch("time.time", return_value=time.time() + 61):
                state.update_from_packet("abr", self.BAD)

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 2, "window expiry did not re-enable the warning"
        assert "4 further failures suppressed" in warnings[1].getMessage()


class TestCallbackRegistrationLocking:
    """Registration/removal run on user threads while the receive thread
    iterates the listener lists, so they must synchronize on the state lock —
    CPython's per-op atomicity is not a guarantee to build on."""

    @pytest.mark.parametrize(
        ("register", "remove"),
        [
            ("on_incoming_attack", "remove_incoming_attack_callback"),
            ("on_incoming_attack_updated", "remove_incoming_attack_updated_callback"),
            ("on_incoming_attack_withdrawn", "remove_incoming_attack_withdrawn_callback"),
            ("on_occupation_started", "remove_occupation_started_callback"),
            ("on_occupation_updated", "remove_occupation_updated_callback"),
            ("on_occupation_ended", "remove_occupation_ended_callback"),
            ("on_movement_arrived", "remove_movement_arrived_callback"),
            ("on_movement_recalled", "remove_movement_recalled_callback"),
            ("on_movement_removed", "remove_movement_removed_callback"),
        ],
    )
    def test_register_and_remove_wait_for_the_state_lock(self, state, register, remove):
        def callback(*args):
            pass

        done = threading.Event()

        def worker():
            getattr(state, register)(callback)
            getattr(state, remove)(callback)
            done.set()

        thread = threading.Thread(target=worker, daemon=True)
        state._lock.acquire()
        try:
            thread.start()
            assert not done.wait(0.2), f"{register}/{remove} mutated the listener list without the lock"
        finally:
            state._lock.release()
        assert done.wait(2.0)
        thread.join()


class TestArrivalCallbackPayload:
    """A bare MID is useless: the movement is gone from state by the time the
    callback runs, so consumers cannot recover what arrived."""

    def test_arrived_callback_can_receive_the_movement(self, state):
        state.update_from_packet("gam", gam_payload(600, oid=999))
        seen: list[tuple[int, Movement | None]] = []
        state.on_movement_arrived(lambda mid, mov: seen.append((mid, mov)))

        arrive(state, 600)

        assert wait_for(lambda: len(seen) == 1), "two-arg callback never received the movement"
        mid, mov = seen[0]
        assert mid == 600
        assert mov is not None, "movement popped before dispatch, callback got nothing"
        assert mov.movement_id == 600 and mov.is_attack
        assert mov.source_player_name == "Attacker"

    def test_removed_callback_can_receive_the_movement(self, state):
        state.update_from_packet("gam", gam_payload(601, oid=999))
        seen: list[tuple[int, Movement | None]] = []
        state.on_movement_removed(lambda mid, mov: seen.append((mid, mov)))

        state.update_from_packet("mrm", {"MID": 601})

        assert wait_for(lambda: len(seen) == 1)
        assert seen[0][0] == 601
        assert seen[0][1] is not None and seen[0][1].movement_id == 601

    def test_legacy_single_argument_callbacks_still_work(self, state):
        """Consumers register Callable[[int], None] today — that must keep working."""
        arrived: list[int] = []
        removed: list[int] = []
        state.on_movement_arrived(arrived.append)
        state.on_movement_removed(removed.append)

        state.update_from_packet("gam", gam_payload(602))
        state.update_from_packet("gam", gam_payload(603, extra={"TT": 1200}))
        arrive(state, 602)
        state.update_from_packet("mrm", {"MID": 603})

        assert wait_for(lambda: arrived == [602] and removed == [603])

    def test_bound_method_with_one_parameter_is_treated_as_legacy(self, state):
        class Consumer:
            def __init__(self):
                self.seen: list[int] = []

            def on_arrived(self, mid: int) -> None:
                self.seen.append(mid)

        consumer = Consumer()
        state.on_movement_arrived(consumer.on_arrived)
        state.update_from_packet("gam", gam_payload(604))
        arrive(state, 604)

        assert wait_for(lambda: consumer.seen == [604])

    def test_movement_is_still_removed_from_state(self, state):
        state.update_from_packet("gam", gam_payload(605))
        state.on_movement_arrived(lambda mid, mov: None)

        arrive(state, 605)

        assert state.get_movement_by_id(605) is None
        assert 605 not in state.movements

    def test_unknown_movement_removal_passes_none(self, state):
        seen: list[tuple[int, Movement | None]] = []
        state.on_movement_removed(lambda mid, mov: seen.append((mid, mov)))

        state.update_from_packet("mrm", {"MID": 606})

        assert wait_for(lambda: seen == [(606, None)])

    def test_callbacks_can_be_unregistered(self, state):
        arrived: list[int] = []

        def two_arg(mid, mov):
            arrived.append(mid)

        state.on_movement_arrived(arrived.append)
        state.on_movement_arrived(two_arg)
        state.remove_movement_arrived_callback(arrived.append)
        state.remove_movement_arrived_callback(two_arg)

        state.update_from_packet("gam", gam_payload(607))
        arrive(state, 607)
        time.sleep(0.15)
        assert arrived == []

        with pytest.raises(ValueError):
            state.remove_movement_arrived_callback(two_arg)
        with pytest.raises(ValueError):
            state.remove_movement_recalled_callback(two_arg)


class TestThreadSafety:
    def test_concurrent_updates_and_reads(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 1, "PN": "me"}})
        stop = threading.Event()
        errors = []

        def writer():
            i = 0
            while not stop.is_set():
                i += 1
                try:
                    state.update_from_packet("gam", gam_payload(1000 + (i % 50)))
                except Exception as e:  # pragma: no cover
                    errors.append(e)

        def reader():
            while not stop.is_set():
                try:
                    state.get_all_movements()
                    state.get_incoming_attacks()
                except Exception as e:  # pragma: no cover
                    errors.append(e)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        time.sleep(0.5)
        stop.set()
        for t in threads:
            t.join()
        assert errors == []


class TestMovementAreas:
    def test_kings_tower_target_name(self, state):
        state.update_from_packet("gam", gam_payload(950, extra={"TA": [23, 10, 20, 55, 7, 1, 30, "Tower"]}))
        mov = state.get_movement_by_id(950)
        assert mov is not None
        assert (mov.target_type, mov.target_area_id, mov.target_name) == (23, 55, "Tower")

    def test_camp_target_has_no_id_or_name(self, state):
        state.update_from_packet("gam", gam_payload(951, extra={"TA": [2, 510, 256, -1, 0, -1, 0]}))
        mov = state.get_movement_by_id(951)
        assert mov is not None
        assert (mov.target_x, mov.target_y, mov.target_area_id, mov.target_name) == (510, 256, -1, "")

    def test_area_row_is_typed(self, state):
        state.update_from_packet("gam", gam_payload(952, extra={"TA": [23, 10, 20, 55, 7, 1, 30, "Tower"]}))
        mov = state.get_movement_by_id(952)
        assert mov is not None and mov.target_area is not None
        assert (mov.target_area.area_type, mov.target_area.object_id, mov.target_area.owner_id) == (23, 55, 7)

    def test_unreadable_area_row_keeps_the_movement(self, state):
        state.update_from_packet("gam", gam_payload(953, extra={"TA": ["junk"], "SA": 0}))
        mov = state.get_movement_by_id(953)
        assert mov is not None
        assert (mov.target_area, mov.source_area, mov.target_x) == (None, None, -1)


class TestAllianceAttackAlerts:
    ME, ALLY, ENEMY, OUTSIDER, CLAN = 1, 2, 3, 4, 301

    def attack(
        self, state, mid: int, owner: int, target: int, owners: list[dict], movement_type: int = 0
    ) -> list[Movement]:
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        payload = gam_payload(mid, movement_type=movement_type, oid=owner, tid=target)
        payload["O"] = owners
        state.update_from_packet("gam", payload)
        time.sleep(0.15)
        return fired

    def test_attack_on_me_fires(self, state):
        login(state, self.ME, self.CLAN)
        assert len(self.attack(state, 1, self.ENEMY, self.ME, [])) == 1

    def test_attack_on_an_alliance_member_fires(self, state):
        login(state, self.ME, self.CLAN)
        owners = [{"OID": self.ALLY, "AID": self.CLAN, "N": "ally"}, {"OID": self.ENEMY, "AID": 99, "N": "enemy"}]
        fired = self.attack(state, 2, self.ENEMY, self.ALLY, owners)
        assert len(fired) == 1 and fired[0].target_alliance_id == self.CLAN

    def test_npc_attack_on_an_alliance_member_does_not_fire(self, state):
        # Client: showAsAllianceAttackWarning is false for NPC (dungeon) owners
        login(state, self.ME, self.CLAN)
        owners = [{"OID": self.ALLY, "AID": self.CLAN, "N": "ally"}]
        assert self.attack(state, 8, -202, self.ALLY, owners) == []

    @pytest.mark.parametrize("owner", [-801, -300, -432, -440, -334, -366, -1001, -9999])
    def test_attack_on_an_alliance_member_by_a_non_dungeon_npc_fires(self, state, owner):
        # Client: showAsAllianceAttackWarning (bundle lines 14420, 19456); an unknown NPC id gets a dummy owner
        login(state, self.ME, self.CLAN)
        owners = [{"OID": self.ALLY, "AID": self.CLAN, "N": "ally"}]
        assert len(self.attack(state, 11, owner, self.ALLY, owners)) == 1

    @pytest.mark.parametrize("owner", [-202, -214, -220, -230, -399, -410, -450, -460, -470, -500, -601, -705, -1000])
    def test_attack_on_an_alliance_member_by_a_dungeon_owner_does_not_fire(self, state, owner):
        login(state, self.ME, self.CLAN)
        owners = [{"OID": self.ALLY, "AID": self.CLAN, "N": "ally"}]
        assert self.attack(state, 12, owner, self.ALLY, owners) == []

    def test_alien_attack_on_an_alliance_member_fires(self, state):
        # Client: AlienAttackMovementVO.showAsAllianceAttackWarning is always true (bundle line 33091)
        login(state, self.ME, self.CLAN)
        owners = [{"OID": self.ALLY, "AID": self.CLAN, "N": "ally"}]
        fired = self.attack(state, 13, -1000, self.ALLY, owners, movement_type=MovementType.ALIEN_ATTACK)
        assert len(fired) == 1

    def test_alien_attack_on_the_daimyo_township_does_not_fire(self, state):
        # Client: AlienAttackMovementVO.isAttackingMovement counts only you (bundle line 33073)
        login(state, self.ME, self.CLAN)
        assert self.attack(state, 14, -1000, -815, [], movement_type=MovementType.ALIEN_ATTACK) == []
        assert len(self.attack(state, 15, -1000, self.ME, [], movement_type=MovementType.ALIEN_ATTACK)) == 1

    def test_an_owner_record_in_a_later_packet_fires_once(self, state):
        # checkAllAttackMovements counts warnings anew; getOwnerInfoVO keeps the owners seen
        login(state, self.ME, self.CLAN)
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        ally = {"OID": self.ALLY, "AID": self.CLAN, "N": "ally"}
        first = gam_payload(16, oid=self.ENEMY, tid=self.ALLY)
        first["O"] = [ally]
        state.update_from_packet("gam", first)
        time.sleep(0.1)
        assert fired == []

        later = gam_payload(16, oid=self.ENEMY, tid=self.ALLY)
        later["O"] = [{"OID": self.ENEMY, "AID": 0, "N": "enemy"}]
        state.update_from_packet("gam", later)
        state.update_from_packet("gam", later)
        time.sleep(0.15)

        assert [m.movement_id for m in fired] == [16]
        assert state.movements[16].target_owner is not None

    def test_a_movement_without_an_owner_id_is_no_npc_attack(self, state):
        # The client reads a missing OID as 0: no owner, so no alliance warning
        login(state, self.ME, self.CLAN)
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        payload = gam_payload(17, tid=self.ALLY)
        del payload["M"][0]["M"]["OID"]
        payload["O"] = [{"OID": self.ALLY, "AID": self.CLAN, "N": "ally"}]
        state.update_from_packet("gam", payload)
        time.sleep(0.15)

        assert fired == []

    def test_an_alien_attack_on_the_daimyo_township_is_not_incoming(self, state):
        login(state, self.ME, self.CLAN)
        state.update_from_packet("gam", gam_payload(18, movement_type=MovementType.ALIEN_ATTACK, oid=-1000, tid=-815))
        state.update_from_packet("gam", gam_payload(19, oid=-202, tid=-815))

        assert (state.movements[18].is_incoming, state.movements[19].is_incoming) == (False, True)

    def test_npc_attack_on_me_fires(self, state):
        login(state, self.ME, self.CLAN)
        assert len(self.attack(state, 9, -202, self.ME, [])) == 1

    def test_attack_on_an_ally_by_an_unknown_player_does_not_fire(self, state):
        login(state, self.ME, self.CLAN)
        owners = [{"OID": self.ALLY, "AID": self.CLAN, "N": "ally"}]
        assert self.attack(state, 10, self.ENEMY, self.ALLY, owners) == []

    def test_ally_attacking_an_outsider_does_not_fire(self, state):
        # Live: the server shares an alliance member's own attack on a player outside the alliance
        login(state, self.ME, self.CLAN)
        owners: list[dict] = [{"OID": self.OUTSIDER, "AID": -1, "N": "outsider"}, {"OID": self.ALLY, "AID": self.CLAN}]
        assert self.attack(state, 3, self.ALLY, self.OUTSIDER, owners) == []

    def test_attack_on_the_daimyo_township_fires(self, state):
        login(state, self.ME, self.CLAN)
        assert len(self.attack(state, 4, self.ENEMY, -815, [])) == 1
        assert [m.movement_id for m in state.get_incoming_attacks()] == [4]

    def test_no_alliance_means_only_attacks_on_me(self, state):
        login(state, self.ME)
        owners = [{"OID": self.ALLY, "AID": self.CLAN}]
        assert self.attack(state, 5, self.ENEMY, self.ALLY, owners) == []

    def test_no_local_player_means_no_alerts(self, state):
        assert self.attack(state, 6, self.ENEMY, self.ME, []) == []

    def test_owner_records_are_kept_across_updates(self, state):
        login(state, self.ME, self.CLAN)
        owners = [{"OID": self.ENEMY, "AID": 99, "AR": 8, "L": 70, "MP": 1267, "N": "enemy", "AN": "Foes"}]
        self.attack(state, 7, self.ENEMY, self.ME, owners)
        state.update_from_packet("abr", {"A": {"M": {"MID": 7, "T": 0, "TT": 600, "OID": self.ENEMY, "TID": self.ME}}})
        mov = state.get_movement_by_id(7)
        assert mov is not None and mov.owner is not None
        assert (mov.owner.level, mov.owner.alliance_rank, mov.owner.might) == (70, 8, 1267)
        assert (mov.owner_alliance_id, mov.source_player_name, mov.source_alliance_name) == (99, "enemy", "Foes")


# Live capture of a cra reply, names scrubbed
SENT_ATTACK: dict = {
    "AAM": {
        "M": {
            "MID": 93053681,
            "PT": 0,
            "TT": 128,
            "D": 0,
            "TID": -202,
            "T": 0,
            "HBW": -1,
            "KID": 0,
            "TA": [2, 510, 256, -1, 0, -1, 0],
            "SID": 1001,
            "OID": 1001,
            "SA": [1, 512, 256, 2001, 1001, 2, 2, 2, 1, 0, "Home", 0, 0, -1, -1, -1, 0, 0, [], 0],
        },
        "UM": {
            "PWD": 0,
            "TWD": 0,
            "L": {
                "ID": 0,
                "WID": 2,
                "VIS": 0,
                "N": "",
                "GID": -1,
                "W": 2,
                "D": 0,
                "SPR": 2,
                "EQ": [[6515210043, 6, 2, 10, 0, [[242, [25.0]]], 802, 22, 0, -1, -1, 1]],
                "AE": [[426, [10.0], "GE"]],
            },
        },
        "FA": {"L": [[656, 1], [640, 2]], "M": [], "R": [], "RW": []},
        "AST": [],
        "ATT": 0,
        "ASCT": 0,
        "FC": 0,
    },
    "O": [
        {
            "OID": 1001,
            "DUM": False,
            "N": "me",
            "L": 13,
            "LL": 0,
            "H": 0,
            "AVP": 1490,
            "MP": 4442,
            "R": 0,
            "AID": 301,
            "AR": 1,
            "AN": "Clan",
            "RPT": 0,
            "AP": [[0, 2001, 512, 256, 1], [0, 2002, 510, 257, 4]],
            "VP": [],
            "SA": 0,
            "VF": 0,
            "PF": 0,
            "RRD": 0,
        },
        {},
    ],
}


class TestSentMovements:
    ME = 1001
    MID = 93053681

    def test_attack_reply_is_stored_at_once(self, state):
        login(state, self.ME)
        state.update_from_packet("cra", SENT_ATTACK)
        [mov] = state.get_outgoing_movements()
        assert mov.movement_id == self.MID
        assert mov.units == {656: 1, 640: 2}
        assert (mov.target_x, mov.target_y, mov.target_id) == (510, 256, -202)
        assert mov.source_name == "Home"
        assert mov.commander is not None
        [item] = mov.commander.equipment
        assert (item.equipment_id, item.slot, item.unique_id, item.equipment_type) == (6515210043, 6, 802, 1)
        assert [(e.effect_id, e.values, e.source) for e in mov.commander.area_effects] == [(426, [10.0], "GE")]
        assert (mov.source_player_name, mov.source_alliance_name) == ("me", "Clan")
        assert mov.estimated_arrival == pytest.approx(time.time() + 128, abs=2)

    def test_later_gam_updates_the_same_movement(self, state):
        login(state, self.ME)
        state.update_from_packet("cra", SENT_ATTACK)
        created = state.movements[self.MID].created_at
        wrapper = {**SENT_ATTACK["AAM"], "M": {**SENT_ATTACK["AAM"]["M"], "PT": 10}}
        state.update_from_packet("gam", {"M": [wrapper], "O": []})
        [mov] = state.get_outgoing_movements()
        assert (mov.progress_time, mov.created_at, mov.source_player_name) == (10, created, "me")

    def test_the_commander_resolves_like_its_gli_entry(self, state):
        # LordFactory.createLord builds both; LordVO.getUniqueBoni reads both
        entry = {**SENT_ATTACK["AAM"]["UM"]["L"], "E": [[110, [40.0], "AB"]]}
        attack = {"AAM": {**SENT_ATTACK["AAM"], "UM": {"PWD": 0, "TWD": 0, "L": entry}}, "O": SENT_ATTACK["O"]}
        login(state, self.ME)
        state.update_from_packet("cra", attack)
        [mov] = state.get_outgoing_movements()
        game_data = GameData.parse("test", {})
        assert mov.commander == Commander.model_validate(entry)
        bonuses = commander_bonuses(game_data, mov.commander)
        assert [bonus.effect_id for bonus in bonuses] == [242, 110, 426]
        assert bonuses == commander_bonuses(game_data, Commander.model_validate(entry))

    def test_a_movement_without_a_commander_has_none(self, state):
        login(state, self.ME)
        state.update_from_packet("gam", gam_payload(5, oid=self.ME))
        assert state.movements[5].commander is None

    def test_own_attack_does_not_alert(self, state):
        login(state, self.ME)
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        state.update_from_packet("cra", SENT_ATTACK)
        time.sleep(0.1)
        assert fired == []

    @pytest.mark.parametrize("cmd", ["cds", "csm", "cat", "crm", "css", "tde", "cdd", "cpm"])
    def test_replies_under_a_are_stored(self, state, cmd):
        login(state, self.ME)
        state.update_from_packet(cmd, {"A": {"M": {"MID": 5, "T": 3, "TT": 60, "OID": self.ME}}, "O": []})
        assert [m.movement_id for m in state.get_outgoing_movements()] == [5]

    @pytest.mark.parametrize("cmd", ["cam", "abgcam"])
    def test_other_attack_replies_are_stored(self, state, cmd):
        login(state, self.ME)
        state.update_from_packet(cmd, SENT_ATTACK)
        assert [m.movement_id for m in state.get_outgoing_movements()] == [self.MID]

    def test_treasure_hunt_reply_is_stored(self, state):
        login(state, self.ME)
        state.update_from_packet("thm", {"TM": {"M": {"MID": 6, "T": 0, "TT": 60, "OID": self.ME}}})
        assert [m.movement_id for m in state.get_outgoing_movements()] == [6]

    def test_daimyo_taunt_payload_is_the_wrapper(self, state):
        login(state, self.ME)
        state.update_from_packet("ldt", {"M": {"MID": 7, "T": 0, "TT": 60, "OID": self.ME}})
        assert [m.movement_id for m in state.get_outgoing_movements()] == [7]

    def test_reply_coins_and_rubies_are_applied(self, state):
        login(state, self.ME)
        state.update_from_packet("cra", {**SENT_ATTACK, "gcu": {"C1": 1200, "C2": 30}})
        assert state.local_player is not None
        assert (state.local_player.coins, state.local_player.rubies) == (1200, 30)
        assert state.get_last_packet_time("gcu") is not None

    def test_reply_without_gcu_keeps_coins_and_rubies(self, state):
        login(state, self.ME)
        state.update_from_packet("gbd", {"gcu": {"C1": 500, "C2": 7}})
        state.update_from_packet("cra", SENT_ATTACK)
        assert state.local_player is not None
        assert (state.local_player.coins, state.local_player.rubies) == (500, 7)

    def test_error_reply_stores_nothing(self, state):
        login(state, self.ME)
        state.update_from_packet("cra", {"TS": 10, "AS": 3})
        state.update_from_packet("csm", {})
        assert state.movements == {}

    def test_unreadable_block_keeps_the_movement(self, state):
        login(state, self.ME)
        state.update_from_packet("cra", {**SENT_ATTACK, "AAM": {**SENT_ATTACK["AAM"], "UM": "junk"}})
        assert [m.movement_id for m in state.get_outgoing_movements()] == [self.MID]


class TestCallbackOrdering:
    """Callbacks run one at a time, in the order their packets were applied."""

    def test_an_attack_and_its_removal_arrive_in_order_and_never_at_once(self, state):
        login(state)
        gate = threading.Event()
        events: list[str] = []
        running: list[int] = []
        overlapped: list[bool] = []

        def track(name: str, block: bool):
            def callback(*_args):
                running.append(1)
                overlapped.append(len(running) > 1)
                if block:
                    assert gate.wait(timeout=5)
                events.append(name)
                running.pop()

            return callback

        state.on_incoming_attack(track("incoming", block=True))
        state.on_movement_removed(track("removed", block=False))

        state.update_from_packet("gam", gam_payload(100))
        state.update_from_packet("mrm", {"MID": 100})
        # The removal is queued behind the blocked attack callback, not run beside it.
        assert wait_for(lambda: running == [1])
        assert events == []
        gate.set()

        assert wait_for(lambda: events == ["incoming", "removed"])
        assert overlapped == [False, False]

    def test_two_attacks_fire_on_one_thread(self, state):
        login(state)
        threads: list[str] = []
        state.on_incoming_attack(lambda _mov: threads.append(threading.current_thread().name))

        state.update_from_packet("gam", gam_payload(100))
        state.update_from_packet("gam", gam_payload(101))

        assert wait_for(lambda: len(threads) == 2)
        assert len(set(threads)) == 1
        assert threads[0] != threading.current_thread().name


class TestCallbackQueueDepth:
    def test_depth_counts_queued_callbacks_and_warns_past_the_limit_without_dropping(self, state, monkeypatch, caplog):
        import empire_core.state.base as base_module

        monkeypatch.setattr(base_module, "CALLBACK_QUEUE_WARN_DEPTH", 3)
        gate = threading.Event()
        removed: list[int] = []

        def slow(mid):
            gate.wait(5)
            removed.append(mid)

        state.on_movement_removed(slow)
        assert state.callback_queue_depth == 0
        with caplog.at_level(logging.WARNING, logger="empire_core.state.base"):
            for mid in range(700, 706):
                state.update_from_packet("mrm", {"MID": mid})
        assert state.callback_queue_depth == 6
        warnings = [r for r in caplog.records if "callbacks are waiting" in r.getMessage()]
        assert len(warnings) == 1, "warning not raised once past the limit"
        gate.set()
        assert wait_for(lambda: removed == list(range(700, 706)))
        assert wait_for(lambda: state.callback_queue_depth == 0)
