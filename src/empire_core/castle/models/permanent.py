"""What each castle has unlocked: its units and its horses.

Commands:
- gpc: Permanent castle data, a login section and a push
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from empire_core.enums import Kingdom
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, js_int

if TYPE_CHECKING:
    from empire_core.gamedata import Horse

logger = logging.getLogger(__name__)


def _wod_ids(value: Any) -> list[int]:
    # The client looks each id up in its game data; an entry that is no number finds no row
    if not isinstance(value, list):
        return []
    return [
        int(entry)
        for entry in value
        if not isinstance(entry, bool) and (isinstance(entry, int) or (isinstance(entry, float) and entry.is_integer()))
    ]


class CastleUnitUnlocks(BaseModel):
    """
    The units and tools a castle can recruit, and those it has still locked.

    Client: ``CastleUnitsVO.parseParamObject`` (bundle line 139200)
    """

    model_config = ConfigDict(populate_by_name=True)

    unlocked_unit_ids: list[int] = Field(
        alias="U", default_factory=list, description="Wod ids of the units and tools the castle can recruit"
    )
    locked_unit_ids: list[int] = Field(
        alias="L", default_factory=list, description="Wod ids of the units and tools still locked there"
    )

    @field_validator("unlocked_unit_ids", "locked_unit_ids", mode="before")
    @classmethod
    def _ids(cls, value: Any) -> list[int]:
        return _wod_ids(value)


class PermanentCastle(BaseModel):
    """
    One castle's unlocked units and horses.

    Client: ``CastlePermanentCastleVO.parseParamObject`` (bundle line 139158),
    ``CastleHorsesVO.parseParamObject`` (bundle line 139177)
    """

    model_config = ConfigDict(populate_by_name=True)

    castle_id: ClientInt = Field(alias="AID", description="The castle's object id")
    kingdom_id: Kingdom = Field(alias="KID", description="The castle's kingdom")
    units: CastleUnitUnlocks = Field(
        alias="U", default_factory=CastleUnitUnlocks, description="Units and tools unlocked and locked there"
    )
    horse_ids: list[EnumOrInt["Horse"]] = Field(
        alias="UH", default_factory=list, description="The horses the castle's movements can use"
    )

    @field_validator("kingdom_id", mode="before")
    @classmethod
    def _kingdom(cls, value: Any) -> Any:
        return value if isinstance(value, Kingdom) else js_int(value)

    @field_validator("units", mode="before")
    @classmethod
    def _units(cls, value: Any) -> Any:
        return value if isinstance(value, (dict, CastleUnitUnlocks)) else {}

    @field_validator("horse_ids", mode="before")
    @classmethod
    def _horses(cls, value: Any) -> Any:
        return _wod_ids(value)


class PermanentCastleDataResponse(BaseResponse):
    """
    Every castle's unlocked units and horses.

    Command: gpc, as a login section of ``gbd`` and as a push
    Payload: {"A": [{"AID": castle_id, "KID": kingdom, "U": {"U": [wod_id, ...], "L": [wod_id, ...]},
              "UH": [wod_id, ...]}, ...]}

    The client never asks for it: there is no ``C2S`` constant for gpc. An
    update names only the castles it changes; castles it leaves out keep
    what they had.

    Client: ``GPCCommand.executeCommand`` (bundle line 123044),
    ``CastlePermanentCastleData.parseGPC`` (bundle line 139128), read from
    ``gbd`` (bundle line 129381)
    """

    command = "gpc"

    castles: list[PermanentCastle] = Field(alias="A", default_factory=list, description="One entry per castle")

    @field_validator("castles", mode="before")
    @classmethod
    def _castles(cls, value: Any) -> list[PermanentCastle]:
        return readable_list(PermanentCastle, value, warn=logger, what="gpc castles")


__all__ = ["CastleUnitUnlocks", "PermanentCastle", "PermanentCastleDataResponse"]
