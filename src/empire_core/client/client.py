"""
EmpireClient for EmpireCore.

Uses a threaded Connection class, designed to work well with Discord.py
by not competing for the event loop.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Any, TypeVar, cast

from pydantic import ValidationError

from empire_core.alliance.service import AllianceService
from empire_core.army.service import ArmyService
from empire_core.attack.service import AttackService
from empire_core.castle.service import CastleService
from empire_core.commanders.service import CommandersService, EquipmentService, SkillsService
from empire_core.config import LOGIN_DEFAULTS, EmpireConfig, ServerError, default_config
from empire_core.defense.service import DefenseService
from empire_core.events.service import EventsService
from empire_core.exceptions import (
    CommandError,
    EmpireError,
    EmpireTimeoutError,
    LoginCooldownError,
    LoginError,
    PacketError,
)
from empire_core.gamedata import GameData
from empire_core.map.service import MapService
from empire_core.movements.models import GetMovementsRequest
from empire_core.movements.service import MovementsService
from empire_core.network.connection import NON_ERROR_COMMANDS, Connection
from empire_core.player.service import PlayerService
from empire_core.protocol.models import BaseRequest, BaseResponse, parse_response
from empire_core.protocol.packet import Packet
from empire_core.ranking.service import RankingService
from empire_core.services import BaseService, get_registered_services
from empire_core.spy.service import SpyService
from empire_core.state.manager import GameState

logger = logging.getLogger(__name__)

# Packets carrying the movement filter settings; each is followed by a gam request.
MOVEMENT_FILTER_COMMANDS = frozenset({"gbd", "mvf"})

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
    movements: MovementsService
    defense: DefenseService
    player: PlayerService
    events: EventsService

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        config: EmpireConfig | None = None,
    ):
        self.config = config or default_config
        self.username = username or self.config.username
        self.password = password or self.config.password

        self.connection = Connection(self.config.game_url, keepalive_zone=self.config.default_zone)
        self.state = GameState()
        self.game_data: GameData | None = None
        self.is_logged_in = False

        # Command -> handlers mapping for efficient dispatch
        # Only commands with handlers will be parsed.
        # Written from caller threads (services, client.player.get_player_details_bulk) and
        # read by the receive thread, so every access goes through the lock -
        # CPython's per-op atomicity is not a guarantee to build on and does
        # not hold on free-threaded builds.
        self._handlers: dict[str, list[Callable[[BaseResponse], None]]] = {}
        self._handlers_lock = threading.Lock()

        # Wire up packet handler for state updates
        self.connection.on_packet = self._on_packet
        self.connection.on_disconnect = self._on_disconnect

        # Auto-attach registered services
        self._services: dict[str, BaseService] = {}
        for name, service_cls in get_registered_services().items():
            service = service_cls(self)
            self._services[name] = service
            setattr(self, name, service)

        self.alliance: AllianceService = cast(AllianceService, self._services["alliance"])
        self.castle: CastleService = cast(CastleService, self._services["castle"])
        self.army: ArmyService = cast(ArmyService, self._services["army"])
        self.attack: AttackService = cast(AttackService, self._services["attack"])
        self.commanders: CommandersService = cast(CommandersService, self._services["commanders"])
        self.equipment: EquipmentService = cast(EquipmentService, self._services["equipment"])
        self.skills: SkillsService = cast(SkillsService, self._services["skills"])
        self.spy: SpyService = cast(SpyService, self._services["spy"])
        self.ranking: RankingService = cast(RankingService, self._services["ranking"])
        self.map: MapService = cast(MapService, self._services["map"])
        self.movements: MovementsService = cast(MovementsService, self._services["movements"])
        self.defense: DefenseService = cast(DefenseService, self._services["defense"])
        self.player: PlayerService = cast(PlayerService, self._services["player"])
        self.events: EventsService = cast(EventsService, self._services["events"])

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

        # Update internal state (always runs for state-tracked commands)
        self._update_state(cmd, payload)
        if cmd in MOVEMENT_FILTER_COMMANDS and packet.error_code == 0:
            self._request_movements()

        # Client: CastleExtensionResponseCommand.execute (bundle line 110733) hands
        # the status to each command, and the commands parse only on success.
        if packet.error_code != 0 and cmd not in NON_ERROR_COMMANDS:
            return

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
        """Ask for the movement list (gam) once the movement filter settings (mvf) are known.

        Runs on the receive thread, so it sends without waiting; the reply reaches
        state like any gam. The client sends it from ``MVFCommand.executeCommand``,
        the handler of an mvf push. Its login data parser (``GBDCommand``) only
        reads the gbd's mvf section, but a live login gets no mvf push, so the
        library also asks after every gbd; nothing else would list the movements
        after a login.

        Client: ``MVFCommand.executeCommand`` (bundle line 129703) and
        ``GBDCommand.executeCommand`` (line 129381, ``parse_MVF(n.mvf)``).
        """
        try:
            self.send(GetMovementsRequest())
        except EmpireError:
            logger.warning("Could not ask for the movement list after the login data", exc_info=True)

    def _update_state(self, cmd: str, payload: dict[str, Any] | list[Any]) -> None:
        """Sync state update from packet - delegates to GameState.

        Array payloads are forwarded unchanged; GameState's per-command
        handlers decide which shapes they accept.
        """
        self.state.update_from_packet(cmd, cast(dict[str, Any], payload))

    def _on_disconnect(self, generation: int) -> None:
        """Handle unexpected connection loss of the session ``generation``; a newer session is left alone.

        State data is reset, as the game client resets it, so nothing from
        the lost session is reported after it. The next login's gbd rebuilds
        the player and castles, and the gam asked for after it the movements.
        Registered callbacks and the callback executor stay, so they keep
        working after a re-login.
        """
        if not self.connection.run_if_current(generation, self._forget_session):
            logger.debug(f"Client {self.username}: drop of an earlier session reported late, ignored")
            return
        logger.warning(f"Client {self.username} disconnected unexpectedly")

    def _forget_session(self) -> None:
        self.is_logged_in = False
        self.state.reset()

    def on_disconnect(self, callback: Callable[[], None]) -> None:
        """Register a callback for the session dropping on its own; :meth:`close` does not fire it.

        Runs on the receive thread as it shuts down, after ``is_logged_in`` is
        cleared, and fires once per dropped session. Keep it short and hand a
        re-login to another thread. Registering the same callback twice is a no-op.
        """
        self.connection.add_disconnect_listener(callback)

    def remove_disconnect_callback(self, callback: Callable[[], None]) -> None:
        """Remove a callback added with :meth:`on_disconnect`; unknown callbacks are ignored."""
        self.connection.remove_disconnect_listener(callback)

    def login(self) -> bool:
        """
        Perform the full login sequence:
        1. Connect WebSocket
        2. Version Check (XML)
        3. Zone Login (XML)
        4. AutoJoin Room (XML)
        5. XT Version Check
        6. XT Login (Auth)

        Returns:
            Always ``True``. Every failure path raises, so ``if not
            client.login():`` is dead code - check for exceptions instead.
            The ``bool`` return is kept only for backwards compatibility with
            callers that already assert on it.

        Raises:
            NetworkError: The WebSocket connection could not be established
            EmpireTimeoutError: A required login step timed out
            LoginCooldownError: The server is rate-limiting this account
            LoginError: Username or password missing, or the server rejected
                the credentials

        Every failure mode is an ``EmpireError`` subclass, so
        ``except EmpireError`` catches all of them.

        On any of these, the connection and its background threads are closed
        before the error propagates, so a failed login leaks nothing.
        """
        if not self.username or not self.password:
            raise LoginError("Username and password are required")

        logger.debug(f"Logging in as {self.username}...")

        try:
            # Connect if not already connected
            if not self.connection.connected:
                self.connection.connect(timeout=self.config.connection_timeout)

            return self._login_sequence()
        except Exception:
            # The documented cleanup call (close()) never runs on the raising
            # path, so without this a failed login leaves an open socket plus
            # a receive and a keepalive thread pinging an unauthenticated
            # session forever.
            self._close_after_failed_login()
            raise

    def _login_sequence(self) -> bool:
        """Run the handshake/auth exchange on an already-connected socket."""
        # 1. Version Check
        ver_packet = f"<msg t='sys'><body action='verChk' r='0'><ver v='{self.config.game_version}' /></body></msg>"
        try:
            self.connection.request(ver_packet, "apiOK", timeout=self.config.request_timeout)
        except EmpireTimeoutError as e:
            raise EmpireTimeoutError("Version check timed out") from e

        # Same client-version fingerprint the XT login sends below: a second
        # hardcoded copy would silently drift on the next game-client bump.
        conm_value = LOGIN_DEFAULTS["CONM"]

        # 2. Zone Login (XML)
        login_packet = (
            f"<msg t='sys'><body action='login' r='0'>"
            f"<login z='{self.config.default_zone}'>"
            f"<nick><![CDATA[]]></nick>"
            f"<pword><![CDATA[{conm_value}%en%0]]></pword>"
            f"</login></body></msg>"
        )
        try:
            self.connection.request(login_packet, "rlu", timeout=self.config.login_timeout)
        except EmpireTimeoutError as e:
            raise EmpireTimeoutError("Zone login timed out") from e

        # 3. AutoJoin Room
        join_packet = "<msg t='sys'><body action='autoJoin' r='-1'></body></msg>"
        try:
            self.connection.request(join_packet, "joinOK", timeout=self.config.request_timeout)
        except EmpireTimeoutError:
            # The server does not always send joinOK; not fatal
            logger.debug("No joinOK received, continuing login")

        roundtrip_packet = "<msg t='sys'><body action='roundTrip' r='1'></body></msg>"
        try:
            self.connection.request(roundtrip_packet, "roundTripRes", timeout=self.config.request_timeout)
        except EmpireTimeoutError:
            # roundTripRes is informational only; not fatal
            logger.debug("No roundTripRes received, continuing login")

        # 5. XT Login (Real Auth)
        xt_payload = {
            **LOGIN_DEFAULTS,
            "NOM": self.username,
            "PW": self.password,
        }
        xt_packet = f"%xt%{self.config.default_zone}%lli%1%{json.dumps(xt_payload)}%"

        # Register the gbd waiter up front: it arrives right after a
        # successful lli and would otherwise race the lli handling below.
        gbd_waiter = self.connection.create_waiter("gbd")
        try:
            try:
                lli_response = self.connection.request(xt_packet, "lli", timeout=self.config.login_timeout)
            except EmpireTimeoutError as e:
                raise EmpireTimeoutError("XT login timed out") from e

            if lli_response.error_code != 0:
                if lli_response.error_code == ServerError.LOGIN_COOLDOWN:
                    cooldown = 0
                    if isinstance(lli_response.payload, dict):
                        cooldown = int(lli_response.payload.get("CD", 0))
                    raise LoginCooldownError(cooldown)

                raise LoginError(f"Auth failed with code {lli_response.error_code}")

            # Wait for gbd (Get Big Data) which contains player info, castles, etc.
            try:
                self.connection.wait_for_result("gbd", gbd_waiter, timeout=self.config.request_timeout)
            except EmpireTimeoutError:
                logger.warning(f"gbd packet not received for {self.username}, player state may be incomplete")

            logger.debug(f"Logged in as {self.username}")
            self.is_logged_in = True
            return True
        finally:
            self.connection.cancel_waiter("gbd", gbd_waiter)

    def _close_after_failed_login(self) -> None:
        """Best-effort cleanup that must never mask the original failure."""
        try:
            self.close()
        except Exception:
            logger.exception("Cleanup after failed login raised")

    def close(self) -> None:
        """Disconnect from the server and release background resources.

        Safe to call more than once, and safe to call after a failed login.
        """
        self.is_logged_in = False
        # Disconnect first: shutting the state executor down while packets can
        # still arrive lets a late callback lazily recreate it, leaking a
        # thread pool nobody owns any more.
        self.connection.disconnect()
        self.state.shutdown()
        self.state.reset()

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

        Explicit by design: the items payload is a large download, so no other
        API fetches it behind your back. Cached on disk per game version, so
        this is cheap after the first call.

        Args:
            refresh: Ignore any cached copy and re-download
            cache_dir: Where to keep trimmed data (default: XDG cache dir)

        Returns:
            The loaded data, also available as ``client.game_data``

        Raises:
            NetworkError: The CDN could not be reached
        """
        self.game_data = GameData.load(refresh=refresh, cache_dir=cache_dir)
        return self.game_data

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

        Raises:
            CommandError: The server answered with a non-zero error code
            PacketError: The response payload did not match the response model
            EmpireTimeoutError: No response within ``timeout``
            ConnectionClosedError: Connection dropped while waiting
            NetworkError: The send itself failed
            ReceiveThreadError: Called with ``wait=True`` on the receive thread

        Example:
            from empire_core.protocol.models import AllianceChatMessageRequest

            request = AllianceChatMessageRequest.create("Hello!")
            client.send(request)

            # Or wait for response:
            response = client.send(GetCastlesRequest(), wait=True)
        """
        packet = request.to_packet(zone=self.config.default_zone)

        if not wait:
            self.connection.send(packet)
            return None

        command = request.get_command()
        response_command = request.get_response_command()
        # A request whose reply names what was asked for defines accepts_reply(payload).
        accepts_reply = getattr(request, "accepts_reply", None)
        response_packet = self.connection.request(
            packet,
            response_command,
            timeout=timeout,
            accepts=(lambda reply: accepts_reply(reply.payload)) if accepts_reply is not None else None,
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
