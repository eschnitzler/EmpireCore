"""
The client: logs in the way the game client does and carries every service.

The connection runs on its own threads, so the client never competes with a
host event loop.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from pathlib import Path
from types import TracebackType
from typing import Any, NoReturn, TypeVar, cast, overload

from pydantic import ValidationError
from typing_extensions import Unpack

from empire_core.alliance.service import AllianceService
from empire_core.army.service import ArmyService
from empire_core.attack.service import AttackService
from empire_core.castle.service import CastleService
from empire_core.client.stream import Args, EventStream, callback_sources
from empire_core.commanders.service import CommandersService, EquipmentService, SkillsService
from empire_core.config import LOGIN_DEFAULTS, EmpireConfig, default_config, generate_session_id
from empire_core.defense.service import DefenseService
from empire_core.events.service import EventsService
from empire_core.exceptions import (
    AccountBannedError,
    ClientVersionError,
    CommandError,
    ConnectionClosedError,
    EmpireError,
    EmpireTimeoutError,
    LoginCooldownError,
    LoginError,
    NetworkError,
    PacketError,
    VersionCheckStatus,
    WrongServerError,
)
from empire_core.gamedata import GameData
from empire_core.map.service import MapService
from empire_core.messages.service import MessagesService
from empire_core.movements.models import GetMovementsRequest
from empire_core.movements.service import MovementsService
from empire_core.network.connection import NON_ERROR_COMMANDS, Connection
from empire_core.player.service import PlayerService
from empire_core.protocol.auth import LoginRequest, LoginResponse, LoginTokenResponse, build_version_check
from empire_core.protocol.base import NO_ROOM, read_or_none
from empire_core.protocol.errors import GGEError
from empire_core.protocol.js import js_number_or_none
from empire_core.protocol.models import BaseRequest, BaseResponse, parse_response
from empire_core.protocol.packet import Packet
from empire_core.ranking.service import RankingService
from empire_core.spy.service import SpyService
from empire_core.state.manager import GameState
from empire_core.utils.callbacks import BoundCallbacks, Callbacks, Registry, Remover

logger = logging.getLogger(__name__)


LOBBY_ROOM_NAME = "Lobby"

# Login data sections the client parses as it parses the push of the same name.
# Client: GBDCommand.exec (bundle line 129381) hands n.sne to parse_SNE and n.ahl to parse_AHL,
# as SNECommand and AHLCommand do.
LOGIN_SECTION_PUSHES = ("sne", "ahl")

# Library policy for keep_session: the client never re-logs in by itself after a drop.
RELOGIN_FIRST_DELAY = 5.0
RELOGIN_MAX_DELAY = 300.0


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


T = TypeVar("T", bound=BaseResponse)


class EmpireClient:
    """
    Empire client for connecting to GGE game servers.

    This client uses blocking I/O with a background receive thread,
    making it safe to use from Discord.py without blocking the event loop
    (run client operations in a thread pool).

    Usage:
        client = EmpireClient(username="user", password="pass")
        client.login()
        movements = client.movements.get_movements()
        client.close()

        # Or, cleaning up automatically:
        with EmpireClient(username="user", password="pass") as client:
            client.login()
            movements = client.movements.get_movements()

    Keeping the session:
        With ``keep_session=True`` (or the attribute set later), a logged-in
        session that drops is logged in again on a thread of its own, on the
        same client, so callbacks and :meth:`listen` streams carry on.
        :meth:`on_session_restored` fires once it is back, and
        :meth:`on_session_lost` when it gives up. :meth:`close` ends it, also
        while it waits between attempts, and a :meth:`login` of your own stops
        it before it logs in.

        The game client does not do this: after a drop
        (``CastleConnectionLostCommand.execute``, bundle line 120253) it
        empties the game and shows a reconnect dialog, and logs in again only
        when the player clicks it (``onReconnect``, bundle line 120256). So
        the delays are library policy: the first attempt comes
        ``RELOGIN_FIRST_DELAY`` (5) seconds after the drop, a failed one is
        retried after twice the last delay, up to ``RELOGIN_MAX_DELAY`` (300)
        seconds. A :class:`~empire_core.exceptions.LoginCooldownError`
        counts as a failed attempt too, and is retried no sooner than the
        seconds the refusal named (see :meth:`remaining_login_cooldown`): after
        the longer of that cooldown and the delay. A refusal that waiting does
        not cure (a ban, the wrong server, the client version, credentials, or
        any other refusal) ends the attempts, logged as an error and reported
        to :meth:`on_session_lost`; the client then stays logged out. A
        re-login sends no reCAPTCHA token.
    """

    alliance: AllianceService
    castle: CastleService
    army: ArmyService
    attack: AttackService
    commanders: CommandersService
    equipment: EquipmentService
    skills: SkillsService
    spy: SpyService
    ranking: RankingService
    map: MapService
    messages: MessagesService
    movements: MovementsService
    defense: DefenseService
    player: PlayerService
    events: EventsService

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        config: EmpireConfig | None = None,
        login_token: str | None = None,
        keep_session: bool = False,
    ):
        self.config = config or default_config
        self.username = username or self.config.username
        self.password = password or self.config.password
        # A persistent login's token: logs in without the password, and is
        # replaced by the one the server pushes (slt) after each login, just after gbd.
        self.login_token = login_token
        # One per client, as the game client makes one per page load.
        self.session_id = generate_session_id()

        self.connection = Connection(self.config.game_url, keepalive_zone=self.config.default_zone)
        self.state = GameState()
        self.game_data: GameData | None = None
        self.is_logged_in = False
        # Log in again by itself after a drop (see the class docstring).
        self.keep_session = keep_session
        # Set by close() and cleared by login(): no re-login may start or go on while set.
        self._closed = threading.Event()
        # Held while a login connects, while close() or login() marks the client
        # closed, and while a re-login starts or stops keeping the session.
        self._session_lock = threading.RLock()
        self._relogin_thread: threading.Thread | None = None
        # Whether _relogin_thread still keeps the session: a drop then starts no other.
        self._relogin_running = False
        # The generation of the last session that dropped while logged in.
        self._dropped_logged_in: int | None = None
        # The client's on_* callbacks: each registered once, removing one not registered is a no-op
        self._registry = Registry(unique=True, missing_ok=True)
        # The seconds the last cooldown refusal named, and when it came (time.monotonic()).
        self._login_cooldown: tuple[float, float] | None = None

        # Command -> handlers mapping for efficient dispatch
        # Only commands with handlers will be parsed.
        # Written from caller threads (services registering handlers) and
        # read by the receive thread, so every access goes through the lock -
        # CPython's per-op atomicity is not a guarantee to build on and does
        # not hold on free-threaded builds.
        self._handlers: dict[str, list[Callable[[BaseResponse], None]]] = {}
        self._handlers_lock = threading.Lock()
        self._streams: set[EventStream] = set()
        self._streams_lock = threading.Lock()

        # Wire up packet handler for state updates
        self.connection.on_packet = self._on_packet
        self.connection.on_disconnect = self._on_disconnect
        self.connection.after_disconnect = self._keep_session_after_drop
        self.connection.add_disconnect_listener(self._fire_disconnect)

        self._attach_services()

    def _attach_services(self) -> None:
        """Build one of each service; they register their packet handlers on the way."""
        self.alliance = AllianceService(self)
        self.castle = CastleService(self)
        self.army = ArmyService(self)
        self.attack = AttackService(self)
        self.commanders = CommandersService(self)
        self.equipment = EquipmentService(self)
        self.skills = SkillsService(self)
        self.spy = SpyService(self)
        self.ranking = RankingService(self)
        self.map = MapService(self)
        self.messages = MessagesService(self)
        self.movements = MovementsService(self)
        self.defense = DefenseService(self)
        self.player = PlayerService(self)
        self.events = EventsService(self)

    def _register_handler(self, command: str, handler: Callable[[BaseResponse], None]) -> None:
        """
        Register a handler for a specific command.

        Called by services to register interest in specific responses.
        Only commands with handlers will be parsed and dispatched.
        """
        with self._handlers_lock:
            if command not in self._handlers:
                self._handlers[command] = []
            self._handlers[command].append(handler)

    def _unregister_handler(self, command: str, handler: Callable[[BaseResponse], None]) -> None:
        """Remove a previously registered handler; unknown handlers are ignored."""
        with self._handlers_lock:
            handlers = self._handlers.get(command)
            if not handlers:
                return
            try:
                handlers.remove(handler)
            except ValueError:
                return
            if not handlers:
                del self._handlers[command]

    def _on_packet(self, packet: Packet) -> None:
        """Handle incoming packets for state updates and service dispatch."""
        cmd = packet.command_id
        # Most payloads are JSON objects, but some server pushes are JSON
        # arrays (e.g. 'sce' special currency updates, which arrive as
        # ``[["PTT", 123]]``). Both have to reach GameState; XML packets
        # (ET.Element) and empty payloads have nothing to apply.
        payload: object = packet.payload
        if not cmd or not isinstance(payload, (dict, list)):
            return

        if cmd == "slt" and packet.error_code == 0 and isinstance(payload, dict):
            self._store_login_token(payload)

        self._update_state(cmd, payload, packet.error_code)
        if cmd == "mvf" and packet.error_code == 0:
            self._request_movements()

        # Client: CastleExtensionResponseCommand.execute (bundle line 110733) hands
        # the status to each command, and the commands parse only on success.
        if packet.error_code != 0 and cmd not in NON_ERROR_COMMANDS:
            return

        if cmd == "gbd" and isinstance(payload, dict):
            for section in LOGIN_SECTION_PUSHES:
                if isinstance(body := payload.get(section), dict):
                    self._dispatch(section, body)
        self._dispatch(cmd, payload)

    def _dispatch(self, cmd: str, payload: dict[str, Any] | list[Any]) -> None:
        """Parse a payload and hand it to the handlers registered for ``cmd``, if any."""
        # Only parse and dispatch if handlers are registered. The snapshot is
        # taken under the lock so a concurrent (un)register can neither be
        # observed half-applied nor mutate the list being iterated below.
        with self._handlers_lock:
            handlers = list(self._handlers.get(cmd, ()))
        if not handlers:
            return

        if not isinstance(payload, dict):
            # Response models are all keyed objects, so an array payload has
            # no model to parse into - GameState is its only consumer.
            logger.debug(f"No response model for array payload of '{cmd}'; state updated only")
            return

        try:
            response = parse_response(cmd, payload)
        except ValidationError:
            logger.exception(f"Could not parse '{cmd}' payload for handler dispatch")
            return

        if response:
            for handler in handlers:
                try:
                    handler(response)
                except Exception:
                    logger.exception(f"Handler error for command '{cmd}'")

    def _request_movements(self) -> None:
        """Ask for the movement list (gam) after an mvf push changes the movement filter settings.

        Runs on the receive thread, so it sends without waiting; the reply reaches
        state like any gam, but no concurrent ``get_movements`` takes it (see
        :meth:`Connection.send_and_drop_reply`). After a login nothing needs
        asking: the server pushes gam by itself shortly after the login data (seen live).

        Client: ``MVFCommand.executeCommand`` (bundle line 129703).
        """
        try:
            self.connection.send_and_drop_reply(
                self.frame(GetMovementsRequest()), "gam", window=self.config.request_timeout
            )
        except EmpireError:
            logger.warning("Could not ask for the movement list after the login data", exc_info=True)

    def _store_login_token(self, payload: dict[str, Any]) -> None:
        """
        Keep the login token the server pushed after a persistent login.

        Client: ``SLTCommand.executeCommand`` (bundle line 120936)
        """
        token = read_or_none(LoginTokenResponse.model_validate, payload)
        if token is not None and token.login_token:
            self.login_token = token.login_token
        else:
            logger.warning(f"slt push without a usable login token (keys: {sorted(payload)})")

    def _update_state(self, cmd: str, payload: dict[str, Any] | list[Any], error_code: int = 0) -> None:
        """Sync state update from packet - delegates to GameState.

        Array payloads are forwarded unchanged; GameState's per-command
        handlers decide which shapes they accept, and which error replies they skip.
        """
        self.state.update_from_packet(cmd, cast(dict[str, Any], payload), error_code)

    def _on_disconnect(self, generation: int) -> None:
        """Handle unexpected connection loss of the session ``generation``; a newer session is left alone.

        State data is reset, as the game client resets it, so nothing from
        the lost session is reported after it. The next login's gbd rebuilds
        the player and castles, and the gam the server pushes after it the movements.
        Registered callbacks and the callback executor stay, so they keep
        working after a re-login. With :attr:`keep_session`, a session that
        was logged in is logged in again on a thread of its own.
        """
        was_logged_in = self.is_logged_in
        if not self.connection.run_if_current(generation, self._forget_session):
            logger.debug(f"Client {self.username}: drop of an earlier session reported late, ignored")
            return
        logger.warning(f"Client {self.username} disconnected unexpectedly")
        self._dropped_logged_in = generation if was_logged_in else None

    def _keep_session_after_drop(self, generation: int) -> None:
        """Start the re-login once the disconnect callbacks have run, so their events come before its own.

        None starts while one still keeps the session: that one logs in again itself.
        """
        with self._session_lock:
            if (
                not self.keep_session
                or self._dropped_logged_in != generation
                or generation != self.connection.generation
                or self._closed.is_set()
                or self._relogin_running
            ):
                return
            self._relogin_running = True
            self._relogin_thread = threading.Thread(
                target=self._restore_session, name=f"EmpireCore-Relogin-{self.username}", daemon=True
            )
            self._relogin_thread.start()

    def _restore_session(self) -> None:
        """Log in again until a login holds, waiting between attempts; :meth:`close` and :meth:`login` end it.

        Stops without a login when another one already holds the connection.
        """
        delay = RELOGIN_FIRST_DELAY
        wait = max(delay, self.remaining_login_cooldown())
        try:
            while not self._closed.wait(wait):
                try:
                    restored = self._relogin()
                except (LoginCooldownError, NetworkError, EmpireTimeoutError) as e:
                    delay = min(delay * 2, RELOGIN_MAX_DELAY)
                    wait = max(delay, self.remaining_login_cooldown())
                    logger.warning(f"Client {self.username}: re-login failed ({e}); next attempt in {wait:.0f}s")
                    continue
                except Exception as e:
                    logger.exception(f"Client {self.username}: re-login stopped; the session is not restored")
                    self._dispatch_session_event(self.on_session_lost, e)
                    return
                if restored:
                    logger.info(f"Client {self.username}: session restored")
                    self._dispatch_session_event(self.on_session_restored)
                return
        finally:
            with self._session_lock:
                if self._relogin_thread is threading.current_thread():
                    self._relogin_running = False

    def _relogin(self) -> bool:
        """Log in on a new connection and wait for the movement list the server pushes; say whether it held.

        False when :meth:`close` or :meth:`login` came first or another login
        holds the connection. A failure ends the new session unless it already
        ended, so a :meth:`close` from a disconnect callback has nothing to wait
        for. A session that drops before it held raises ``ConnectionClosedError``,
        retried as any failed attempt.
        """
        started = time.monotonic()
        with self._session_lock:
            if self._closed.is_set() or self.connection.connected:
                return False
            self.connection.connect(timeout=self.config.connection_timeout)
            generation = self.connection.generation
        # Before the login, as the push follows gbd closely.
        movements = self.connection.create_waiter("gam")
        try:
            try:
                self._login_sequence(started, None)
            except Exception:
                if self.connection.generation == generation and self.connection.connected:
                    self._end_session_quietly()
                raise
            try:
                self.connection.wait_for_result("gam", movements, timeout=self.config.request_timeout)
            except EmpireTimeoutError:
                logger.warning(f"Client {self.username}: no movement list after the re-login; movements may be missing")
        finally:
            self.connection.cancel_waiter("gam", movements)
        with self._session_lock:
            if self._closed.is_set():
                return False
            if self.connection.generation != generation or not self.connection.connected:
                raise ConnectionClosedError("The restored session dropped before it held")
            self._relogin_running = False
        return True

    def _dispatch_session_event(self, callbacks: BoundCallbacks[Any], *args: Any) -> None:
        for callback in callbacks.calls():
            self.state._dispatch_callback(callback, *args)

    def _fire_disconnect(self) -> None:
        """The connection's disconnect listener: the :meth:`on_disconnect` callbacks, on the receive thread."""
        for callback in self.on_disconnect.calls():
            try:
                callback()
            except Exception:
                logger.exception("Error in disconnect callback")

    def _forget_session(self) -> None:
        self.is_logged_in = False
        self.state.reset()
        self.messages._reset()

    on_disconnect = Callbacks[Callable[[], None]]()
    """Register a callback for the session dropping on its own; :meth:`close` does not fire it.

    Runs on the receive thread as it shuts down, after ``is_logged_in`` is
    cleared, and fires once per dropped session. Keep it short and hand a
    re-login to another thread, or leave it to :attr:`keep_session`, which
    starts its own once these callbacks have run. Registering the same
    callback twice is a no-op.
    """
    remove_disconnect_callback = Remover(on_disconnect)
    """Remove a callback added with :meth:`on_disconnect`; unknown callbacks are ignored."""

    @overload
    def listen(
        self, source: Callable[[Callable[[Unpack[Args]], Any]], None], /, *, maxsize: int = 0
    ) -> EventStream[Unpack[Args]]: ...

    @overload
    def listen(
        self,
        *sources: Callable[[Callable[..., Any]], None],
        names: Iterable[str] | None = None,
        maxsize: int = 0,
    ) -> EventStream[Unpack[tuple[Any, ...]]]: ...

    def listen(
        self,
        *sources: Callable[..., None],
        names: Iterable[str] | None = None,
        maxsize: int = 0,
    ) -> EventStream[Unpack[tuple[Any, ...]]]:
        """Stream callback calls to the running event loop: every registration's, or those of ``sources`` and ``names``.

        Call it from a coroutine; the stream delivers on that coroutine's loop. ``sources``
        are the registration methods themselves (``client.state.on_incoming_attack``,
        ``client.alliance.on_chat_message``, ...): any ``on_<name>`` of the client, its state
        or a service that has a ``remove_<name>_callback``. Each event is a
        :class:`~empire_core.client.stream.ClientEvent` named after its registration. A stream
        of one registration types its events' ``args`` as that registration's callback
        parameters: ``client.listen(client.state.on_incoming_attack_updated)`` yields
        ``ClientEvent[Movement, Movement]``. The movement callbacks, which take either
        ``(movement_id)`` or ``(movement_id, movement)``, and streams of several
        registrations yield untyped ``args``.

        ``names`` picks registrations by the event names instead, for subscriptions kept as
        data: ``client.listen(names={"incoming_attack", "chat_message"})``. A name is the
        registration's without ``on_``, as :class:`~empire_core.client.stream.ClientEvent` has
        it, and an unknown one raises ``ValueError`` here, not later. A stream by name has
        untyped ``args``. ``sources`` and ``names`` can be given together; the stream then has
        the registrations of both. Only with neither does it have every registration: an
        empty ``names`` alone picks none.

        The stream listens inside ``async with`` only: entering it subscribes, leaving it
        stops listening, and iterating a stream that was not entered raises ``RuntimeError``.
        Inside the block it outlives sessions, as callbacks do: a dropped session is a
        ``"disconnect"`` event, and after :meth:`close` and a new :meth:`login` the stream
        delivers the new session's events. Only leaving the block, ``stream.close()`` and
        :meth:`close_streams` end it.

        Nothing is dropped while the loop keeps up. A ``maxsize`` above 0 caps the events
        waiting unread: one more stops the stream, which raises
        :class:`~empire_core.exceptions.EventStreamOverflowError` once the consumer reaches it.

        Raises:
            RuntimeError: No event loop is running.
            ValueError: A source is not a callback registration of this client, a name is not
                one's, or ``names`` is a single string.

        Example::

            async with client.listen(client.state.on_incoming_attack) as attacks:
                async for attack in attacks:
                    (movement,) = attack.args
        """
        loop = asyncio.get_running_loop()
        by_name = callback_sources(self)
        known = {source.register: source for source in by_name.values()}
        if unknown := [source for source in sources if source not in known]:
            raise ValueError(f"not callback registrations of this client: {unknown}")
        if isinstance(names, str):
            raise ValueError(f"names takes a collection of names, not the string {names!r}")
        names = None if names is None else tuple(names)
        if unknown_names := sorted(set(names or ()) - set(by_name)):
            raise ValueError(f"no callback registration of this client is named {unknown_names}")
        if not sources and names is None:
            return EventStream(self, list(by_name.values()), loop, maxsize)
        chosen = [known[source] for source in sources] + [by_name[name] for name in names or ()]
        return EventStream(self, list(dict.fromkeys(chosen)), loop, maxsize)

    def close_streams(self) -> None:
        """End every stream of :meth:`listen` still listening, after the events already on their way.

        :meth:`close` leaves streams listening, as it leaves callbacks registered. A client
        handed on to other code, as an :class:`~empire_core.pool.AccountPool` release does,
        calls this so no stream of the previous holder keeps queueing.
        """
        with self._streams_lock:
            streams = list(self._streams)
        for stream in streams:
            stream._finish()

    def _remember_stream(self, stream: EventStream) -> None:
        with self._streams_lock:
            self._streams.add(stream)

    def _forget_stream(self, stream: EventStream) -> None:
        with self._streams_lock:
            self._streams.discard(stream)

    def login(self, recaptcha_token: str | Callable[[], str] | None = None) -> None:
        """
        Log in the way the game client does.

        1. Connect the WebSocket
        2. ``verChk``, answered by ``apiOK``
        3. Zone login with the build number, answered by ``rlu``
        4. ``autoJoin``, answered by ``joinOK`` with the room id
        5. ``roundTrip`` and the version check ``vck``
        6. ``lli``, with the measured connection and round-trip times

        With :attr:`password` set it logs in by password; without one, by the
        :attr:`login_token` an earlier login got. After a login the server
        pushes a fresh token, kept in :attr:`login_token`; the push comes after
        ``gbd``, so it lands shortly after this method returns.

        A :attr:`keep_session` re-login still under way, or waiting between
        attempts, is ended first, so only this login runs.

        Args:
            recaptcha_token: A reCAPTCHA v3 token for the action ``login``, or
                a function returning one, sent as ``RCT``. The game client
                always attaches one; the library cannot make one itself, and
                logins are accepted without it today.

        Raises:
            NetworkError: The WebSocket connection could not be established
            EmpireTimeoutError: A required login step timed out
            ClientVersionError: The version check says ``config.client_version`` is too low or too high
            LoginCooldownError: The server is rate-limiting this account
            AccountBannedError: The account is banned or deleted
            WrongServerError: The account is on another server
            LoginError: Username and password or token missing, the version
                check failed, or the server rejected the login

        Every failure mode is an ``EmpireError`` subclass, so
        ``except EmpireError`` catches all of them.

        On any of these, the connection and its background threads are closed
        before the error propagates, so a failed login leaks nothing.

        Client: ``BasicSmartfoxClient`` (dll line 7130), ``BasicJoinedRoomCommand`` (dll line 33011),
        ``CastleLoginCommand`` (bundle line 131762)
        """
        if not self.username or not (self.password or self.login_token):
            raise LoginError("Username and a password or login token are required")

        logger.debug(f"Logging in as {self.username}...")

        self._stop_relogin()
        self._closed.clear()
        try:
            # The client times the connection from before it opens the socket.
            started = time.monotonic()
            with self._session_lock:
                if not self.connection.connected:
                    self.connection.connect(timeout=self.config.connection_timeout)

            self._login_sequence(started, recaptcha_token)
        except Exception:
            # The documented cleanup call (close()) never runs on the raising
            # path, so without this a failed login leaves an open socket plus
            # a receive and a keepalive thread pinging an unauthenticated
            # session forever.
            self._end_session_quietly()
            raise

    def _login_sequence(self, started: float, recaptcha_token: str | Callable[[], str] | None) -> None:
        """Run the handshake/auth exchange on an already-connected socket."""
        ver_packet = f"<msg t='sys'><body action='verChk' r='0'><ver v='{self.config.game_version}' /></body></msg>"
        try:
            self.connection.request(ver_packet, "apiOK", timeout=self.config.request_timeout)
        except EmpireTimeoutError as e:
            raise EmpireTimeoutError("API version check (verChk) timed out") from e
        connection_time = _elapsed_ms(started)

        login_packet = (
            f"<msg t='sys'><body action='login' r='0'>"
            f"<login z='{self.config.default_zone}'>"
            f"<nick><![CDATA[]]></nick>"
            f"<pword><![CDATA[{self.config.build_number}%{LOGIN_DEFAULTS['LANG']}%{LOGIN_DEFAULTS['DID']}]]></pword>"
            f"</login></body></msg>"
        )
        rooms: dict[int, str] = {}

        def on_room(packet: Packet) -> None:
            entry = _room_entry(packet)
            if entry is not None:
                rooms[entry[0]] = entry[1]

        self.connection.subscribe("rlu", on_room)
        try:
            try:
                on_room(self.connection.request(login_packet, "rlu", timeout=self.config.login_timeout))
            except EmpireTimeoutError as e:
                raise EmpireTimeoutError("Zone login timed out") from e

            join_packet = "<msg t='sys'><body action='autoJoin' r='-1'></body></msg>"
            try:
                join_ok = self.connection.request(join_packet, "joinOK", timeout=self.config.request_timeout)
            except EmpireTimeoutError as e:
                raise EmpireTimeoutError("Room join (joinOK) timed out") from e
        finally:
            self.connection.unsubscribe("rlu", on_room)

        room_id = _joined_room_id(join_ok)
        self.connection.room_id = room_id
        # The client sends roundTrip and vck only once it has joined the lobby (dll line 7163, 33011).
        if rooms.get(room_id) != LOBBY_ROOM_NAME:
            raise LoginError(f"Joined room {room_id} ({rooms.get(room_id, 'not in the room list')}) is not the lobby")

        round_trip_time = self._version_check()

        request = LoginRequest.create(
            self.username or "",
            self.password,
            **LOGIN_DEFAULTS,
            CONM=connection_time,
            RTM=round_trip_time,
            LT=None if self.password else self.login_token,
            RCT=recaptcha_token() if callable(recaptcha_token) else recaptcha_token,
        )
        xt_packet = self.frame(request)

        # Register the gbd waiter up front: it arrives right after a
        # successful lli and would otherwise race the lli handling below.
        gbd_waiter = self.connection.create_waiter("gbd")
        try:
            try:
                lli_response = self.connection.request(xt_packet, "lli", timeout=self.config.login_timeout)
            except EmpireTimeoutError as e:
                raise EmpireTimeoutError("XT login timed out") from e

            if lli_response.error_code != 0:
                self._raise_login_refusal(lli_response)

            # Wait for gbd (Get Big Data) which contains player info, castles, etc.
            try:
                self.connection.wait_for_result("gbd", gbd_waiter, timeout=self.config.request_timeout)
            except EmpireTimeoutError:
                logger.warning(f"gbd packet not received for {self.username}, player state may be incomplete")

            logger.debug(f"Logged in as {self.username}")
            self._login_cooldown = None
            self.is_logged_in = True
        finally:
            self.connection.cancel_waiter("gbd", gbd_waiter)

    def _version_check(self) -> int:
        """
        Send ``roundTrip`` and ``vck`` back to back, as the client does on joining the lobby.

        Returns the round trip in milliseconds, or 0 when its answer has not
        come back by the time ``vck`` is answered: the client sends whatever
        it has measured when it logs in.

        Client: ``BasicSmartfoxClient.onJoinRoom`` (dll line 7163), ``BasicJoinedRoomCommand`` (dll line 33011),
        ``CastleVCKCommand.executeCommand`` (bundle line 120444)
        """
        answered: list[float] = []

        def on_round_trip(_packet: Packet) -> None:
            answered.append(time.monotonic())

        room_id = self.connection.room_id
        self.connection.subscribe("roundTripRes", on_round_trip)
        try:
            sent = time.monotonic()
            self.connection.send(f"<msg t='sys'><body action='roundTrip' r='{room_id}'></body></msg>")
            vck_packet = build_version_check(
                self.config.default_zone, self.config.build_number, self.session_id, room_id
            )
            try:
                vck = self.connection.request(vck_packet, "vck", timeout=self.config.request_timeout)
            except EmpireTimeoutError as e:
                raise EmpireTimeoutError("Version check (vck) timed out") from e
        finally:
            self.connection.unsubscribe("roundTripRes", on_round_trip)

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
                self.login_token = None
                raise LoginError("The login token was refused", code)
            case _:
                raise LoginError("Auth failed", code)

    def remaining_login_cooldown(self) -> float:
        """Seconds until the login cooldown the server last named is over; 0 when there is none.

        Only what the server last said: the ``CD`` of the last refused login of
        this client, less the time since, cleared by a login that holds. The
        server may start a cooldown this client has not been told about yet.

        Client: ``LLICommand.executeCommand`` (bundle line 120673) shows the
        refusal's ``REMAINING_COOLDOWN`` in a timer dialog.
        """
        cooldown = self._login_cooldown
        if cooldown is None:
            return 0.0
        seconds, refused_at = cooldown
        return max(0.0, seconds - (time.monotonic() - refused_at))

    on_session_lost = Callbacks[Callable[[Exception], None]]()
    """Register a callback for a :attr:`keep_session` re-login that gives up.

    ``callback(error)`` fires once, with the refusal that ended the attempts
    (a ban, the wrong server, the client version, credentials, or any other
    refusal waiting does not cure); the client then stays logged out until
    a :meth:`login` of your own. Neither :meth:`close` nor a :meth:`login`
    of your own that stops the re-login fires it; that login raises its own
    failure. Runs on the callback thread (see
    :class:`~empire_core.state.manager.GameState`). Registering the same
    callback twice is a no-op.
    """
    remove_session_lost_callback = Remover(on_session_lost)
    """Remove a callback added with :meth:`on_session_lost`; unknown callbacks are ignored."""

    on_session_restored = Callbacks[Callable[[], None]]()
    """Register a callback for a :attr:`keep_session` re-login that holds.

    Fires once per restored session, after the login data and the movement
    list the server pushes after it have reached state (or that list did
    not come within ``config.request_timeout``), so the events of that
    state come first. Runs on the callback thread (see
    :class:`~empire_core.state.manager.GameState`). A :meth:`login` of
    your own does not fire it. Registering the same callback twice is a no-op.
    """
    remove_session_restored_callback = Remover(on_session_restored)
    """Remove a callback added with :meth:`on_session_restored`; unknown callbacks are ignored."""

    def _end_session_quietly(self) -> None:
        """End the session after a failed login; never masks the failure, and leaves a re-login going."""
        try:
            self._end_session()
        except Exception:
            logger.exception("Cleanup after failed login raised")

    def _end_session(self) -> None:
        self.is_logged_in = False
        # Disconnect first: shutting the state executor down while packets can
        # still arrive lets a late callback lazily recreate it, leaking a
        # thread pool nobody owns any more.
        self.connection.disconnect()
        self.state.shutdown()
        self.state.reset()

    def close(self) -> None:
        """Disconnect from the server and release background resources.

        Safe to call more than once, and safe to call after a failed login.
        Registered callbacks and the streams of :meth:`listen` stay, as on a
        dropped session: they keep working after the next :meth:`login`.

        Ends a :attr:`keep_session` re-login, also one waiting between
        attempts, and returns once it has stopped: no re-login follows a
        close until the next :meth:`login`. The game client's ``logout``
        likewise marks the disconnect as the user's (``userForcedDisconnect``,
        ggs.dll line 7170), and with it set does not log in again by the stored
        token (``VCKLegacyCommand.executeCommand``, bundle line 121066).
        """
        self._stop_relogin()
        self._end_session()

    def _stop_relogin(self) -> None:
        """Mark the client closed and wait for a :attr:`keep_session` re-login still keeping the session to end."""
        with self._session_lock:
            self._closed.set()
            relogin = self._relogin_thread if self._relogin_running else None
        if relogin is not None and relogin is not threading.current_thread():
            # Disconnecting first fails a re-login under way at its next step.
            self.connection.disconnect()
            relogin.join()

    def __enter__(self) -> EmpireClient:
        """Enter a context that closes the client on exit.

        Does not log in - call :meth:`login` inside the block, so its failure
        modes stay visible to the caller.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def load_game_data(self, *, refresh: bool = False, cache_dir: str | Path | None = None) -> GameData:
        """
        Load the static game data (unit and tool stats) and attach it.

        Explicit by design: the items payload is a large download. Kept for the
        process and cached on disk per game version (see :meth:`GameData.load`),
        so this is cheap after the first call.

        Args:
            refresh: Ignore any cached copy and any failure backoff, and re-download
            cache_dir: Where to keep trimmed data (default: XDG cache dir)

        Returns:
            The loaded data, also available as ``client.game_data``

        Raises:
            NetworkError: Nothing is loaded (or refresh is set) and the CDN could not be
                reached, now or less than five minutes ago
        """
        self.game_data = GameData.load(refresh=refresh, cache_dir=cache_dir)
        return self.game_data

    def frame(self, request: BaseRequest) -> str:
        """
        The request as this session sends it: in its zone and the room it joined.

        Client: ``BasicSmartfoxClient.sendMessage`` and ``sendCommand`` (ggs.dll lines 7174 and 7198)
        """
        return request.to_packet(zone=self.config.default_zone, room_id=self.connection.room_id)

    def request_packet(self, request: BaseRequest, response_command: str, timeout: float = 5.0) -> Packet:
        """
        Send a request and return the raw reply packet for ``response_command``.

        For replies whose command id the response registry gives to another
        model (``hgh`` answers both alliance search and highscores), or that a
        caller reads itself. Raises as :meth:`Connection.request` does.
        """
        return self.connection.request(
            self.frame(request), response_command, timeout=timeout, accepts=self._reply_check(request)
        )

    @staticmethod
    def _reply_check(request: BaseRequest) -> Callable[[Packet], bool] | None:
        """The waiter check of a request whose reply names what was asked for (it defines ``accepts_reply``)."""
        accepts_reply = getattr(request, "accepts_reply", None)
        return (lambda reply: bool(accepts_reply(reply.payload))) if accepts_reply is not None else None

    def send(
        self,
        request: BaseRequest,
        wait: bool = False,
        timeout: float = 5.0,
    ) -> BaseResponse | None:
        """
        Send a request to the server using protocol models.

        Args:
            request: The request model to send
            wait: Whether to wait for a response
            timeout: Timeout in seconds when waiting

        Returns:
            The parsed response if wait=True, otherwise None

        With ``wait=True``, requests for one command run one at a time across
        threads, and the wait for an earlier one counts against ``timeout``.
        With ``wait=False`` the reply, if the command has one, is not paired
        with this send: it can answer a concurrent waiting request for that
        command that has no reply check (see :meth:`Connection.request`).

        Raises:
            CommandError: The server answered with a non-zero error code
            PacketError: The response payload did not match the response model
            EmpireTimeoutError: No response within ``timeout``
            ConnectionClosedError: Connection dropped while waiting
            NetworkError: The send itself failed
            ReceiveThreadError: Called with ``wait=True`` on the receive thread

        Example:
            from empire_core.alliance import AllianceChatMessageRequest

            request = AllianceChatMessageRequest.create("Hello!")
            client.send(request)

            # Or wait for response:
            response = client.send(GetCastlesRequest(), wait=True)
        """
        packet = self.frame(request)

        if not wait:
            self.connection.send(packet)
            return None

        command = request.get_command()
        response_command = request.get_response_command()
        response_packet = self.connection.request(
            packet, response_command, timeout=timeout, accepts=self._reply_check(request)
        )

        if response_packet.error_code != 0:
            # Reported under the command sent, which is what the caller asked for.
            raise CommandError(command, response_packet.error_code, response_packet.payload)

        if isinstance(response_packet.payload, dict):
            try:
                return parse_response(response_command, response_packet.payload)
            except ValidationError as e:
                # Server field-type drift must surface as a library error, not
                # as a raw pydantic exception leaking through the public API.
                raise PacketError(f"Could not parse '{response_command}' response: {e}") from e

        return None

    def request(self, request: BaseRequest, response_type: type[T], timeout: float = 5.0) -> T:
        """
        Send a request and return its typed response.

        Like ``send(request, wait=True)`` but verifies the parsed response
        is of the expected type, so callers get a non-optional result.

        Raises:
            PacketError: The response could not be parsed as ``response_type``
            CommandError / EmpireTimeoutError / ConnectionClosedError / NetworkError:
                See :meth:`send`.
        """
        response = self.send(request, wait=True, timeout=timeout)
        if not isinstance(response, response_type):
            raise PacketError(
                f"Expected {response_type.__name__} for '{request.get_command()}', got {type(response).__name__}"
            )
        return response
