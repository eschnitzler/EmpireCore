"""Tests for Connection waiter routing (no real socket needed)."""

import threading
import time

import pytest
import websocket

from empire_core.exceptions import ConnectionClosedError, EmpireTimeoutError, NetworkError
from empire_core.network.connection import SESSION_IDLE_TIMEOUT, Connection
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


class RecordingSocket:
    """Stand-in for an already-connected websocket that records sends."""

    def __init__(self):
        self.connected = True
        self.closed = False
        self.sent: list[str] = []

    def send(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True
        self.connected = False


def make_ws_factory(created: list, gate: threading.Event | None = None):
    """Build a websocket.WebSocket replacement recording every instance.

    If ``gate`` is given, the handshake blocks on it, which makes the window
    between "connect() started" and "connect() finished" controllable.
    """

    class FakeWS:
        def __init__(self):
            self.connected = False
            self.closed = False
            self.timeouts: list[float] = []
            created.append(self)

        def settimeout(self, timeout):
            self.timeouts.append(timeout)

        def connect(self, _url):
            if gate is not None:
                assert gate.wait(timeout=5), "handshake gate never opened"
            self.connected = True

        def recv(self):
            time.sleep(0.005)
            raise websocket.WebSocketTimeoutException()

        def send(self, _data):
            pass

        def close(self):
            self.closed = True
            self.connected = False

    return FakeWS


def quiesce(conn: Connection) -> None:
    """Retire background threads without going through disconnect()."""
    conn._running = False
    conn._generation += 1
    if conn._recv_thread:
        conn._recv_thread.join(timeout=2.0)


def wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


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


LOGIN_FRAME = '%xt%EmpireEx_21%lli%1%{"CONM": 175, "NOM": "the-player", "PW": "s3cr3t-password"}%'


@pytest.fixture
def sending_conn(conn) -> Connection:
    """A Connection that can send() onto a RecordingSocket."""
    conn.ws = RecordingSocket()
    conn._running = True
    return conn


def logged_text(caplog) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


class TestSendRedaction:
    """send() must never write credentials to the log.

    The library's own examples enable DEBUG globally, so anything logged here
    lands in user-visible logs.
    """

    def test_login_frame_body_is_never_logged(self, sending_conn, caplog):
        with caplog.at_level("DEBUG", logger="empire_core.network.connection"):
            sending_conn.send(LOGIN_FRAME)

        logged = logged_text(caplog)
        assert "s3cr3t-password" not in logged
        assert "the-player" not in logged
        # The frame still went out unmodified...
        assert sending_conn.ws.sent == [LOGIN_FRAME]
        # ...and the command id plus size stay observable for debugging.
        assert "lli" in logged
        assert str(len(LOGIN_FRAME)) in logged

    def test_long_login_frame_is_redacted_not_merely_truncated(self, sending_conn, caplog):
        # Today the password escapes only because LOGIN_DEFAULTS happens to
        # push "PW" past the 100-char slice. Reorder the payload and it leaks.
        frame = '%xt%EmpireEx_21%lli%1%{"PW": "s3cr3t-password", "NOM": "the-player", "CONM": 175}%'
        with caplog.at_level("DEBUG", logger="empire_core.network.connection"):
            sending_conn.send(frame)

        assert "s3cr3t-password" not in logged_text(caplog)

    @pytest.mark.parametrize("command", ["lli", "core_reg", "scp"])
    def test_all_auth_commands_are_redacted(self, sending_conn, caplog, command):
        frame = f'%xt%EmpireEx_21%{command}%1%{{"PW": "topsecret", "NOM": "someone"}}%'
        with caplog.at_level("DEBUG", logger="empire_core.network.connection"):
            sending_conn.send(frame)

        assert "topsecret" not in logged_text(caplog)

    def test_credential_keys_masked_in_unrecognised_frames(self, sending_conn, caplog):
        # Defence in depth: a credential-bearing command we do not know about.
        frame = '%xt%EmpireEx_21%newauth%1%{"PW": "topsecret"}%'
        with caplog.at_level("DEBUG", logger="empire_core.network.connection"):
            sending_conn.send(frame)

        logged = logged_text(caplog)
        assert "topsecret" not in logged
        assert "newauth" in logged

    def test_xml_password_element_is_masked(self, sending_conn, caplog):
        # Short enough that truncation cannot be what saves us.
        frame = "<msg t='sys'><body action='login' r='0'><pword><![CDATA[hunter2]]></pword></body></msg>"
        assert frame.index("hunter2") < 100
        with caplog.at_level("DEBUG", logger="empire_core.network.connection"):
            sending_conn.send(frame)

        assert "hunter2" not in logged_text(caplog)

    def test_redaction_failure_is_not_reported_as_a_send_failure(self, sending_conn, monkeypatch, caplog):
        # The frame is already on the wire by the time we log it; a bug in the
        # redaction path must not be raised as NetworkError to the caller.
        def boom(_frame):
            raise ValueError("bad pattern")

        monkeypatch.setattr("empire_core.network.connection._summarise_frame", boom)
        with caplog.at_level("DEBUG", logger="empire_core.network.connection"), pytest.raises(ValueError):
            sending_conn.send("%xt%EmpireEx_21%gdi%1%{}%")

        assert sending_conn.ws.sent == ["%xt%EmpireEx_21%gdi%1%{}%"]

    def test_ordinary_frame_is_still_logged_and_bounded(self, sending_conn, caplog):
        frame = "%xt%EmpireEx_21%gdi%1%" + "x" * 500 + "%"
        with caplog.at_level("DEBUG", logger="empire_core.network.connection"):
            sending_conn.send(frame)

        logged = logged_text(caplog)
        assert "gdi" in logged
        assert len(logged) < 200  # truncation kept as defence in depth


class TestLifecycleExclusion:
    def test_concurrent_connect_opens_a_single_socket(self, conn, monkeypatch):
        created: list = []
        gate = threading.Event()
        monkeypatch.setattr(websocket, "WebSocket", make_ws_factory(created, gate))

        first = threading.Thread(target=conn.connect, daemon=True)
        first.start()
        assert wait_until(lambda: len(created) == 1), "first connect never started"

        second = threading.Thread(target=conn.connect, daemon=True)
        second.start()
        time.sleep(0.1)

        # The second caller must be waiting for the lifecycle lock, not racing
        # a competing handshake whose socket gets overwritten (and leaked) at
        # self.ws - or worse, sharing a generation with the first.
        assert len(created) == 1

        gate.set()
        first.join(timeout=5)
        second.join(timeout=5)
        try:
            assert len(created) == 1
            assert conn._generation == 1
            assert conn.ws is created[0]
        finally:
            quiesce(conn)

    def test_connect_closes_a_socket_left_over_from_a_dead_session(self, conn, monkeypatch):
        created: list = []
        monkeypatch.setattr(websocket, "WebSocket", make_ws_factory(created))
        # A session whose recv loop died: _running is False but the socket
        # object (and its server-side session) is still around.
        stale = RecordingSocket()
        conn.ws = stale
        conn._running = False

        conn.connect()
        try:
            assert stale.closed, "previous socket leaked when self.ws was replaced"
            assert conn.ws is created[0]
        finally:
            quiesce(conn)

    def test_disconnect_cannot_interleave_with_connect(self, conn, monkeypatch):
        created: list = []
        gate = threading.Event()
        monkeypatch.setattr(websocket, "WebSocket", make_ws_factory(created, gate))
        monkeypatch.setattr("empire_core.network.connection.THREAD_JOIN_TIMEOUT", 0.3)

        connector = threading.Thread(target=conn.connect, daemon=True)
        connector.start()
        assert wait_until(lambda: len(created) == 1), "connect never started"

        disconnector = threading.Thread(target=conn.disconnect, daemon=True)
        disconnector.start()
        time.sleep(0.05)

        gate.set()
        connector.join(timeout=5)
        disconnector.join(timeout=5)

        # disconnect() must serialise behind connect() instead of returning
        # early (it saw _running False) and leaving a live session nobody
        # asked for.
        assert conn.connected is False
        assert conn.ws is None
        assert created[0].closed

    def test_stale_recv_epilogue_waits_and_rechecks_generation(self, conn):
        # The epilogue must not cancel the waiters of a session that replaced
        # it. Holding the lifecycle lock stands in for a connect() in flight;
        # the generation bump inside it is what the epilogue has to notice.
        conn._running = True
        conn._generation = 1
        loop = threading.Thread(target=conn._recv_loop, args=(FakeSocket([]), 1), daemon=True)

        with conn._lifecycle_lock:
            loop.start()
            time.sleep(0.1)
            # Blocked on the lock, so the old session's state is untouched.
            assert conn._running is True
            conn._generation = 2
            waiter = conn.create_waiter("gam")

        loop.join(timeout=5)
        assert conn._running is True, "stale epilogue tore down the new session"
        assert waiter.error is None, "stale epilogue cancelled the new session's waiters"

    def test_stuck_recv_thread_is_reported(self, conn, monkeypatch, caplog):
        monkeypatch.setattr("empire_core.network.connection.THREAD_JOIN_TIMEOUT", 0.05)
        release = threading.Event()
        stuck = threading.Thread(target=release.wait, name="EmpireCore-Recv", daemon=True)
        stuck.start()
        conn._recv_thread = stuck
        conn._running = True

        try:
            with caplog.at_level("WARNING", logger="empire_core.network.connection"):
                conn.disconnect()
            assert "EmpireCore-Recv" in logged_text(caplog)
        finally:
            release.set()
            stuck.join(timeout=2)


class TestConnectedProperty:
    def test_connected_snapshots_the_socket(self, conn):
        # A concurrent disconnect() nulls self.ws; reading it twice raises
        # AttributeError inside callers' except handlers (keepalive loop) and
        # in MapScanner's abort checks.
        reads = []

        class VanishingWS(Connection):
            @property
            def ws(self):
                reads.append(1)
                return self._ws if len(reads) == 1 else None

            @ws.setter
            def ws(self, value):
                self._ws = value

        flaky = VanishingWS("wss://example.invalid/")
        flaky.ws = RecordingSocket()
        flaky._running = True
        reads.clear()

        assert flaky.connected is True
        assert len(reads) == 1


class TestDisconnectListeners:
    def test_listener_and_legacy_attribute_both_fire(self, live_conn):
        # The client claims on_disconnect for itself, so consumers currently
        # monkey-patch it. Listeners must coexist with it.
        calls: list[str] = []
        live_conn.on_disconnect = lambda: calls.append("attribute")
        live_conn.add_disconnect_listener(lambda: calls.append("listener"))

        live_conn._recv_loop(FakeSocket([]), 1)

        assert sorted(calls) == ["attribute", "listener"]

    def test_multiple_listeners_are_independent(self, live_conn):
        calls: list[str] = []

        def boom():
            raise RuntimeError("listener blew up")

        live_conn.add_disconnect_listener(boom)
        live_conn.add_disconnect_listener(lambda: calls.append("second"))

        live_conn._recv_loop(FakeSocket([]), 1)

        assert calls == ["second"]

    def test_remove_disconnect_listener(self, live_conn):
        calls: list[str] = []

        def listener():
            calls.append("called")

        live_conn.add_disconnect_listener(listener)
        live_conn.remove_disconnect_listener(listener)
        live_conn.remove_disconnect_listener(listener)  # idempotent

        live_conn._recv_loop(FakeSocket([]), 1)

        assert calls == []

    def test_listeners_not_called_on_intentional_disconnect(self, live_conn):
        calls: list[str] = []
        live_conn.add_disconnect_listener(lambda: calls.append("called"))
        live_conn._closing = True

        live_conn._recv_loop(FakeSocket([]), 1)

        assert calls == []

    def test_disconnect_callback_may_reconnect_without_deadlocking(self, conn, monkeypatch):
        # A listener that reconnects runs on the recv thread; if the epilogue
        # still held the lifecycle lock, connect() would deadlock.
        created: list = []
        monkeypatch.setattr(websocket, "WebSocket", make_ws_factory(created))
        conn._running = True
        conn._generation = 1
        conn.add_disconnect_listener(lambda: conn.connect(timeout=0.5))

        loop = threading.Thread(target=conn._recv_loop, args=(FakeSocket([]), 1), daemon=True)
        loop.start()
        loop.join(timeout=5)
        try:
            assert not loop.is_alive(), "disconnect listener deadlocked the recv thread"
            assert len(created) == 1
        finally:
            quiesce(conn)


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


class TestSessionLiveness:
    """A session can go stale server-side while the socket stays open."""

    def test_silent_session_is_closed(self, live_conn):
        ws = RecordingSocket()
        live_conn.ws = ws
        live_conn._last_recv_at = time.monotonic() - (SESSION_IDLE_TIMEOUT + 1)

        live_conn._check_session_liveness()

        assert ws.closed, "stale session left open; reconnect can never fire"

    def test_recent_traffic_keeps_session(self, live_conn):
        ws = RecordingSocket()
        live_conn.ws = ws
        live_conn._last_recv_at = time.monotonic()

        live_conn._check_session_liveness()

        assert not ws.closed

    def test_superseded_generation_is_left_alone(self, live_conn):
        ws = RecordingSocket()
        live_conn.ws = ws
        live_conn._last_recv_at = time.monotonic() - (SESSION_IDLE_TIMEOUT + 1)
        live_conn._running = False

        live_conn._check_session_liveness()

        assert not ws.closed

    def test_received_frame_stamps_liveness(self, live_conn):
        live_conn._last_recv_at = time.monotonic() - 999

        live_conn._recv_loop(FakeSocket([make_frame("gam")]), 1)

        assert time.monotonic() - live_conn._last_recv_at < 5
