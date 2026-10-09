"""
A client's session: the login the game client runs, and the keep_session re-login after a drop.

:class:`~empire_core.client.client.EmpireClient` owns one and delegates
``login``, ``close`` and ``remaining_login_cooldown`` to it.
"""

from __future__ import annotations

import logging
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, NoReturn

from empire_core.config import LOGIN_DEFAULTS
from empire_core.enums import GGEError
from empire_core.exceptions import (
    AccountBannedError,
    ClientVersionError,
    ConnectionClosedError,
    EmpireTimeoutError,
    LoginCooldownError,
    LoginError,
    NetworkError,
    VersionCheckStatus,
    WrongServerError,
)
from empire_core.protocol.auth import LoginRequest, LoginResponse, build_version_check
from empire_core.protocol.base import NO_ROOM, read_or_none
from empire_core.protocol.js import js_number_or_none
from empire_core.protocol.packet import Packet

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


LOBBY_ROOM_NAME = "Lobby"

# Failures a later login attempt may not meet; any other ends the attempts.
RETRIED_LOGIN_ERRORS = (LoginCooldownError, NetworkError, EmpireTimeoutError)


def _joined_room_id(join_ok: Packet) -> int:
    """
    The room id in a ``joinOK``'s ``r`` attribute, read with ``Number()``.

    Where the client would get NaN, this reads -1 (no room).

    Client: ``BasicSmartfoxClient.handleSystemMessage`` (dll line 7232)
    """
    body = join_ok.payload.find("body") if isinstance(join_ok.payload, ET.Element) else None
    if body is None:
        return NO_ROOM
    number = js_number_or_none(body.get("r", ""))
    return NO_ROOM if number is None else int(number)


def _room_entry(packet: Packet) -> tuple[int, str] | None:
    """
    The room id and name one ``rlu`` message lists, or None when it has no name.

    ``%xt%rlu%-1%{id}%{a}%{b}%{flags}%{name}%``: the id lands in the status
    field and the name is the fourth field after it.

    Client: ``BasicSmartfoxClient.setRoomList`` (dll line 7155)
    """
    raw = packet.payload.get("raw") if isinstance(packet.payload, dict) else None
    fields = raw.split("%") if isinstance(raw, str) else []
    return (packet.error_code, fields[3]) if len(fields) > 3 else None


def _elapsed_ms(start: float, end: float | None = None) -> int:
    """Whole milliseconds between two ``time.monotonic()`` readings, the second defaulting to now."""
    return int(((time.monotonic() if end is None else end) - start) * 1000)


def _first_field(packet: Packet) -> str | None:
    """The first field after the status of a reply that is not JSON, or None when it has none."""
    raw = packet.payload.get("raw") if isinstance(packet.payload, dict) else None
    first = raw.split("%")[0] if isinstance(raw, str) else ""
    return first or None


class Session:
    """Logs its client in, ends the session, and with ``keep_session`` logs in again after a drop."""

    def __init__(self, client: EmpireClient) -> None:
        self._client = client
        # Set by close() and cleared by login(): no re-login may start or go on while set.
        self._closed = threading.Event()
        # Counts login() calls: a login(retry=True) stops once a newer login() started.
        self._logins = 0
        # Held while a login connects, while close() or login() marks the client
        # closed, and while a re-login starts or stops keeping the session.
        self._session_lock = threading.RLock()
        self._relogin_thread: threading.Thread | None = None
        # Whether _relogin_thread still keeps the session: a drop then starts no other.
        self._relogin_running = False
        # The generation of the last session that dropped while logged in.
        self._dropped_logged_in: int | None = None
        # The seconds the last cooldown refusal named, and when it came (time.monotonic()).
        self._login_cooldown: tuple[float, float] | None = None

    @property
    def restoring(self) -> bool:
        """See :attr:`EmpireClient.is_restoring_session`."""
        return self._relogin_running

    def login(self, recaptcha_token: str | Callable[[], str] | None, retry: bool) -> None:
        """See :meth:`EmpireClient.login`."""
        client = self._client
        if not client.username or not (client.password or client.login_token):
            raise LoginError("Username and a password or login token are required")

        logger.debug(f"Logging in as {client.username}...")

        self._stop_relogin()
        with self._session_lock:
            self._logins += 1
            login = self._logins
            self._closed.clear()
        waits = self._waits()
        attempt = 0
        failure: Exception | None = None
        while True:
            attempt += 1
            try:
                self._login_attempt(login, recaptcha_token)
                return
            except Exception as e:
                # close() or a newer login() owns the connection now.
                if self._ended(login):
                    if failure is not None:
                        raise failure from e
                    raise
                # The documented cleanup call (close()) never runs on the raising
                # path, so without this a failed login leaves an open socket plus
                # a receive and a keepalive thread pinging an unauthenticated
                # session forever.
                self._end_quietly()
                if not (retry and isinstance(e, RETRIED_LOGIN_ERRORS)):
                    self._client.state.shutdown()
                    raise
                with self._session_lock:
                    if self._ended(login):
                        raise
                    wait = next(waits)
                    self._retrying("login", attempt, wait, e)
                failure = e
                self._closed.wait(wait)
                if self._ended(login):
                    raise

    def _ended(self, login: int) -> bool:
        """Whether :meth:`close` or a newer :meth:`login` ended login number ``login``."""
        return self._closed.is_set() or login != self._logins

    def _login_attempt(self, login: int, recaptcha_token: str | Callable[[], str] | None) -> None:
        """Connect unless connected, and log in; ``ConnectionClosedError`` when the login ended before the connect."""
        client = self._client
        # The client times the connection from before it opens the socket.
        started = time.monotonic()
        with self._session_lock:
            if self._ended(login):
                raise ConnectionClosedError("Closed before the login")
            if not client.connection.connected:
                client.connection.connect(timeout=client.config.connection_timeout)
        self._login_sequence(started, recaptcha_token)

    def close(self) -> None:
        """See :meth:`EmpireClient.close`."""
        self._stop_relogin()
        self._end()

    def remaining_login_cooldown(self) -> float:
        """See :meth:`EmpireClient.remaining_login_cooldown`."""
        cooldown = self._login_cooldown
        if cooldown is None:
            return 0.0
        seconds, refused_at = cooldown
        return max(0.0, seconds - (time.monotonic() - refused_at))

    def dropped(self, generation: int) -> None:
        """The connection's ``on_disconnect``: forget the dropped session ``generation``, unless a newer one started.

        State data is reset, as the game client resets it, so nothing from
        the lost session is reported after it. The next login's gbd rebuilds
        the player and castles, and the gam the server pushes after it the movements.
        Registered callbacks and the callback executor stay, so they keep
        working after a re-login. With ``keep_session``, a session that
        was logged in is logged in again by :meth:`after_drop`.
        """
        client = self._client
        logged_in = client.is_logged_in

        def forget() -> None:
            self._forget()
            client.messages._reset()
            client.rewards._reset()

        if not client.connection.run_if_current(generation, forget):
            logger.debug(f"Client {client.username}: drop of an earlier session reported late, ignored")
            return
        cause = client.connection.close_error
        reason = f" ({str(cause) or type(cause).__name__})" if cause is not None else ""
        logger.warning(f"Client {client.username} disconnected unexpectedly{reason}")
        self._dropped_logged_in = generation if logged_in else None

    def after_drop(self, generation: int) -> None:
        """The connection's ``after_disconnect``: start the re-login once the disconnect callbacks have run.

        Their events then come before the re-login's own.

        None starts while one still keeps the session: that one logs in again itself.
        """
        client = self._client
        with self._session_lock:
            if (
                not client.keep_session
                or self._dropped_logged_in != generation
                or generation != client.connection.generation
                or self._closed.is_set()
                or self._relogin_running
            ):
                return
            self._relogin_running = True
            self._relogin_thread = threading.Thread(
                target=self._restore, name=f"EmpireCore-Relogin-{client.username}", daemon=True
            )
            self._relogin_thread.start()

    def _login_sequence(self, started: float, recaptcha_token: str | Callable[[], str] | None) -> None:
        """Run the handshake/auth exchange on an already-connected socket."""
        client = self._client
        config = client.config
        connection = client.connection
        ver_packet = f"<msg t='sys'><body action='verChk' r='0'><ver v='{config.game_version}' /></body></msg>"
        try:
            connection.request(ver_packet, "apiOK", timeout=config.request_timeout)
        except EmpireTimeoutError as e:
            raise EmpireTimeoutError("API version check (verChk) timed out") from e
        connection_time = _elapsed_ms(started)

        login_packet = (
            f"<msg t='sys'><body action='login' r='0'>"
            f"<login z='{config.default_zone}'>"
            f"<nick><![CDATA[]]></nick>"
            f"<pword><![CDATA[{config.build_number}%{LOGIN_DEFAULTS['LANG']}%{LOGIN_DEFAULTS['DID']}]]></pword>"
            f"</login></body></msg>"
        )
        rooms: dict[int, str] = {}

        def on_room(packet: Packet) -> None:
            entry = _room_entry(packet)
            if entry is not None:
                rooms[entry[0]] = entry[1]

        connection.subscribe("rlu", on_room)
        try:
            try:
                on_room(connection.request(login_packet, "rlu", timeout=config.login_timeout))
            except EmpireTimeoutError as e:
                raise EmpireTimeoutError("Zone login timed out") from e

            join_packet = "<msg t='sys'><body action='autoJoin' r='-1'></body></msg>"
            try:
                join_ok = connection.request(join_packet, "joinOK", timeout=config.request_timeout)
            except EmpireTimeoutError as e:
                raise EmpireTimeoutError("Room join (joinOK) timed out") from e
        finally:
            connection.unsubscribe("rlu", on_room)

        room_id = _joined_room_id(join_ok)
        connection.room_id = room_id
        # The client sends roundTrip and vck only once it has joined the lobby (dll line 7163, 33011).
        if rooms.get(room_id) != LOBBY_ROOM_NAME:
            raise LoginError(f"Joined room {room_id} ({rooms.get(room_id, 'not in the room list')}) is not the lobby")

        round_trip_time = self._version_check()

        request = LoginRequest.create(
            client.username or "",
            client.password,
            **LOGIN_DEFAULTS,
            CONM=connection_time,
            RTM=round_trip_time,
            LT=None if client.password else client.login_token,
            RCT=recaptcha_token() if callable(recaptcha_token) else recaptcha_token,
        )
        xt_packet = client.frame(request)

        # Register the gbd waiter up front: it arrives right after a
        # successful lli and would otherwise race the lli handling below.
        gbd_waiter = connection.create_waiter("gbd")
        try:
            try:
                lli_response = connection.request(xt_packet, "lli", timeout=config.login_timeout)
            except EmpireTimeoutError as e:
                raise EmpireTimeoutError("XT login timed out") from e

            if lli_response.error_code != 0:
                self._raise_login_refusal(lli_response)

            # Wait for gbd (Get Big Data) which contains player info, castles, etc.
            try:
                connection.wait_for_result("gbd", gbd_waiter, timeout=config.request_timeout)
            except EmpireTimeoutError:
                logger.warning(f"gbd packet not received for {client.username}, player state may be incomplete")

            logger.debug(f"Logged in as {client.username}")
            self._login_cooldown = None
            client.is_logged_in = True
        finally:
            connection.cancel_waiter("gbd", gbd_waiter)

    def _version_check(self) -> int:
        """
        Send ``roundTrip`` and ``vck`` back to back, as the client does on joining the lobby.

        Returns the round trip in milliseconds, or 0 when its answer has not
        come back by the time ``vck`` is answered: the client sends whatever
        it has measured when it logs in.

        Client: ``BasicSmartfoxClient.onJoinRoom`` (dll line 7163), ``BasicJoinedRoomCommand`` (dll line 33011),
        ``CastleVCKCommand.executeCommand`` (bundle line 120444)
        """
        client = self._client
        connection = client.connection
        answered: list[float] = []

        def on_round_trip(_packet: Packet) -> None:
            answered.append(time.monotonic())

        room_id = connection.room_id
        connection.subscribe("roundTripRes", on_round_trip)
        try:
            sent = time.monotonic()
            connection.send(f"<msg t='sys'><body action='roundTrip' r='{room_id}'></body></msg>")
            vck_packet = build_version_check(
                client.config.default_zone, client.config.build_number, client.session_id, room_id
            )
            try:
                vck = connection.request(vck_packet, "vck", timeout=client.config.request_timeout)
            except EmpireTimeoutError as e:
                raise EmpireTimeoutError("Version check (vck) timed out") from e
        finally:
            connection.unsubscribe("roundTripRes", on_round_trip)

        if vck.error_code in tuple(VersionCheckStatus):
            raise ClientVersionError(VersionCheckStatus(vck.error_code), _first_field(vck))
        if vck.error_code != 0:
            raise LoginError(f"Version check failed with code {vck.error_code}")
        return _elapsed_ms(sent, answered[0]) if answered else 0

    def _raise_login_refusal(self, lli: Packet) -> NoReturn:
        """
        Raise the error for a refused ``lli``.

        Client: ``LLICommand.executeCommand`` (bundle line 120651)
        """
        code = lli.error_code
        details = LoginResponse()
        if isinstance(lli.payload, dict):
            details = read_or_none(LoginResponse.model_validate, lli.payload) or details
        match code:
            case GGEError.LOGIN_COOLDOWN_ACTIVE:
                self._login_cooldown = (float(details.remaining_cooldown_seconds or 0), time.monotonic())
                raise LoginCooldownError(int(details.remaining_cooldown_seconds or 0))
            case GGEError.IS_BANNED:
                raise AccountBannedError(details.remaining_ban_seconds, details.account_deleted)
            case GGEError.EXISTING_MAPPING_WRONG_SERVER:
                raise WrongServerError(details.instance_id)
            case GGEError.INVALID_LOGIN_TOKEN:
                # The client forgets a token the server refused.
                self._client.login_token = None
                raise LoginError("The login token was refused", code)
            case _:
                raise LoginError("Auth failed", code)

    def _waits(self) -> Iterator[float]:
        """The waits before each next login attempt: the configured first delay, doubled after each failure up to
        the configured cap, or the login cooldown the server named if that is longer.

        Library policy, except the cooldown: the client logs in again only when the player clicks its
        reconnect dialog (``CastleConnectionLostCommand.execute``, ``onReconnect``, bundle lines 120253, 120256),
        and shows a refused login's cooldown in a timer dialog (``LLICommand.executeCommand``, bundle line 120673).
        """
        config = self._client.config
        delay = min(config.relogin_first_delay, config.relogin_max_delay)
        while True:
            yield max(delay, self.remaining_login_cooldown())
            delay = min(delay * 2, config.relogin_max_delay)

    def _retrying(self, kind: str, attempt: int, wait: float, error: Exception) -> None:
        """Report a failed ``kind`` attempt ("login" or "re-login") that is tried again in ``wait`` seconds."""
        client = self._client
        logger.warning(f"Client {client.username}: {kind} attempt {attempt} failed ({error}); next in {wait:.0f}s")
        client.state._fire(client.on_session_retry, attempt, wait, error)

    def _restore(self) -> None:
        """Log in again until a login holds, waiting between attempts; :meth:`close` and :meth:`login` end it.

        Stops without a login when another one already holds the connection.
        """
        client = self._client
        waits = self._waits()
        wait = next(waits)
        attempt = 0
        lost: Exception | None = None
        try:
            while not self._closed.wait(wait):
                attempt += 1
                try:
                    restored = self._relogin()
                except RETRIED_LOGIN_ERRORS as e:
                    if self._closed.is_set():
                        return
                    wait = next(waits)
                    self._retrying("re-login", attempt, wait, e)
                    continue
                except Exception as e:
                    if self._closed.is_set():
                        return
                    logger.exception(f"Client {client.username}: re-login stopped; the session is not restored")
                    lost = e
                    break
                if restored:
                    logger.info(f"Client {client.username}: session restored")
                    client.state._fire(client.on_session_restored)
                return
        finally:
            with self._session_lock:
                if self._relogin_thread is threading.current_thread():
                    self._relogin_running = False
        if lost is not None:
            client.state._fire(client.on_session_lost, lost)

    def _relogin(self) -> bool:
        """Log in on a new connection and wait for the movement list the server pushes; say whether it held.

        False when :meth:`close` or :meth:`login` came first or another login
        holds the connection. A failure ends the new session unless it already
        ended, so a :meth:`close` from a disconnect callback has nothing to wait
        for. A session that drops before it held raises ``ConnectionClosedError``,
        retried as any failed attempt.
        """
        client = self._client
        connection = client.connection
        started = time.monotonic()
        with self._session_lock:
            if self._closed.is_set() or connection.connected:
                return False
            connection.connect(timeout=client.config.connection_timeout)
            generation = connection.generation
        # Before the login, as the push follows gbd closely.
        movements = connection.create_waiter("gam")
        try:
            try:
                self._login_sequence(started, None)
            except Exception:
                if connection.generation == generation and connection.connected:
                    self._end_quietly()
                raise
            try:
                connection.wait_for_result("gam", movements, timeout=client.config.request_timeout)
            except EmpireTimeoutError:
                logger.warning(
                    f"Client {client.username}: no movement list after the re-login; movements may be missing"
                )
        finally:
            connection.cancel_waiter("gam", movements)
        with self._session_lock:
            if self._closed.is_set():
                return False
            if connection.generation != generation or not connection.connected:
                raise ConnectionClosedError("The restored session dropped before it held")
            self._relogin_running = False
        return True

    def _stop_relogin(self) -> None:
        """Mark the client closed and wait for a ``keep_session`` re-login still keeping the session to end."""
        with self._session_lock:
            self._closed.set()
            relogin = self._relogin_thread if self._relogin_running else None
        if relogin is not None and relogin is not threading.current_thread():
            # Disconnecting first fails a re-login under way at its next step.
            self._client.connection.disconnect()
            relogin.join()

    def _end_quietly(self) -> None:
        """End the session after a failed login attempt; never masks the failure, and leaves a re-login going.

        The callback thread stays, so the callbacks of the next attempts run on it in order.
        """
        try:
            self._client.connection.disconnect()
            self._forget()
        except Exception:
            logger.exception("Cleanup after failed login raised")

    def _end(self) -> None:
        # Disconnect first: shutting the state executor down while packets can
        # still arrive lets a late callback lazily recreate it, leaking a
        # thread pool nobody owns any more.
        self._client.connection.disconnect()
        self._client.state.shutdown()
        self._forget()

    def _forget(self) -> None:
        """The session is over: the client is logged out and state holds nothing of it."""
        self._client.is_logged_in = False
        self._client.state.reset()
