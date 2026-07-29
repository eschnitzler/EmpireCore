"""Tests for Connection waiter routing (no real socket needed)."""

import threading

import pytest
import websocket

from empire_core.exceptions import ConnectionClosedError, EmpireTimeoutError, NetworkError
from empire_core.network.connection import Connection
from empire_core.protocol.packet import Packet


def make_packet(command: str, payload: str = "{}") -> Packet:
    return Packet.from_bytes(f"%xt%{command}%1%0%{payload}%".encode())


def make_frame(command: str, payload: str = "{}") -> bytes:
    return f"%xt%{command}%1%0%{payload}%".encode()


class FakeSocket:
    """Minimal stand-in for websocket.WebSocket for driving _recv_loop.

    ``frames`` entries are returned from recv() in order; an Exception
    instance is raised instead of returned. When the list is exhausted the
    socket behaves like a closed one.
    """

    def __init__(self, frames):
        self.frames = list(frames)
        self.connected = True

    def recv(self):
        if not self.frames:
            raise websocket.WebSocketConnectionClosedException("no more frames")
        item = self.frames.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def conn() -> Connection:
    return Connection("wss://example.invalid/")


@pytest.fixture
def live_conn(conn) -> Connection:
    """A Connection whose recv loop will run for generation 1."""
    conn._running = True
    conn._generation = 1
    return conn


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


class TestCorrelationIsFifo:
    """Pinning tests for the documented FIFO-by-command-id correlation.

    Correlation has no payload-level matching, so these behaviours are
    surprising but intentional for now. If a future change adds real
    correlation, these tests should fail and be updated deliberately.
    """

    def test_unsolicited_push_consumes_pending_waiter(self, conn):
        # A server push with the same command id as a pending request
        # satisfies that request instead of being passed through only to
        # subscribers.
        waiter = conn.create_waiter("gam")
        push = make_packet("gam", '{"pushed": 1}')
        conn._route_packet(push)
        assert conn.wait_for_result("gam", waiter, timeout=0.1) is push

    def test_identical_concurrent_commands_can_cross_deliver(self, conn):
        # Two callers issuing the same command are answered in registration
        # order, regardless of which response belongs to whom.
        first = conn.create_waiter("gdi")
        second = conn.create_waiter("gdi")
        for_second = make_packet("gdi", '{"PID": 2}')
        for_first = make_packet("gdi", '{"PID": 1}')
        # Responses arrive out of order relative to registration.
        conn._route_packet(for_second)
        conn._route_packet(for_first)
        assert conn.wait_for_result("gdi", first, timeout=0.1).payload == {"PID": 2}
        assert conn.wait_for_result("gdi", second, timeout=0.1).payload == {"PID": 1}


class TestRecvLoopResilience:
    def test_unparseable_frames_do_not_kill_the_loop(self, live_conn):
        # A frame of only null bytes and a frame with invalid UTF-8 are both
        # inputs Packet.from_bytes can reject. Neither may cost us the
        # connection: the following good frame must still be routed.
        routed: list[Packet] = []
        live_conn.on_packet = routed.append
        ws = FakeSocket([b"\x00", b"\xff\xfe", make_frame("gam")])

        live_conn._recv_loop(ws, 1)

        assert "gam" in [p.command_id for p in routed]

    def test_routing_error_does_not_kill_the_loop(self, live_conn, caplog):
        # Independent of Packet.from_bytes: any failure in the parse/route
        # step must be contained to that frame - but never silently.
        seen: list[str | None] = []
        original_route = live_conn._route_packet

        def flaky_route(packet):
            if not seen:
                seen.append(packet.command_id)
                raise RuntimeError("boom")
            seen.append(packet.command_id)
            original_route(packet)

        live_conn._route_packet = flaky_route  # type: ignore[method-assign]
        ws = FakeSocket([make_frame("gam"), make_frame("gaa")])

        with caplog.at_level("ERROR", logger="empire_core.network.connection"):
            live_conn._recv_loop(ws, 1)

        assert seen == ["gam", "gaa"]
        # The dropped frame is reported with a traceback
        assert any(record.exc_info for record in caplog.records)

    def test_bad_frame_does_not_cancel_waiters(self, live_conn):
        # The waiter for a command that arrives after a bad frame must still
        # be satisfied rather than failed with ConnectionClosedError.
        waiter = live_conn.create_waiter("gam")
        ws = FakeSocket([b"\x00", make_frame("gam")])

        live_conn._recv_loop(ws, 1)

        assert waiter.result is not None
        assert waiter.result.command_id == "gam"

    def test_socket_error_still_ends_the_loop(self, live_conn):
        # Socket-level failures are fatal: waiters are cancelled and
        # on_disconnect fires so the client can re-login.
        disconnects: list[bool] = []
        live_conn.on_disconnect = lambda: disconnects.append(True)
        waiter = live_conn.create_waiter("gam")
        ws = FakeSocket([OSError("socket died")])

        live_conn._recv_loop(ws, 1)

        assert disconnects == [True]
        assert live_conn._running is False
        assert isinstance(waiter.error, ConnectionClosedError)

    def test_bad_frame_alone_does_not_fire_on_disconnect(self, live_conn):
        # Only the real socket close at the end of the frame list should
        # trigger the disconnect callback - and exactly once.
        disconnects: list[bool] = []
        live_conn.on_disconnect = lambda: disconnects.append(True)
        ws = FakeSocket([b"\x00", b"\xff\xfe"])

        live_conn._recv_loop(ws, 1)

        assert disconnects == [True]


class TestConnectErrors:
    def _patch_ws(self, monkeypatch, error: Exception):
        closed: list[bool] = []

        class FailingWS:
            def settimeout(self, _timeout):
                pass

            def connect(self, _url):
                raise error

            def close(self):
                closed.append(True)

        monkeypatch.setattr(websocket, "WebSocket", FailingWS)
        return closed

    def test_websocket_exception_is_wrapped_in_network_error(self, conn, monkeypatch):
        cause = websocket.WebSocketException("handshake failed")
        self._patch_ws(monkeypatch, cause)

        with pytest.raises(NetworkError) as exc_info:
            conn.connect(timeout=0.1)

        assert "example.invalid" in str(exc_info.value)
        assert exc_info.value.__cause__ is cause

    def test_connection_refused_is_wrapped_in_network_error(self, conn, monkeypatch):
        cause = ConnectionRefusedError("refused")
        closed = self._patch_ws(monkeypatch, cause)

        with pytest.raises(NetworkError):
            conn.connect(timeout=0.1)

        assert closed == [True]
        assert conn.ws is None

    def test_timeout_is_wrapped_in_network_error(self, conn, monkeypatch):
        self._patch_ws(monkeypatch, TimeoutError("timed out"))

        with pytest.raises(NetworkError):
            conn.connect(timeout=0.1)


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
