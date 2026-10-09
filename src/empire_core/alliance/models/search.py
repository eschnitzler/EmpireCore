"""Alliance search.

Commands:
- hgh: Search alliances
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_serializer, field_validator, model_validator

from empire_core.enums import RankingType
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    readable_list,
)
from empire_core.protocol.js import ClientInt
from empire_core.protocol.text import encode_json_text

logger = logging.getLogger(__name__)


# =============================================================================
# HGH - Search Alliance (Highscore/Search)
# =============================================================================


class AllianceSearchResult(BasePayload):
    """
    One row of an alliance highscore list: ``[rank, score, [alliance_id, name, member_count, fame_points]]``.

    Client: ``CastleHighscoreDialog.onGetHighscoreData`` (bundle line 27538)
    shifts rank and score off an alliance list's row and fills an
    ``AllianceHighscoreInfoVO`` (bundle line 27680) from the third field, which
    it ignores unless that is an array. Every number is read with ``int``.
    """

    rank: ClientInt = Field(default=0, description="Rank on the list")
    score: ClientInt = Field(default=0, description="The listed value, the alliance's might on list type 11")
    alliance_id: ClientInt = Field(default=0, description="Alliance id")
    name: str = Field(default="", description="Alliance name")
    member_count: ClientInt = Field(default=0, description="Number of members")
    fame_points: ClientInt = Field(default=0, description="The alliance's current fame")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        fields: dict[str, Any] = dict(zip(("rank", "score"), data[:2], strict=False))
        info = data[2] if len(data) > 2 else None
        if isinstance(info, list):
            fields.update(zip(("alliance_id", "name", "member_count", "fame_points"), info, strict=False))
            if "name" in fields:
                fields["name"] = "" if fields["name"] is None else str(fields["name"])
        return fields


class SearchAllianceRequest(BaseRequest):
    """
    Search for an alliance.

    Command: hgh
    Payload: {"LT": 11, "LID": 6, "SV": name_query}

    Client: ``CastleHighscoreDialog.requestHighscoreData`` (bundle line 27636); 6 is
    ``ClientConstHighscore.getLeagueIdByLevel`` of the level cap (bundle line 45331)
    """

    command = "hgh"

    list_type: RankingType = Field(
        validation_alias="LT",
        serialization_alias="LT",
        default=RankingType.ALLIANCE_MIGHT_POINTS,
        description="The highscore list searched",
    )
    league_type_id: int = Field(
        validation_alias="LID",
        serialization_alias="LID",
        default=6,
        description="The league to search in; 6 is the level 70 league",
    )
    search_value: str = Field(
        validation_alias="SV", serialization_alias="SV", description="The alliance name to search for"
    )

    @field_serializer("search_value")
    def _encoded_search_value(self, value: str) -> str:
        # C2SGetHighscoreVO encodes SV as it encodes any text it sends
        return encode_json_text(value)

    @classmethod
    def create(cls, query: str) -> "SearchAllianceRequest":
        return cls(search_value=query)


class SearchAllianceResponse(BaseResponse, register=False):
    """
    Response to alliance search.

    Command: hgh — shared with GetHighscoreResponse, which owns the registry
    entry; this model is instantiated manually by AllianceService.

    Not registered: see class docstring.

    Client: ``HGHCommand.executeCommand`` (bundle line 124377)
    """

    command = "hgh"

    results: list[AllianceSearchResult] = Field(
        validation_alias="L", serialization_alias="L", default_factory=list, description="The matching rows"
    )

    @field_validator("results", mode="before")
    @classmethod
    def _rows(cls, value: Any) -> Any:
        # The client shifts fields off each row; one that is not a row is skipped instead of failing the reply
        return readable_list(
            AllianceSearchResult,
            value,
            accept=lambda row: isinstance(row, list),
            warn=logger,
            what="alliance search rows",
        )


__all__ = [
    "AllianceSearchResult",
    "SearchAllianceRequest",
    "SearchAllianceResponse",
]
