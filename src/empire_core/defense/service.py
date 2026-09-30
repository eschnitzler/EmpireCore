"""
The defense of your own castles and of castles you could support.
"""

from __future__ import annotations

import logging

from empire_core.defense.models import (
    GetDefenseRequest,
    GetDefenseResponse,
    GetSupportDefenseRequest,
    GetSupportDefenseResponse,
)
from empire_core.enums import Kingdom
from empire_core.services.base import BaseService

logger = logging.getLogger(__name__)


class DefenseService(BaseService):
    """
    The defense of your own castles and of castles you could support.

    Reached as client.defense.
    """

    def get_own_defense(
        self,
        castle_x: int,
        castle_y: int,
        castle_id: int,
        kingdom: Kingdom | None = None,
        timeout: float = 5.0,
    ) -> GetDefenseResponse:
        """
        Get the keep, wall and moat setup of one of your own castles.

        Args:
            castle_x: The castle's map x
            castle_y: The castle's map y
            castle_id: The castle's id: ``CastleInfo.castle_id`` from ``client.castle.get_all()``
                or ``Castle.id`` from ``client.state.get_castles()``
            kingdom: The castle's kingdom; None sends -1, as the client does
            timeout: Timeout in seconds

        Returns:
            The ``dfc`` reply: units, wall, keep, moat, priorities and castellan.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SDefenceCompleteVO`` (bundle line 32769), sent by
        ``CastleDefenceDialog.updateDefenceData`` (bundle line 15978)
        """
        request = GetDefenseRequest(CX=castle_x, CY=castle_y, AID=castle_id, KID=kingdom)
        return self.request(request, GetDefenseResponse, timeout=timeout)

    def get_support_defense_info(
        self,
        target_x: int,
        target_y: int,
        source_x: int | None = None,
        source_y: int | None = None,
        timeout: float = 5.0,
    ) -> GetSupportDefenseResponse:
        """
        Get the defense of another alliance member's castle, as the client asks before sending support.

        The server rejects your own castle with NO_SELF_DESTRUCTION (92); use
        :meth:`get_own_defense` for that.

        Args:
            target_x: Map x of the castle to support
            target_y: Map y of the castle to support
            source_x: Map x of your castle the support would leave from (defaults to your first castle)
            source_y: Map y of your castle the support would leave from (defaults to your first castle)
            timeout: Timeout in seconds

        Returns:
            GetSupportDefenseResponse with defense info.
            Use response.get_total_defenders() to get total troop count.

        Raises:
            ValueError: No source coordinates given and no own castle known
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SSupportDefenceInfoVO`` (bundle line 72078), sent by
        ``CastleStartAttackDialog.supportDefence`` (bundle line 14833)
        """
        if source_x is None or source_y is None:
            main_castle = next(iter(self.client.state.get_castles()), None)
            if main_castle is None:
                raise ValueError("No source coordinates given and no own castles in state")
            source_x = main_castle.x
            source_y = main_castle.y
            logger.debug(f"SDI: Using source castle at {source_x}:{source_y}")

        request = GetSupportDefenseRequest(TX=target_x, TY=target_y, SX=source_x, SY=source_y)
        return self.request(request, GetSupportDefenseResponse, timeout=timeout)
