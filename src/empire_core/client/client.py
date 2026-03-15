from __future__ import annotations
from collections.abc import Callable

"""
EmpireClient for EmpireCore.

Uses a threaded Connection class, designed to work well with Discord.py
by not competing for the event loop.
"""


import json
import logging
import time
from typing import TYPE_CHECKING, TypeVar

from empire_core.config import (
    LOGIN_DEFAULTS,
    EmpireConfig,
    ServerError,
    default_config,
)
from empire_core.exceptions import LoginCooldownError, LoginError, TimeoutError
from empire_core.network.connection import Connection
from empire_core.protocol.models import BaseRequest, BaseResponse, ErrorResponse, parse_response
from empire_core.protocol.models.alliance import GetAllianceInfoRequest, GetAllianceInfoResponse
from empire_core.protocol.models.chat import AllianceChatLogResponse
from empire_core.protocol.models.defense import (
    GetSupportDefenseRequest,
    GetSupportDefenseResponse,
)
from empire_core.protocol.models.map import (
    GetMapAreaRequest,
    GetMapAreaResponse,
    Kingdom,
    MapAreaItem,
    MapItemType,
)
from empire_core.protocol.models.player import (
    GetPlayerInfoRequest,
    GetPlayerInfoResponse,
    SearchPlayerRequest,
    SearchPlayerResponse,
)
from empire_core.protocol.packet import Packet
from empire_core.services import get_registered_services
from empire_core.state.manager import GameState
from empire_core.state.world_models import Movement

if TYPE_CHECKING:
    from empire_core.services import AllianceService, ArmyService, BaseService, CastleService, LordsService

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
    """

    alliance: AllianceService
    castle: CastleService
    army: ArmyService
    lords: LordsService

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        config: EmpireConfig | None = None,
    ):
        self.config = config or default_config
        self.username = username or self.config.username
        self.password = password or self.config.password

        self.connection = Connection(self.config.game_url)
        self.state = GameState()
        self.is_logged_in = False

        # Command -> handlers mapping for efficient dispatch
        # Only commands with handlers will be parsed
        self._handlers: dict[str, list[Callable[[BaseResponse], None]]] = {}

        # Wire up packet handler for state updates
        self.connection.on_packet = self._on_packet
        self.connection.on_disconnect = self._on_disconnect

        # Auto-attach registered services
        self._services: dict[str, "BaseService"] = {}
        for name, service_cls in get_registered_services().items():
            service = service_cls(self)
            self._services[name] = service
            setattr(self, name, service)

    def _register_handler(self, command: str, handler: Callable[[BaseResponse], None]) -> None:
        """
        Register a handler for a specific command.

        Called by services to register interest in specific responses.
        Only commands with handlers will be parsed and dispatched.
        """
        if command not in self._handlers:
            self._handlers[command] = []
        self._handlers[command].append(handler)

    def _on_packet(self, packet: Packet) -> None:
        """Handle incoming packets for state updates and service dispatch."""
        cmd = packet.command_id
        if not cmd or not isinstance(packet.payload, dict):
            return

        # Update internal state (always runs for state-tracked commands)
        self._update_state(cmd, packet.payload)

        # Only parse and dispatch if handlers are registered
        handlers = self._handlers.get(cmd)
        if handlers:
            response = parse_response(cmd, packet.payload)
            if response:
                # Copy list to avoid issues if handlers are added during iteration
                for handler in list(handlers):
                    try:
                        handler(response)
                    except Exception:
                        pass

    def _update_state(self, cmd: str, payload: dict) -> None:
        """Sync state update from packet - delegates to GameState."""
        self.state.update_from_packet(cmd, payload)

    def _on_disconnect(self) -> None:
        """Handle disconnect."""
        self.is_logged_in = False
        self.state.shutdown()
        logger.warning("Client disconnected")

    def login(self) -> bool:
        """
        Perform the full login sequence:
        1. Connect WebSocket
        2. Version Check (XML)
        3. Zone Login (XML)
        4. AutoJoin Room (XML)
        5. XT Version Check
        6. XT Login (Auth)
        """
        if not self.username or not self.password:
            raise ValueError("Username and password are required")

        logger.debug(f"Logging in as {self.username}...")

        # Connect if not already connected
        if not self.connection.connected:
            self.connection.connect(timeout=self.config.connection_timeout)

        # 1. Version Check
        ver_packet = f"<msg t='sys'><body action='verChk' r='0'><ver v='{self.config.game_version}' /></body></msg>"
        self.connection.send(ver_packet)

        try:
            response = self.connection.wait_for("apiOK", timeout=self.config.request_timeout)
        except TimeoutError:
            raise TimeoutError("Version check timed out")

        conm_value = 1150008

        # 2. Zone Login (XML)
        login_packet = (
            f"<msg t='sys'><body action='login' r='0'>"
            f"<login z='{self.config.default_zone}'>"
            f"<nick><![CDATA[]]></nick>"
            f"<pword><![CDATA[{conm_value}%en%0]]></pword>"
            f"</login></body></msg>"
        )
        self.connection.send(login_packet)

        try:
            self.connection.wait_for("rlu", timeout=self.config.login_timeout)
        except TimeoutError:
            raise TimeoutError("Zone login timed out")

        # 3. AutoJoin Room
        join_packet = "<msg t='sys'><body action='autoJoin' r='-1'></body></msg>"
        self.connection.send(join_packet)

        try:
            self.connection.wait_for("joinOK", timeout=self.config.request_timeout)
        except TimeoutError:
            pass

        roundtrip_packet = "<msg t='sys'><body action='roundTrip' r='1'></body></msg>"
        self.connection.send(roundtrip_packet)

        try:
            self.connection.wait_for("roundTripRes", timeout=self.config.request_timeout)
        except TimeoutError:
            pass

        # 5. XT Login (Real Auth)
        xt_payload = {
            **LOGIN_DEFAULTS,
            "NOM": self.username,
            "PW": self.password,
        }
        xt_packet = f"%xt%{self.config.default_zone}%lli%1%{json.dumps(xt_payload)}%"
        self.connection.send(xt_packet)

        try:
            lli_response = self.connection.wait_for("lli", timeout=self.config.login_timeout)

            if lli_response.error_code != 0:
                if lli_response.error_code == ServerError.LOGIN_COOLDOWN:
                    cooldown = 0
                    if isinstance(lli_response.payload, dict):
                        cooldown = int(lli_response.payload.get("CD", 0))
                    raise LoginCooldownError(cooldown)

                raise LoginError(f"Auth failed with code {lli_response.error_code}")

            # Wait for gbd (Get Big Data) which contains player info, castles, etc.
            # This arrives shortly after lli success
            try:
                self.connection.wait_for("gbd", timeout=self.config.request_timeout)
            except TimeoutError:
                logger.warning("gbd packet not received, player state may be incomplete")

            logger.debug(f"Logged in as {self.username}")
            self.is_logged_in = True
            return True

        except TimeoutError:
            raise TimeoutError("XT login timed out")

    def close(self) -> None:
        """Disconnect from the server."""
        self.is_logged_in = False
        self.state.shutdown()
        self.connection.disconnect()

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

        Example:
            from empire_core.protocol.models import AllianceChatMessageRequest

            request = AllianceChatMessageRequest.create("Hello!")
            client.send(request)

            # Or wait for response:
            response = client.send(GetCastlesRequest(), wait=True)
        """
        packet = request.to_packet(zone=self.config.default_zone)
        self.connection.send(packet)

        if wait:
            command = request.get_command()
            try:
                response_packet = self.connection.wait_for(command, timeout=timeout)

                if not response_packet:
                    return None

                if response_packet.error_code != 0:
                    return ErrorResponse(E=response_packet.error_code)

                if isinstance(response_packet.payload, dict):
                    return parse_response(command, response_packet.payload)

                return None
            except Exception:
                return None

        return None

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
            List of Movement objects
        """
        packet = Packet.build_xt(self.config.default_zone, "gam", {})
        self.connection.send(packet)

        if wait:
            try:
                self.connection.wait_for("gam", timeout=timeout)
            except TimeoutError:
                pass

        return list(self.state.movements.values())

    def send_alliance_chat(self, message: str) -> None:
        """
        Send a message to alliance chat.

        Args:
            message: The message to send
        """
        # Alliance chat command: acm (Alliance Chat Message)
        # Payload format: {"M": "message text"}
        # Note: Special chars need encoding: % -> &percnt;, " -> &quot;, etc.
        encoded_message = (
            message.replace("%", "&percnt;")
            .replace('"', "&quot;")
            .replace("'", "&145;")
            .replace("\n", "<br />")
            .replace("\\", "%5C")
        )
        payload = {"M": encoded_message}
        packet = Packet.build_xt(self.config.default_zone, "acm", payload)
        self.connection.send(packet)

    def get_player_info(self, player_id: int, wait: bool = True, timeout: float = 5.0) -> GetPlayerInfoResponse | None:
        """
        Get info about a player.

        Args:
            player_id: The player's ID
            wait: If True, wait for response
            timeout: Timeout in seconds

        Returns:
            GetPlayerInfoResponse or None
        """
        request = GetPlayerInfoRequest(PID=player_id)
        response = self.send(request, wait=wait, timeout=timeout)
        if isinstance(response, GetPlayerInfoResponse):
            return response
        return None

    def get_alliance_info(
        self, alliance_id: int, wait: bool = True, timeout: float = 5.0
    ) -> GetAllianceInfoResponse | None:
        """
        Get info about an alliance.

        Args:
            alliance_id: The alliance ID
            wait: If True, wait for response
            timeout: Timeout in seconds

        Returns:
            GetAllianceInfoResponse or None
        """
        request = GetAllianceInfoRequest(AID=alliance_id)
        response = self.send(request, wait=wait, timeout=timeout)
        if isinstance(response, GetAllianceInfoResponse):
            return response
        return None

    # ============================================================
    # Movement Helpers
    # ============================================================

    def get_incoming_attacks(self) -> list[Movement]:
        """Get all incoming attack movements."""
        return [m for m in self.state.movements.values() if m.is_incoming and m.is_attack]

    def get_incoming_movements(self) -> list[Movement]:
        """Get all incoming movements."""
        return [m for m in self.state.movements.values() if m.is_incoming]

    def get_outgoing_movements(self) -> list[Movement]:
        """Get all outgoing movements."""
        return [m for m in self.state.movements.values() if m.is_outgoing]

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

    # ============================================================
    # Chat Subscription
    # ============================================================

    def get_alliance_chat(self, wait: bool = True, timeout: float = 5.0) -> AllianceChatLogResponse | None:
        """
        Get alliance chat history.

        Args:
            wait: If True, wait for response
            timeout: Timeout in seconds

        Returns:
            AllianceChatLogResponse or None
        """
        from empire_core.protocol.models.chat import AllianceChatLogRequest

        request = AllianceChatLogRequest()
        response = self.send(request, wait=wait, timeout=timeout)
        if isinstance(response, AllianceChatLogResponse):
            return response
        return None

    def subscribe_alliance_chat(self, callback) -> None:
        """
        Subscribe to alliance chat messages.

        Args:
            callback: Function to call with each chat packet.
                      Packet payload will have format:
                      {"CM": {"PN": "player_name", "MT": "message_text", ...}}
        """
        # Alliance chat messages come via 'acm' command (not 'aci')
        self.connection.subscribe("acm", callback)

    def unsubscribe_alliance_chat(self, callback) -> None:
        """Unsubscribe from alliance chat."""
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
        wait: bool = True,
        timeout: float = 5.0,
    ) -> GetSupportDefenseResponse | None:
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
            wait: If True, wait for response
            timeout: Timeout in seconds

        Returns:
            GetSupportDefenseResponse with defense info, or None on failure.
            Use response.get_total_defenders() to get total troop count.
        """
        # Default to bot's main castle as source
        if source_x is None or source_y is None:
            if self.state.castles:
                main_castle = list(self.state.castles.values())[0]
                source_x = main_castle.x
                source_y = main_castle.y
                logger.debug(f"SDI: Using source castle at {source_x}:{source_y}")
            else:
                logger.warning("SDI: No castles available for source coordinates")
                return None

        logger.debug(f"SDI: Sending request TX={target_x}, TY={target_y}, SX={source_x}, SY={source_y}")
        request = GetSupportDefenseRequest(TX=target_x, TY=target_y, SX=source_x, SY=source_y)
        logger.debug(f"SDI: Request packet = {request.to_packet(zone=self.config.default_zone)}")
        response = self.send(request, wait=wait, timeout=timeout)
        logger.debug(f"SDI: Response = {response}")

        if isinstance(response, GetSupportDefenseResponse):
            return response
        return None

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
        wait: bool = True,
        timeout: float = 5.0,
    ) -> GetMapAreaResponse | None:
        """
        Scan a specific area of the map.

        Args:
            x1: Left X coordinate
            y1: Top Y coordinate
            x2: Right X coordinate
            y2: Bottom Y coordinate
            kingdom: Kingdom to scan (GREEN, SANDS, ICE, FIRE, STORM)
            wait: If True, wait for response
            timeout: Timeout in seconds

        Returns:
            GetMapAreaResponse with map data, or None on failure.
        """
        request = GetMapAreaRequest(KID=kingdom, AX1=x1, AY1=y1, AX2=x2, AY2=y2)
        response = self.send(request, wait=wait, timeout=timeout)

        if isinstance(response, GetMapAreaResponse):
            return response
        return None

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
        if self.state and self.state.castles:
            # Find a castle in the target kingdom
            for castle in self.state.castles.values():
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
    ) -> list[MapAreaItem]:
        """Scan a kingdom map. See MapScanner.scan_kingdom."""
        from empire_core.client.map_scanner import MapScanner

        return MapScanner(self).scan_kingdom(kingdom, item_types, timeout, request_timeout)

    # ============================================================
    # Player Details (gdi - includes capture info)
    # ============================================================

    def get_player_details(
        self,
        player_id: int,
        wait: bool = True,
        timeout: float = 5.0,
    ) -> GetPlayerInfoResponse | None:
        """
        Get detailed player information including castle list with capture info.

        This uses the 'gdi' command which provides more detail than 'gpi',
        including which locations are being captured and by whom.

        Args:
            player_id: The player ID to look up
            wait: If True, wait for response
            timeout: Timeout in seconds

        Returns:
            GetPlayerInfoResponse with player details, or None on failure.
        """
        request = GetPlayerInfoRequest(PID=player_id)
        response = self.send(request, wait=wait, timeout=timeout)

        if isinstance(response, GetPlayerInfoResponse):
            return response
        return None

    def get_player_details_bulk(
        self,
        player_ids: list[int],
        timeout: float = 10.0,
    ) -> dict[int, GetPlayerInfoResponse]:
        """
        Get detailed info for multiple players in parallel.

        Registers a handler first, then sends all requests in a burst,
        and collects responses via a thread-safe queue.

        Args:
            player_ids: List of player IDs to fetch
            timeout: Max time to wait for all responses

        Returns:
            Dict mapping player_id -> GetPlayerInfoResponse
        """
        import queue

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
            for pid in unique_ids:
                request = GetPlayerInfoRequest(PID=pid)
                self.send(request, wait=False)

            collected: dict[int, GetPlayerInfoResponse] = {}
            deadline = time.time() + timeout

            while len(collected) < len(unique_ids) and time.time() < deadline:
                try:
                    resp = response_queue.get(timeout=min(0.5, deadline - time.time()))
                    if resp.player_id in unique_ids:
                        collected[resp.player_id] = resp
                except queue.Empty:
                    continue

            return collected
        finally:
            if "gdi" in self._handlers and capture_gdi in self._handlers["gdi"]:
                self._handlers["gdi"].remove(capture_gdi)

    def search_player_by_name(
        self,
        player_name: str,
        timeout: float = 5.0,
    ) -> SearchPlayerResponse | None:
        request = SearchPlayerRequest(PN=player_name)
        response = self.send(request, wait=True, timeout=timeout)

        if isinstance(response, SearchPlayerResponse):
            return response
        return None
