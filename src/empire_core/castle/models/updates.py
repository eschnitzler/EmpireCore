"""Castle pushes: units received, building XP, changed buildings, slum level and area booster.

Commands (all pushed by the server):
- rue: Units received in a castle
- fbe: A building finished
- cbx: A building gave XP
- gdb: Damaged buildings of the joined castle
- gcb: Buildings of the joined castle whose efficiency changed
- csl: The joined castle's slum level
- gab: The joined castle's area booster
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from empire_core.protocol.base import BaseResponse
from empire_core.protocol.js import ClientInt

from .objects import BuildingRow, building_rows


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

    castle_id: ClientInt = Field(alias="AID", default=0, description="The castle's object id")
    kingdom_id: ClientInt = Field(alias="SID", default=0, description="The castle's kingdom")
    wod_id: ClientInt = Field(alias="WID", default=0, description="The unit's wod id")
    amount: ClientInt = Field(alias="NUA", default=0, description="How many of the unit the castle now holds")


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

    object_id: int = Field(alias="OID", default=-1, description="The building's object id")
    xp: int | float = Field(alias="XP", default=0, description="The XP gained")


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

    buildings: list[BuildingRow] = Field(alias="B", default_factory=list, description="The changed buildings")

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

    level: int = Field(alias="SL", default=-1, description="The slum level, -1 for none")


class AreaBooster(BaseResponse):
    """
    The joined castle's builder discount.

    Command: gab
    Payload: {"B": discount}

    Client: ``GABCommand.executeCommand`` (bundle line 122923),
    ``AreaDataCommonInfo.parseGAB`` (bundle line 130992)
    """

    command = "gab"

    builder_discount: int | float = Field(alias="B", default=0, description="The builder discount")


__all__ = [
    "AreaBooster",
    "BuildingEfficiencyChanged",
    "BuildingFinished",
    "BuildingXP",
    "DamagedBuildings",
    "SlumLevel",
    "UnitsReceived",
]
