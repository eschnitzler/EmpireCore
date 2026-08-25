"""
EmpireClient for EmpireCore.

Uses a threaded Connection class, designed to work well with Discord.py
by not competing for the event loop.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import warnings
from collections.abc import Callable
from types import TracebackType
from typing import Any, TypeVar, cast

from pydantic import ValidationError

from empire_core.client.map_scanner import MapScanner, ScanResult
from empire_core.config import (
    LOGIN_DEFAULTS,
    EmpireConfig,
    ServerError,
    default_config,
)
from empire_core.exceptions import (
    CommandError,
    EmpireTimeoutError,
    LoginCooldownError,
    LoginError,
    PacketError,
)
from empire_core.network.connection import Connection
from empire_core.protocol.models import BaseRequest, BaseResponse, encode_chat_text, parse_response
from empire_core.protocol.models.alliance import GetAllianceInfoRequest, GetAllianceInfoResponse
from empire_core.protocol.models.chat import AllianceChatLogRequest, AllianceChatLogResponse
from empire_core.protocol.models.defense import (
    GetSupportDefenseRequest,
    GetSupportDefenseResponse,
)
from empire_core.protocol.models.map import (
    GetMapAreaRequest,
    GetMapAreaResponse,
    Kingdom,
    MapItemType,
)
from empire_core.protocol.models.player import (
    GetPlayerInfoRequest,
    GetPlayerInfoResponse,
    SearchPlayerRequest,
    SearchPlayerResponse,
)
from empire_core.protocol.packet import Packet
from empire_core.services import (
    AllianceService,
    ArmyService,
    BaseService,
    CastleService,
    CommandersService,
    RankingService,
    SpyService,
    get_registered_services,
)
from empire_core.state.manager import GameState
from empire_core.state.world_models import Movement
from empire_core.utils.events import GameEvent
from empire_core.utils.events import get_active_events as _get_active_events

logger = logging.getLogger(__name__)

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
        movements = client.get_movements()
        client.close()

        # Or, cleaning up automatically:
        with EmpireClient(username="user", password="pass") as client:
            client.login()
            movements = client.get_movements()
    """

    alliance: AllianceService
    castle: CastleService
    army: ArmyService
    commanders: CommandersService
    spy: SpyService
    ranking: RankingService

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
        self.is_logged_in = False

        # Command -> handlers mapping for efficient dispatch
        # Only commands with handlers will be parsed.
        # Written from caller threads (services, get_player_details_bulk) and
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
        self.commanders: CommandersService = cast(CommandersService, self._services["commanders"])
        self.spy: SpyService = cast(SpyService, self._services["spy"])
        self.ranking: RankingService = cast(RankingService, self._services["ranking"])

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
        # arrays (e.g. 'sce' inventory updates, which arrive as
        # ``[["PTT", 123]]``). Both have to reach GameState; XML packets
        # (ET.Element) and empty payloads have nothing to apply.
        payload: object = packet.payload
        if not cmd or not isinstance(payload, (dict, list)):
            return

        # Update internal state (always runs for state-tracked commands)
        self._update_state(cmd, payload)

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

    def _update_state(self, cmd: str, payload: dict[str, Any] | list[Any]) -> None:
        """Sync state update from packet - delegates to GameState.

        Array payloads are forwarded unchanged; GameState's per-command
        handlers decide which shapes they accept.
        """
        self.state.update_from_packet(cmd, cast(dict[str, Any], payload))

    def _on_disconnect(self) -> None:
        """Handle unexpected connection loss.

        State (including its callback executor) is intentionally left
        running so registered callbacks keep working after a re-login.
        """
        self.is_logged_in = False
        logger.warning(f"Client {self.username} disconnected unexpectedly")

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

        Raises:
            CommandError: The server answered with a non-zero error code
            PacketError: The response payload did not match the response model
            EmpireTimeoutError: No response within ``timeout``
            ConnectionClosedError: Connection dropped while waiting
            NetworkError: The send itself failed

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
        response_packet = self.connection.request(packet, response_command, timeout=timeout)

        if response_packet.error_code != 0:
            # Reported under the command sent, which is what the caller asked for.
            raise CommandError(command, response_packet.error_code)

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

    # ============================================================
    # Game Commands
    # ============================================================

    def get_movements(self, wait: bool = True, timeout: float = 5.0) -> list[Movement]:
        """
        Request army movements from server.

        Args:
            wait: If True, wait for response before returning
            timeout: Timeout in seconds when waiting

        Returns:
            List of Movement objects, read from state after the response has
            been applied. With ``wait=False`` this is whatever state holds
            right now, which is not yet the answer to this request.

        Raises:
            CommandError: ``wait=True`` and the server rejected 'gam'
            EmpireTimeoutError: ``wait=True`` and no response within ``timeout``
        """
        packet = Packet.build_xt(self.config.default_zone, "gam", {})

        if wait:
            response = self.connection.request(packet, "gam", timeout=timeout)
            # Without this, a rejected request returns the previous (possibly
            # empty) movement list, indistinguishable from "no movements".
            if response.error_code != 0:
                raise CommandError("gam", response.error_code)
        else:
            self.connection.send(packet)

        return self.state.get_all_movements()

    def send_alliance_chat(self, message: str) -> None:
        """
        Send a message to alliance chat.

        Args:
            message: The message to send
        """
        payload = {"M": encode_chat_text(message)}
        packet = Packet.build_xt(self.config.default_zone, "acm", payload)
        self.connection.send(packet)

    def get_player_info(self, player_id: int, timeout: float = 5.0) -> GetPlayerInfoResponse:
        """
        Get detailed player information (gdi), including castle list with
        capture info.

        Args:
            player_id: The player's ID
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`send`
        """
        return self.request(GetPlayerInfoRequest(PID=player_id), GetPlayerInfoResponse, timeout=timeout)

    def get_alliance_info(self, alliance_id: int, timeout: float = 5.0) -> GetAllianceInfoResponse:
        """
        Get info about an alliance.

        Args:
            alliance_id: The alliance ID
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`send`
        """
        return self.request(GetAllianceInfoRequest(AID=alliance_id), GetAllianceInfoResponse, timeout=timeout)

    # ============================================================
    # Movement Helpers
    # ============================================================

    def get_incoming_attacks(self) -> list[Movement]:
        """Get all incoming attack movements."""
        return self.state.get_incoming_attacks()

    def get_incoming_movements(self) -> list[Movement]:
        """Get all incoming movements."""
        return self.state.get_incoming_movements()

    def get_outgoing_movements(self) -> list[Movement]:
        """Get all outgoing movements."""
        return self.state.get_outgoing_movements()

    # ============================================================
    # Event Info
    # ============================================================

    def get_active_event_ids(self) -> list[int]:
        """
        Get list of currently active event IDs.

        Returns:
            List of event IDs (EID) from sei packet.
            Empty list if no events are active or not yet logged in.
        """
        return list(self.state.active_event_ids)  # Return copy, not reference

    def get_active_events(
        self,
        lang: str = "en",
        force_refresh: bool = False,
    ) -> list[GameEvent]:
        """
        Get currently active events with human-readable names resolved from the GGS CDN.

        Combines ``get_active_event_ids()`` with a CDN lookup to produce typed
        ``GameEvent`` objects. CDN data is cached after the first call.

        Args:
            lang: Language code for display names (default: "en").
            force_refresh: Force re-fetch of CDN data, bypassing the cache.

        Returns:
            List of GameEvent objects for currently active events. An empty
            list always means "no events are active" — CDN failures raise.

        Raises:
            NetworkError: The CDN fetch failed and no cached data exists, so
                the answer is unknown rather than empty.

        Example:
            events = client.get_active_events()
            event_names = {e.internal_name for e in events}

            if "Nomad" in event_names:
                # handle nomad event ...
                pass
        """
        event_ids = self.get_active_event_ids()
        return _get_active_events(event_ids, lang=lang, force_refresh=force_refresh)

    # ============================================================
    # Chat Subscription
    # ============================================================

    def get_alliance_chat(self, timeout: float = 5.0) -> AllianceChatLogResponse:
        """
        Get alliance chat history.

        Args:
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`send`
        """
        return self.request(AllianceChatLogRequest(), AllianceChatLogResponse, timeout=timeout)

    def _warn_raw_chat_subscription(self, method: str) -> None:
        warnings.warn(
            f"EmpireClient.{method}() delivers raw wire packets and is deprecated; "
            "use client.alliance.on_chat_message(), which delivers a typed "
            "AllianceChatMessageResponse with .player_name/.decoded_text.",
            DeprecationWarning,
            stacklevel=3,
        )

    def subscribe_alliance_chat(self, callback: Callable[[Packet], None]) -> None:
        """
        Subscribe to alliance chat messages as raw packets.

        .. deprecated::
            Use :meth:`AllianceService.on_chat_message`
            (``client.alliance.on_chat_message``) instead. It delivers a typed
            ``AllianceChatMessageResponse`` with ``player_name`` and
            ``decoded_text``, so consumers never touch protocol keys or
            reimplement the chat-text decoder.

        Args:
            callback: Function to call with each chat packet.
                      Packet payload will have format:
                      {"CM": {"PN": "player_name", "MT": "message_text", ...}}
        """
        self._warn_raw_chat_subscription("subscribe_alliance_chat")
        # Alliance chat messages come via 'acm' command (not 'aci')
        self.connection.subscribe("acm", callback)

    def unsubscribe_alliance_chat(self, callback: Callable[[Packet], None]) -> None:
        """Unsubscribe from raw alliance chat packets.

        .. deprecated::
            See :meth:`subscribe_alliance_chat`.
        """
        self._warn_raw_chat_subscription("unsubscribe_alliance_chat")
        self.connection.unsubscribe("acm", callback)

    # ============================================================
    # Defense Info
    # ============================================================

    def get_castle_defense(
        self,
        target_x: int,
        target_y: int,
        source_x: int | None = None,
        source_y: int | None = None,
        timeout: float = 5.0,
    ) -> GetSupportDefenseResponse:
        """
        Get defense info for an alliance member's castle.

        Uses the SDI (Support Defense Info) command to query the total
        troops defending a castle. Can only query castles of players
        in the same alliance as the bot.

        Args:
            target_x: Target castle X coordinate
            target_y: Target castle Y coordinate
            source_x: Source castle X coordinate (defaults to bot's main castle)
            source_y: Source castle Y coordinate (defaults to bot's main castle)
            timeout: Timeout in seconds

        Returns:
            GetSupportDefenseResponse with defense info.
            Use response.get_total_defenders() to get total troop count.

        Raises:
            ValueError: No source coordinates given and no own castle known
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`send`
        """
        # Default to bot's main castle as source
        if source_x is None or source_y is None:
            main_castle = next(iter(self.state.get_castles()), None)
            if main_castle is None:
                raise ValueError("No source coordinates given and no own castles in state")
            source_x = main_castle.x
            source_y = main_castle.y
            logger.debug(f"SDI: Using source castle at {source_x}:{source_y}")

        request = GetSupportDefenseRequest(TX=target_x, TY=target_y, SX=source_x, SY=source_y)
        return self.request(request, GetSupportDefenseResponse, timeout=timeout)

    # ============================================================
    # Map Scanning
    # ============================================================

    def scan_map_area(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        kingdom: Kingdom = Kingdom.GREEN,
        timeout: float = 5.0,
    ) -> GetMapAreaResponse:
        """
        Scan a specific area of the map.

        Args:
            x1: Left X coordinate
            y1: Top Y coordinate
            x2: Right X coordinate
            y2: Bottom Y coordinate
            kingdom: Kingdom to scan (GREEN, SANDS, ICE, FIRE, STORM)
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`send`
        """
        request = GetMapAreaRequest(KID=kingdom, AX1=x1, AY1=y1, AX2=x2, AY2=y2)
        return self.request(request, GetMapAreaResponse, timeout=timeout)

    def _get_kingdom_start_position(self, kingdom: Kingdom) -> tuple[int, int]:
        """
        Get a starting position for scanning a kingdom.

        Uses the bot's own castle position in the target kingdom if available.
        Falls back to map center (650, 650) if no castle found.

        Args:
            kingdom: The kingdom to find a starting position for

        Returns:
            (x, y) tuple for the starting position
        """
        if self.state:
            # Find a castle in the target kingdom
            for castle in self.state.get_castles():
                if castle.KID == kingdom.value:
                    return (castle.X, castle.Y)

        # No castle in this kingdom - use map center as fallback
        return (650, 650)

    def scan_kingdom(
        self,
        kingdom: Kingdom = Kingdom.GREEN,
        item_types: list[MapItemType] | None = None,
        timeout: float = 300.0,
        request_timeout: float = 5.0,
        chunk_delay: float = 0.2,
        include_unowned_types: set[MapItemType] | None = None,
    ) -> ScanResult:
        """Scan a kingdom map. See MapScanner.scan_kingdom."""
        return MapScanner(self).scan_kingdom(
            kingdom,
            item_types,
            timeout,
            request_timeout,
            chunk_delay,
            include_unowned_types=include_unowned_types,
        )

    def scan_chunks(
        self,
        kingdom: Kingdom,
        chunks: list[tuple[int, int]],
        item_types: list[MapItemType] | None = None,
        timeout: float = 300.0,
        request_timeout: float = 5.0,
        chunk_delay: float = 0.2,
        include_unowned_types: set[MapItemType] | None = None,
    ) -> ScanResult:
        """Scan an explicit chunk list (no BFS). See MapScanner.scan_chunks."""
        return MapScanner(self).scan_chunks(
            kingdom,
            chunks,
            item_types,
            timeout,
            request_timeout,
            chunk_delay,
            include_unowned_types=include_unowned_types,
        )

    # ============================================================
    # Player Details (gdi - includes capture info)
    # ============================================================

    def get_player_details(
        self,
        player_id: int,
        timeout: float = 5.0,
    ) -> GetPlayerInfoResponse:
        """Alias for :meth:`get_player_info` (both use the 'gdi' command)."""
        return self.get_player_info(player_id, timeout=timeout)

    def get_player_details_bulk(
        self,
        player_ids: list[int],
        timeout: float = 10.0,
        send_delay: float = 0.05,
    ) -> dict[int, GetPlayerInfoResponse]:
        """
        Get detailed info for multiple players in parallel.

        Registers a handler first, then sends all requests (paced by
        ``send_delay``), and collects responses via a thread-safe queue.

        Args:
            player_ids: List of player IDs to fetch
            timeout: Max time to wait for all responses. The pacing sleeps are
                not charged against it - the clock starts once all requests
                are out.
            send_delay: Seconds to wait between consecutive 'gdi' sends. The
                server drops connections that sustain high request rates (the
                same reason MapScanner paces its chunks), and a large id list
                would otherwise go out as one burst on a connection other
                callers share. Set to 0 to send without pacing.

        Returns:
            Dict mapping player_id -> GetPlayerInfoResponse
        """
        if not player_ids:
            return {}

        unique_ids = set(player_ids)
        response_queue: queue.Queue[GetPlayerInfoResponse] = queue.Queue()

        def capture_gdi(response: BaseResponse) -> None:
            if isinstance(response, GetPlayerInfoResponse):
                response_queue.put(response)

        # Register BEFORE sending to avoid dropping early responses
        self._register_handler("gdi", capture_gdi)

        try:
            for index, pid in enumerate(unique_ids):
                if index and send_delay > 0:
                    time.sleep(send_delay)
                request = GetPlayerInfoRequest(PID=pid)
                self.send(request, wait=False)

            collected: dict[int, GetPlayerInfoResponse] = {}
            deadline = time.time() + timeout

            while len(collected) < len(unique_ids) and time.time() < deadline:
                try:
                    resp = response_queue.get(timeout=max(0.05, min(0.5, deadline - time.time())))
                    if resp.player_id in unique_ids:
                        collected[resp.player_id] = resp
                except queue.Empty:
                    continue

            return collected
        finally:
            self._unregister_handler("gdi", capture_gdi)

    def search_player_by_name(
        self,
        player_name: str,
        timeout: float = 5.0,
    ) -> SearchPlayerResponse:
        return self.request(SearchPlayerRequest(PN=player_name), SearchPlayerResponse, timeout=timeout)
