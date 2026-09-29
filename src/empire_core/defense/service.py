"""
Defense service: the defense of an alliance member's castle.
"""

from __future__ import annotations

import logging

from empire_core.defense.models import GetSupportDefenseRequest, GetSupportDefenseResponse
from empire_core.services.base import BaseService, register_service

logger = logging.getLogger(__name__)


@register_service("defense")
class DefenseService(BaseService):
    """
    Service for castle defense info.

    Accessible via client.defense after auto-registration.
    """

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
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        # Default to bot's main castle as source
        if source_x is None or source_y is None:
            main_castle = next(iter(self.client.state.get_castles()), None)
            if main_castle is None:
                raise ValueError("No source coordinates given and no own castles in state")
            source_x = main_castle.x
            source_y = main_castle.y
            logger.debug(f"SDI: Using source castle at {source_x}:{source_y}")

        request = GetSupportDefenseRequest(TX=target_x, TY=target_y, SX=source_x, SY=source_y)
        return self.request(request, GetSupportDefenseResponse, timeout=timeout)
