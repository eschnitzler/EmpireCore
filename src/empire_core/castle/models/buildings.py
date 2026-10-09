"""
Building commands.

Every command acts on the castle joined with ``jca`` (``client.castle.select``)
and names a building by its object id, a ``BuildingRow.object_id`` from the
castle's ``CastleBuildings`` (``client.castle.join``).

Commands:
- ebu: Build
- eup: Upgrade a building
- emo: Move a building
- sbd: Sell a decoration
- edo: Take a building down
- fco: Finish a construction at once
- msb: Shorten a construction with a minute skip
- eud: Upgrade the wall, gate or a tower
- rbu: Repair a building
- ira: Repair every building
- ebe: Buy a castle expansion
- etc: Open an expansion's treasure chest
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field, field_serializer, field_validator

from empire_core.enums import ExpansionType
from empire_core.gamedata import EnumOrStr
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock
from empire_core.protocol.js import ClientInt, js_int

from .details import CastleProductionArea
from .objects import BuildingRow, CastleBuildings, ConstructionList, block_or_none, building_or_none, building_rows
from .resources import CastleResources

if TYPE_CHECKING:
    from empire_core.gamedata import Currency

_OBJECT_ID = "The building's object id, a BuildingRow.object_id from client.castle.join(...).buildings"
_PRIVATE_OFFER = "The private offer the purchase uses, -1 for none"
_PAY_WITH_RUBIES = "Pay the missing resources with rubies"


class _BuildingReply(BaseResponse):
    """The blocks building replies share; one that cannot be read is None."""

    @field_validator("resources", mode="before", check_fields=False)
    @classmethod
    def _resources(cls, value: Any) -> CastleResources | None:
        return block_or_none(CastleResources, value)

    @field_validator("production_area", mode="before", check_fields=False)
    @classmethod
    def _production_area(cls, value: Any) -> CastleProductionArea | None:
        return block_or_none(CastleProductionArea, value)

    @field_validator("castle_buildings", mode="before", check_fields=False)
    @classmethod
    def _castle_buildings(cls, value: Any) -> CastleBuildings | None:
        return block_or_none(CastleBuildings, value)

    @field_validator("construction_list", mode="before", check_fields=False)
    @classmethod
    def _construction_list(cls, value: Any) -> ConstructionList | None:
        return block_or_none(ConstructionList, value)

    @field_validator("building", mode="before", check_fields=False)
    @classmethod
    def _row(cls, value: Any) -> Any:
        return building_or_none(value)

    @field_validator("buildings", mode="before", check_fields=False)
    @classmethod
    def _rows(cls, value: Any) -> Any:
        return building_rows(value)


# =============================================================================
# EBU - Build
# =============================================================================


class BuildRequest(BaseRequest):
    """
    Place a new building in the joined castle.

    Command: ebu
    Payload: {"WID": wod_id, "X": x, "Y": y, "R": rotation, "PWR": 0 or 1, "PO": offer_id, "DOID": district_id}

    Keys follow the client's order: the constructor initialises PWR before PO.
    To place a building into a district the client sends X and Y as -1 and
    the district's object id as DOID.

    Client: ``C2SIsoBuyObjectVO`` (bundle line 31942), sent by
    ``IsoServerCommands.buyObjectFromShop`` (bundle line 63766)
    """

    command = "ebu"

    wod_id: int = Field(alias="WID", description="The building type's wod id")
    x: int = Field(alias="X", description="Castle grid x, -1 when placing into a district")
    y: int = Field(alias="Y", description="Castle grid y, -1 when placing into a district")
    rotation: int = Field(alias="R", default=0, description="Rotation")
    pay_with_rubies: bool = Field(alias="PWR", default=False, description=_PAY_WITH_RUBIES)
    private_offer_id: int = Field(alias="PO", default=-1, description=_PRIVATE_OFFER)
    district_object_id: int = Field(
        alias="DOID", default=-1, description="Object id of the district to place into, -1 for none"
    )

    @field_serializer("pay_with_rubies")
    def _flag(self, value: bool) -> int:
        return 1 if value else 0


class BuildResponse(_BuildingReply):
    """
    The new building.

    Command: ebu
    Payload: {"NO": row, "grc": {..}, "scl": {..}, "gcu": {..}, "sin": .., "fbe": ..}

    ``sin`` and ``fbe`` are kept as sent.

    Client: ``EBUCommand.executeCommand`` (bundle line 122760),
    ``AreaDataUpdater.parseEBU`` (bundle line 131512)
    """

    command = "ebu"

    building: BuildingRow | None = Field(alias="NO", default=None, description="The new building")
    resources: CastleResources | None = Field(alias="grc", default=None, description="The castle's resources after")
    construction_list: ConstructionList | None = Field(
        alias="scl", default=None, description="The construction slots after"
    )
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after")


# =============================================================================
# EUP - Upgrade Building
# =============================================================================


class UpgradeBuildingRequest(BaseRequest):
    """
    Upgrade a building in the joined castle.

    Command: eup
    Payload: {"OID": object_id, "PWR": 0 or 1, "PO": offer_id}

    Keys follow the client's order: the constructor initialises PWR before PO.

    Client: ``C2SIsoUpgradeObjectVO`` (bundle line 31971)
    """

    command = "eup"

    object_id: int = Field(alias="OID", description=_OBJECT_ID)
    pay_with_rubies: bool = Field(alias="PWR", default=False, description=_PAY_WITH_RUBIES)
    private_offer_id: int = Field(alias="PO", default=-1, description=_PRIVATE_OFFER)

    @field_serializer("pay_with_rubies")
    def _flag(self, value: bool) -> int:
        return 1 if value else 0


class UpgradeBuildingResponse(_BuildingReply):
    """
    The upgraded buildings.

    Command: eup
    Payload: {"O": [row, ...], "grc": {..}, "scl": {..}, "gcu": {..}}

    Client: ``EUPCommand.executeCommand`` (bundle line 122860),
    ``AreaDataUpdater.parseEUP`` (bundle line 131516)
    """

    command = "eup"

    buildings: list[BuildingRow] = Field(alias="O", default_factory=list, description="The changed buildings")
    resources: CastleResources | None = Field(alias="grc", default=None, description="The castle's resources after")
    construction_list: ConstructionList | None = Field(
        alias="scl", default=None, description="The construction slots after"
    )
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after")


# =============================================================================
# EMO - Move Building
# =============================================================================


class MoveBuildingRequest(BaseRequest):
    """
    Move a building in the joined castle.

    Command: emo
    Payload: {"OID": object_id, "X": x, "Y": y, "R": rotation}

    Client: ``C2SIsoMoveObjectVO`` (bundle line 63796), sent by
    ``IsoServerCommands.moveObject`` (bundle line 63776) for a building outside
    a district
    """

    command = "emo"

    object_id: int = Field(alias="OID", description=_OBJECT_ID)
    x: int = Field(alias="X", description="Castle grid x")
    y: int = Field(alias="Y", description="Castle grid y")
    rotation: int = Field(alias="R", default=0, description="Rotation")


class MoveBuildingResponse(_BuildingReply):
    """
    The moved building.

    Command: emo
    Payload: {"MO": row}

    Client: ``EMOCommand.executeCommand`` (bundle line 122815), which also
    reads the reply to a failed move, ``AreaDataUpdater.parseEMO`` (bundle line 131518)
    """

    command = "emo"

    building: BuildingRow | None = Field(alias="MO", default=None, description="The building where it now stands")


# =============================================================================
# SBD - Sell Decoration
# =============================================================================


class SellBuildingRequest(BaseRequest):
    """
    Sell a decoration placed in the joined castle.

    Command: sbd
    Payload: {"OID": object_id}

    Client: ``C2SellBuildingDeco`` (bundle line 77740), sent from the sell
    dialog of a placed decoration (bundle line 28587)
    """

    command = "sbd"

    object_id: int = Field(alias="OID", description=_OBJECT_ID)


class SellBuildingResponse(_BuildingReply):
    """
    The sold decoration.

    Command: sbd
    Payload: {"OID": object_id, "gcu": {..}}

    Client: ``SBDCommand.executeCommand`` (bundle line 131722),
    ``AreaDataUpdater.parseSBD`` (bundle line 131522)
    """

    command = "sbd"

    object_id: int = Field(alias="OID", default=-1, description="Object id of the removed decoration")

    _object_id = field_validator("object_id", mode="before")(js_int)
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after")


# =============================================================================
# EDO - Take a Building Down
# =============================================================================


class DestroyBuildingRequest(BaseRequest):
    """
    Start taking a building in the joined castle down.

    Command: edo
    Payload: {"OID": object_id}

    Client: ``C2SIsoDisassembleObjectVO`` (bundle line 41065)
    """

    command = "edo"

    object_id: int = Field(alias="OID", description=_OBJECT_ID)


class DestroyBuildingResponse(_BuildingReply):
    """
    The building being taken down.

    Command: edo
    Payload: {"O": row, "scl": {..}}

    Client: ``EDOCommand.executeCommand`` (bundle line 122781),
    ``AreaDataUpdater.parseEDO`` (bundle line 131513), which reads the reply
    itself as the row
    """

    command = "edo"

    building: BuildingRow | None = Field(alias="O", default=None, description="The building")
    construction_list: ConstructionList | None = Field(
        alias="scl", default=None, description="The construction slots after"
    )


# =============================================================================
# FCO - Finish a Construction at Once
# =============================================================================


class FastCompleteRequest(BaseRequest):
    """
    Finish a building's running construction at once: for free with ``FS`` 1, else for rubies.

    Command: fco
    Payload: {"OID": object_id, "FS": 0 or 1}

    Client: ``C2SIsoFastCompleteObjectVO`` (bundle line 31951), sent by
    ``IsoServerCommands.fastCompleteBuilding`` (bundle line 63773) with ``FS`` 1 when
    ``CastleSpecialEventData.hasSkipForFree`` (bundle line 139853)
    """

    command = "fco"

    object_id: int = Field(alias="OID", description=_OBJECT_ID)
    free_skip: bool = Field(
        alias="FS", default=False, description="Finish for free, the time left being within the free skip time"
    )

    @field_serializer("free_skip")
    def _flag(self, value: bool) -> int:
        return 1 if value else 0


class FastCompleteResponse(_BuildingReply):
    """
    The finished building.

    Command: fco
    Payload: {"O": row, "gcu": {..}}

    Client: ``FCOCommand.executeCommand`` (bundle line 122908),
    ``AreaDataUpdater.parseFCO`` (bundle line 131519)
    """

    command = "fco"

    building: BuildingRow | None = Field(alias="O", default=None, description="The building")
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after")


# =============================================================================
# MSB - Minute Skip a Construction
# =============================================================================


class TimeSkipBuildingRequest(BaseRequest):
    """
    Shorten a building's running construction with a minute skip.

    Command: msb
    Payload: {"OID": object_id, "MST": minute_skip}

    Keys follow the client's order: the constructor initialises OID and sets
    MST after it.

    Client: ``C2SMinuteSkipBuildingVO`` (bundle line 81363), built by
    ``BuildingMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 50021);
    ``CastleMinuteSkipDialog.onScrollItemClick`` passes the currency's
    ``jsonKey`` (bundle line 7722)
    """

    command = "msb"

    object_id: int = Field(alias="OID", description=_OBJECT_ID)
    minute_skip: EnumOrStr["Currency"] = Field(
        alias="MST",
        description="The minute skip used, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``; sent as its key",
    )


class TimeSkipBuildingResponse(_BuildingReply):
    """
    The construction slots after a minute skip.

    Command: msb
    Payload: {"scl": {..}}

    Client: ``MSBCommand.executeCommand`` (bundle line 125767)
    """

    command = "msb"

    construction_list: ConstructionList | None = Field(
        alias="scl", default=None, description="The construction slots after"
    )


# =============================================================================
# EUD - Upgrade the Wall, Gate or a Tower
# =============================================================================


class UpgradeWallRequest(BaseRequest):
    """
    Upgrade the joined castle's wall, gate or one of its towers.

    Command: eud
    Payload: {"OID": object_id, "PO": offer_id, "PWR": 0 or 1}

    Client: ``C2SIsoUpgradeDefenceVO`` (bundle line 41075)
    """

    command = "eud"

    object_id: int = Field(
        alias="OID",
        description="Object id of the wall, gate or tower, a BuildingRow.object_id",
    )
    private_offer_id: int = Field(alias="PO", default=-1, description=_PRIVATE_OFFER)
    pay_with_rubies: bool = Field(alias="PWR", default=False, description=_PAY_WITH_RUBIES)

    @field_serializer("pay_with_rubies")
    def _flag(self, value: bool) -> int:
        return 1 if value else 0


class UpgradeWallResponse(_BuildingReply):
    """
    The upgraded wall, gate or tower.

    Command: eud
    Payload: {"N": row, "grc": {..}, "gcu": {..}}

    Client: ``EUDCommand.executeCommand`` (bundle line 122845),
    ``AreaDataUpdater.parseEUD`` (bundle line 131515)
    """

    command = "eud"

    building: BuildingRow | None = Field(alias="N", default=None, description="The upgraded object")
    resources: CastleResources | None = Field(alias="grc", default=None, description="The castle's resources after")
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after")


# =============================================================================
# RBU - Repair a Building
# =============================================================================


class RepairBuildingRequest(BaseRequest):
    """
    Repair a damaged building in the joined castle.

    Command: rbu
    Payload: {"OID": object_id, "PO": offer_id, "PWR": 0 or 1}

    Client: ``C2SIsoRepairBuildingVO`` (bundle line 31961)
    """

    command = "rbu"

    object_id: int = Field(alias="OID", description=_OBJECT_ID)
    private_offer_id: int = Field(alias="PO", default=-1, description=_PRIVATE_OFFER)
    pay_with_rubies: bool = Field(alias="PWR", default=False, description=_PAY_WITH_RUBIES)

    @field_serializer("pay_with_rubies")
    def _flag(self, value: bool) -> int:
        return 1 if value else 0


class RepairBuildingResponse(_BuildingReply):
    """
    The building being repaired.

    Command: rbu
    Payload: {"O": row, "scl": {..}, "grc": {..}, "gcu": {..}}

    Client: ``RBUCommand.executeCommand`` (bundle line 123162),
    ``AreaDataUpdater.parseRBU`` (bundle line 131507)
    """

    command = "rbu"

    building: BuildingRow | None = Field(alias="O", default=None, description="The building")
    construction_list: ConstructionList | None = Field(
        alias="scl", default=None, description="The construction slots after"
    )
    resources: CastleResources | None = Field(alias="grc", default=None, description="The castle's resources after")
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after")


# =============================================================================
# IRA - Repair Every Building
# =============================================================================


class RepairAllRequest(BaseRequest):
    """
    Repair every damaged building in the joined castle at once.

    Command: ira
    Payload: {}

    Client: ``C2SIsoRepairAllVO`` (bundle line 37983)
    """

    command = "ira"


class RepairAllResponse(_BuildingReply):
    """
    The repaired buildings.

    Command: ira
    Payload: {"gpa": {..}, "B": [row, ...], "gcu": {..}}

    Client: ``IRACommand.executeCommand`` (bundle line 123079),
    ``AreaDataUpdater.parseIRA`` (bundle line 131508)
    """

    command = "ira"

    production_area: CastleProductionArea | None = Field(
        alias="gpa", default=None, description="The castle's production area after"
    )
    buildings: list[BuildingRow] = Field(alias="B", default_factory=list, description="The repaired buildings")
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after")


# =============================================================================
# EBE - Buy an Expansion
# =============================================================================


class BuyExtensionRequest(BaseRequest):
    """
    Buy an expansion of the joined castle's grounds.

    Command: ebe
    Payload: {"X": x, "Y": y, "R": rotation, "CT": expansion_type}

    Client: ``C2SIsoBuyExpansionVO`` (bundle line 63787), sent by
    ``IsoServerCommands.buyExpansion`` (bundle line 63769) with the
    expansion's ``IsoExpansionEnum`` id
    """

    command = "ebe"

    x: int = Field(alias="X", description="Castle grid x of the expansion")
    y: int = Field(alias="Y", description="Castle grid y of the expansion")
    rotation: int = Field(alias="R", default=0, description="Rotation")
    expansion_type: ExpansionType = Field(
        alias="CT", default=ExpansionType.NORMAL, description="Pay with resources (NORMAL) or rubies (PREMIUM)"
    )


class BuyExtensionResponse(_BuildingReply):
    """
    The castle after the expansion.

    Command: ebe
    Payload: {"gca": {..}, "grc": {..}, "scl": {..}, "gcu": {..}, "sin": ..}

    ``sin`` is kept as sent.

    Client: ``EBECommand.executeCommand`` (bundle line 122743),
    ``AreaDataUpdater.parseEBE`` (bundle line 131511)
    """

    command = "ebe"

    castle_buildings: CastleBuildings | None = Field(
        alias="gca", default=None, description="The castle's buildings after"
    )
    resources: CastleResources | None = Field(alias="grc", default=None, description="The castle's resources after")
    construction_list: ConstructionList | None = Field(
        alias="scl", default=None, description="The construction slots after"
    )
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after")


# =============================================================================
# ETC - Open an Expansion's Treasure Chest
# =============================================================================


class CollectExtensionGiftRequest(BaseRequest):
    """
    Open a treasure chest found on an expansion of the joined castle.

    Command: etc
    Payload: {"OID": object_id}

    Client: ``C2SExtensionTreasureChestVO`` (bundle line 86720), sent by
    ``CastleTreasureChestBuildingDialog`` (bundle line 86704)
    """

    command = "etc"

    object_id: int = Field(alias="OID", description="The treasure chest's object id")


class CollectExtensionGiftResponse(_BuildingReply):
    """
    The opened chest.

    Command: etc
    Payload: {"RID": reward_id, "OID": object_id}

    Client: ``AreaDataUpdater.parseETC`` (bundle line 131517);
    ``CastleTreasureChestBuildingDialog.onEtcArrived`` (bundle line 86706)
    reads ``RID`` through ``int()``
    """

    command = "etc"

    reward_id: ClientInt = Field(alias="RID", default=0, description="The reward list the chest held")
    object_id: ClientInt = Field(alias="OID", default=-1, description="Object id of the removed chest")


__all__ = [
    "BuildRequest",
    "BuildResponse",
    "UpgradeBuildingRequest",
    "UpgradeBuildingResponse",
    "MoveBuildingRequest",
    "MoveBuildingResponse",
    "SellBuildingRequest",
    "SellBuildingResponse",
    "DestroyBuildingRequest",
    "DestroyBuildingResponse",
    "FastCompleteRequest",
    "FastCompleteResponse",
    "TimeSkipBuildingRequest",
    "TimeSkipBuildingResponse",
    "UpgradeWallRequest",
    "UpgradeWallResponse",
    "RepairBuildingRequest",
    "RepairBuildingResponse",
    "RepairAllRequest",
    "RepairAllResponse",
    "BuyExtensionRequest",
    "BuyExtensionResponse",
    "CollectExtensionGiftRequest",
    "CollectExtensionGiftResponse",
]
