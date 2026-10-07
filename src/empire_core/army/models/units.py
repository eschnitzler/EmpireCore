"""Unit inventory, dismissing units, and attack waves.

Commands:
- gui: Get units inventory
- dup: Dismiss units

AttackWave and WaveFlank are the waves a cra attack sends.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator, Field

from empire_core.gamedata import WodAmounts, WodAmountSlots, wod_amount_pairs
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, object_or_none

BUY_UNIT_PACKAGE_SK = 73
"""``SK`` of every ``bup``: each client caller leaves ``C2SBuyUnitPackageVO``'s
default; nothing in the client reads it or says what it means."""


RawBlock = Annotated[dict[str, Any] | None, BeforeValidator(object_or_none)]
"""A reply block this module keeps as sent; the docstring names the client parser."""


# =============================================================================
# GUI - Get Units Inventory
# =============================================================================


class GetUnitsRequest(BaseRequest):
    """
    Get the unit inventories of the castle the session is in.

    Command: gui
    Payload: {}

    The request names no castle: the server answers for the joined castle, and
    with ``NOT_IN_OWNED_CASTLE`` once a map scan has moved the session away.

    Client: ``C2SGetUnitInventoryVO`` (no fields)
    """

    command = "gui"


def _spy_positions(value: object) -> object:
    """
    One wod/amount array per position, each pair read through ``int()``.

    Client: ``CastleSpyArmyInfoVO.parseArmyInfo`` (bundle line 30699) hands each
    position to ``AUnitInventory.fillFromWodAmountArray`` (bundle line 42572),
    which skips entries that are not arrays and reads ``int(i[0])``, ``int(i[1])``,
    into a ``UnitInventoryList``, whose ``addUnit`` skips an amount of 0 or less
    (bundle line 21826). A position that is not an array fills nothing, so it
    reads as empty; it is kept, since the client reads positions by order.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        return value
    return [[[wod_id, amount] for wod_id, amount in wod_amount_pairs(position) if amount > 0] for position in value]


SpyPositions = Annotated[list[list[list[int]]], BeforeValidator(_spy_positions)]
"""A spy report's ``S``: ``[wod_id, amount]`` pairs per position, in the order
left, middle, right, keep, stronghold, support, then an optional reserve."""


class UnitInventory(BasePayload):
    """
    A castle's unit inventories, the ``gui`` block.

    Client: ``CastleMilitaryData.parse_GUI``, which fills each inventory with
    ``AUnitInventory.fillFromWodAmountArray`` (bundle line 42572)
    """

    units: WodAmounts = Field(alias="I", default_factory=dict, description="Units and tools in the castle")
    in_production: WodAmounts = Field(alias="TU", default_factory=dict, description="Units on their way in")
    stronghold: WodAmounts = Field(alias="SHI", default_factory=dict, description="Units stored in the stronghold")
    hospital: WodAmounts = Field(alias="HI", default_factory=dict, description="Wounded units in the hospital")


class GetUnitsResponse(BaseResponse, UnitInventory):
    """
    The unit inventories of the castle the session is in.

    Command: gui
    Payload: {"I": [[wod_id, amount], ...], "TU": [...], "SHI": [...], "HI": [...]}

    Client: ``GUICommand.exec`` (bundle line 125600) hands the reply to
    ``CastleMilitaryData.parse_GUI``, which reads I, TU, SHI and HI and nothing else.
    """

    command = "gui"


UnitInventoryBlock = Annotated[UnitInventory | None, BeforeValidator(object_or_none)]


# =============================================================================
# DUP - Dismiss Units
# =============================================================================


class DismissUnitsRequest(BaseRequest):
    """
    Dismiss units of the joined castle.

    Command: dup
    Payload: {"WID": wod_id, "A": amount, "S": 0 or 1}

    Client: ``C2SDismissUnitPackageVO`` (bundle line 84341), built by
    ``CastleRecruitDismissUnitsDialog.dismissUnits`` (bundle line 84330)
    """

    command = "dup"

    wod_id: int = Field(alias="WID")
    amount: int = Field(alias="A")
    from_stronghold: int = Field(alias="S", default=0, description="1 to dismiss from the stronghold")


class DismissUnitsResponse(BaseResponse):
    """
    The joined castle after a ``dup``.

    Command: dup

    Client: ``DUPCommand.executeCommand`` (bundle line 125585)
    """

    command = "dup"

    production_area: RawBlock = Field(
        alias="gpa", default=None, description="The castle's production and storage figures, as a raw block"
    )
    unit_inventory: UnitInventoryBlock = Field(alias="gui", default=None)


# =============================================================================
# CRA - Create Attack
# =============================================================================


class WaveFlank(BasePayload):
    """
    One flank of an attack wave.

    Payload: {"T": [[tool_id, count], ...], "U": [[unit_id, count], ...]}, one pair per slot

    Client: ``CastleAttackWaveVO.getWaveInfoObject`` (bundle line 99930) sends each
    container's ``getSlotList()`` (bundle line 20573)
    """

    tools: WodAmountSlots = Field(alias="T", default=(), description="The tool slots, [-1, 0] for an empty one")
    units: WodAmountSlots = Field(alias="U", default=(), description="The unit slots, [-1, 0] for an empty one")


class AttackWave(BasePayload):
    """
    A single attack wave: left, right and middle flank.

    Payload: {"L": flank, "R": flank, "M": flank}, in the client's key order.

    Client: ``CastleAttackWaveVO.getWaveInfoObject`` (bundle line 99930)
    """

    left: WaveFlank = Field(alias="L", default_factory=WaveFlank)
    right: WaveFlank = Field(alias="R", default_factory=WaveFlank)
    middle: WaveFlank = Field(alias="M", default_factory=WaveFlank)

    def unit_count(self) -> int:
        """Total units across all three flanks."""
        return sum(slot.amount for flank in (self.left, self.middle, self.right) for slot in flank.units)

    def is_complete(self) -> bool:
        """
        Whether the client would send this wave.

        The game drops any wave without units, tools included.
        """
        return self.unit_count() > 0


__all__ = [
    "AttackWave",
    "WaveFlank",
    "BUY_UNIT_PACKAGE_SK",
    "UnitInventory",
    "GetUnitsRequest",
    "GetUnitsResponse",
    "DismissUnitsRequest",
    "DismissUnitsResponse",
]
