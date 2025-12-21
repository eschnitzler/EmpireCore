"""
Alliance management and chat tools.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from empire_core.protocol.packet import Packet

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


@dataclass
class AllianceMember:
    """Alliance member info."""

    player_id: int
    name: str
    level: int = 0
    rank: str = "member"
    online: bool = False
    last_seen: int = 0
    castle_count: int = 0


@dataclass
class ChatMessage:
    """A chat message."""

    timestamp: int
    player_name: str
    player_id: int
    message: str
    channel: str = "global"


class AllianceService:
    """Service for alliance operations."""

    def __init__(self, client: "EmpireClient"):
        self.client = client
        self.alliance_members: Dict[int, AllianceMember] = {}
        self._alliance_callbacks: List[Callable[[List[AllianceMember]], None]] = []

    @property
    def alliance(self):
        """Get current alliance info from player state."""
        if self.client.state.local_player:
            return self.client.state.local_player.alliance
        return None

    @property
    def alliance_id(self) -> Optional[int]:
        """Get alliance ID."""
        if self.client.state.local_player:
            return self.client.state.local_player.AID
        return None

    @property
    def is_in_alliance(self) -> bool:
        """Check if player is in an alliance."""
        return self.alliance_id is not None and self.alliance_id > 0

    async def refresh_members(self) -> bool:
        """Refresh alliance member list from server."""
        if not self.is_in_alliance:
            logger.warning("Not in an alliance")
            return False

        packet = Packet.build_xt(self.client.config.default_zone, "gal", {})
        await self.client.connection.send(packet)
        return True

    async def send_alliance_chat(self, message: str) -> bool:
        """Send message to alliance chat."""
        if not self.is_in_alliance:
            logger.warning("Not in an alliance")
            return False

        packet = Packet.build_xt(self.client.config.default_zone, "sam", {"M": message})
        await self.client.connection.send(packet)
        logger.info(f"Sent alliance message: {message[:50]}...")
        return True

    async def coordinate_attack(self, target_x: int, target_y: int, target_name: str = "Target") -> bool:
        """Send attack coordination message to alliance."""
        message = f"⚔️ Attack: {target_name} at ({target_x}, {target_y})"
        return await self.send_alliance_chat(message)

    async def request_support(self, castle_id: int, castle_name: str, reason: str = "under attack") -> bool:
        """Request support from alliance members."""
        message = f"🛡️ Need support at {castle_name} (ID: {castle_id}) - {reason}"
        return await self.send_alliance_chat(message)

    async def donate_resources(
        self,
        alliance_id: int,
        kingdom_id: int = 0,
        wood: int = 0,
        stone: int = 0,
        food: int = 0,
        wait_for_response: bool = False,
        timeout: float = 5.0,
    ) -> bool:
        """
        Donate resources to the alliance.

        Args:
            alliance_id: ID of the alliance to donate to.
            kingdom_id: Kingdom ID (KID, default 0).
            wood: Amount of wood to donate.
            stone: Amount of stone to donate.
            food: Amount of food to donate.
            wait_for_response: Whether to wait for server confirmation.
            timeout: Response timeout in seconds.

        Returns:
            bool: True if donation sent successfully.
        """
        if wood <= 0 and stone <= 0 and food <= 0:
            raise ValueError("Must specify at least one resource to donate.")

        logger.info(f"Donating {wood}W/{stone}S/{food}F to alliance {alliance_id} in K{kingdom_id}")

        payload = {
            "AID": alliance_id,
            "KID": kingdom_id,
            "RV": {
                "O": wood,  # Wood
                "G": stone,  # Stone
                "C": food,  # Food
            },
        }

        response = await self.client._send_command_generic(
            "ado", payload, "Alliance Donation", wait_for_response, timeout
        )

        return response

    def get_online_members(self) -> List[AllianceMember]:
        """Get online alliance members."""
        return [m for m in self.alliance_members.values() if m.online]

    def get_members_by_rank(self, rank: str) -> List[AllianceMember]:
        """Get members by rank."""
        return [m for m in self.alliance_members.values() if m.rank.lower() == rank.lower()]

    def get_member(self, player_id: int) -> Optional[AllianceMember]:
        """Get specific member by ID."""
        return self.alliance_members.get(player_id)

    def get_member_count(self) -> int:
        """Get total member count."""
        return len(self.alliance_members)

    def update_members(self, members_data: List[Dict[str, Any]]):
        """Update member list from server data."""
        self.alliance_members.clear()
        for m_data in members_data:
            member = AllianceMember(
                player_id=m_data.get("PID", 0),
                name=m_data.get("N", "Unknown"),
                level=m_data.get("L", 0),
                rank=m_data.get("R", "member"),
                online=m_data.get("O", False),
                last_seen=m_data.get("LS", 0),
                castle_count=m_data.get("CC", 0),
            )
            self.alliance_members[member.player_id] = member

        logger.info(f"Updated {len(self.alliance_members)} alliance members")

        # Notify callbacks
        for callback in self._alliance_callbacks:
            try:
                callback(list(self.alliance_members.values()))
            except Exception as e:
                logger.error(f"Member callback error: {e}")

    def on_members_updated(self, callback: Callable[[List[AllianceMember]], None]):
        """Register callback for when member list updates."""
        self._alliance_callbacks.append(callback)


class ChatService:
    """Service for chat functionality."""

    MAX_HISTORY = 100

    def __init__(self, client: "EmpireClient"):
        self.client = client
        self.chat_history: List[ChatMessage] = []
        self._chat_callbacks: List[Callable[[ChatMessage], None]] = []

    async def send_global_chat(self, message: str) -> bool:
        """Send message to global chat."""
        return await self._send_chat(message, "global")

    async def send_kingdom_chat(self, message: str, kingdom_id: int = 0) -> bool:
        """Send message to kingdom chat."""
        return await self._send_chat(message, f"kingdom_{kingdom_id}")

    async def send_private_message(self, player_id: int, message: str) -> bool:
        """Send private message to a player."""
        packet = Packet.build_xt(
            self.client.config.default_zone,
            "spm",
            {"RID": player_id, "M": message},
        )
        await self.client.connection.send(packet)
        logger.info(f"Sent PM to {player_id}")
        return True

    async def _send_chat(self, message: str, channel: str) -> bool:
        """Send chat message to channel."""
        packet = Packet.build_xt(
            self.client.config.default_zone,
            "sct",
            {"M": message, "C": channel},
        )
        await self.client.connection.send(packet)
        logger.debug(f"Sent to {channel}: {message[:50]}...")
        return True

    def on_chat_message(self, callback: Callable[[ChatMessage], None]):
        """Register callback for incoming messages."""
        self._chat_callbacks.append(callback)

    def handle_incoming_chat(self, data: Dict[str, Any]):
        """Handle incoming chat message from server."""
        msg = ChatMessage(
            timestamp=data.get("T", 0),
            player_name=data.get("N", ""),
            player_id=data.get("PID", 0),
            message=data.get("M", ""),
            channel=data.get("C", "global"),
        )
        self.chat_history.append(msg)

        # Trim history
        if len(self.chat_history) > self.MAX_HISTORY:
            self.chat_history = self.chat_history[-self.MAX_HISTORY :]

        # Notify callbacks
        for callback in self._chat_callbacks:
            try:
                callback(msg)
            except Exception as e:
                logger.error(f"Chat callback error: {e}")

    def get_chat_history(self, channel: Optional[str] = None, limit: int = 50) -> List[ChatMessage]:
        """Get chat history, optionally filtered by channel."""
        messages = self.chat_history
        if channel:
            messages = [m for m in messages if m.channel == channel]
        return messages[-limit:]

    def search_chat_history(self, keyword: str) -> List[ChatMessage]:
        """Search chat history for keyword."""
        keyword_lower = keyword.lower()
        return [m for m in self.chat_history if keyword_lower in m.message.lower()]
