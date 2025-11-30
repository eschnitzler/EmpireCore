"""
Advanced alliance management tools.
"""
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)


@dataclass
class AllianceMember:
    """Alliance member info."""
    player_id: int
    name: str
    level: int
    rank: str
    online: bool = False
    last_seen: int = 0


class AllianceManager:
    """Manage alliance operations."""
    
    def __init__(self, client: EmpireClient):
        self.client = client
        self.members: Dict[int, AllianceMember] = {}
    
    async def get_member_list(self):
        """Get alliance member list."""
        # Command: gal (get alliance list)
        packet = f"%xt%{self.client.config.default_zone}%gal%1%{{}}%"
        await self.client.connection.send(packet)
    
    async def send_alliance_message(self, message: str):
        """Send message to alliance chat."""
        import json
        payload = {"M": message}
        packet = f"%xt%{self.client.config.default_zone}%sam%1%{json.dumps(payload)}%"
        await self.client.connection.send(packet)
        logger.info(f"Sent alliance message: {message}")
    
    async def coordinate_attack(
        self,
        target_x: int,
        target_y: int,
        target_name: str
    ):
        """Coordinate attack with alliance."""
        message = f"Attack planned: {target_name} ({target_x},{target_y})"
        await self.send_alliance_message(message)
    
    def get_online_members(self) -> List[AllianceMember]:
        """Get online members."""
        return [m for m in self.members.values() if m.online]
    
    def get_members_by_rank(self, rank: str) -> List[AllianceMember]:
        """Get members by rank."""
        return [m for m in self.members.values() if m.rank == rank]


class ChatManager:
    """Manage chat functionality."""
    
    def __init__(self, client: EmpireClient):
        self.client = client
        self.chat_history: List[Dict] = []
    
    async def send_chat(self, message: str, channel: str = "global"):
        """Send chat message."""
        import json
        payload = {
            "M": message,
            "C": channel
        }
        packet = f"%xt%{self.client.config.default_zone}%sct%1%{json.dumps(payload)}%"
        await self.client.connection.send(packet)
        logger.info(f"Sent chat: {message}")
    
    async def send_private_message(self, player_id: int, message: str):
        """Send private message."""
        import json
        payload = {
            "RID": player_id,
            "M": message
        }
        packet = f"%xt%{self.client.config.default_zone}%spm%1%{json.dumps(payload)}%"
        await self.client.connection.send(packet)
    
    def on_chat_message(self, data: Dict):
        """Handle incoming chat message."""
        self.chat_history.append({
            'timestamp': data.get('T', 0),
            'player': data.get('N', ''),
            'message': data.get('M', ''),
            'channel': data.get('C', 'global')
        })
        
        # Keep last 100 messages
        if len(self.chat_history) > 100:
            self.chat_history = self.chat_history[-100:]
