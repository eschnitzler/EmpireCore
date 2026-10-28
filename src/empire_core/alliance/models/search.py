"""Alliance search.

Commands:
- hgh: Search alliances
- aas: Join an alliance automatically, or list alliances to join
- sal: Alliances to join, pushed
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_serializer, field_validator, model_validator

from empire_core.alliance.models.membership import AllianceMembership
from empire_core.enums import RankingType
from empire_core.gamedata import EnumOrInt, LeagueType
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
        default=RankingType.ALLIANCE_MIGHT_POINTS,
        description="The highscore list searched",
    )
    league_type_id: EnumOrInt[LeagueType] = Field(
        validation_alias="LID",
        default=LeagueType(6),
        description="The league to search in; 6 is the level 70 league",
    )
    search_value: str = Field(validation_alias="SV", description="The alliance name to search for")

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
        validation_alias="L", default_factory=list, description="The matching rows"
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


# =============================================================================
# AAS / SAL - Alliances to join
# =============================================================================


class AllianceSearchListItem(BasePayload):
    """
    An alliance offered to join.

    Client: ``SearchListAllianceItemVO.parseItem`` (bundle line 42860), which reads ``AID``, ``M``, ``AH``
    and ``AL`` through ``int()`` and keeps ``N``, ``D`` and ``ALL`` as sent
    """

    alliance_id: ClientInt = Field(validation_alias="AID", default=0, description="Alliance id")
    name: str = Field(validation_alias="N", default="", description="Alliance name")
    distance: int | float = Field(validation_alias="D", default=0, description="Distance to the alliance")
    member_count: ClientInt = Field(validation_alias="M", default=0, description="Number of members")
    honor: ClientInt = Field(validation_alias="AH", default=0, description="The alliance's honor")
    level: ClientInt = Field(validation_alias="AL", default=0, description="The alliance's level")
    language: str = Field(validation_alias="ALL", default="", description="The alliance's language code")


def _search_list(value: Any) -> list[AllianceSearchListItem]:
    return readable_list(
        AllianceSearchListItem, value, accept=lambda row: isinstance(row, dict), warn=logger, what="alliances to join"
    )


class AutoAllianceSearchRequest(BaseRequest):
    """
    Join an alliance automatically, or have alliances to join listed.

    Command: aas
    Payload: {"N": name, "D": description, "ALL": language}

    Client: ``C2SAutoAllianceSearchVO`` (bundle line 44117), sent with the translated default
    alliance name by ``CastleAllianceTeaserDialog.onJoinAlliance`` (bundle line 14670), and with
    the picked language too by ``CastleSearchAllianceDialog.setAllianceLanguage`` (bundle line 34593)
    """

    command = "aas"

    name: str = Field(validation_alias="N", description="An alliance name; the game sends its default one")
    description: str = Field(validation_alias="D", default="", description="An alliance description")
    language: str = Field(validation_alias="ALL", default="", description="Language code to search in; empty for all")


class AutoAllianceSearchResponse(BaseResponse):
    """
    Either your new membership, or alliances to join.

    Command: aas
    Payload: {"gal": {...}, "gam": {...}} when you were put in an alliance, else {"AL": [...]}

    Client: ``AASCommand.executeCommand`` (bundle lines 121270-121279): a ``gal`` is applied with the
    ``gam`` beside it, else each ``AL`` row is listed
    """

    command = "aas"

    membership: AllianceMembership | None = Field(
        validation_alias="gal", default=None, description="Your new membership; None when alliances are listed"
    )
    alliances: list[AllianceSearchListItem] = Field(
        validation_alias="AL", default_factory=list, description="Alliances to join, when you were put in none"
    )

    @field_validator("membership", mode="before")
    @classmethod
    def _membership(cls, value: Any) -> Any:
        return value if isinstance(value, (dict, AllianceMembership)) else None

    @field_validator("alliances", mode="before")
    @classmethod
    def _alliances(cls, value: Any) -> Any:
        return _search_list(value)


class AllianceSearchListResponse(BaseResponse):
    """
    Alliances to join, pushed.

    Command: sal
    Payload: {"AL": [...]}

    Client: ``SALCommand.executeCommand`` (bundle line 122033), ``CastleAllianceData.parse_SAL``
    (bundle line 11579), which only hands the list to the open search dialog
    """

    command = "sal"

    alliances: list[AllianceSearchListItem] = Field(
        validation_alias="AL", default_factory=list, description="Alliances to join"
    )

    @field_validator("alliances", mode="before")
    @classmethod
    def _alliances(cls, value: Any) -> Any:
        return _search_list(value)


__all__ = [
    "AllianceSearchListItem",
    "AllianceSearchListResponse",
    "AllianceSearchResult",
    "AutoAllianceSearchRequest",
    "AutoAllianceSearchResponse",
    "SearchAllianceRequest",
    "SearchAllianceResponse",
]
