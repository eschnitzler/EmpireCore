"""Tests for Connection waiter routing (no real socket needed)."""

import threading
import time

import pytest
import websocket

from empire_core.exceptions import ConnectionClosedError, EmpireTimeoutError, NetworkError, ReceiveThreadError
from empire_core.network.connection import SESSION_IDLE_TIMEOUT, Connection, _summarize_frame
from empire_core.protocol.packet import Packet


def make_packet(command: str, payload: str = "{}") -> Packet:
    return Packet.from_bytes(f"%xt%{command}%1%0%{payload}%".encode())


def make_frame(command: str, payload: str = "{}") -> bytes:
    return f"%xt%{command}%1%0%{payload}%".encode()


class FakeSocket:
    """Minimal stand-in for websocket.WebSocket for driving _recv_loop.

    ``frames`` entries are returned from recv_data() in order, bytes as a
    binary message, str as a text one and an (opcode, data) tuple as given;
    an Exception instance is raised instead of returned. When the list is
    exhausted the socket behaves like a closed one.
    """

    def __init__(self, frames):
        self.frames = list(frames)
        self.connected = True

    def recv_data(self):
        if not self.frames:
            raise websocket.WebSocketConnectionClosedException("no more frames")
        item = self.frames.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, tuple):
            return item
        return (websocket.ABNF.OPCODE_BINARY if isinstance(item, bytes) else websocket.ABNF.OPCODE_TEXT), item


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
        def __init__(self, **_options):
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

        def recv_data(self):
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

    def test_canceled_waiter_not_reused(self, conn):
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


def gdi_reply(player_id: int, error_code: int = 0) -> Packet:
    return Packet.from_bytes(f'%xt%gdi%1%{error_code}%{{"O": {{"OID": {player_id}}}}}%'.encode())


def about(player_id: int):
    """The gdi reply check GetPlayerInfoRequest makes."""
    return lambda packet: packet.payload["O"]["OID"] == player_id


class Caller:
    """Runs one Connection.request on its own thread and keeps the outcome."""

    def __init__(self, conn: Connection, cmd_id: str, timeout: float = 5.0, accepts=None):
        self.result: Packet | None = None
        self.error: Exception | None = None

        def run():
            try:
                self.result = conn.request(
                    f"%xt%EmpireEx_21%{cmd_id}%1%{{}}%", cmd_id, timeout=timeout, accepts=accepts
                )
            except Exception as e:
                self.error = e

        self.thread = threading.Thread(target=run)
        self.thread.start()

    def join(self) -> "Caller":
        self.thread.join(timeout=5)
        assert not self.thread.is_alive()
        return self

    def answer(self) -> Packet:
        """The reply the request returned."""
        self.join()
        assert self.result is not None, self.error
        return self.result


def sent(conn: Connection) -> list[str]:
    return conn.ws.sent  # type: ignore[union-attr]


class TestOneRequestPerCommand:
    """The protocol has no request id, so request() runs one request per command id at a time."""

    def test_a_second_caller_sends_only_once_the_first_is_answered(self, sending_conn):
        first = Caller(sending_conn, "gdi", accepts=about(1))
        assert wait_until(lambda: len(sent(sending_conn)) == 1)
        second = Caller(sending_conn, "gdi", accepts=about(2))

        # The second caller's answer arriving first is not the first caller's.
        sending_conn._route_packet(gdi_reply(2))
        assert len(sent(sending_conn)) == 1
        sending_conn._route_packet(gdi_reply(1))
        assert first.answer().payload == {"O": {"OID": 1}}

        assert wait_until(lambda: len(sent(sending_conn)) == 2)
        sending_conn._route_packet(gdi_reply(2))
        assert second.answer().payload == {"O": {"OID": 2}}

    def test_time_spent_queued_counts_against_the_timeout(self, sending_conn):
        first = Caller(sending_conn, "gdi", accepts=about(1))
        assert wait_until(lambda: len(sent(sending_conn)) == 1)

        with pytest.raises(EmpireTimeoutError, match="still running"):
            sending_conn.request("%xt%EmpireEx_21%gdi%1%{}%", "gdi", timeout=0.05, accepts=about(2))
        assert len(sent(sending_conn)) == 1

        sending_conn._route_packet(gdi_reply(1))
        assert first.join().result is not None

    def test_different_commands_run_in_parallel(self, sending_conn):
        gdi = Caller(sending_conn, "gdi")
        gaa = Caller(sending_conn, "gaa")
        assert wait_until(lambda: len(sent(sending_conn)) == 2)
        sending_conn._route_packet(make_packet("gaa"))
        sending_conn._route_packet(make_packet("gdi"))
        assert gdi.answer().command_id == "gdi"
        assert gaa.answer().command_id == "gaa"

    def test_an_error_reply_goes_to_the_caller_in_flight_not_to_the_one_queued(self, sending_conn):
        first = Caller(sending_conn, "gdi", accepts=about(1))
        assert wait_until(lambda: len(sent(sending_conn)) == 1)
        second = Caller(sending_conn, "gdi", accepts=about(2))

        sending_conn._route_packet(Packet.from_bytes(b"%xt%gdi%1%114%%"))
        assert first.answer().error_code == 114

        assert wait_until(lambda: len(sent(sending_conn)) == 2)
        sending_conn._route_packet(gdi_reply(2))
        assert second.answer().error_code == 0

    def test_a_send_failure_releases_the_command(self, sending_conn):
        sending_conn._running = False
        with pytest.raises(NetworkError):
            sending_conn.request("%xt%EmpireEx_21%gdi%1%{}%", "gdi", timeout=1)
        sending_conn._running = True
        caller = Caller(sending_conn, "gdi")
        assert wait_until(lambda: len(sent(sending_conn)) == 1)
        sending_conn._route_packet(make_packet("gdi"))
        assert caller.join().result is not None

    def test_command_lock_keeps_requests_for_that_command_out(self, sending_conn):
        with sending_conn.command_lock("gdi"):
            caller = Caller(sending_conn, "gdi", timeout=0.05).join()
        assert isinstance(caller.error, EmpireTimeoutError)
        assert sent(sending_conn) == []

    def test_command_lock_is_reentrant_on_the_holding_thread(self, sending_conn):
        with sending_conn.command_lock("gdi"):
            with sending_conn.command_lock("gdi", timeout=0):
                pass

    def test_no_time_left_after_the_lock_means_no_send(self, sending_conn):
        with pytest.raises(EmpireTimeoutError):
            sending_conn.request("%xt%EmpireEx_21%gdi%1%{}%", "gdi", timeout=0)
        assert sent(sending_conn) == []
        assert sending_conn._waiters == {}

    def test_command_lock_is_refused_on_the_receive_thread(self, sending_conn):
        sending_conn._recv_thread = threading.current_thread()
        with pytest.raises(ReceiveThreadError):
            with sending_conn.command_lock("gdi"):
                pass


class TestReplyChecks:
    def test_a_push_for_another_player_does_not_answer_the_request(self, conn):
        seen: list[Packet] = []
        conn.on_packet = seen.append
        pushed: list[Packet] = []
        conn.subscribe("gdi", pushed.append)
        waiter = conn.create_waiter("gdi", about(1))

        conn._route_packet(gdi_reply(9))
        assert not waiter.event.is_set()
        assert len(seen) == 1 and len(pushed) == 1

        conn._route_packet(gdi_reply(1))
        assert conn.wait_for_result("gdi", waiter, timeout=0.1).payload == {"O": {"OID": 1}}

    def test_a_late_reply_to_a_timed_out_request_is_not_taken_by_the_next(self, sending_conn):
        with pytest.raises(EmpireTimeoutError):
            sending_conn.request("%xt%EmpireEx_21%gdi%1%{}%", "gdi", timeout=0.01, accepts=about(1))

        caller = Caller(sending_conn, "gdi", accepts=about(2))
        assert wait_until(lambda: len(sent(sending_conn)) == 2)
        sending_conn._route_packet(gdi_reply(1))
        sending_conn._route_packet(gdi_reply(2))
        assert caller.answer().payload == {"O": {"OID": 2}}

    def test_the_oldest_waiter_that_accepts_the_reply_takes_it(self, conn):
        for_one = conn.create_waiter("gdi", about(1))
        for_two = conn.create_waiter("gdi", about(2))
        conn._route_packet(gdi_reply(2))
        assert for_two.event.is_set() and not for_one.event.is_set()

    def test_without_a_check_the_first_reply_is_taken(self, conn):
        waiter = conn.create_waiter("gam")
        push = make_packet("gam", '{"pushed": 1}')
        conn._route_packet(push)
        assert conn.wait_for_result("gam", waiter, timeout=0.1) is push

    def test_a_check_that_raises_takes_nothing_and_is_logged_once(self, conn, caplog):
        def broken(_packet):
            raise KeyError("O")

        waiter = conn.create_waiter("gdi", broken)
        with caplog.at_level("ERROR", logger="empire_core.network.connection"):
            conn._route_packet(make_packet("gdi"))
            conn._route_packet(make_packet("gdi"))
        assert not waiter.event.is_set()
        assert len([r for r in caplog.records if "Reply check" in r.getMessage()]) == 1


def time_out(conn: Connection, cmd_id: str, timeout: float = 0.05, accepts=None) -> None:
    with pytest.raises(EmpireTimeoutError):
        conn.request(f"%xt%EmpireEx_21%{cmd_id}%1%{{}}%", cmd_id, timeout=timeout, accepts=accepts)


class TestLateReplies:
    """A reply whose request stopped waiting is owed to that request, never handed to the next."""

    def test_the_next_unchecked_request_sends_once_the_late_reply_is_in_and_gets_its_own(self, sending_conn):
        time_out(sending_conn, "gui", timeout=0.6)
        caller = Caller(sending_conn, "gui")
        time.sleep(0.05)
        assert len(sent(sending_conn)) == 1

        sending_conn._route_packet(make_packet("gui", '{"late": 1}'))
        assert wait_until(lambda: len(sent(sending_conn)) == 2)
        sending_conn._route_packet(make_packet("gui", '{"own": 1}'))
        assert caller.answer().payload == {"own": 1}

    def test_the_late_reply_still_reaches_state_and_subscribers(self, sending_conn):
        seen: list[Packet] = []
        sending_conn.on_packet = seen.append
        pushed: list[Packet] = []
        sending_conn.subscribe("gui", pushed.append)
        time_out(sending_conn, "gui")
        sending_conn._route_packet(make_packet("gui", '{"late": 1}'))
        assert len(seen) == 1 and len(pushed) == 1
        assert sending_conn._waiters == {}

    def test_a_reply_that_never_comes_holds_the_next_request_back_only_for_the_window(self, sending_conn):
        time_out(sending_conn, "gui", timeout=0.05)
        caller = Caller(sending_conn, "gui")
        assert wait_until(lambda: len(sent(sending_conn)) == 2, timeout=0.5)
        sending_conn._route_packet(make_packet("gui", '{"own": 1}'))
        assert caller.answer().payload == {"own": 1}

    def test_after_a_lost_reply_the_next_request_still_has_its_whole_timeout(self, sending_conn):
        time_out(sending_conn, "gui", timeout=0.2)
        caller = Caller(sending_conn, "gui", timeout=0.15)
        assert wait_until(lambda: len(sent(sending_conn)) == 2, timeout=0.5)
        time.sleep(0.05)
        sending_conn._route_packet(make_packet("gui", '{"own": 1}'))
        assert caller.answer().payload == {"own": 1}

    def test_after_a_lost_checked_reply_only_that_request_times_out(self, sending_conn):
        lid0 = lambda packet: packet.payload.get("LID") == 0  # noqa: E731
        time_out(sending_conn, "spl", timeout=0.3, accepts=lid0)
        for count in (2, 3, 4):
            caller = Caller(sending_conn, "spl", timeout=0.5, accepts=lid0)
            assert wait_until(lambda: len(sent(sending_conn)) == count)  # noqa: B023
            sending_conn._route_packet(make_packet("spl", '{"LID": 0}'))
            assert caller.answer().payload == {"LID": 0}

    def test_an_error_after_a_lost_checked_reply_still_goes_to_the_owed_waiter(self, sending_conn):
        time_out(sending_conn, "gdi", timeout=0.2, accepts=about(1))
        caller = Caller(sending_conn, "gdi", timeout=0.1, accepts=about(2))
        assert wait_until(lambda: len(sent(sending_conn)) == 2)
        sending_conn._route_packet(Packet.from_bytes(b"%xt%gdi%1%114%%"))
        caller.join()
        assert isinstance(caller.error, EmpireTimeoutError)

    def test_a_late_error_is_not_taken_by_the_next_checked_request(self, sending_conn):
        time_out(sending_conn, "gdi", timeout=0.2, accepts=about(1))
        caller = Caller(sending_conn, "gdi", accepts=about(2))
        # A check tells the late success reply apart, so the next request is sent at once.
        assert wait_until(lambda: len(sent(sending_conn)) == 2)

        sending_conn._route_packet(Packet.from_bytes(b"%xt%gdi%1%114%%"))
        sending_conn._route_packet(gdi_reply(2))
        assert caller.answer().payload == {"O": {"OID": 2}}

    def test_a_late_reply_after_the_window_is_not_kept_back(self, sending_conn):
        time_out(sending_conn, "gui", timeout=0.01)
        time.sleep(0.02)
        sending_conn._route_packet(make_packet("gui"))
        assert sending_conn._waiters == {}

    def test_a_disconnect_ends_the_wait_for_an_owed_reply(self, sending_conn):
        time_out(sending_conn, "gui", timeout=0.6)
        caller = Caller(sending_conn, "gui", timeout=2.0)
        time.sleep(0.05)
        started = time.monotonic()
        sending_conn._running = False
        sending_conn._cancel_all_waiters()
        caller.join()
        assert isinstance(caller.error, NetworkError)
        assert time.monotonic() - started < 0.4

    def test_a_reply_to_drop_is_asked_for_once_the_request_in_flight_is_answered(self, sending_conn):
        caller = Caller(sending_conn, "gam")
        assert wait_until(lambda: len(sent(sending_conn)) == 1)
        dropper = threading.Thread(target=sending_conn.send_and_drop_reply, args=("%xt%EmpireEx_21%gam%1%{}%", "gam"))
        dropper.start()
        time.sleep(0.05)
        assert len(sent(sending_conn)) == 1

        sending_conn._route_packet(make_packet("gam", '{"own": 1}'))
        assert caller.answer().payload == {"own": 1}
        dropper.join(timeout=2)
        assert len(sent(sending_conn)) == 2
        sending_conn._route_packet(make_packet("gam", '{"dropped": 1}'))
        assert sending_conn._waiters == {}

    def test_the_receive_thread_drops_a_reply_without_waiting_for_the_request_in_flight(self, sending_conn):
        caller = Caller(sending_conn, "gam")
        assert wait_until(lambda: len(sent(sending_conn)) == 1)
        sending_conn._recv_thread = threading.current_thread()
        sending_conn.send_and_drop_reply("%xt%EmpireEx_21%gam%1%{}%", "gam")
        assert len(sent(sending_conn)) == 2

        sending_conn._route_packet(make_packet("gam", '{"own": 1}'))
        sending_conn._route_packet(make_packet("gam", '{"dropped": 1}'))
        assert caller.answer().payload == {"own": 1}
        assert sending_conn._waiters == {}

    def test_a_request_after_a_dropped_reply_waits_for_it(self, sending_conn):
        sending_conn.send_and_drop_reply("%xt%EmpireEx_21%gam%1%{}%", "gam")
        caller = Caller(sending_conn, "gam")
        time.sleep(0.05)
        assert len(sent(sending_conn)) == 1

        sending_conn._route_packet(make_packet("gam", '{"dropped": 1}'))
        assert wait_until(lambda: len(sent(sending_conn)) == 2)
        sending_conn._route_packet(make_packet("gam", '{"own": 1}'))
        assert caller.answer().payload == {"own": 1}

    def test_dropping_a_reply_works_on_the_receive_thread(self, sending_conn):
        sending_conn._recv_thread = threading.current_thread()
        sending_conn.send_and_drop_reply("%xt%EmpireEx_21%gam%1%{}%", "gam")
        assert len(sent(sending_conn)) == 1

    def test_a_failed_send_owes_no_reply(self, sending_conn):
        sending_conn._running = False
        with pytest.raises(NetworkError):
            sending_conn.send_and_drop_reply("%xt%EmpireEx_21%gam%1%{}%", "gam")
        assert sending_conn._waiters == {}


class TestReceiveThreadGuard:
    """A wait on the receive thread could only time out, stalling every other reply meanwhile."""

    def test_a_subscriber_that_requests_fails_at_once_and_routing_goes_on(self, live_conn):
        live_conn.ws = RecordingSocket()
        live_conn._recv_thread = threading.current_thread()
        errors: list[Exception] = []
        routed: list[str | None] = []

        def on_acm(_packet):
            try:
                live_conn.request("%xt%EmpireEx_21%gdi%1%{}%", "gdi", timeout=30)
            except ReceiveThreadError as e:
                errors.append(e)

        live_conn.subscribe("acm", on_acm)
        live_conn.on_packet = lambda p: routed.append(p.command_id)
        started = time.monotonic()

        live_conn._recv_loop(FakeSocket([make_frame("acm"), make_frame("gam")]), 1)

        assert time.monotonic() - started < 5
        assert len(errors) == 1
        assert live_conn.ws.sent == []
        assert routed == ["acm", "gam"]

    @pytest.mark.parametrize("call", ["wait_for", "wait_for_result"])
    def test_waiting_for_a_push_on_the_receive_thread_fails_at_once(self, conn, call):
        conn._recv_thread = threading.current_thread()
        with pytest.raises(ReceiveThreadError):
            if call == "wait_for":
                conn.wait_for("sne", timeout=30)
            else:
                conn.wait_for_result("sne", conn.create_waiter("sne"), timeout=30)
        assert conn._waiters == {}

    def test_other_threads_may_still_wait(self, conn):
        conn._recv_thread = threading.Thread(target=lambda: None)
        waiter = conn.create_waiter("gam")
        conn._route_packet(make_packet("gam"))
        assert conn.wait_for_result("gam", waiter, timeout=0.1).command_id == "gam"


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

    def test_every_packet_of_a_batched_message_is_routed(self, live_conn):
        routed: list[str | None] = []
        live_conn.on_packet = lambda p: routed.append(p.command_id)
        batched = make_frame("gam") + b"\x00" + make_frame("dcl") + b"\x00"
        apiok = "<msg t='sys'><body action='apiOK' r='0'></body></msg>"

        live_conn._recv_loop(FakeSocket([batched, apiok + "%xt%gaa%1%0%{}%"]), 1)

        assert routed == ["gam", "dcl", "apiOK", "gaa"]

    def test_a_packet_split_across_messages_is_routed_once_whole(self, live_conn):
        waiter = live_conn.create_waiter("gam")
        frame = make_frame("gam", '{"M": [], "O": []}')

        live_conn._recv_loop(FakeSocket([frame[:9], frame[9:]]), 1)

        assert waiter.result is not None
        assert waiter.result.payload == {"M": [], "O": []}

    def test_socket_error_still_ends_the_loop(self, live_conn):
        # Socket-level failures are fatal: waiters are canceled and
        # on_disconnect fires so the client can re-login.
        disconnects: list[bool] = []
        live_conn.on_disconnect = lambda _generation: disconnects.append(True)
        waiter = live_conn.create_waiter("gam")
        ws = FakeSocket([OSError("socket died")])

        live_conn._recv_loop(ws, 1)

        assert disconnects == [True]
        assert live_conn._running is False
        assert isinstance(waiter.error, ConnectionClosedError)
        assert isinstance(waiter.error.__cause__, OSError)
        assert "socket died" in str(waiter.error)
        assert live_conn.close_error is waiter.error.__cause__

    def test_a_clean_disconnect_leaves_no_close_error(self, live_conn):
        waiter = live_conn.create_waiter("gam")

        live_conn.disconnect()

        assert live_conn.close_error is None
        assert str(waiter.error) == "Connection closed"
        assert waiter.error.__cause__ is None

    def test_bad_frame_alone_does_not_fire_on_disconnect(self, live_conn):
        # Only the real socket close at the end of the frame list should
        # trigger the disconnect callback - and exactly once.
        disconnects: list[bool] = []
        live_conn.on_disconnect = lambda _generation: disconnects.append(True)
        ws = FakeSocket([b"\x00", b"\xff\xfe"])

        live_conn._recv_loop(ws, 1)

        assert disconnects == [True]

    def test_an_unexpected_error_in_the_loop_still_runs_the_epilogue(self, live_conn, caplog):
        # Nothing in the loop is expected to raise outside recv(); if something does,
        # the connection must still end cleanly rather than look alive with a dead thread.
        class Undecodable(bytes):
            def decode(self, *args, **kwargs):
                raise MemoryError("injected")

        disconnects: list[int] = []
        live_conn.on_disconnect = disconnects.append
        waiter = live_conn.create_waiter("gam")

        with caplog.at_level("ERROR", logger="empire_core.network.connection"):
            live_conn._recv_loop(FakeSocket([Undecodable(make_frame("gam")), make_frame("gam")]), 1)

        assert live_conn._running is False
        assert isinstance(waiter.error, ConnectionClosedError)
        assert isinstance(waiter.error.__cause__, MemoryError)
        assert str(waiter.error) == "Connection closed: MemoryError: injected"
        assert live_conn.close_error is waiter.error.__cause__
        assert disconnects == [1]
        assert any(record.exc_info and "unexpected error" in record.getMessage() for record in caplog.records)

    def test_a_framing_error_drops_the_buffer_but_keeps_the_session(self, live_conn, monkeypatch, caplog):
        from empire_core.network import connection as connection_module

        original = connection_module.FrameBuffer.feed
        calls = {"n": 0}

        def flaky_feed(self, message):
            calls["n"] += 1
            if calls["n"] == 2:
                raise MemoryError("injected")
            return original(self, message)

        monkeypatch.setattr(connection_module.FrameBuffer, "feed", flaky_feed)
        routed: list[str | None] = []
        live_conn.on_packet = lambda p: routed.append(p.command_id)
        disconnects: list[int] = []
        live_conn.on_disconnect = disconnects.append
        partial = make_frame("gaa")[:9]

        with caplog.at_level("ERROR", logger="empire_core.network.connection"):
            live_conn._recv_loop(FakeSocket([partial, make_frame("acm"), make_frame("gam")]), 1)

        # The partial packet went with the dropped buffer; the next packet starts clean
        assert routed == ["gam"]
        assert disconnects == [1], "only the socket closing at the end ends the session"
        assert any(record.exc_info and "could not be split" in record.getMessage() for record in caplog.records)


class _ByteSocket:
    """Raw socket bytes for a real websocket.WebSocket; empty once read, which it sees as closed."""

    def __init__(self, data: bytes):
        self.data = memoryview(data)
        self.pos = 0

    def recv(self, n):
        chunk = self.data[self.pos : self.pos + n].tobytes()
        self.pos += len(chunk)
        return chunk

    def gettimeout(self):
        return None

    def settimeout(self, _timeout):
        pass


def _ws_frame(opcode: int, payload: bytes) -> bytes:
    assert len(payload) < 126
    return bytes([0x80 | opcode, len(payload)]) + payload


class TestMessageDecoding:
    """Messages decode as the client's FileReader.readAsText(data, "utf-8") decodes them."""

    def _route(self, live_conn, *frames: bytes) -> list:
        ws = websocket.WebSocket(skip_utf8_validation=True)
        ws.sock = _ByteSocket(b"".join(frames))  # type: ignore[assignment]
        ws.connected = True
        routed: list = []
        live_conn.on_packet = routed.append
        live_conn._recv_loop(ws, 1)
        return routed

    def test_an_invalid_byte_is_replaced_in_binary_and_text_messages(self, live_conn):
        bad = b'%xt%acm%1%0%{"CM":{"MT":"caf\xe9"}}%'
        for opcode in (websocket.ABNF.OPCODE_BINARY, websocket.ABNF.OPCODE_TEXT):
            live_conn._running = True
            routed = self._route(live_conn, _ws_frame(opcode, bad), _ws_frame(opcode, make_frame("gam")))
            assert [p.command_id for p in routed] == ["acm", "gam"]
            assert routed[0].payload == {"CM": {"MT": "caf\ufffd"}}

    def test_a_leading_byte_order_mark_is_dropped(self, live_conn):
        routed = self._route(live_conn, _ws_frame(websocket.ABNF.OPCODE_BINARY, b"\xef\xbb\xbf" + make_frame("gam")))
        assert [p.command_id for p in routed] == ["gam"]

    def test_connect_leaves_utf8_to_the_decoder(self, conn, monkeypatch):
        options: list[dict] = []
        created: list = []
        factory = make_ws_factory(created)

        def recording(**kwargs):
            options.append(kwargs)
            return factory(**kwargs)

        monkeypatch.setattr(websocket, "WebSocket", recording)
        conn.connect()
        try:
            assert options == [{"skip_utf8_validation": True}]
        finally:
            conn.disconnect()


class TestConnectErrors:
    def _patch_ws(self, monkeypatch, error: Exception):
        closed: list[bool] = []

        class FailingWS:
            def __init__(self, **_options):
                pass

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

    def test_credential_keys_masked_in_unrecognized_frames(self, sending_conn, caplog):
        # Defense in depth: a credential-bearing command we do not know about.
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

        monkeypatch.setattr("empire_core.network.connection._summarize_frame", boom)
        with caplog.at_level("DEBUG", logger="empire_core.network.connection"), pytest.raises(ValueError):
            sending_conn.send("%xt%EmpireEx_21%gdi%1%{}%")

        assert sending_conn.ws.sent == ["%xt%EmpireEx_21%gdi%1%{}%"]

    def test_ordinary_frame_is_still_logged_and_bounded(self, sending_conn, caplog):
        frame = "%xt%EmpireEx_21%gdi%1%" + "x" * 500 + "%"
        with caplog.at_level("DEBUG", logger="empire_core.network.connection"):
            sending_conn.send(frame)

        logged = logged_text(caplog)
        assert "gdi" in logged
        assert len(logged) < 200  # truncation kept as defense in depth


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

        # disconnect() must serialize behind connect() instead of returning
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
        assert waiter.error is None, "stale epilogue canceled the new session's waiters"

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
        live_conn.on_disconnect = lambda _generation: calls.append("attribute")
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


class TestFrameRedactionEscapedQuotes:
    """Finding: a JSON-escaped quote inside a credential value must not stop
    the mask early and leak the tail of the secret."""

    def test_escaped_quote_does_not_leak_the_password_tail(self):
        summary = _summarize_frame('%xt%z%unk%1%{"PW": "hun\\"ter2secret"}%')
        assert "ter2secret" not in summary
        assert '"<redacted>"' in summary

    def test_escaped_backslash_before_the_closing_quote(self):
        summary = _summarize_frame('%xt%z%unk%1%{"PW": "hunter2\\\\"}%')
        assert "hunter2" not in summary
        assert '"<redacted>"' in summary

    def test_plain_password_is_still_masked(self):
        summary = _summarize_frame('%xt%z%unk%1%{"PW": "hunter2", "NM": "user"}%')
        assert "hunter2" not in summary
        assert '"NM": "user"' in summary
