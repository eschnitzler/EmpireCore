"""Castle pushes: units received, building XP, changed buildings, slum level and area booster.

Commands (all pushed by the server):
- rue: Units received in a castle
- fbe: A building finished
- cbx: A building gave XP
- gdb: Damaged buildings of the joined castle
- gcb: Buildings of the joined castle whose efficiency changed
- csl: The joined castle's slum level
- gab: The joined castle's area booster
- kik: The server's new day
- ghw: The joined castle moved on the map
- gca: The joined castle's buildings, whole
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from empire_core.enums import Weekday
from empire_core.gamedata import EnumOrInt, UnitOrTool
from empire_core.map.models.areas import MapObject
from empire_core.protocol.base import BaseResponse, object_or_none
from empire_core.protocol.js import ClientInt

from .objects import BuildingRow, CastleBuildings, block_or_none, building_rows


class UnitsReceived(BaseResponse):
    """
    Units that finished and arrived in one of your castles: the castle's new count of that unit.

    Command: rue
    Payload: {"AID": castle_id, "SID": kingdom_id, "WID": wod_id, "NUA": amount}

    Client: ``RUECommand.executeCommand`` (bundle line 125646),
    ``CastleUserCastleListDetailed.parse_rue`` (bundle line 140918),
    ``CastleMilitaryData.parse_rue`` (bundle line 138834)
    """

    command = "rue"

    castle_id: ClientInt = Field(validation_alias="AID", default=0, description="The castle's object id")
    kingdom_id: ClientInt = Field(validation_alias="SID", default=0, description="The castle's kingdom")
    wod_id: UnitOrTool = Field(validation_alias="WID", default=0, description="The unit or tool")
    amount: ClientInt = Field(
        validation_alias="NUA",
        default=0,
        description="How many of the unit the castle now holds",
    )


class BuildingXP(BaseResponse):
    """
    XP a building in the joined castle gave.

    Command: cbx
    Payload: {"OID": object_id, "XP": xp}

    Client: ``CBXCommand.executeCommand`` (bundle line 123345),
    ``AreaDataUpdater.parseCBX`` (bundle line 131521),
    ``IsoUpdaterData.onGainedBuildingPoints`` (bundle line 130308)
    """

    command = "cbx"

    object_id: int = Field(validation_alias="OID", default=-1, description="The building's object id")
    xp: int | float = Field(validation_alias="XP", default=0, description="The XP gained")


class BuildingFinished(BuildingXP):
    """
    A building in the joined castle finished, and the XP it gave.

    Command: fbe
    Payload: {"OID": object_id, "XP": xp}

    Client: ``FBECommand.exec`` (bundle line 122879), which reads it as ``cbx``
    """

    command = "fbe"


class DamagedBuildings(BaseResponse):
    """
    Buildings of the joined castle that were damaged, as their rows are now.

    Command: gdb
    Payload: {"B": [row, ...]}

    Client: ``GDBCommand.executeCommand`` (bundle line 122998),
    ``AreaDataUpdater.parseGDB`` (bundle line 131510),
    ``IsoUpdaterData.updateMultipleObjectInfos`` (bundle line 130259)
    """

    command = "gdb"

    buildings: list[BuildingRow] = Field(
        validation_alias="B", default_factory=list, description="The changed buildings"
    )

    @field_validator("buildings", mode="before")
    @classmethod
    def _rows(cls, value: Any) -> list[BuildingRow]:
        return building_rows(value)


class BuildingEfficiencyChanged(DamagedBuildings):
    """
    Buildings of the joined castle whose efficiency changed, as their rows are now.

    Command: gcb
    Payload: {"B": [row, ...]}

    Client: ``GCBCommand.executeCommand`` (bundle line 122968),
    ``AreaDataUpdater.parseGCB`` (bundle line 131509)
    """

    command = "gcb"


class SlumLevel(BaseResponse):
    """
    The joined castle's slum level.

    Command: csl
    Payload: {"SL": level}

    Client: ``CSLCommand.executeCommand`` (bundle line 122715),
    ``AreaDataSlum.parseCSL`` (bundle line 131305)
    """

    command = "csl"

    level: int = Field(validation_alias="SL", default=-1, description="The slum level, -1 for none")


class AreaBooster(BaseResponse):
    """
    The joined castle's builder discount.

    Command: gab
    Payload: {"B": discount}

    Client: ``GABCommand.executeCommand`` (bundle line 122923),
    ``AreaDataCommonInfo.parseGAB`` (bundle line 130992)
    """

    command = "gab"

    builder_discount: int | float = Field(validation_alias="B", default=0, description="The builder discount")


class NewDay(BaseResponse):
    """
    A new day began on the server. On a Monday the client sets every castle's open-gate counter to 0.

    Command: kik
    Payload: {"DOW": day_of_week}

    Client: ``KIKCommand.executeCommand`` (bundle line 123151)
    """

    command = "kik"

    day_of_week: EnumOrInt[Weekday] | None = Field(
        validation_alias="DOW", default=None, description="The day that began; None when the push names none"
    )


class JoinedAreaMoved(BaseResponse):
    """
    The castle you have joined now stands at a new position on the map.

    Command: ghw
    Payload: {"X": x, "Y": y}

    Client: ``GHWCommand.executeCommand`` (bundle line 129574), ``AreaDataModel.changePosOfOwnArea``
    (bundle line 131929)
    """

    command = "ghw"

    x: ClientInt = Field(validation_alias="X", description="The castle's new x position")
    y: ClientInt = Field(validation_alias="Y", description="The castle's new y position")


class CastleBuildingsPushed(BaseResponse):
    """
    The joined castle's buildings, sent whole, and its owner.

    The client never sends ``gca`` (``C2S_GET_CASTLE`` is declared but unused), so it arrives only from the server.

    Command: gca
    Payload: {"O": owner, "gca": {"BD": [..], "D": [..], ...}}

    Client: ``GCACommand.executeCommand`` (bundle line 122991), ``CastleOtherPlayerData.parseOwnerInfo``
    (bundle line 139045), ``AreaDataUpdater.parseGCA`` (bundle line 131546)
    """

    command = "gca"

    owner: MapObject | None = Field(validation_alias="O", default=None, description="The castle's owner")
    buildings: CastleBuildings | None = Field(
        validation_alias="gca", default=None, description="The castle's buildings; None when unreadable"
    )

    _owner = field_validator("owner", mode="before")(object_or_none)

    @field_validator("buildings", mode="before")
    @classmethod
    def _buildings(cls, value: Any) -> CastleBuildings | None:
        return block_or_none(CastleBuildings, value)


__all__ = [
    "AreaBooster",
    "BuildingEfficiencyChanged",
    "BuildingFinished",
    "BuildingXP",
    "CastleBuildingsPushed",
    "DamagedBuildings",
    "JoinedAreaMoved",
    "NewDay",
    "SlumLevel",
    "UnitsReceived",
]
