"""
EmpireClient for EmpireCore.

Uses a threaded Connection class, designed to work well with Discord.py
by not competing for the event loop.
"""

import json
import logging
from typing import Dict, List, Optional, Union

from empire_core.config import (
    LOGIN_DEFAULTS,
    EmpireConfig,
    ServerError,
    default_config,
)
from empire_core.exceptions import LoginCooldownError, LoginError, TimeoutError
from empire_core.network.connection import Connection
from empire_core.protocol.packet import Packet
from empire_core.state.manager import GameState
from empire_core.state.world_models import Movement

logger = logging.getLogger(__name__)


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

        # Wire up packet handler for state updates
        self.connection.on_packet = self._on_packet
        self.connection.on_disconnect = self._on_disconnect

    def _on_packet(self, packet: Packet) -> None:
        """Handle incoming packets for state updates."""
        if packet.command_id and isinstance(packet.payload, dict):
            # GameState.update_from_packet is async in the old code,
            # but we can make a sync version or just update directly
            self._update_state(packet.command_id, packet.payload)

    def _update_state(self, cmd: str, payload: dict) -> None:
        """Sync state update from packet."""
        # Handle movement updates
        if cmd == "gam":
            # Get Army Movements response
            if "M" in payload:
                self.state.movements.clear()
                for m_data in payload["M"]:
                    try:
                        movement = Movement.model_validate(m_data)
                        self.state.movements[movement.MID] = movement
                    except Exception as e:
                        logger.debug(f"Failed to parse movement: {e}")

    def _on_disconnect(self) -> None:
        """Handle disconnect."""
        self.is_logged_in = False
        logger.warning("Client disconnected")

    def login(self) -> None:
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
        logger.debug("Sending version check...")
        ver_packet = f"<msg t='sys'><body action='verChk' r='0'><ver v='{self.config.game_version}' /></body></msg>"
        self.connection.send(ver_packet)

        try:
            response = self.connection.wait_for("apiOK", timeout=self.config.request_timeout)
            logger.debug("Version OK")
        except TimeoutError:
            raise TimeoutError("Version check timed out")

        # 2. Zone Login (XML)
        logger.debug(f"Entering zone {self.config.default_zone}...")
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
            logger.debug("Zone entered (rlu received)")
        except TimeoutError:
            raise TimeoutError("Zone login timed out")

        # 3. AutoJoin Room
        logger.debug("Joining room...")
        join_packet = "<msg t='sys'><body action='autoJoin' r='-1'></body></msg>"
        self.connection.send(join_packet)

        try:
            self.connection.wait_for("joinOK", timeout=self.config.request_timeout)
            logger.debug("Room joined")
        except TimeoutError:
            # joinOK sometimes doesn't come, proceed anyway
            logger.debug("joinOK timed out, proceeding...")

        # 4. XT Login (Real Auth)
        logger.debug(f"Authenticating as {self.username}...")
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

        except TimeoutError:
            raise TimeoutError("XT login timed out")

    def close(self) -> None:
        """Disconnect from the server."""
        self.is_logged_in = False
        self.connection.disconnect()

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
                logger.warning("get_movements timed out")

        return list(self.state.movements.values())

    def send_alliance_chat(self, message: str) -> None:
        """
        Send a message to alliance chat.

        Args:
            message: The message to send
        """
        # Alliance chat command: acm (Alliance Chat Message)
        payload = {"TXT": message}
        packet = Packet.build_xt(self.config.default_zone, "acm", payload)
        self.connection.send(packet)
        logger.debug(f"Sent alliance chat: {message}")

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
                logger.warning(f"get_player_info({player_id}) timed out")
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
                logger.warning(f"get_alliance_info({alliance_id}) timed out")
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

    def subscribe_alliance_chat(self, callback) -> None:
        """
        Subscribe to alliance chat messages.

        Args:
            callback: Function to call with each chat packet
        """
        # Alliance chat incoming: aci (Alliance Chat Incoming) or similar
        # Need to verify the actual command ID from packet captures
        self.connection.subscribe("aci", callback)

    def unsubscribe_alliance_chat(self, callback) -> None:
        """Unsubscribe from alliance chat."""
        self.connection.unsubscribe("aci", callback)
