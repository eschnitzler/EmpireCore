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
                    except Exception:
                        pass

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

        except TimeoutError:
            raise TimeoutError("XT login timed out")

    def close(self) -> None:
        """Disconnect from the server."""
        self.is_logged_in = False
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
