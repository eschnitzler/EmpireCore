"""
The defense of your own castles and of castles you could support.

The setters take the keep, wall and moat as ``get_own_defense`` returns them,
so a setup can be read, changed and sent back.
"""

from __future__ import annotations

import logging

from empire_core.defense.models import (
    ChangeKeepDefenseRequest,
    ChangeMoatDefenseRequest,
    ChangeWallDefenseRequest,
    GetDefenseRequest,
    GetDefenseResponse,
    GetSupportDefenseRequest,
    GetSupportDefenseResponse,
    KeepDefense,
    MoatDefense,
    WallDefense,
    WallSection,
    WallSectionSetup,
)
from empire_core.enums import Kingdom
from empire_core.services.base import BaseService

logger = logging.getLogger(__name__)


def _section(section: WallSection) -> WallSectionSetup:
    return WallSectionSetup(S=section.slots, UP=section.unit_percent, UC=section.unit_composition)


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

    def set_keep(
        self, castle_x: int, castle_y: int, castle_id: int, keep: KeepDefense, timeout: float = 5.0
    ) -> KeepDefense:
        """
        Set the keep's tools, support tools and unit settings of one of your castles.

        Sends ``keep.slots``, ``keep.support_tool_slots``,
        ``keep.min_attacking_units_for_tools`` and ``keep.unit_composition``.

        Args:
            castle_x: The castle's map x
            castle_y: The castle's map y
            castle_id: The castle's id, as for :meth:`get_own_defense`
            keep: The keep setup, ``get_own_defense(...).keep`` changed as wanted
            timeout: Timeout in seconds

        Returns:
            The ``dfk`` reply: the keep setup the server stored.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SDefenceKeepVO`` (bundle line 66597), sent by
        ``CastleDefenceDialog.sendKeepData`` (bundle line 16041); ``DFKCommand``
        (bundle line 123495)
        """
        request = ChangeKeepDefenseRequest(
            CX=castle_x,
            CY=castle_y,
            AID=castle_id,
            MAUCT=keep.min_attacking_units_for_tools,
            UC=keep.unit_composition,
            S=keep.slots,
            STS=keep.support_tool_slots,
        )
        return self.request(request, KeepDefense, timeout=timeout)

    def set_wall(
        self, castle_x: int, castle_y: int, castle_id: int, wall: WallDefense, timeout: float = 5.0
    ) -> WallDefense:
        """
        Set the wall's tools and unit split of one of your castles.

        Sends each section's ``slots``, ``unit_percent`` (a whole percent, as
        the client rounds its slider) and ``unit_composition``.

        Args:
            castle_x: The castle's map x
            castle_y: The castle's map y
            castle_id: The castle's id, as for :meth:`get_own_defense`
            wall: The wall setup, ``get_own_defense(...).wall`` changed as wanted
            timeout: Timeout in seconds

        Returns:
            The ``dfw`` reply: the wall setup the server stored.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SDefenceWallVO`` (bundle line 66616), sent by
        ``CastleDefenceDialog.sendWallData`` (bundle line 16045) with
        ``calcUnitPercentArray`` (bundle line 15985); ``DFWCommand`` (bundle line 123525)
        """
        request = ChangeWallDefenseRequest(
            CX=castle_x,
            CY=castle_y,
            AID=castle_id,
            L=_section(wall.left),
            M=_section(wall.middle),
            R=_section(wall.right),
        )
        return self.request(request, WallDefense, timeout=timeout)

    def set_moat(
        self, castle_x: int, castle_y: int, castle_id: int, moat: MoatDefense, timeout: float = 5.0
    ) -> MoatDefense:
        """
        Set the moat's tools of one of your castles.

        Args:
            castle_x: The castle's map x
            castle_y: The castle's map y
            castle_id: The castle's id, as for :meth:`get_own_defense`
            moat: The moat setup, ``get_own_defense(...).moat`` changed as wanted
            timeout: Timeout in seconds

        Returns:
            The ``dfm`` reply: the moat setup the server stored.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SDefenceMoatVO`` (bundle line 66607), sent by
        ``CastleDefenceDialog.sendMoatData`` (bundle line 16049); ``DFMCommand``
        (bundle line 123510)
        """
        request = ChangeMoatDefenseRequest(
            CX=castle_x,
            CY=castle_y,
            AID=castle_id,
            LS=moat.left_slots,
            MS=moat.middle_slots,
            RS=moat.right_slots,
        )
        return self.request(request, MoatDefense, timeout=timeout)

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
