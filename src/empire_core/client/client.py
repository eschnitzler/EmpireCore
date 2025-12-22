import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Awaitable, Callable, Dict, List, Optional, Union

from empire_core.config import (
    LOGIN_DEFAULTS,
    MAP_CHUNK_SIZE,
    EmpireConfig,
    ServerError,
    default_config,
)
from empire_core.network.connection import SFSConnection

if TYPE_CHECKING:
    from empire_core.accounts import Account

from empire_core.automation.alliance_tools import AllianceService, ChatService
from empire_core.automation.battle_reports import BattleReportService
from empire_core.automation.building_queue import BuildingManager
from empire_core.automation.defense_manager import DefenseManager
from empire_core.automation.map_scanner import MapScanner
from empire_core.automation.quest_automation import QuestService
from empire_core.automation.resource_manager import ResourceManager
from empire_core.automation.unit_production import UnitManager
from empire_core.client.actions import GameActionsMixin
from empire_core.client.commands import GameCommandsMixin
from empire_core.client.defense import DefenseService
from empire_core.events.base import PacketEvent
from empire_core.events.manager import EventManager
from empire_core.exceptions import LoginError, TimeoutError
from empire_core.protocol.packet import Packet
from empire_core.state.manager import GameState
from empire_core.state.world_models import Movement
from empire_core.storage.database import GameDatabase
from empire_core.utils.decorators import handle_errors
from empire_core.utils.response_awaiter import ResponseAwaiter

logger = logging.getLogger(__name__)


class EmpireClient(
    GameActionsMixin,
    GameCommandsMixin,
):
    def __init__(self, config: Union[EmpireConfig, "Account", None] = None):
        if config is None:
            self.config = default_config
        elif hasattr(config, "to_empire_config"):
            # Handle Account object
            self.config = config.to_empire_config()
        else:
            # Handle EmpireConfig object
            self.config = config

        self.connection = SFSConnection(self.config.game_url)
        self.username: Optional[str] = self.config.username
        self.is_logged_in = False

        self.events = EventManager()
        self.state = GameState()
        self.db = GameDatabase()

        # Services (Composition)
        self.scanner = MapScanner(self)
        self.resources = ResourceManager(self)
        self.buildings = BuildingManager(self)
        self.units = UnitManager(self)
        self.quests = QuestService(self)
        self.defense_manager = DefenseManager(self)

        # Core Services
        self.defense = DefenseService(self)
        self.reports = BattleReportService(self)
        self.alliance = AllianceService(self)
        self.chat = ChatService(self)

        self.response_awaiter = ResponseAwaiter()
        self.connection.packet_handler = self._on_packet
        self.connection.on_close = self._handle_disconnect

        self._reconnect_task: Optional[asyncio.Task] = None
        self._auto_reconnect = True
        self._max_reconnect_attempts = 10
        self._reconnect_delay = 5.0  # Initial delay
        self._is_reconnecting = False

    async def _handle_disconnect(self):
        """Called when the underlying connection is lost."""
        self.is_logged_in = False
        logger.warning("Client: Connection lost. Resetting logged_in state.")

        if self._auto_reconnect and not self._reconnect_task:
            self._is_reconnecting = True
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        """Internal loop to handle reconnection attempts."""
        attempt = 0
        delay = self._reconnect_delay

        try:
            while attempt < self._max_reconnect_attempts:
                if self.is_logged_in:
                    break

                attempt += 1
                logger.info(f"Client: Reconnection attempt {attempt}/{self._max_reconnect_attempts} in {delay}s...")
                await asyncio.sleep(delay)

                try:
                    # Try to re-login (login() handles connect() + handshake)
                    await self.login()
                    logger.info("Client: Reconnection successful!")
                    return
                except Exception as e:
                    logger.error(f"Client: Reconnection attempt {attempt} failed: {e}")
                    # Exponential backoff
                    delay = min(delay * 2, 60.0)

            logger.critical("Client: Maximum reconnection attempts reached. Giving up.")
        finally:
            self._reconnect_task = None
            self._is_reconnecting = False

    @property
    def event(self):
        """Decorator for registering event handlers."""
        return self.events.listen

    @handle_errors(log_msg="Error processing packet", re_raise=False)
    async def _on_packet(self, packet: Packet):
        """Global packet handler called by connection."""
        logger.debug(f"Client received packet: {packet.command_id}")

        if packet.command_id == "gaa":
            logger.debug(f"GAA Payload: {packet.payload}")

        # Update State
        if packet.command_id and isinstance(packet.payload, dict):
            await self.state.update_from_packet(packet.command_id, packet.payload)

        # Notify response awaiter - Pass FULL packet so error_code is available
        if packet.command_id:
            self.response_awaiter.set_response(packet.command_id, packet)

        pkt_event = PacketEvent(
            command_id=packet.command_id or "unknown",
            payload=packet.payload,
            is_xml=packet.is_xml,
        )
        await self.events.emit(pkt_event)

    @handle_errors(log_msg="Login failed")
    async def login(self, username: Optional[str] = None, password: Optional[str] = None):
        """
        Performs the full login sequence:
        Connect -> Version Check -> XML Login (Zone) -> AutoJoin -> XT Login (Auth)
        """
        username = username or self.config.username
        password = password or self.config.password

        if not username or not password:
            raise ValueError("Username and password must be provided")

        self.username = username

        # 0. Initialize Database & Services
        await self.db.initialize()
        await self.scanner.initialize()

        if not self.connection.connected:
            await self.connection.connect()

        # 1. Version Check
        logger.info("Handshake: Sending Version Check...")
        ver_waiter = self.connection.create_waiter("apiOK", predicate=lambda p: p.is_xml and p.command_id == "apiOK")

        ver_packet = f"<msg t='sys'><body action='verChk' r='0'><ver v='{self.config.game_version}' /></body></msg>"
        await self.connection.send(ver_packet)

        try:
            await asyncio.wait_for(ver_waiter, timeout=self.config.request_timeout)
            logger.info("Handshake: Version OK.")
        except asyncio.TimeoutError:
            raise TimeoutError("Handshake: Version Check timed out.")

        # 2. XML Login (Zone Entry)
        logger.info(f"Handshake: Entering Zone {self.config.default_zone}...")

        login_packet = (
            f"<msg t='sys'><body action='login' r='0'>"
            f"<login z='{self.config.default_zone}'>"
            f"<nick><![CDATA[]]></nick>"
            f"<pword><![CDATA[undefined%en%0]]></pword>"
            f"</login></body></msg>"
        )

        # Wait for 'rlu' (Room List Update)
        rlu_waiter = self.connection.create_waiter("rlu")

        await self.connection.send(login_packet)

        try:
            await asyncio.wait_for(rlu_waiter, timeout=self.config.login_timeout)
            logger.info("Handshake: Received Room List (Zone Entered).")
        except asyncio.TimeoutError:
            raise TimeoutError("Handshake: Zone Login (rlu) timed out.")

        # 3. AutoJoin (Room Join)
        logger.info("Handshake: Joining Room (AutoJoin)...")
        join_packet = "<msg t='sys'><body action='autoJoin' r='-1'></body></msg>"

        join_ok_waiter = self.connection.create_waiter(
            "joinOK", predicate=lambda p: p.is_xml and p.command_id == "joinOK"
        )

        await self.connection.send(join_packet)

        try:
            await asyncio.wait_for(join_ok_waiter, timeout=self.config.request_timeout)
            logger.info("Handshake: Room Joined (joinOK received).")
        except asyncio.TimeoutError:
            logger.warning("Handshake: joinOK timed out, but proceeding...")

        # 4. XT Login (Real Auth)
        logger.info(f"Handshake: Authenticating as {username}...")

        xt_login_payload = {
            **LOGIN_DEFAULTS,
            "NOM": username,
            "PW": password,
        }

        xt_packet = f"%xt%{self.config.default_zone}%lli%1%{json.dumps(xt_login_payload)}%"

        # Wait for lli response
        lli_waiter = self.connection.create_waiter("lli")
        await self.connection.send(xt_packet)

        try:
            lli_packet = await asyncio.wait_for(lli_waiter, timeout=self.config.login_timeout)

            # Check status
            if lli_packet.error_code != 0:
                # Check for cooldown
                if lli_packet.error_code == ServerError.LOGIN_COOLDOWN:
                    cooldown = 0
                    if isinstance(lli_packet.payload, dict):
                        cooldown = int(lli_packet.payload.get("CD", 0))

                    logger.warning(f"Handshake: Login Slowdown active. Wait {cooldown}s.")
                    from empire_core.exceptions import LoginCooldownError

                    raise LoginCooldownError(cooldown)

                logger.error(f"Handshake: Auth Failed with status {lli_packet.error_code}")
                raise LoginError(f"Auth Failed with status {lli_packet.error_code}")

            logger.info("Handshake: Authenticated.")
        except asyncio.TimeoutError:
            raise TimeoutError("XT Login timed out.")

        self.is_logged_in = True
        logger.info("Handshake: Ready.")

    @handle_errors(log_msg="Error getting map chunk")
    async def get_map_chunk(self, kingdom: int, x: int, y: int):
        """
        Requests a chunk of the map.

        Args:
            kingdom: Kingdom ID (0=Green, 2=Ice, 1=Sands, 3=Fire)
            x: Top-Left X
            y: Top-Left Y
        """
        # Command: gaa (Get Area)
        payload = {
            "KID": kingdom,
            "AX1": x,
            "AY1": y,
            "AX2": x + MAP_CHUNK_SIZE,
            "AY2": y + MAP_CHUNK_SIZE,
        }

        packet = Packet.build_xt(self.config.default_zone, "gaa", payload)
        await self.connection.send(packet)

    @handle_errors(log_msg="Error getting movements")
    async def get_movements(self):
        """
        Requests list of army movements.
        """
        packet = Packet.build_xt(self.config.default_zone, "gam", {})
        await self.connection.send(packet)

    @handle_errors(log_msg="Error getting detailed castle info")
    async def get_detailed_castle_info(self):
        """
        Requests detailed information for all own castles (Resources, Units, etc.).
        """
        packet = Packet.build_xt(self.config.default_zone, "dcl", {})
        await self.connection.send(packet)

    @handle_errors(log_msg="Error closing client", re_raise=False)
    async def close(self):
        self._auto_reconnect = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
        await self.connection.disconnect()
        await self.db.close()

    async def wait_until_ready(self, timeout: float = 60.0):
        """Wait until the client is logged in and ready."""
        if self.is_logged_in:
            return

        start = time.time()
        while not self.is_logged_in:
            if (time.time() - start) > timeout:
                raise TimeoutError("Timed out waiting for client to be ready")

            if not self._is_reconnecting and not self.connection.connected:
                # If we are not logged in, not reconnecting, and not connected,
                # then we've either given up or auto-reconnect is off.
                raise RuntimeError("Client not connected and not attempting reconnection.")

            await asyncio.sleep(0.5)

    # ============================================================
    # Movement Tracking Methods
    # ============================================================

    @property
    def movements(self) -> Dict[int, Movement]:
        """Get all currently tracked movements."""
        return self.state.movements

    def get_all_movements(self) -> List[Movement]:
        """Get all tracked movements as a list."""
        return self.state.get_all_movements()

    def get_incoming_movements(self) -> List[Movement]:
        """Get all incoming movements (attacks, supports, transports to us)."""
        return self.state.get_incoming_movements()

    def get_outgoing_movements(self) -> List[Movement]:
        """Get all outgoing movements (our attacks, transports, etc.)."""
        return self.state.get_outgoing_movements()

    def get_returning_movements(self) -> List[Movement]:
        """Get all returning movements (armies coming back)."""
        return self.state.get_returning_movements()

    def get_incoming_attacks(self) -> List[Movement]:
        """Get all incoming attack movements (high priority)."""
        return self.state.get_incoming_attacks()

    def get_movements_to_castle(self, castle_id: int) -> List[Movement]:
        """Get all movements targeting a specific castle."""
        return self.state.get_movements_to_castle(castle_id)

    def get_movements_from_castle(self, castle_id: int) -> List[Movement]:
        """Get all movements originating from a specific castle."""
        return self.state.get_movements_from_castle(castle_id)

    def get_next_arrival(self) -> Optional[Movement]:
        """Get the movement that will arrive soonest."""
        return self.state.get_next_arrival()

    def get_movement(self, movement_id: int) -> Optional[Movement]:
        """Get a specific movement by ID."""
        return self.state.get_movement_by_id(movement_id)

    @handle_errors(log_msg="Error refreshing movements")
    async def refresh_movements(self, wait: bool = True, timeout: float = 5.0) -> List[Movement]:
        """
        Refresh movement data from server.

        Args:
            wait: Wait for response before returning
            timeout: Timeout in seconds when waiting

        Returns:
            List of all current movements
        """
        if wait:
            self.response_awaiter.create_waiter("gam")

        await self.get_movements()

        if wait:
            try:
                await self.response_awaiter.wait_for("gam", timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("Refresh movements timed out")

        return self.get_all_movements()

    async def watch_movements(
        self,
        interval: float = 5.0,
        callback: Optional[Callable[[List[Movement]], Awaitable[None]]] = None,
        stop_event: Optional[asyncio.Event] = None,
    ):
        """
        Continuously poll for movement updates.

        Args:
            interval: Polling interval in seconds
            callback: Optional async callback to call with movements list
            stop_event: Optional event to signal stopping
        """
        stop = stop_event or asyncio.Event()

        while not stop.is_set():
            try:
                movements = await self.refresh_movements(wait=True, timeout=interval)

                if callback:
                    await callback(movements)

                # Check for incoming attacks
                attacks = self.get_incoming_attacks()
                if attacks:
                    for attack in attacks:
                        logger.warning(
                            f"Incoming attack! ID: {attack.MID}, "
                            f"Target: {attack.target_area_id}, "
                            f"Time: {attack.format_time_remaining()}"
                        )

            except Exception as e:
                logger.error(f"Error in movement watch: {e}")

            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                continue

    def format_movements_summary(self) -> str:
        """Get a formatted summary of all movements."""
        lines = []

        incoming = self.get_incoming_movements()
        outgoing = self.get_outgoing_movements()
        returning = self.get_returning_movements()

        if not incoming and not outgoing and not returning:
            return "No active movements."

        if incoming:
            lines.append(f"Incoming ({len(incoming)}):")
            for m in sorted(incoming, key=lambda x: x.time_remaining):
                lines.append(f"  - {m.movement_type_name} from {m.source_area_id}: {m.format_time_remaining()}")

        if outgoing:
            lines.append(f"Outgoing ({len(outgoing)}):")
            for m in sorted(outgoing, key=lambda x: x.time_remaining):
                lines.append(f"  - {m.movement_type_name} to {m.target_area_id}: {m.format_time_remaining()}")

        if returning:
            lines.append(f"Returning ({len(returning)}):")
            for m in sorted(returning, key=lambda x: x.time_remaining):
                lines.append(f"  - From {m.source_area_id}: {m.format_time_remaining()}")

        return "\n".join(lines)
