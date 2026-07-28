"""Tests for Connection waiter routing (no real socket needed)."""

import threading

import pytest

from empire_core.exceptions import ConnectionClosedError, EmpireTimeoutError
from empire_core.network.connection import Connection
from empire_core.protocol.packet import Packet


def make_packet(command: str, payload: str = "{}") -> Packet:
    return Packet.from_bytes(f"%xt%{command}%1%0%{payload}%".encode())


@pytest.fixture
def conn() -> Connection:
    return Connection("wss://example.invalid/")


class TestWaiters:
    def test_waiter_receives_routed_packet(self, conn):
        waiter = conn.create_waiter("gam")
        packet = make_packet("gam")
        conn._route_packet(packet)
        result = conn.wait_for_result("gam", waiter, timeout=0.1)
        assert result is packet

    def test_waiter_registered_before_response_arrives(self, conn):
        # The core race fix: a response arriving immediately after the
        # waiter is created (before wait is called) must still be captured.
        waiter = conn.create_waiter("gaa")
        conn._route_packet(make_packet("gaa"))
        result = conn.wait_for_result("gaa", waiter, timeout=0.1)
        assert result.command_id == "gaa"

    def test_waiters_consumed_fifo(self, conn):
        first = conn.create_waiter("gaa")
        second = conn.create_waiter("gaa")
        p1 = make_packet("gaa", '{"n": 1}')
        p2 = make_packet("gaa", '{"n": 2}')
        conn._route_packet(p1)
        conn._route_packet(p2)
        assert conn.wait_for_result("gaa", first, timeout=0.1).payload == {"n": 1}
        assert conn.wait_for_result("gaa", second, timeout=0.1).payload == {"n": 2}

    def test_state_handler_runs_before_waiter_is_woken(self, conn):
        # on_packet is what feeds GameState. If the waiter is completed first, a
        # caller doing request(...) then reading state can miss the very response
        # it waited for.
        waiter = conn.create_waiter("gam")
        waiter_already_set = []

        def on_packet(_packet):
            waiter_already_set.append(waiter.event.is_set())

        conn.on_packet = on_packet
        conn._route_packet(make_packet("gam"))
        assert waiter_already_set == [False]

    def test_timeout_raises_library_timeout(self, conn):
        waiter = conn.create_waiter("gam")
        with pytest.raises(EmpireTimeoutError):
            conn.wait_for_result("gam", waiter, timeout=0.01)
        # And it is also caught by the builtin, for callers using that
        waiter = conn.create_waiter("gam")
        with pytest.raises(TimeoutError):
            conn.wait_for_result("gam", waiter, timeout=0.01)

    def test_cancel_all_waiters_raises_connection_closed(self, conn):
        waiter = conn.create_waiter("gam")
        conn._cancel_all_waiters()
        with pytest.raises(ConnectionClosedError):
            conn.wait_for_result("gam", waiter, timeout=0.1)

    def test_cancelled_waiter_not_reused(self, conn):
        waiter = conn.create_waiter("gam")
        conn.cancel_waiter("gam", waiter)
        packet = make_packet("gam")
        conn._route_packet(packet)  # No waiter registered anymore; no crash
        assert waiter.result is None


class TestSubscribers:
    def test_subscribers_receive_all_packets(self, conn):
        received: list[Packet] = []
        conn.subscribe("acm", received.append)
        conn._route_packet(make_packet("acm"))
        conn._route_packet(make_packet("acm"))
        assert len(received) == 2

    def test_unsubscribe(self, conn):
        received: list[Packet] = []
        conn.subscribe("acm", received.append)
        conn.unsubscribe("acm", received.append)
        conn._route_packet(make_packet("acm"))
        assert received == []

    def test_subscriber_exception_does_not_break_routing(self, conn):
        received: list[Packet] = []

        def bad(_packet):
            raise RuntimeError("boom")

        conn.subscribe("acm", bad)
        conn.subscribe("acm", received.append)
        conn._route_packet(make_packet("acm"))
        assert len(received) == 1

    def test_global_handler_called(self, conn):
        seen: list[Packet] = []
        conn.on_packet = seen.append
        conn._route_packet(make_packet("xyz"))
        assert len(seen) == 1


class TestThreadSafety:
    def test_concurrent_route_and_wait(self, conn):
        # Waiters resolved from another thread while the main thread waits
        waiter = conn.create_waiter("gam")

        def route():
            conn._route_packet(make_packet("gam"))

        t = threading.Thread(target=route)
        t.start()
        result = conn.wait_for_result("gam", waiter, timeout=1.0)
        t.join()
        assert result.command_id == "gam"
