"""Your alliance members' aqua points on the Storm Islands.

Commands:
- ama: Each member's aqua points
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_validator, model_validator

from empire_core.enums import AllianceRank
from empire_core.gamedata.lenient import EnumOrInt
from empire_core.map.models.owners import OwnerCrest
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt

logger = logging.getLogger(__name__)


class AllianceMemberAquaPoints(BasePayload):
    """
    One member's row: ``[player_id, name, level, unlocked, aqua_points, rank, crest]``.

    Client: ``CastleEilandPlayerRankingItemVO`` (bundle line 55535), which reads the numbers
    through ``int()``, the unlocked flag as ``== 1`` and the crest with ``CrestVO.loadFromParamObject``
    only when one is sent
    """

    player_id: ClientInt = Field(default=0, description="Player id")
    name: str = Field(default="", description="Player name")
    level: ClientInt = Field(default=0, description="Player level")
    has_unlocked_storm_islands: bool = Field(default=False, description="Whether the member reached the Storm Islands")
    aqua_points: ClientInt = Field(default=0, description="The member's aqua points")
    rank: EnumOrInt[AllianceRank] = Field(default=0, description="The member's alliance rank")
    crest: OwnerCrest | None = Field(default=None, description="The member's crest; None when not sent")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        keys = ("player_id", "name", "level", "has_unlocked_storm_islands", "aqua_points", "rank", "crest")
        fields: dict[str, Any] = dict(zip(keys, data, strict=False))
        fields["has_unlocked_storm_islands"] = fields.get("has_unlocked_storm_islands") == 1
        if "name" in fields:
            fields["name"] = "" if fields["name"] is None else str(fields["name"])
        if not isinstance(fields.get("crest"), dict):
            fields.pop("crest", None)
        return fields


class AllianceMemberAquaPointsRequest(BaseRequest):
    """
    Ask for each member's aqua points.

    Command: ama
    Payload: {"AID": alliance_id}

    Client: ``C2SAllianceMemberAquaPoints`` (bundle line 55525), sent with your alliance's id by
    ``CastleEilandRankingDialogPlayer.requestHighscoreData`` (bundle line 98146) and the Storm
    Islands performance dialog (bundle line 105751)
    """

    command = "ama"

    alliance_id: int = Field(validation_alias="AID", description="Your alliance's id")


class AllianceMemberAquaPointsResponse(BaseResponse):
    """
    Each member's aqua points, as the server lists them.

    Command: ama
    Payload: {"APH": [row, ...]}

    Client: ``AMACommand.executeCommand`` (bundle line 124386) hands the reply to the dialogs, which read
    ``APH`` (``CastleEilandRankingDialogPlayer.onGetHighscoreData``, bundle line 98146, and
    ``CastleStormIslandsMainDialogPerformanceAlliance.onGetHighscoreData``, bundle line 105752)
    """

    command = "ama"

    members: list[AllianceMemberAquaPoints] = Field(
        validation_alias="APH", default_factory=list, description="One row per member"
    )

    @field_validator("members", mode="before")
    @classmethod
    def _rows(cls, value: Any) -> Any:
        return readable_list(
            AllianceMemberAquaPoints,
            value,
            accept=lambda row: isinstance(row, list),
            warn=logger,
            what="member aqua points",
        )


__all__ = ["AllianceMemberAquaPoints", "AllianceMemberAquaPointsRequest", "AllianceMemberAquaPointsResponse"]
