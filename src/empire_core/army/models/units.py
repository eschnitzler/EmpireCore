"""Unit inventory, dismissing units, and attack waves.

Commands:
- gui: Get units inventory
- dup: Dismiss units
- sts: Store soldiers in the stronghold
- tas: Take soldiers out of the stronghold

AttackWave and WaveFlank are the waves a cra attack sends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BeforeValidator, Field

from empire_core.gamedata import WodAmounts, WodAmountSlots, WodAmountSlotsInput
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


class UnitInventory(BasePayload):
    """
    A castle's unit inventories, the ``gui`` block.

    Client: ``CastleMilitaryData.parse_GUI``, which fills each inventory with
    ``AUnitInventory.fillFromWodAmountArray`` (bundle line 42572)
    """

    units: WodAmounts = Field(validation_alias="I", default_factory=dict, description="Units and tools in the castle")
    in_production: WodAmounts = Field(validation_alias="TU", default_factory=dict, description="Units on their way in")
    stronghold: WodAmounts = Field(
        validation_alias="SHI",
        default_factory=dict,
        description="Units stored in the stronghold",
    )
    hospital: WodAmounts = Field(
        validation_alias="HI",
        default_factory=dict,
        description="Wounded units in the hospital",
    )


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

    wod_id: int = Field(validation_alias="WID")
    amount: int = Field(validation_alias="A")
    from_stronghold: int = Field(validation_alias="S", default=0, description="1 to dismiss from the stronghold")


class DismissUnitsResponse(BaseResponse):
    """
    The joined castle after a ``dup``.

    Command: dup

    Client: ``DUPCommand.executeCommand`` (bundle line 125585)
    """

    command = "dup"

    production_area: RawBlock = Field(
        validation_alias="gpa",
        default=None,
        description="The castle's production and storage figures, as a raw block",
    )
    unit_inventory: UnitInventoryBlock = Field(validation_alias="gui", default=None)


# =============================================================================
# STS / TAS - Stronghold
# =============================================================================


class StoreSoldiersRequest(BaseRequest):
    """
    Store soldiers of the joined castle in its stronghold.

    Command: sts
    Payload: {"WID": wod_id, "A": amount}

    The client offers at most the stronghold's free space or the soldiers at home, whichever is
    less, and nothing once the stronghold is full (bundle lines 84422, 138864-138866).

    Client: ``C2SStoreSoldiersVO`` (bundle line 84439), sent by
    ``CastleInventoryStrongholdListItemComponent.storeSoldiers`` (bundle line 84429)
    """

    command = "sts"

    wod_id: int = Field(validation_alias="WID")
    amount: int = Field(validation_alias="A")


class StoreSoldiersResponse(BaseResponse, UnitInventory):
    """
    The joined castle's unit inventories after an ``sts``: the whole reply is a ``gui`` block.

    Command: sts

    Client: ``STSCommand.executeCommand`` (bundle line 125692) hands the reply to
    ``CastleMilitaryData.parse_GUI`` (bundle line 138833)
    """

    command = "sts"


class TakeSoldiersRequest(BaseRequest):
    """
    Take soldiers of the joined castle out of its stronghold.

    Command: tas
    Payload: {"WID": wod_id, "A": amount}

    Client: ``C2STakeSoldiersVO`` (bundle line 84480), sent by
    ``StrongholdInventoryListItemComponent.takeSoldiers`` (bundle line 84462)
    """

    command = "tas"

    wod_id: int = Field(validation_alias="WID")
    amount: int = Field(validation_alias="A")


class TakeSoldiersResponse(BaseResponse, UnitInventory):
    """
    The joined castle's unit inventories after a ``tas``: the whole reply is a ``gui`` block.

    Command: tas

    Client: ``TASCommand.executeCommand`` (bundle line 125707) hands the reply to
    ``CastleMilitaryData.parse_GUI`` (bundle line 138833)
    """

    command = "tas"


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

    tools: WodAmountSlots = Field(
        validation_alias="T",
        default=(),
        description="The tool slots, [-1, 0] for an empty one",
    )
    units: WodAmountSlots = Field(
        validation_alias="U",
        default=(),
        description="The unit slots, [-1, 0] for an empty one",
    )

    if TYPE_CHECKING:

        def __init__(self, *, tools: WodAmountSlotsInput = (), units: WodAmountSlotsInput = ()) -> None: ...


class AttackWave(BasePayload):
    """
    A single attack wave: left, right and middle flank.

    Payload: {"L": flank, "R": flank, "M": flank}, in the client's key order.

    Client: ``CastleAttackWaveVO.getWaveInfoObject`` (bundle line 99930)
    """

    left: WaveFlank = Field(validation_alias="L", default_factory=WaveFlank)
    right: WaveFlank = Field(validation_alias="R", default_factory=WaveFlank)
    middle: WaveFlank = Field(validation_alias="M", default_factory=WaveFlank)

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
    "StoreSoldiersRequest",
    "StoreSoldiersResponse",
    "TakeSoldiersRequest",
    "TakeSoldiersResponse",
]
