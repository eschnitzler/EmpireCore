"""Map bookmarks and alliance search.

Commands:
- gbl: Your own and your alliance's bookmarks
- hgh: Search alliances
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_serializer, field_validator, model_validator

from empire_core.enums import BookmarkType, RankingType
from empire_core.map.models.items import MapAreaItem, parse_area_rows
from empire_core.player.models.profile import PlayerProfileBase
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    enum_or_none,
    object_or_none,
    readable_list,
)
from empire_core.protocol.js import ClientInt, js_int, js_number_or_none, js_truthy
from empire_core.protocol.text import encode_json_text

logger = logging.getLogger(__name__)


# =============================================================================
# GBL - Bookmarks
# =============================================================================


class GetBookmarksRequest(BaseRequest):
    """
    Ask for your own and your alliance's map bookmarks.

    Command: gbl
    Payload: {}

    Client: ``C2SGetBookmarkList`` (bundle line 25872)
    """

    command = "gbl"


class BookmarkAttackOrder(BasePayload):
    """
    The attack order an alliance attack order bookmark carries.

    Client: ``CastleBookmarkAttackOrderDetailsVO.parseParamObject`` (bundle line 68503)
    """

    assigned_attacker_ids: list[int] = Field(alias="M", default_factory=list, description="The players sent to attack")
    attack_in_seconds: int | float | None = Field(
        alias="TI", default=None, description="Seconds until the attack; None when the reply has no number for it"
    )

    @field_validator("assigned_attacker_ids", mode="before")
    @classmethod
    def _player_ids(cls, value: Any) -> Any:
        return [js_int(v) for v in value] if isinstance(value, list) else []

    @field_validator("attack_in_seconds", mode="before")
    @classmethod
    def _number(cls, value: Any) -> Any:
        return js_number_or_none(value)


class Bookmark(BasePayload):
    """
    One map bookmark: an entry of a gbl reply's ``BL`` or ``ABL``.

    Client: ``CastleBookmarkData.parseBookmarkObject`` (bundle line 33427) reads
    ``OI`` as an owner record, then ``CastleWorldmapBookmarkVO.parseParamObject``
    (bundle line 68469) reads the rest.
    """

    kingdom: ClientInt = Field(alias="KID", default=0, description="The bookmarked area's kingdom")
    x: ClientInt = Field(alias="X", default=0, description="Map x")
    y: ClientInt = Field(alias="Y", default=0, description="Map y")
    area: MapAreaItem | None = Field(alias="AI", default=None, description="The bookmarked map row")
    owner: PlayerProfileBase | None = Field(
        alias="OI", default=None, description="The owner record of the bookmarked area"
    )
    name: str | None = Field(alias="N", default=None, description="The bookmark's name")
    bookmark_type: int | None = Field(
        alias="TY", default=None, description="What the bookmark marks, a BookmarkType value"
    )
    bookmark_id: ClientInt = Field(alias="BID", default=0, description="The bookmark's id")
    creator_id: ClientInt = Field(alias="C", default=0, description="The player who made it; 0 when unsent")
    attack_order: BookmarkAttackOrder | None = Field(
        default=None, description="The attack order; only on alliance attack order bookmarks"
    )

    @model_validator(mode="before")
    @classmethod
    def _flat_entry(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        kingdom = data.get("KID")
        data = {**data, "KID": kingdom if js_truthy(kingdom) else data.get("K")}
        creator = data.get("C")
        if js_truthy(creator) and js_int(data.get("TY")) == BookmarkType.ALLIANCE_ATTACK_ORDER:
            data["attack_order"] = BookmarkAttackOrder.model_validate(data)
        if not js_truthy(creator):
            data.pop("C", None)
        return data

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, value: Any) -> Any:
        # Stored as sent; a value that is not text reads as no name instead of losing the bookmark
        return value if isinstance(value, str) else None

    @field_validator("area", mode="before")
    @classmethod
    def _area_row(cls, value: Any) -> Any:
        # parseParamObject reads AI only when it is a non-empty row
        if isinstance(value, MapAreaItem):
            return value
        rows, _ = parse_area_rows([value]) if isinstance(value, list) and value else ([], 0)
        return rows[0] if rows else None

    @field_validator("owner", mode="before")
    @classmethod
    def _owner_record(cls, value: Any) -> Any:
        # parseOwnerInfo reads nothing from a record without an OID
        owner = object_or_none(value)
        return owner if isinstance(owner, dict) and js_truthy(owner.get("OID")) else None

    @field_validator("bookmark_type", mode="before")
    @classmethod
    def _type(cls, value: Any) -> Any:
        # getTypeById(+TY)
        number = js_number_or_none(value)
        return int(number) if number is not None and number == int(number) else None

    @property
    def bookmark_type_enum(self) -> BookmarkType | None:
        """``bookmark_type`` as a :class:`BookmarkType`, None for a type the client does not define."""
        return None if self.bookmark_type is None else enum_or_none(BookmarkType, self.bookmark_type)


class GetBookmarksResponse(BaseResponse):
    """
    Your own and your alliance's map bookmarks.

    Command: gbl

    Client: ``GBLCommand.executeCommand`` (bundle line 131706),
    ``CastleBookmarkData.parse_GBL`` (bundle line 33453)
    """

    command = "gbl"

    own_bookmarks: list[Bookmark] = Field(alias="BL", default_factory=list, description="Your own bookmarks")
    alliance_bookmarks: list[Bookmark] = Field(
        alias="ABL", default_factory=list, description="Your alliance's bookmarks"
    )

    @field_validator("own_bookmarks", "alliance_bookmarks", mode="before")
    @classmethod
    def _entries(cls, value: Any) -> Any:
        return readable_list(Bookmark, value, accept=lambda e: isinstance(e, dict), warn=logger, what="bookmarks")


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
        alias="LT", default=RankingType.ALLIANCE_MIGHT_POINTS, description="The highscore list searched"
    )
    league_type_id: int = Field(
        alias="LID",
        default=6,
        description="The league to search in; 6 is the level 70 league",
    )
    search_value: str = Field(alias="SV", description="The alliance name to search for")

    @field_serializer("search_value")
    def _encoded_search_value(self, value: str) -> str:
        # C2SGetHighscoreVO encodes SV as it encodes any text it sends
        return encode_json_text(value)

    @classmethod
    def create(cls, query: str) -> "SearchAllianceRequest":
        return cls(SV=query)


class SearchAllianceResponse(BaseResponse, register=False):
    """
    Response to alliance search.

    Command: hgh — shared with GetHighscoreResponse, which owns the registry
    entry; this model is instantiated manually by AllianceService.

    Not registered: see class docstring.
    """

    command = "hgh"

    results: list[AllianceSearchResult] = Field(alias="L", default_factory=list, description="The matching rows")

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
    "GetBookmarksRequest",
    "GetBookmarksResponse",
    "Bookmark",
    "BookmarkAttackOrder",
    "AllianceSearchResult",
    "SearchAllianceRequest",
    "SearchAllianceResponse",
]
