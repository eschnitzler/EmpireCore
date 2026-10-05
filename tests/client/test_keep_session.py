"""keep_session: a held client logs in again by itself after a drop (no real socket)."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Iterator

import pytest

from empire_core.client import session as session_module
from empire_core.client.client import EmpireClient
from empire_core.enums import MovementType
from empire_core.exceptions import (
    AccountBannedError,
    ConnectionClosedError,
    EmpireTimeoutError,
    LoginCooldownError,
    NetworkError,
)
from empire_core.protocol.errors import GGEError
from tests.client.test_disconnect import arrive_packet, drop, new_session
from tests.service_helpers import xt_packet
from tests.state.state_helpers import gam_payload, wait_for

GBD = {"gpi": {"PID": 1, "PN": "me"}}

OCCUPATION = MovementType.SIEGE

# An attack by its movement id, or a movement of another type as (movement id, type).
Listed = int | tuple[int, int]
# What one login attempt does: raise, be refused with a cooldown of that many seconds, or log in and list these.
Attempt = Exception | float | list[Listed]


def list_movement(client: EmpireClient, listed: Listed) -> None:
    mid, movement_type = listed if isinstance(listed, tuple) else (listed, 0)
    arrive_packet(client, "gam", gam_payload(mid, movement_type=movement_type))


class RecordingEvent(threading.Event):
    """The client's closed flag, recording each wait and returning at once unless it is set."""

    def __init__(self) -> None:
        super().__init__()
        self.waits: list[float] = []

    def wait(self, timeout: float | None = None) -> bool:
        self.waits.append(timeout or 0.0)
        return self.is_set()


class FakeServer:
    """Stands in for connect() and the login exchange, one scripted outcome per attempt."""

    def __init__(self, client: EmpireClient, attempts: list[Attempt]) -> None:
        self.client = client
        self.attempts = attempts
        self.connects = 0
        self.logins = 0

    def connect(self, timeout: float = 10.0) -> None:
        self.connects += 1
        new_session(self.client)

    def login_sequence(self, _started: float, _recaptcha: object) -> None:
        self.logins += 1
        if not self.client.connection.connected:
            raise ConnectionClosedError("closed")
        attempt = self.attempts.pop(0)
        if isinstance(attempt, Exception):
            raise attempt
        if isinstance(attempt, float):
            self.client._session._raise_login_refusal(
                xt_packet("lli", {"CD": attempt}, error_code=GGEError.LOGIN_COOLDOWN_ACTIVE)
            )
        arrive_packet(self.client, "gbd", GBD)
        self.client.is_logged_in = True
        arrive_packet(self.client, "gam", {"M": []})
        for listed in attempt:
            list_movement(self.client, listed)


@pytest.fixture
def client() -> Iterator[EmpireClient]:
    client = EmpireClient(username="user", password="pass", keep_session=True)
    yield client
    client.close()


def serve(client: EmpireClient, monkeypatch: pytest.MonkeyPatch, *attempts: Attempt) -> FakeServer:
    server = FakeServer(client, list(attempts))
    monkeypatch.setattr(client.connection, "connect", server.connect)
    monkeypatch.setattr(client._session, "_login_sequence", server.login_sequence)
    return server


def logged_in(client: EmpireClient, *gams: Listed) -> None:
    """A live, logged-in session that listed ``gams``."""
    new_session(client)
    arrive_packet(client, "gbd", GBD)
    for listed in gams:
        list_movement(client, listed)
    client.is_logged_in = True


def relogin_done(client: EmpireClient) -> Callable[[], bool]:
    return lambda: client._session._relogin_thread is not None and not client._session._relogin_thread.is_alive()


@pytest.fixture
def waits(client: EmpireClient) -> list[float]:
    closed = RecordingEvent()
    client._session._closed = closed
    return closed.waits


class TestRestore:
    def test_a_drop_is_followed_by_a_backoff_and_a_restored_session(self, client, monkeypatch, waits):
        server = serve(client, monkeypatch, NetworkError("down"), EmpireTimeoutError("slow"), [])
        restored: list[bool] = []
        disconnects: list[bool] = []
        client.on_session_restored(lambda: restored.append(client.is_logged_in))
        client.on_disconnect(lambda: disconnects.append(client.is_logged_in))
        logged_in(client)

        drop(client)

        assert wait_for(lambda: restored == [True])
        first = session_module.RELOGIN_FIRST_DELAY
        assert waits == [first, 2 * first, 4 * first]
        assert server.logins == 3
        assert disconnects == [False]
        assert client.state.local_player is not None and client.state.local_player.name == "me"

    def test_the_backoff_stops_growing_at_its_cap(self, client, monkeypatch, waits):
        monkeypatch.setattr(session_module, "RELOGIN_MAX_DELAY", 12.0)
        serve(client, monkeypatch, *[NetworkError("down")] * 4, [])
        logged_in(client)

        drop(client)

        assert wait_for(relogin_done(client))
        assert waits == [5.0, 10.0, 12.0, 12.0, 12.0]

    def test_a_refusal_waiting_does_not_cure_ends_the_attempts(self, client, monkeypatch, waits):
        banned = AccountBannedError(None)
        server = serve(client, monkeypatch, banned, [])
        restored: list[bool] = []
        lost: list[Exception] = []
        client.on_session_restored(lambda: restored.append(True))
        client.on_session_lost(lost.append)
        logged_in(client)

        drop(client)

        assert wait_for(lambda: lost == [banned])
        assert wait_for(relogin_done(client))
        assert server.logins == 1
        assert not client.is_logged_in
        assert not client.connection.connected
        assert restored == []

    def test_a_removed_lost_callback_no_longer_fires(self, client, monkeypatch, waits):
        serve(client, monkeypatch, AccountBannedError(None))
        lost: list[Exception] = []
        client.on_session_lost(lost.append)
        client.on_session_lost(lost.append)
        client.on_session_lost.remove(lost.append)
        client.on_session_lost.remove(lost.append)
        logged_in(client)

        drop(client)

        assert wait_for(relogin_done(client))
        time.sleep(0.05)
        assert lost == []

    def test_a_drop_before_the_movement_list_is_retried_by_the_same_relogin(self, client, monkeypatch, waits):
        server = serve(client, monkeypatch, [])
        attempts: list[threading.Thread] = []
        restored: list[bool] = []
        client.on_session_restored(lambda: restored.append(True))
        login_sequence = server.login_sequence

        def dropping_at_first(started: float, recaptcha: object) -> None:
            attempts.append(threading.current_thread())
            if len(attempts) > 1:
                login_sequence(started, recaptcha)
                return
            client.is_logged_in = True
            drop(client)

        monkeypatch.setattr(client._session, "_login_sequence", dropping_at_first)
        logged_in(client)

        drop(client)

        assert wait_for(lambda: restored == [True])
        assert attempts == [client._session._relogin_thread] * 2
        assert waits == [5.0, 10.0]

    def test_a_drop_during_a_login_starts_nothing(self, client, monkeypatch):
        server = serve(client, monkeypatch, [])
        new_session(client)

        drop(client)

        assert client._session._relogin_thread is None
        assert server.connects == 0

    def test_off_by_default(self, monkeypatch):
        client = EmpireClient(username="user", password="pass")
        server = serve(client, monkeypatch, [])
        logged_in(client)

        drop(client)

        assert client._session._relogin_thread is None
        assert server.connects == 0
        client.close()

    def test_a_login_of_your_own_that_came_first_is_left_alone(self, client, monkeypatch, waits):
        server = serve(client, monkeypatch, [])
        restored: list[bool] = []
        client.on_session_restored(lambda: restored.append(True))
        logged_in(client)
        monkeypatch.setattr(RecordingEvent, "wait", lambda self, timeout=None: bool(new_session(client)) and False)

        drop(client)

        assert wait_for(relogin_done(client))
        assert server.connects == 0
        assert restored == []

    def test_a_removed_restored_callback_no_longer_fires(self, client, monkeypatch, waits):
        serve(client, monkeypatch, [], [])
        calls: list[str] = []

        def callback() -> None:
            calls.append("restored")

        client.on_session_restored(callback)
        client.on_session_restored(callback)
        logged_in(client)
        drop(client)
        assert wait_for(lambda: calls == ["restored"])
        client.on_session_restored.remove(callback)
        client.on_session_restored.remove(callback)
        drop(client)
        assert wait_for(relogin_done(client))
        time.sleep(0.05)

        assert calls == ["restored"]


class TestCooldown:
    def test_a_refusal_is_retried_after_exactly_the_seconds_it_named(self, client, monkeypatch, waits):
        # A kick live: refused with a 55 s cooldown, waited out to the second, restored.
        serve(client, monkeypatch, 55.0, [])
        restored: list[bool] = []
        client.on_session_restored(lambda: restored.append(True))
        logged_in(client)

        drop(client)

        assert wait_for(lambda: restored == [True])
        assert waits[0] == session_module.RELOGIN_FIRST_DELAY
        assert waits[1] == pytest.approx(55.0, abs=0.05)
        assert len(waits) == 2

    def test_a_refusal_shorter_than_the_delay_waits_the_delay(self, client, monkeypatch, waits):
        serve(client, monkeypatch, 4.7, [])
        logged_in(client)

        drop(client)

        assert wait_for(relogin_done(client))
        assert waits == [5.0, 10.0]

    def test_refusals_without_seconds_back_off_as_failures_do(self, client, monkeypatch, waits):
        serve(client, monkeypatch, *[0.0] * 6, [])
        logged_in(client)

        drop(client)

        assert wait_for(relogin_done(client))
        assert waits == [5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 300.0]

    def test_a_cooldown_still_running_delays_the_first_attempt(self, client, monkeypatch, waits):
        serve(client, monkeypatch, [])
        client._session._login_cooldown = (60.0, time.monotonic())
        logged_in(client)

        drop(client)

        assert wait_for(relogin_done(client))
        assert waits[0] == pytest.approx(60.0, abs=0.05)

    def test_the_remaining_cooldown_counts_down_from_the_last_refusal(self, client, monkeypatch):
        now = [100.0]
        monkeypatch.setattr(session_module.time, "monotonic", lambda: now[0])
        assert client.remaining_login_cooldown() == 0.0

        with pytest.raises(LoginCooldownError) as refused:
            client._session._raise_login_refusal(
                xt_packet("lli", {"CD": 30.5}, error_code=GGEError.LOGIN_COOLDOWN_ACTIVE)
            )
        now[0] = 110.0

        assert refused.value.cooldown == 30
        assert client.remaining_login_cooldown() == 20.5
        now[0] = 200.0
        assert client.remaining_login_cooldown() == 0.0


class TestClose:
    def test_close_during_the_backoff_ends_it_at_once(self, client, monkeypatch):
        monkeypatch.setattr(session_module, "RELOGIN_FIRST_DELAY", 60.0)
        server = serve(client, monkeypatch, [])
        logged_in(client)
        drop(client)
        relogin = client._session._relogin_thread
        assert relogin is not None and relogin.is_alive()

        started = time.monotonic()
        client.close()

        assert time.monotonic() - started < 2
        assert not relogin.is_alive()
        assert server.connects == 0

    def test_close_never_starts_a_relogin(self, client, monkeypatch):
        server = serve(client, monkeypatch, [])
        logged_in(client)

        client.close()

        assert client._session._relogin_thread is None
        assert server.connects == 0

    def test_a_drop_reported_after_close_started_starts_nothing(self, client, monkeypatch):
        server = serve(client, monkeypatch, [])
        logged_in(client)
        client._session._closed.set()

        client._session.dropped(client.connection.generation)
        client._session.after_drop(client.connection.generation)

        assert client._session._relogin_thread is None
        assert server.connects == 0

    def test_a_close_while_the_relogin_connects_ends_the_new_session(self, client, monkeypatch, waits):
        server = serve(client, monkeypatch, [])
        connecting = threading.Event()
        proceed = threading.Event()
        connect = server.connect

        def slow_connect(timeout: float = 10.0) -> None:
            connecting.set()
            proceed.wait(2)
            connect(timeout)

        monkeypatch.setattr(client.connection, "connect", slow_connect)
        logged_in(client)
        drop(client)
        assert connecting.wait(2)

        closer = threading.Thread(target=client.close)
        closer.start()
        proceed.set()
        closer.join(2)

        assert not closer.is_alive()
        assert not client._session._relogin_thread.is_alive()
        assert not client.connection.connected
        assert not client.is_logged_in

    def test_close_from_a_disconnect_callback_while_the_relogin_fails_returns_at_once(
        self, client, monkeypatch, waits, caplog
    ):
        logging_in = threading.Event()

        def login_sequence(_started: float, _recaptcha: object) -> None:
            logging_in.set()
            client.connection.request("<verChk/>", "apiOK", timeout=30)

        monkeypatch.setattr(client.connection, "connect", lambda timeout=10.0: new_session(client))
        monkeypatch.setattr(client._session, "_login_sequence", login_sequence)
        logged_in(client)
        drop(client)
        assert logging_in.wait(2)
        took: list[float] = []

        def close_now() -> None:
            started = time.monotonic()
            client.close()
            took.append(time.monotonic() - started)

        # The failing re-login gets the time to end its session before the close.
        client.on_disconnect(lambda: time.sleep(0.3))
        client.on_disconnect(close_now)
        monkeypatch.setattr(client.connection, "_recv_thread", threading.current_thread())
        drop(client)

        assert took and took[0] < 1
        assert not client._session._relogin_thread.is_alive()
        assert "still alive" not in caplog.text

    def test_a_close_before_the_relogin_waits_for_its_movement_list_leaves_no_waiter(self, client, monkeypatch, waits):
        serve(client, monkeypatch, [])
        create_waiter = client.connection.create_waiter
        closers: list[threading.Thread] = []

        def close_first(command: str, accepts=None):
            if command == "gam" and threading.current_thread() is client._session._relogin_thread:
                closers.append(threading.Thread(target=client.close))
                closers[0].start()
                assert wait_for(lambda: client.connection.ws is None)
            return create_waiter(command, accepts)

        monkeypatch.setattr(client.connection, "create_waiter", close_first)
        logged_in(client)

        drop(client)

        assert wait_for(lambda: bool(closers))
        closers[0].join(2)
        assert not closers[0].is_alive()
        assert "gam" not in client.connection._waiters

    def test_login_after_close_lets_the_next_drop_relogin(self, client, monkeypatch, waits):
        server = serve(client, monkeypatch, [], [])
        logged_in(client)
        client.close()

        client.login()
        drop(client)

        assert wait_for(relogin_done(client))
        assert server.logins == 2
        assert client.is_logged_in


class TestLoginOfYourOwn:
    def test_a_login_while_the_relogin_logs_in_ends_it_first(self, client, monkeypatch, waits):
        server = serve(client, monkeypatch, [], [])
        relogin_logging_in = threading.Event()
        inside: list[int] = [0]
        most_inside: list[int] = [0]
        events: list[object] = []
        client.on_session_restored(lambda: events.append("restored"))
        client.on_session_lost(events.append)
        login_sequence = server.login_sequence

        def one_at_a_time(started: float, recaptcha: object) -> None:
            inside[0] += 1
            most_inside[0] = max(most_inside[0], inside[0])
            try:
                if threading.current_thread() is client._session._relogin_thread:
                    relogin_logging_in.set()
                    assert wait_for(lambda: not client.connection.connected)
                    raise ConnectionClosedError("closed by the login")
                login_sequence(started, recaptcha)
            finally:
                inside[0] -= 1

        monkeypatch.setattr(client._session, "_login_sequence", one_at_a_time)
        logged_in(client)
        drop(client)
        assert relogin_logging_in.wait(2)

        client.login()

        assert most_inside == [1]
        assert not client._session._relogin_thread.is_alive()
        assert client.is_logged_in
        assert server.logins == 1
        time.sleep(0.05)
        assert events == []


class TestAttacksAcrossARelogin:
    def test_announced_attacks_are_not_announced_again_and_new_ones_are(self, client, monkeypatch, waits):
        serve(client, monkeypatch, [100, 101])
        events: list[object] = []
        client.state.on_incoming_attack(lambda mov: events.append(mov.movement_id))
        client.on_session_restored(lambda: events.append("restored"))
        logged_in(client, 100)
        assert wait_for(lambda: events == [100])

        drop(client)

        assert wait_for(lambda: events == [100, 101, "restored"])
        assert sorted(m.movement_id for m in client.state.get_all_movements()) == [100, 101]

    def test_an_attack_gone_while_logged_out_is_not_announced_and_a_new_one_is(self, client, monkeypatch, waits):
        serve(client, monkeypatch, [102])
        events: list[object] = []
        client.state.on_incoming_attack(lambda mov: events.append(mov.movement_id))
        client.on_session_restored(lambda: events.append("restored"))
        logged_in(client, 100)
        assert wait_for(lambda: events == [100])

        drop(client)

        assert wait_for(lambda: events == [100, 102, "restored"])
        assert [m.movement_id for m in client.state.get_all_movements()] == [102]

    def test_attacks_and_occupations_announced_before_the_drop_are_not_announced_again(
        self, client, monkeypatch, waits
    ):
        serve(client, monkeypatch, [100, (400, OCCUPATION), 101, (401, OCCUPATION)])
        events: list[object] = []
        client.state.on_incoming_attack(lambda mov: events.append(("attack", mov.movement_id)))
        client.state.on_occupation_started(lambda mov: events.append(("occupation", mov.movement_id)))
        client.on_session_restored(lambda: events.append("restored"))
        logged_in(client, 100, (400, OCCUPATION))
        assert wait_for(lambda: events == [("attack", 100), ("occupation", 400)])

        drop(client)

        assert wait_for(lambda: len(events) == 5)
        assert events[2:] == [("attack", 101), ("occupation", 401), "restored"]
        assert [m.movement_id for m in client.state.get_announced_attacks()] == [100, 101]
        assert [m.movement_id for m in client.state.get_occupations()] == [400, 401]

    def test_an_explicit_reannounce_still_fires_after_the_relogin(self, client, monkeypatch, waits):
        serve(client, monkeypatch, [100, (400, OCCUPATION)])
        events: list[object] = []
        client.state.on_incoming_attack(lambda mov: events.append(("attack", mov.movement_id)))
        client.state.on_occupation_started(lambda mov: events.append(("occupation", mov.movement_id)))
        client.on_session_restored(lambda: events.append("restored"))
        logged_in(client, 100, (400, OCCUPATION))
        drop(client)
        assert wait_for(lambda: events == [("attack", 100), ("occupation", 400), "restored"])

        assert client.state.reannounce(100)
        assert client.state.reannounce(400)

        assert wait_for(lambda: events[3:] == [("attack", 100), ("occupation", 400)])


class TestStream:
    def test_a_stream_carries_on_across_the_relogin(self, client, monkeypatch, waits):
        serve(client, monkeypatch, [101])
        logged_in(client, 100)

        async def scenario():
            async with client.listen(
                client.on_disconnect, client.on_session_restored, client.state.on_incoming_attack
            ) as events:
                await asyncio.to_thread(drop, client)
                return [await asyncio.wait_for(events.__anext__(), 2) for _ in range(3)]

        got = asyncio.run(scenario())

        assert [event.name for event in got] == ["disconnect", "incoming_attack", "session_restored"]
        assert got[1].args[0].movement_id == 101

    def test_a_relogin_that_gives_up_streams_session_lost(self, client, monkeypatch, waits):
        banned = AccountBannedError(None)
        serve(client, monkeypatch, banned)
        logged_in(client)

        async def scenario():
            async with client.listen(names={"disconnect", "session_lost"}) as events:
                await asyncio.to_thread(drop, client)
                return [await asyncio.wait_for(events.__anext__(), 2) for _ in range(2)]

        got = asyncio.run(scenario())

        assert [(event.name, event.args) for event in got] == [("disconnect", ()), ("session_lost", (banned,))]
