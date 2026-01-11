"""
EmpireClient for EmpireCore.

Uses a threaded Connection class, designed to work well with Discord.py
by not competing for the event loop.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Callable, List, Optional, TypeVar

from empire_core.config import (
    LOGIN_DEFAULTS,
    EmpireConfig,
    ServerError,
    default_config,
)
from empire_core.exceptions import LoginCooldownError, LoginError, TimeoutError
from empire_core.network.connection import Connection
from empire_core.protocol.models import BaseRequest, BaseResponse, parse_response
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
)
from empire_core.protocol.packet import Packet
from empire_core.services import get_registered_services
from empire_core.state.manager import GameState
from empire_core.state.world_models import Movement

if TYPE_CHECKING:
    from empire_core.services import BaseService

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

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        config: Optional[EmpireConfig] = None,
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
        2. Version Check
        3. Zone Login (XML)
        4. AutoJoin Room
        5. XT Login (Auth)
        """
        if not self.username or not self.password:
            raise ValueError("Username and password are required")

        logger.info(f"Logging in as {self.username}...")

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

        # 2. Zone Login (XML)
        login_packet = (
            f"<msg t='sys'><body action='login' r='0'>"
            f"<login z='{self.config.default_zone}'>"
            f"<nick><![CDATA[]]></nick>"
            f"<pword><![CDATA[undefined%en%0]]></pword>"
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
            # joinOK sometimes doesn't come, proceed anyway
            pass

        # 4. XT Login (Real Auth)
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

            logger.info(f"Logged in as {self.username}")
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
                if response_packet and isinstance(response_packet.payload, dict):
                    return parse_response(command, response_packet.payload)
            except Exception:
                return None

        return None

    # ============================================================
    # Game Commands
    # ============================================================

    def get_movements(self, wait: bool = True, timeout: float = 5.0) -> List[Movement]:
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

    def get_player_info(self, player_id: int, wait: bool = True, timeout: float = 5.0) -> Optional[dict]:
        """
        Get info about a player.

        Args:
            player_id: The player's ID
            wait: If True, wait for response
            timeout: Timeout in seconds

        Returns:
            Player info dict or None
        """
        payload = {"PID": player_id}
        packet = Packet.build_xt(self.config.default_zone, "gpi", payload)
        self.connection.send(packet)

        if wait:
            try:
                response = self.connection.wait_for("gpi", timeout=timeout)
                return response.payload if isinstance(response.payload, dict) else None
            except TimeoutError:
                return None

        return None

    def get_alliance_info(self, alliance_id: int, wait: bool = True, timeout: float = 5.0) -> Optional[dict]:
        """
        Get info about an alliance.

        Args:
            alliance_id: The alliance ID
            wait: If True, wait for response
            timeout: Timeout in seconds

        Returns:
            Alliance info dict or None
        """
        payload = {"AID": alliance_id}
        packet = Packet.build_xt(self.config.default_zone, "gia", payload)
        self.connection.send(packet)

        if wait:
            try:
                response = self.connection.wait_for("gia", timeout=timeout)
                return response.payload if isinstance(response.payload, dict) else None
            except TimeoutError:
                return None

        return None

    # ============================================================
    # Movement Helpers
    # ============================================================

    def get_incoming_attacks(self) -> List[Movement]:
        """Get all incoming attack movements."""
        return [m for m in self.state.movements.values() if m.is_incoming and m.is_attack]

    def get_incoming_movements(self) -> List[Movement]:
        """Get all incoming movements."""
        return [m for m in self.state.movements.values() if m.is_incoming]

    def get_outgoing_movements(self) -> List[Movement]:
        """Get all outgoing movements."""
        return [m for m in self.state.movements.values() if m.is_outgoing]

    # ============================================================
    # Chat Subscription
    # ============================================================

    def get_alliance_chat(self, wait: bool = True, timeout: float = 5.0) -> Optional[dict]:
        """
        Get alliance chat history.

        Args:
            wait: If True, wait for response
            timeout: Timeout in seconds

        Returns:
            Chat history dict or None
        """
        # Alliance chat list command: acl
        packet = Packet.build_xt(self.config.default_zone, "acl", {})
        self.connection.send(packet)

        if wait:
            try:
                response = self.connection.wait_for("acl", timeout=timeout)
                return response.payload if isinstance(response.payload, dict) else None
            except TimeoutError:
                return None

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
                logger.info(f"SDI: Using source castle at {source_x}:{source_y}")
            else:
                logger.warning("SDI: No castles available for source coordinates")
                return None

        logger.info(f"SDI: Sending request TX={target_x}, TY={target_y}, SX={source_x}, SY={source_y}")
        request = GetSupportDefenseRequest(TX=target_x, TY=target_y, SX=source_x, SY=source_y)
        logger.info(f"SDI: Request packet = {request.to_packet(zone=self.config.default_zone)}")
        response = self.send(request, wait=wait, timeout=timeout)
        logger.info(f"SDI: Response = {response}")

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
        timeout: float = 120.0,
        batch_delay: float = 0.5,
    ) -> list[MapAreaItem]:
        """
        Scan a kingdom map with dynamic boundary detection.

        Starts from the bot's castle position and expands outward in waves,
        automatically detecting map boundaries. Sends requests in batches
        with delays to avoid overwhelming the server.

        Args:
            kingdom: Kingdom to scan (GREEN, SANDS, ICE, FIRE, STORM)
            item_types: List of MapItemType values to collect.
                       Defaults to [CASTLE] if None (finds all player castles).
                       Pass empty list [] to collect ALL items.
            timeout: Maximum time to wait for scan completion
            batch_delay: Delay in seconds between request batches

        Returns:
            List of MapAreaItem objects matching the filter.
            Each item has: item_type, x, y, owner_id, raw_data

        Example:
            # Scan for castles (default)
            items = client.scan_kingdom(kingdom=Kingdom.GREEN)
            for item in items:
                print(f"Player {item.owner_id} moving to {item.x}:{item.y}")

            # Scan for monuments and labs
            items = client.scan_kingdom(
                kingdom=Kingdom.GREEN,
                item_types=[MapItemType.MONUMENT, MapItemType.LABORATORY]
            )

            # Scan for everything on the map
            all_items = client.scan_kingdom(kingdom=Kingdom.GREEN, item_types=[])

        Note:
            Uses dynamic boundary detection - adapts to actual map size.
            Sends requests in batches with delays to be gentle on the server.
        """
        import threading
        import time

        CHUNK_SIZE = 90  # Max allowed by GGE server
        MAX_COORD = 20  # Max chunk coordinate (20 * 90 = 1800, well beyond any map)

        # Get starting position
        start_x, start_y = self._get_kingdom_start_position(kingdom)
        start_cx, start_cy = start_x // CHUNK_SIZE, start_y // CHUNK_SIZE

        # Default to castles (type 1 = player main castles)
        if item_types is None:
            item_types = [MapItemType.CASTLE]

        # Empty list means collect everything
        filter_types = set(item_types) if item_types else None

        # Tracking state (protected by lock)
        collected_items: list[MapAreaItem] = []
        chunk_responses: dict[tuple[int, int], bool] = {}  # (cx, cy) -> has_content
        pending_chunks: set[tuple[int, int]] = set()
        lock = threading.Lock()

        filter_desc = f"types={list(item_types)}" if item_types else "all types"
        logger.info(f"Scanning kingdom {kingdom.name} from chunk ({start_cx}, {start_cy}) for {filter_desc}...")

        def chunk_bounds(cx: int, cy: int) -> tuple[int, int, int, int]:
            """Convert chunk coords to world bounds."""
            x1 = cx * CHUNK_SIZE
            y1 = cy * CHUNK_SIZE
            return (x1, y1, x1 + CHUNK_SIZE, y1 + CHUNK_SIZE)

        def handle_gaa_response(packet: Packet) -> None:
            """Process chunk response, collect items."""
            if not isinstance(packet.payload, dict):
                return

            # Extract chunk coords from response
            ax1 = packet.payload.get("AX1", 0)
            ay1 = packet.payload.get("AY1", 0)
            cx, cy = ax1 // CHUNK_SIZE, ay1 // CHUNK_SIZE

            ai_array = packet.payload.get("AI", [])
            has_content = len(ai_array) > 0

            with lock:
                chunk_responses[(cx, cy)] = has_content
                pending_chunks.discard((cx, cy))

                # Collect matching items
                for raw_item in ai_array:
                    if isinstance(raw_item, list) and len(raw_item) >= 4:
                        item = MapAreaItem.from_list(raw_item)

                        # Apply filter (None = collect all)
                        if filter_types is None or item.item_type in filter_types:
                            # Skip unowned items (empty locations, unplaced flags, etc)
                            if item.owner_id == -1:
                                continue
                            collected_items.append(item)

        # Subscribe to gaa responses
        self.connection.subscribe("gaa", handle_gaa_response)

        try:
            visited: set[tuple[int, int]] = set()
            current_wave: set[tuple[int, int]] = {(start_cx, start_cy)}
            total_requests = 0
            waves_processed = 0

            # Track boundaries - stop expanding when we hit edges
            # We consider a direction "bounded" after 2 consecutive empty waves in that direction
            min_x_bounded = False
            max_x_bounded = False
            min_y_bounded = False
            max_y_bounded = False

            start_time = time.time()

            while current_wave:
                if time.time() - start_time > timeout:
                    logger.warning(f"Kingdom scan timeout after {total_requests} requests")
                    break

                # Filter valid chunks for this wave
                valid_chunks = []
                for cx, cy in current_wave:
                    if (cx, cy) in visited:
                        continue
                    # Skip clearly out-of-bounds
                    if cx < 0 or cy < 0 or cx > MAX_COORD or cy > MAX_COORD:
                        continue
                    visited.add((cx, cy))
                    valid_chunks.append((cx, cy))

                if not valid_chunks:
                    break

                # Send this batch
                with lock:
                    pending_chunks.update(valid_chunks)

                for cx, cy in valid_chunks:
                    x1, y1, x2, y2 = chunk_bounds(cx, cy)
                    request = GetMapAreaRequest(KID=kingdom, AX1=x1, AY1=y1, AX2=x2, AY2=y2)
                    self.send(request, wait=False)
                    total_requests += 1

                # Wait for this batch to complete
                batch_start = time.time()
                while True:
                    with lock:
                        if not pending_chunks:
                            break
                    if time.time() - batch_start > 10.0:
                        logger.warning(f"Batch timeout, {len(pending_chunks)} chunks pending")
                        with lock:
                            pending_chunks.clear()
                        break
                    time.sleep(0.02)

                waves_processed += 1

                # Build next wave - expand in all 4 directions from visited chunks
                next_wave: set[tuple[int, int]] = set()

                # Analyze this wave's results for boundary detection
                wave_min_x = min(cx for cx, _ in valid_chunks)
                wave_max_x = max(cx for cx, _ in valid_chunks)
                wave_min_y = min(cy for _, cy in valid_chunks)
                wave_max_y = max(cy for _, cy in valid_chunks)

                # Check if edge chunks were empty (indicates boundary)
                with lock:
                    edge_min_x_empty = all(
                        not chunk_responses.get((wave_min_x, cy), False) for _, cy in valid_chunks if _ == wave_min_x
                    )
                    edge_max_x_empty = all(
                        not chunk_responses.get((wave_max_x, cy), False) for _, cy in valid_chunks if _ == wave_max_x
                    )
                    edge_min_y_empty = all(
                        not chunk_responses.get((cx, wave_min_y), False) for cx, _ in valid_chunks if _ == wave_min_y
                    )
                    edge_max_y_empty = all(
                        not chunk_responses.get((cx, wave_max_y), False) for cx, _ in valid_chunks if _ == wave_max_y
                    )

                # Update boundary flags
                if edge_min_x_empty and wave_min_x <= 1:
                    min_x_bounded = True
                if edge_max_x_empty and wave_max_x >= MAX_COORD - 1:
                    max_x_bounded = True
                if edge_min_y_empty and wave_min_y <= 1:
                    min_y_bounded = True
                if edge_max_y_empty and wave_max_y >= MAX_COORD - 1:
                    max_y_bounded = True

                # Add neighbors for next wave
                for cx, cy in valid_chunks:
                    neighbors = [
                        (cx - 1, cy) if not min_x_bounded else None,
                        (cx + 1, cy) if not max_x_bounded else None,
                        (cx, cy - 1) if not min_y_bounded else None,
                        (cx, cy + 1) if not max_y_bounded else None,
                    ]
                    for neighbor in neighbors:
                        if neighbor and neighbor not in visited:
                            next_wave.add(neighbor)

                # Check if fully bounded
                if min_x_bounded and max_x_bounded and min_y_bounded and max_y_bounded:
                    logger.debug("All boundaries detected, scan complete")
                    break

                current_wave = next_wave

                # Delay between batches
                if current_wave and batch_delay > 0:
                    time.sleep(batch_delay)

        finally:
            self.connection.unsubscribe("gaa", handle_gaa_response)

        logger.info(
            f"Kingdom {kingdom.name} scan complete. "
            f"Sent {total_requests} requests in {waves_processed} waves, "
            f"found {len(collected_items)} items."
        )
        return collected_items

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
