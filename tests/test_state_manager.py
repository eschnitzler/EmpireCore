"""Tests for GameState movement lifecycle and callbacks."""

import logging
import threading
import time
from collections.abc import Generator
from unittest.mock import patch

import pytest

from empire_core.client.client import EmpireClient
from empire_core.state.manager import GameState
from empire_core.state.models import Castle, Player
from empire_core.state.world_models import Movement


def gam_payload(mid: int, movement_type: int = 1, oid: int = 999, tid: int = 1, extra: dict | None = None) -> dict:
    m_data = {
        "MID": mid,
        "T": movement_type,  # 1 = ATTACK
        "PT": 0,
        "TT": 600,
        "D": 0,
        "OID": oid,
        "TID": tid,
        "KID": 0,
        "SID": -1,
    }
    if extra:
        m_data.update(extra)
    return {
        "M": [{"M": m_data}],
        "O": [{"OID": oid, "N": "Attacker", "AN": "EvilAlliance"}],
    }


def mov_payload(mid: int, movement_type: int = 1, oid: int = 999, tt: int = 600, direction: int = 0) -> dict:
    """A pushed single-movement packet (no owner info, no gam refresh)."""
    return {"M": {"MID": mid, "T": movement_type, "PT": 0, "TT": tt, "D": direction, "OID": oid, "TID": 1}}


def gcl_payload(castles: list[tuple[int, str]], owner_id: int = 7, kingdom: int = 0) -> dict:
    """Build a gcl castle section listing `castles` as owned by `owner_id`."""
    return {
        "C": [
            {
                "KID": kingdom,
                "AI": [{"AI": [0, 10, 20, area_id, owner_id, 0, 0, 0, 0, 0, name]} for area_id, name in castles],
            }
        ]
    }


def wait_for(predicate, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def state() -> Generator[GameState, None, None]:
    gs = GameState()
    yield gs
    gs.shutdown()


class TestAttackCallbacks:
    def test_new_attack_fires_callback_once(self, state):
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
        state.update_from_packet("gam", gam_payload(102, movement_type=2))  # 2 = TRANSPORT
        time.sleep(0.2)
        assert fired == []

    def test_callbacks_survive_multiple_dispatch_cycles(self, state):
        # Executor is created lazily and must keep working after shutdown+reuse
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        state.update_from_packet("gam", gam_payload(103))
        assert wait_for(lambda: len(fired) == 1)

        state.shutdown()

        # New packets after a shutdown (e.g. after reconnect) recreate the pool
        state.update_from_packet("gam", gam_payload(104))
        assert wait_for(lambda: len(fired) == 2)


class TestMovementLifecycle:
    def test_update_preserves_created_at_and_names(self, state):
        state.update_from_packet("gam", gam_payload(200))
        first = state.get_movement_by_id(200)
        assert first is not None
        created = first.created_at
        assert first.source_player_name == "Attacker"

        time.sleep(0.02)
        # Update without owner info (mov push)
        state.update_from_packet("mov", {"M": {"MID": 200, "T": 1, "PT": 60, "TT": 600, "D": 0, "OID": 999}})
        updated = state.get_movement_by_id(200)
        assert updated is not None
        assert updated.created_at == created
        assert updated.source_player_name == "Attacker"

    def test_arrival_removes_movement(self, state):
        arrived: list[int] = []
        state.on_movement_arrived(arrived.append)
        state.update_from_packet("gam", gam_payload(201))
        assert state.get_movement_by_id(201) is not None

        state.update_from_packet("atv", {"MID": 201})
        assert state.get_movement_by_id(201) is None
        assert wait_for(lambda: arrived == [201])

    def test_recall_removes_movement(self, state):
        recalled: list[int] = []
        state.on_movement_recalled(recalled.append)
        state.update_from_packet("gam", gam_payload(202))
        state.update_from_packet("mrm", {"MID": 202})
        assert state.get_movement_by_id(202) is None
        assert wait_for(lambda: recalled == [202])

    def test_stale_movements_pruned(self, state):
        state.update_from_packet("gam", gam_payload(203, extra={"TT": 1, "PT": 1}))
        mov = state.get_movement_by_id(203)
        assert mov is not None
        # Simulate the arrival packet having been missed long ago
        mov.last_updated = time.time() - 10_000

        # The next gam triggers pruning
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


class TestMovementTime:
    def test_time_remaining_advances_with_wall_clock(self):
        mov = Movement(MID=1, T=1, PT=0, TT=100, D=0)
        mov.last_updated = time.time() - 30
        # 100s total, packet 30s ago => ~70s remaining
        assert 65 <= mov.time_remaining <= 71
        assert not mov.has_arrived()

    def test_has_arrived_after_eta_passes(self):
        mov = Movement(MID=2, T=1, PT=90, TT=100, D=0)
        mov.last_updated = time.time() - 60  # 10s remained, 60s ago
        assert mov.time_remaining == 0
        assert mov.has_arrived()

    def test_resources_total_includes_special(self):
        from empire_core.state.world_models import MovementResources

        res = MovementResources(MEAD=5)
        assert res.total == 5
        assert not res.is_empty


class TestPlayerParsing:
    def test_relogin_merges_player_data(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7, "PN": "old_name", "LVL": 10}})
        player = state.local_player
        assert player is not None and player.PN == "old_name"

        state.update_from_packet("gbd", {"gpi": {"PID": 7, "PN": "new_name", "LVL": 11}})
        # Identity preserved, data refreshed
        assert state.local_player is player
        assert player.PN == "new_name"
        assert player.LVL == 11

    def test_malformed_inventory_entry_skipped(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7, "PN": "x"}})
        state.update_from_packet("sce", [["GOOD", 5], ["BAD", "not-a-number"], ["ALSO_GOOD", 7]])
        inv = state.local_player.inventory
        assert inv["GOOD"] == 5
        assert inv["ALSO_GOOD"] == 7
        assert "BAD" not in inv


class TestCastleUpdatesAreAtomic:
    """get_castles() hands out live Castle objects, so dcl must swap, not mutate."""

    def test_dcl_swaps_unit_dict_instead_of_clearing_in_place(self, state):
        state.castles[42] = Castle(OID=42, units={7: 100})
        reader_view = state.get_castles()[0].units

        state.update_from_packet("dcl", {"C": [{"AI": [{"AID": 42, "AC": [[8, 5]]}]}]})

        assert reader_view == {7: 100}, "receive thread mutated a dict a reader already holds"
        assert state.get_castles()[0].units == {8: 5}

    def test_dcl_replaces_resources_instead_of_writing_field_by_field(self, state):
        state.castles[42] = Castle(OID=42)
        res_before = state.get_castles()[0].resources

        state.update_from_packet("dcl", {"C": [{"AI": [{"AID": 42, "W": 10, "S": 20, "F": 30}]}]})

        assert (res_before.wood, res_before.stone, res_before.food) == (0, 0, 0), "torn read possible"
        now = state.get_castles()[0].resources
        assert (now.wood, now.stone, now.food) == (10, 20, 30)


class TestStaleMovementPruning:
    """Arrival packets get missed (socket errors, disconnect windows), so every
    mutation and query path must prune — not just the gam handler."""

    @staticmethod
    def _make_stale(state: GameState, mid: int) -> None:
        # Arrival was due long before the STALE_MOVEMENT_GRACE window
        state.movements[mid].last_updated = time.time() - 10_000

    def test_pruned_on_pushed_mov_packet(self, state):
        state.update_from_packet("mov", mov_payload(300, tt=1))
        self._make_stale(state, 300)

        state.update_from_packet("mov", mov_payload(301))
        assert 300 not in state.movements
        assert 301 in state.movements

    def test_pruned_on_query_without_any_gam(self, state):
        # A consumer driven purely by push callbacks never calls gam
        state.update_from_packet("mov", mov_payload(302, tt=1))
        self._make_stale(state, 302)

        assert state.get_incoming_attacks() == []
        assert state.get_all_movements() == []
        assert state.get_incoming_movements() == []
        assert state.get_outgoing_movements() == []
        assert state.get_movement_by_id(302) is None
        assert state.movements == {}, "movements dict grows without bound"

    def test_refreshed_movement_is_not_resurrected_as_new(self, state):
        fired: list[Movement] = []
        state.on_incoming_attack(fired.append)
        state.update_from_packet("mov", mov_payload(304, tt=1))
        assert wait_for(lambda: len(fired) == 1)
        self._make_stale(state, 304)

        # The server pushes a fresh update for the same movement (it was
        # overdue, not gone). Pruning must not drop it just before the update
        # is stored, or the consumer gets a duplicate attack alert.
        state.update_from_packet("mov", mov_payload(304, tt=900))

        time.sleep(0.15)
        assert len(fired) == 1, "stale-then-refreshed movement re-alerted as new"
        assert 304 in state.movements

    def test_grace_period_still_honoured(self, state):
        # Just arrived: inside the 300s grace window, must be kept so the
        # atv/ata handler can still fire arrival callbacks.
        state.update_from_packet("mov", mov_payload(303, tt=1))
        state.movements[303].last_updated = time.time() - 10

        assert state.get_movement_by_id(303) is not None
        assert len(state.get_all_movements()) == 1


class TestMovementParseFailures:
    """Schema drift must not silently swallow every incoming attack."""

    BAD = {"M": {"MID": "not-an-int", "T": 1}}

    def test_parse_failure_is_visible_at_default_level(self, state, caplog):
        with caplog.at_level(logging.DEBUG, logger="empire_core.state.manager"):
            state.update_from_packet("mov", self.BAD)

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1, "movement parse failure invisible at INFO"
        assert warnings[0].exc_info is not None, "no traceback: schema drift undiagnosable"
        assert state.movements == {}

    def test_repeated_failures_do_not_flood(self, state, caplog):
        with caplog.at_level(logging.DEBUG, logger="empire_core.state.manager"):
            for _ in range(25):
                state.update_from_packet("mov", self.BAD)

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1, f"log flooded with {len(warnings)} warnings"


class TestLocalPlayerSnapshots:
    """local_player/inventory are read by user threads while the receive
    thread updates them, so there must be a locked snapshot path."""

    def test_get_local_player_returns_detached_copy(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7, "PN": "me"}})
        snapshot = state.get_local_player()

        assert snapshot is not None and snapshot.PN == "me"
        assert snapshot is not state.local_player
        snapshot.PN = "tampered"
        assert state.local_player.PN == "me"

    def test_get_local_player_is_none_before_login(self, state):
        assert state.get_local_player() is None

    def test_snapshot_containers_are_detached(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "sce": [["A", 1]], "gcl": gcl_payload([(1, "Main")])})
        snapshot = state.get_local_player()

        state.update_from_packet("sce", [["B", 2]])
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(2, "Second")])})

        assert snapshot.inventory == {"A": 1}, "snapshot inventory mutated by receive thread"
        assert list(snapshot.castles) == [1], "snapshot castles mutated by receive thread"

    def test_get_inventory_returns_copy(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "sce": [["A", 1]]})
        inventory = state.get_inventory()

        assert inventory == {"A": 1}
        inventory["A"] = 999
        assert state.get_inventory() == {"A": 1}

    def test_get_inventory_is_empty_before_login(self, state):
        assert state.get_inventory() == {}

    def test_sce_swaps_inventory_instead_of_mutating_in_place(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "sce": [["A", 1]]})
        reader_view = state.local_player.inventory  # what an unlocked reader holds

        state.update_from_packet("sce", [["B", 2]])

        assert reader_view == {"A": 1}, "receive thread mutated a dict a reader already holds"
        assert state.get_inventory() == {"A": 1, "B": 2}

    def test_gcl_swaps_player_castles_instead_of_mutating_in_place(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        reader_view = state.local_player.castles

        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main"), (2, "Outpost")])})

        assert list(reader_view) == [1], "receive thread mutated a dict a reader already holds"
        assert sorted(state.local_player.castles) == [1, 2]

    def test_relogin_merge_has_no_observable_intermediate_state(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7, "PN": "old", "LVL": 10, "XP": 100}})
        player = state.local_player
        watched = ("PN", "LVL", "XP")
        before = {"PN": "old", "LVL": 10, "XP": 100}
        after = {"PN": "new", "LVL": 11, "XP": 200}

        observed: list[dict] = []
        real_setattr = Player.__setattr__

        def spy(self, name, value):
            real_setattr(self, name, value)
            if self is player:
                observed.append({field: getattr(self, field) for field in watched})

        with patch.object(Player, "__setattr__", spy):
            state.update_from_packet("gbd", {"gpi": {"PID": 7, "PN": "new", "LVL": 11, "XP": 200}})

        assert {field: getattr(player, field) for field in watched} == after
        assert all(seen in (before, after) for seen in observed), f"half-merged player observable: {observed}"

    def test_players_dict_holds_only_the_local_player(self, state):
        # Documented contract: `players` is not a map of every player seen
        state.update_from_packet("gbd", {"gpi": {"PID": 7}})
        state.update_from_packet("gam", gam_payload(500, oid=999))
        assert list(state.players) == [7]


class TestPartialSubPacketsPreserveState:
    """A sub-packet that omits a key must not reset that value to 0."""

    def test_partial_gcu_preserves_other_currency(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcu": {"C1": 100, "C2": 5}})
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcu": {"C1": 200}})

        player = state.get_local_player()
        assert (player.gold, player.rubies) == (200, 5)

    def test_partial_vip_preserves_other_fields(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "vip": {"VP": 10, "VRL": 2, "VRS": 3600}})
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "vip": {"VRS": 1800}})

        player = state.get_local_player()
        assert (player.vip_points, player.vip_level, player.vip_time_left) == (10, 2, 1800)


class TestAllianceMembership:
    def test_alliance_parsed(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gal": {"AID": 5, "N": "Clan"}})
        player = state.get_local_player()
        assert player.alliance is not None and player.alliance.name == "Clan"
        assert player.AID == 5

    @pytest.mark.parametrize("gal", [{}, None, {"AID": 0}, {"N": "", "SA": 0}])
    def test_leaving_alliance_clears_it(self, state, gal):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gal": {"AID": 5, "N": "Clan"}})
        # Fresh login after leaving/being kicked: the gal section says "none"
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gal": gal})

        player = state.get_local_player()
        assert player.alliance is None, "stale alliance kept forever after leaving"
        assert player.AID is None

    def test_packet_without_alliance_section_keeps_alliance(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gal": {"AID": 5, "N": "Clan"}})
        # No gal key at all: this packet carries no alliance information
        state.update_from_packet("gbd", {"gpi": {"PID": 7}})

        assert state.get_local_player().alliance is not None


class TestCastleStaleDrop:
    def test_lost_castle_is_dropped(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main"), (2, "Outpost")])})
        assert sorted(c.id for c in state.get_castles()) == [1, 2]

        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        assert [c.id for c in state.get_castles()] == [1]

    def test_castle_section_listing_zero_owned_castles_drops_all(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})

        # Castle section present, but nothing owned any more (lost last castle)
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": {"C": []}})

        assert state.get_castles() == [], "stale castles never removed"
        assert state.get_local_player().castles == {}

    def test_castle_section_listing_only_foreign_castles_drops_all(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(9, "Enemy")], owner_id=1234)})
        assert state.get_castles() == []

    @pytest.mark.parametrize("gcl", [{}, None, {"X": 1}])
    def test_packet_without_castle_section_keeps_castles(self, state, gcl):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl})

        assert [c.id for c in state.get_castles()] == [1]


class TestThreadSafety:
    def test_concurrent_updates_and_reads(self, state):
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
