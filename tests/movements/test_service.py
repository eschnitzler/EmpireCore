"""Tests for the movements service."""

from __future__ import annotations

import threading
import time

import pytest

from empire_core.client.client import EmpireClient
from empire_core.exceptions import CommandError
from empire_core.movements.service import MovementsService
from tests.service_helpers import StubState, conn, make_client, xt_packet
from tests.state.state_helpers import gam_payload, push_payload


class TestGetMovements:
    def test_server_error_raises_command_error(self):
        state = StubState(movements=["stale"])
        client = make_client({"gam": xt_packet("gam", error_code=21)}, state)

        with pytest.raises(CommandError) as exc_info:
            client.movements.get_movements()

        assert exc_info.value.command == "gam"
        assert exc_info.value.code == 21
        assert "get_all_movements" not in state.events

    def test_successful_response_returns_state_movements(self):
        state = StubState(movements=["m1", "m2"])
        client = make_client({"gam": xt_packet("gam", {"M": []})}, state)

        assert client.movements.get_movements() == ["m1", "m2"]

    def test_fire_and_forget_returns_state_movements(self):
        state = StubState(movements=["m1"])
        client = make_client(state=state)

        assert client.movements.get_movements(wait=False) == ["m1"]
        assert conn(client).requested == []
        assert len(conn(client).sent) == 1


class TestMovementReads:
    def test_the_reads_are_lock_protected(self, state):
        client = EmpireClient.__new__(EmpireClient)  # the reads only touch client.state
        client.state = state
        movements = MovementsService(client)
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
                    _ = (movements.incoming_attacks, movements.incoming_movements, movements.outgoing_movements)
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


class TestRecall:
    def test_sends_mcm_and_returns_the_movement_heading_home(self):
        reply = {"A": push_payload(208, direction=1)["A"]}
        client = make_client({"mcm": xt_packet("mcm", reply)})

        movement = client.movements.recall(208)

        assert conn(client).request_payloads == [("mcm", {"MID": 208})]
        assert movement.movement.movement_id == 208
        assert movement.movement.is_returning

    def test_refusal_raises_command_error(self):
        client = make_client({"mcm": xt_packet("mcm", error_code=189)})

        with pytest.raises(CommandError) as exc_info:
            client.movements.recall(208)

        assert (exc_info.value.command, exc_info.value.code) == ("mcm", 189)


class TestCommanderConfirmation:
    def test_background_confirmation_retries_error_then_server_presence(self, state):
        from empire_core.exceptions import EmpireTimeoutError
        from tests.state.state_helpers import later, login, wait_for

        login(state, 1001)
        payload = gam_payload(1, oid=1001, extra={"D": 1, "TT": 1})
        payload["M"][0]["UM"] = {"L": {"ID": 4}}
        state.update_from_packet("gam", payload)
        end = state.movements[1].estimated_end
        client = make_client(
            {
                "gam": [
                    EmpireTimeoutError("test timeout"),
                    xt_packet("gam", error_code=21),
                    xt_packet("gam", payload),
                    xt_packet("gam", {"M": []}),
                ]
            },
            state,
        )
        state.on_commander_confirmation_due(client.movements._confirm_expired_commanders)
        # Each clock wake queues one request; failures and a present MID retain the reservation.
        for attempt in range(4):
            with later(end - time.time() + 2 + attempt * 2):
                state.get_all_movements()
                assert wait_for(lambda attempt=attempt: len(conn(client).requested) == attempt + 1)
                assert wait_for(lambda: not state._commander_confirmation_running)
                assert bool(state.get_away_commanders()) == (attempt < 3)

    def test_failed_explicit_query_does_not_release(self, state):
        from tests.state.state_helpers import later, login

        login(state, 1001)
        payload = gam_payload(1, oid=1001, extra={"D": 1})
        payload["M"][0]["UM"] = {"L": {"ID": 4}}
        state.update_from_packet("gam", payload)
        end = state.movements[1].estimated_end
        client = make_client({"gam": xt_packet("gam", {"M": []}, error_code=21)}, state)
        with later(end - time.time() + 1):
            with pytest.raises(CommandError):
                client.movements.get_movements()
            assert [c.commander_id for c in state.get_away_commanders()] == [4]

    def test_confirmation_due_during_login_is_retried(self, state):
        from tests.state.state_helpers import later, login

        login(state, 1001)
        payload = gam_payload(1, oid=1001, extra={"D": 1})
        payload["M"][0]["UM"] = {"L": {"ID": 4}}
        state.update_from_packet("gam", payload)
        end = state.movements[1].estimated_end
        client = make_client({"gam": xt_packet("gam", {"M": []})}, state)
        client.is_logged_in = False
        with later(end - time.time() + 1):
            client.movements._confirm_expired_commanders()
            assert conn(client).requested == []
            assert state._commander_confirmation_at > time.time()
            client.is_logged_in = True
            client.movements._confirm_expired_commanders()
            assert state.get_away_commanders() == []
