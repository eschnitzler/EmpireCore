"""Tests for GameState movement lifecycle and callbacks."""

import threading
import time
from collections.abc import Generator

import pytest

from empire_core.state.manager import GameState
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
