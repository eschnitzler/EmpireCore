"""GameState movement tracking: types, direction, arrival, pushes and callbacks."""

import logging
import threading
import time
from unittest.mock import patch

import pytest

from empire_core.client.client import EmpireClient
from empire_core.state.manager import GameState
from empire_core.state.world_models import Movement
from tests.state_helpers import arrive, gam_payload, login, push_payload, wait_for


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
        mov = Movement(T=t)
        assert mov.is_attack and not mov.is_support and not mov.is_siege

    @pytest.mark.parametrize("t", [1, 26, 32])
    def test_support_types(self, t):
        mov = Movement(T=t)
        assert mov.is_support and not mov.is_attack

    @pytest.mark.parametrize("t", [5, 15])
    def test_siege_types(self, t):
        assert Movement(T=t).is_siege

    def test_single_value_types(self):
        assert Movement(T=2).is_travel
        assert Movement(T=3).is_spy
        assert Movement(T=4).is_transport
        assert not Movement(T=2).is_transport

    @pytest.mark.parametrize("t", [2, 3, 4, 6, 14])
    def test_non_combat_types_are_not_attacks(self, t):
        assert not Movement(T=t).is_attack

    def test_names_follow_the_client(self):
        assert Movement(T=1).movement_type_name == "DEFENCE"
        assert Movement(T=11).movement_type_name == "NPC_ATTACK"
        assert Movement(T=99).movement_type_name == "UNKNOWN_99"

    def test_direction_flag_marks_returns_for_any_type(self):
        assert Movement(T=11, D=0).is_returning is False
        assert Movement(T=4, D=1).is_returning


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
        state.movements[207].last_updated = time.time() - 601
        # A packet state has no handler for still drives arrivals
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
        state.movements[203].last_updated = time.time() - 10_000

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
        state.movements[222].last_updated = time.time() - 3600
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
        mov = Movement(MID=1, T=0, PT=0, TT=100, D=0)
        mov.last_updated = time.time() - 30
        # 100s total, packet 30s ago => ~70s remaining
        assert 65 <= mov.time_remaining <= 71
        assert not mov.has_arrived()

    def test_has_arrived_after_eta_passes(self):
        mov = Movement(MID=2, T=0, PT=90, TT=100, D=0)
        mov.last_updated = time.time() - 60  # 10s remained, 60s ago
        assert mov.time_remaining == 0
        assert mov.has_arrived()

    def test_resources_total_includes_special(self):
        from empire_core.state.world_models import MovementResources

        res = MovementResources(MEAD=5, A=2, C=1, O=4)
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
            UM={"PWD": 0, "TWD": 30, "AAT": 1, "AAC": 3, "AAN": 3, "AAL": 1, "L": {"EQ": [1], "AE": [2]}},
        )
        assert (mov.attack_type, mov.is_shadow, mov.force_cancelable) == (0, True, True)
        assert (mov.support_tool_ids, mov.auto_skip_cooldown_type) == ([651, 652], 2)
        assert (mov.advisor_type, mov.advisor_movement_count, mov.advisor_movement_number) == (1, 3, 3)
        assert mov.advisor_is_last
        assert (mov.commander_equipment, mov.commander_effects) == ([1], [2])
        assert mov.battle_time == pytest.approx(mov.estimated_arrival + 30)

    def test_one_unreadable_block_does_not_drop_the_attack(self, state):
        login(state)
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        mov = self.stored(state, AST="junk", GA={"M": [[1, 2]]})
        assert mov.units == {1: 2} and mov.support_tool_ids == []
        assert wait_for(lambda: len(fired) == 1)


class TestStaleMovementPruning:
    """Arrival packets get missed (socket errors, disconnect windows), so every
    mutation and query path must prune — not just the gam handler."""

    @staticmethod
    def _make_stale(state: GameState, mid: int) -> None:
        # Arrival was due long ago
        state.movements[mid].last_updated = time.time() - 10_000

    def test_pruned_on_pushed_mov_packet(self, state):
        state.update_from_packet("abr", push_payload(300, tt=1))
        self._make_stale(state, 300)

        state.update_from_packet("abr", push_payload(301))
        assert 300 not in state.movements
        assert 301 in state.movements

    def test_pruned_on_query_without_any_gam(self, state):
        # A consumer driven purely by push callbacks never calls gam
        state.update_from_packet("gbd", {"gpi": {"PID": 1, "PN": "me"}})
        state.update_from_packet("abr", push_payload(302, tt=1))
        self._make_stale(state, 302)

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
        self._make_stale(state, 304)

        # The server pushes a fresh update for the same movement (it was
        # overdue, not gone). Pruning must not drop it just before the update
        # is stored, or the consumer gets a duplicate attack alert.
        state.update_from_packet("abr", push_payload(304, tt=900))

        time.sleep(0.15)
        assert len(fired) == 1, "stale-then-refreshed movement re-alerted as new"
        assert 304 in state.movements

    def test_arrival_is_not_delayed(self, state):
        # There is no arrival packet to wait for: once travel time is up the
        # movement has arrived.
        state.update_from_packet("abr", push_payload(303, tt=1))
        state.movements[303].last_updated = time.time() - 10

        assert state.get_movement_by_id(303) is None
        assert state.get_all_movements() == []


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
        state.update_from_packet("gam", gam_payload(603))
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

    def test_client_movement_helpers_are_lock_protected(self, state):
        """The client facade must read movements through GameState's locked accessors."""
        client = EmpireClient.__new__(EmpireClient)  # the helpers only touch self.state
        client.state = state
        state.update_from_packet("gbd", {"gpi": {"PID": 1, "PN": "me"}})
        stop = threading.Event()
        errors = []

        def writer():
            i = 0
            while not stop.is_set():
                i += 1
                # Ever-increasing MIDs: each update inserts a new key, so the dict
                # genuinely changes size while readers iterate it.
                try:
                    state.update_from_packet("gam", gam_payload(1000 + i))
                except Exception as e:  # pragma: no cover
                    errors.append(e)

        def reader():
            while not stop.is_set():
                try:
                    client.get_incoming_attacks()
                    client.get_incoming_movements()
                    client.get_outgoing_movements()
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
        state.update_from_packet("gam", gam_payload(951, extra={"TA": [2, 630, 243, -1, 0, -1, 0]}))
        mov = state.get_movement_by_id(951)
        assert mov is not None
        assert (mov.target_x, mov.target_y, mov.target_area_id, mov.target_name) == (630, 243, -1, "")


class TestAllianceAttackAlerts:
    ME, ALLY, ENEMY, OUTSIDER, CLAN = 1, 2, 3, 4, 190426

    def attack(self, state, mid: int, owner: int, target: int, owners: list[dict]) -> list[Movement]:
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        payload = gam_payload(mid, oid=owner, tid=target)
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

    def test_ally_attacking_an_outsider_does_not_fire(self, state):
        # Live: the server shares an alliance member's own attack on a player outside the alliance
        login(state, self.ME, self.CLAN)
        owners: list[dict] = [{"OID": self.OUTSIDER, "AID": -1, "N": "outsider"}, {"OID": self.ALLY, "AID": self.CLAN}]
        assert self.attack(state, 3, self.ALLY, self.OUTSIDER, owners) == []

    def test_attack_on_the_daimyo_township_fires(self, state):
        login(state, self.ME, self.CLAN)
        assert len(self.attack(state, 4, self.ENEMY, -815, [])) == 1

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
