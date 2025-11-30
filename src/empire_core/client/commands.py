"""
Additional game commands.
"""
import json
import logging
from typing import Optional
from empire_core.exceptions import ActionError

logger = logging.getLogger(__name__)


class GameCommands:
    """Additional game commands beyond actions."""
    
    def __init__(self, client):
        self.client = client
        self.config = client.config
    
    async def cancel_building(self, castle_id: int, queue_id: int) -> bool:
        """Cancel building upgrade."""
        payload = {"AID": castle_id, "QID": queue_id}
        packet = f"%xt%{self.config.default_zone}%cbu%1%{json.dumps(payload)}%"
        
        try:
            await self.client.connection.send(packet)
            logger.info(f"Cancelled building in castle {castle_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel building: {e}")
            raise ActionError(f"Cancel failed: {e}")
    
    async def speed_up_building(self, castle_id: int, queue_id: int) -> bool:
        """Speed up building with rubies."""
        payload = {"AID": castle_id, "QID": queue_id}
        packet = f"%xt%{self.config.default_zone}%sbu%1%{json.dumps(payload)}%"
        
        try:
            await self.client.connection.send(packet)
            logger.info(f"Speeding up building in castle {castle_id}")
            return True
        except Exception as e:
            raise ActionError(f"Speed up failed: {e}")
    
    async def collect_quest_reward(self, quest_id: int) -> bool:
        """Collect quest reward."""
        payload = {"QID": quest_id}
        packet = f"%xt%{self.config.default_zone}%cqr%1%{json.dumps(payload)}%"
        
        try:
            await self.client.connection.send(packet)
            logger.info(f"Collected quest {quest_id} reward")
            return True
        except Exception as e:
            raise ActionError(f"Quest collection failed: {e}")
    
    async def recall_army(self, movement_id: int) -> bool:
        """Recall/cancel army movement."""
        payload = {"MID": movement_id}
        packet = f"%xt%{self.config.default_zone}%cam%1%{json.dumps(payload)}%"
        
        try:
            await self.client.connection.send(packet)
            logger.info(f"Recalled movement {movement_id}")
            return True
        except Exception as e:
            raise ActionError(f"Recall failed: {e}")
    
    async def send_message(self, player_id: int, subject: str, message: str) -> bool:
        """Send message to player."""
        payload = {
            "RID": player_id,
            "S": subject,
            "M": message
        }
        packet = f"%xt%{self.config.default_zone}%smg%1%{json.dumps(payload)}%"
        
        try:
            await self.client.connection.send(packet)
            logger.info(f"Sent message to player {player_id}")
            return True
        except Exception as e:
            raise ActionError(f"Send message failed: {e}")
    
    async def read_mail(self, mail_id: int) -> bool:
        """Mark mail as read."""
        payload = {"MID": mail_id}
        packet = f"%xt%{self.config.default_zone}%rma%1%{json.dumps(payload)}%"
        
        try:
            await self.client.connection.send(packet)
            return True
        except Exception as e:
            raise ActionError(f"Read mail failed: {e}")
    
    async def delete_mail(self, mail_id: int) -> bool:
        """Delete mail."""
        payload = {"MID": mail_id}
        packet = f"%xt%{self.config.default_zone}%dma%1%{json.dumps(payload)}%"
        
        try:
            await self.client.connection.send(packet)
            return True
        except Exception as e:
            raise ActionError(f"Delete mail failed: {e}")
