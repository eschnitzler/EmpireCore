"""
Action commands for performing game actions (attack, transport, build, etc.)
"""
import json
import logging
from typing import Dict, Optional, Any
from empire_core.exceptions import ActionError

logger = logging.getLogger(__name__)


class GameActions:
    """Handles game action commands."""
    
    def __init__(self, client):
        """
        Initialize with reference to client.
        
        Args:
            client: EmpireClient instance
        """
        self.client = client
        self.config = client.config
    
    async def send_attack(
        self,
        origin_castle_id: int,
        target_area_id: int,
        units: Dict[int, int],
        kingdom_id: int = 0,
        wait_for_response: bool = False,
        timeout: float = 5.0
    ) -> bool:
        """
        Send an attack from one castle to a target.
        
        Args:
            origin_castle_id: ID of attacking castle
            target_area_id: ID of target area
            units: Dictionary of {unit_id: count}
            kingdom_id: Kingdom ID (default 0)
            wait_for_response: Wait for server confirmation (default False)
            timeout: Response timeout in seconds (default 5.0)
            
        Returns:
            bool: True if attack sent successfully
            
        Raises:
            ActionError: If attack fails
        """
        logger.info(f"Sending attack from {origin_castle_id} to {target_area_id}")
        
        # Validate inputs
        if not units or all(count <= 0 for count in units.values()):
            raise ActionError("Must specify at least one unit")
        
        # Build payload
        payload = {
            "OID": origin_castle_id,
            "TID": target_area_id,
            "UN": units,
            "TT": 1,  # 1 = Attack
            "KID": kingdom_id
        }
        
        # Create response waiter if needed
        if wait_for_response:
            waiter_id = self.client.response_awaiter.create_waiter('att')
        
        # Send command
        packet = f"%xt%{self.config.default_zone}%att%1%{json.dumps(payload)}%"
        
        try:
            await self.client.connection.send(packet)
            logger.info(f"Attack command sent successfully")
            
            if wait_for_response:
                logger.debug("Waiting for attack response...")
                response = await self.client.response_awaiter.wait_for('att', timeout)
                logger.info(f"Attack response received: {response}")
                return self._parse_attack_response(response)
            
            return True
        except Exception as e:
            if wait_for_response:
                self.client.response_awaiter.cancel_command('att')
            logger.error(f"Failed to send attack: {e}")
            raise ActionError(f"Attack failed: {e}")
    
    def _parse_attack_response(self, response: Any) -> bool:
        """Parse attack response from server."""
        if isinstance(response, dict):
            # Check for success indicators
            if response.get("success") or response.get("MID"):
                return True
            # Check for error
            if response.get("error"):
                raise ActionError(f"Server rejected attack: {response.get('error')}")
        return True
    
    async def send_transport(
        self,
        origin_castle_id: int,
        target_area_id: int,
        wood: int = 0,
        stone: int = 0,
        food: int = 0,
        wait_for_response: bool = False,
        timeout: float = 5.0
    ) -> bool:
        """
        Send resources from one castle to another.
        
        Args:
            origin_castle_id: ID of sending castle
            target_area_id: ID of receiving area
            wood: Amount of wood
            stone: Amount of stone
            food: Amount of food
            wait_for_response: Wait for server confirmation (default False)
            timeout: Response timeout in seconds (default 5.0)
            
        Returns:
            bool: True if transport sent successfully
            
        Raises:
            ActionError: If transport fails
        """
        logger.info(f"Sending transport from {origin_castle_id} to {target_area_id}")
        
        # Validate inputs
        if wood <= 0 and stone <= 0 and food <= 0:
            raise ActionError("Must send at least one resource")
        
        # Build payload
        payload = {
            "OID": origin_castle_id,
            "TID": target_area_id,
            "RES": {
                "1": wood,
                "2": stone,
                "3": food
            }
        }
        
        # Create response waiter if needed
        if wait_for_response:
            waiter_id = self.client.response_awaiter.create_waiter('tra')
        
        # Send command
        packet = f"%xt%{self.config.default_zone}%tra%1%{json.dumps(payload)}%"
        
        try:
            await self.client.connection.send(packet)
            logger.info(f"Transport command sent successfully")
            
            if wait_for_response:
                logger.debug("Waiting for transport response...")
                response = await self.client.response_awaiter.wait_for('tra', timeout)
                logger.info(f"Transport response received: {response}")
                return self._parse_transport_response(response)
            
            return True
        except Exception as e:
            if wait_for_response:
                self.client.response_awaiter.cancel_command('tra')
            logger.error(f"Failed to send transport: {e}")
            raise ActionError(f"Transport failed: {e}")
    
    def _parse_transport_response(self, response: Any) -> bool:
        """Parse transport response from server."""
        if isinstance(response, dict):
            if response.get("success") or response.get("MID"):
                return True
            if response.get("error"):
                raise ActionError(f"Server rejected transport: {response.get('error')}")
        return True
    
    async def upgrade_building(
        self,
        castle_id: int,
        building_id: int,
        building_type: Optional[int] = None
    ) -> bool:
        """
        Upgrade or build a building in a castle.
        
        Args:
            castle_id: ID of castle
            building_id: ID of building to upgrade
            building_type: Type of building (if constructing new)
            
        Returns:
            bool: True if upgrade started successfully
            
        Raises:
            ActionError: If upgrade fails
        """
        logger.info(f"Upgrading building {building_id} in castle {castle_id}")
        
        # Build payload
        payload = {
            "AID": castle_id,
            "BID": building_id
        }
        
        if building_type is not None:
            payload["BTYP"] = building_type
        
        # Send command
        packet = f"%xt%{self.config.default_zone}%bui%1%{json.dumps(payload)}%"
        
        try:
            await self.client.connection.send(packet)
            logger.info(f"Building upgrade command sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to upgrade building: {e}")
            raise ActionError(f"Building upgrade failed: {e}")
    
    async def recruit_units(
        self,
        castle_id: int,
        unit_id: int,
        count: int
    ) -> bool:
        """
        Recruit/train units in a castle.
        
        Args:
            castle_id: ID of castle
            unit_id: ID of unit type to recruit
            count: Number of units to recruit
            
        Returns:
            bool: True if recruitment started successfully
            
        Raises:
            ActionError: If recruitment fails
        """
        logger.info(f"Recruiting {count}x unit {unit_id} in castle {castle_id}")
        
        if count <= 0:
            raise ActionError("Must recruit at least one unit")
        
        # Build payload
        payload = {
            "AID": castle_id,
            "UID": unit_id,
            "CNT": count
        }
        
        # Send command (command name might be 'rcu' for recruit)
        packet = f"%xt%{self.config.default_zone}%rcu%1%{json.dumps(payload)}%"
        
        try:
            await self.client.connection.send(packet)
            logger.info(f"Unit recruitment command sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to recruit units: {e}")
            raise ActionError(f"Unit recruitment failed: {e}")
