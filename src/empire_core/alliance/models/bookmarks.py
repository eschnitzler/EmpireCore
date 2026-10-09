"""Map bookmarks, your own and your alliance's.

Commands:
- gbl: Your own and your alliance's bookmarks
- bad / bch / bde / abd: Add, change and delete a bookmark; abd deletes an alliance bookmark
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_validator, model_validator

from empire_core.enums import BookmarkType
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

    assigned_attacker_ids: list[int] = Field(
        validation_alias="M", serialization_alias="M", default_factory=list, description="The players sent to attack"
    )
    attack_in_seconds: int | float | None = Field(
        validation_alias="TI",
        serialization_alias="TI",
        default=None,
        description="Seconds until the attack; None when the reply has no number for it",
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

    kingdom: ClientInt = Field(
        validation_alias="KID", serialization_alias="KID", default=0, description="The bookmarked area's kingdom"
    )
    x: ClientInt = Field(validation_alias="X", serialization_alias="X", default=0, description="Map x")
    y: ClientInt = Field(validation_alias="Y", serialization_alias="Y", default=0, description="Map y")
    area: MapAreaItem | None = Field(
        validation_alias="AI", serialization_alias="AI", default=None, description="The bookmarked map row"
    )
    owner: PlayerProfileBase | None = Field(
        validation_alias="OI",
        serialization_alias="OI",
        default=None,
        description="The owner record of the bookmarked area",
    )
    name: str | None = Field(
        validation_alias="N", serialization_alias="N", default=None, description="The bookmark's name"
    )
    bookmark_type: int | None = Field(
        validation_alias="TY",
        serialization_alias="TY",
        default=None,
        description="What the bookmark marks, a BookmarkType value",
    )
    bookmark_id: ClientInt = Field(
        validation_alias="BID", serialization_alias="BID", default=0, description="The bookmark's id"
    )
    creator_id: ClientInt = Field(
        validation_alias="C", serialization_alias="C", default=0, description="The player who made it; 0 when unsent"
    )
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

    own_bookmarks: list[Bookmark] = Field(
        validation_alias="BL", serialization_alias="BL", default_factory=list, description="Your own bookmarks"
    )
    alliance_bookmarks: list[Bookmark] = Field(
        validation_alias="ABL", serialization_alias="ABL", default_factory=list, description="Your alliance's bookmarks"
    )

    @field_validator("own_bookmarks", "alliance_bookmarks", mode="before")
    @classmethod
    def _entries(cls, value: Any) -> Any:
        return readable_list(Bookmark, value, accept=lambda e: isinstance(e, dict), warn=logger, what="bookmarks")


BOOKMARK_NAME_MAX_LENGTH = 30
"""The longest bookmark name the client's bookmark dialog takes: twice the castle name's limit.

Client: ``CastleWorldmapBookmarkSetDialog.initLoaded`` (bundle line 19546) sets ``maxChars`` to
``2 * PlayerConst.CASTLE_NAME_MAX_LENGTH`` (dll line 19599)
"""

MAX_PLAYER_BOOKMARKS = 50
"""How many own bookmarks a player keeps.

Client: ``PlayerConst.BOOKMARKS_MAX_ENTRYS`` (dll line 19599), read by ``CastleBookmarkData.isPlayerListFull``
"""

MAX_ALLIANCE_BOOKMARKS = 20
"""How many bookmarks an alliance keeps.

Client: ``AllianceConst.ALLIANCE_BOOKMARK_MAX_ENTRIES`` (dll line 18805), read by
``CastleBookmarkData.isAllianceListFull``
"""

ATTACK_ORDER_MIN_SECONDS = 3600
"""The soonest an alliance attack order may be set, in seconds from now.

Client: ``AllianceConst.ALLIANCE_BOOKMARK_MIN_TIME_OFFSET`` (dll line 18782), checked by
``TeamAttackConfiguration`` (bundle line 68564)
"""

ATTACK_ORDER_MAX_SECONDS = 86340
"""The latest an alliance attack order may be set, in seconds from now.

Client: ``AllianceConst.ALLIANCE_BOOKMARK_MAX_TIME_OFFSET`` (dll line 18783), checked by
``TeamAttackConfiguration`` (bundle line 68564)
"""


# =============================================================================
# BAD / BCH / BDE / ABD - Add, change and delete bookmarks
# =============================================================================


class AddBookmarkRequest(BaseRequest):
    """
    Bookmark a map position, for yourself or for your alliance.

    Command: bad
    Payload: {"K", "X", "Y", "TY", "TI", "IM", "N", "M"}, in the client's key order

    Only an alliance attack order carries its time (``TI``, seconds from now), its attackers
    (``M``) and whether they get a message (``IM``); every other bookmark sends ``-1``, ``[]``
    and 0. The name goes out as typed.

    Client: ``C2SAddBookmark`` (bundle line 68517), sent by
    ``CastleWorldmapBookmarkSetDialog.onSubmitButtonClicked`` (bundle line 19584); the attack
    order's seconds from ``TeamAttackConfiguration.updateDateAndTimeDisplay`` (bundle line 68566)
    """

    command = "bad"

    kingdom: int = Field(validation_alias="K", serialization_alias="K", description="The kingdom")
    x: int = Field(validation_alias="X", serialization_alias="X", description="Map x")
    y: int = Field(validation_alias="Y", serialization_alias="Y", description="Map y")
    bookmark_type: int = Field(
        validation_alias="TY", serialization_alias="TY", description="What it marks, a BookmarkType value"
    )
    attack_in_seconds: int = Field(
        validation_alias="TI",
        serialization_alias="TI",
        default=-1,
        description="Seconds until the attack order's attack; -1 for any other bookmark",
    )
    message_attackers: int = Field(
        validation_alias="IM",
        serialization_alias="IM",
        default=0,
        description="1 to send the attack order's attackers a message, else 0",
    )
    name: str = Field(validation_alias="N", serialization_alias="N", description="The bookmark's name")
    attacker_ids: list[int] = Field(
        validation_alias="M",
        serialization_alias="M",
        default_factory=list,
        description="The players the attack order sends; empty for any other",
    )


class AddBookmarkResponse(BaseResponse, Bookmark):
    """
    The bookmark added, read as a gbl entry.

    Command: bad

    Client: ``BADCommand.executeCommand`` (bundle line 131653) passes the reply to
    ``CastleBookmarkData.parse_BAD`` (bundle line 33442), which reads it with
    ``parseBookmarkObject`` (bundle line 33427)
    """

    command = "bad"


class ChangeBookmarkRequest(BaseRequest):
    """
    Rename one of your own bookmarks, or switch it between friend and enemy.

    Command: bch
    Payload: {"KID", "X", "Y", "IF", "DN"}, in the client's key order

    Client: ``C2SChangeBookmark`` (bundle line 68532), sent by
    ``CastleWorldmapBookmarkSetDialog.onSubmitButtonClicked`` (bundle line 19584) only for an
    own bookmark the dialog edits; ``IF`` is ``!!typeIndex``
    """

    command = "bch"

    kingdom: int = Field(validation_alias="KID", serialization_alias="KID", description="The bookmark's kingdom")
    x: int = Field(validation_alias="X", serialization_alias="X", description="Map x")
    y: int = Field(validation_alias="Y", serialization_alias="Y", description="Map y")
    friend: bool = Field(
        validation_alias="IF",
        serialization_alias="IF",
        description="True for a friend bookmark, False for an enemy one",
    )
    name: str = Field(validation_alias="DN", serialization_alias="DN", description="The new name")


class ChangeBookmarkResponse(BaseResponse, Bookmark):
    """
    The bookmark changed, read as a gbl entry.

    Command: bch

    Client: ``BCHCommand.executeCommand`` (bundle line 131672), ``CastleBookmarkData.parse_BCH``
    (bundle line 33443)
    """

    command = "bch"


class DeleteBookmarkRequest(BaseRequest):
    """
    Delete own bookmarks by their positions.

    Command: bde
    Payload: {"BM": [[kingdom, x, y], ...]}

    Client: ``C2SDeleteBookmark`` (bundle line 68457), sent by ``CastleBookmarkData.deleteBookmark``
    and ``deleteBookmarks`` (bundle lines 33474-33475) for an own bookmark
    """

    command = "bde"

    positions: list[list[int]] = Field(
        validation_alias="BM", serialization_alias="BM", description="Each bookmark's [kingdom, x, y]"
    )


class BookmarkPosition(BasePayload):
    """
    Where a deleted bookmark was.

    Client: ``CastleBookmarkData.parse_BDE`` (bundle line 33445) reads ``K``, ``X`` and ``Y``
    """

    kingdom: ClientInt = Field(validation_alias="K", serialization_alias="K", default=0, description="The kingdom")
    x: ClientInt = Field(validation_alias="X", serialization_alias="X", default=0, description="Map x")
    y: ClientInt = Field(validation_alias="Y", serialization_alias="Y", default=0, description="Map y")


class DeleteBookmarkResponse(BaseResponse):
    """
    The own bookmarks deleted.

    Command: bde

    Client: ``BDECommand.executeCommand`` (bundle line 131687), ``CastleBookmarkData.parse_BDE``
    (bundle line 33445): the ``BM`` list, else the reply itself as one position
    """

    command = "bde"

    deleted: list[BookmarkPosition] = Field(
        validation_alias="BM", serialization_alias="BM", default_factory=list, description="The positions deleted"
    )

    @model_validator(mode="before")
    @classmethod
    def _one_or_many(cls, data: Any) -> Any:
        if not isinstance(data, dict) or js_truthy(data.get("BM")):
            return data
        return {**data, "BM": [data]}

    @field_validator("deleted", mode="before")
    @classmethod
    def _positions(cls, value: Any) -> Any:
        return readable_list(
            BookmarkPosition, value, accept=lambda e: isinstance(e, dict), warn=logger, what="positions"
        )


class DeleteAllianceBookmarkRequest(BaseRequest):
    """
    Delete alliance bookmarks by their ids.

    Command: abd
    Payload: {"BM": [[bookmark_id, notify], ...]}

    ``notify`` is 1 to tell an attack order's attackers, as the delete dialog's notify button does.

    Client: ``C2SDeleteAllianceBookmark`` (bundle line 68446), sent by
    ``CastleBookmarkData.deleteBookmark`` (bundle line 33474) from
    ``CastleDeleteAllianceBookmarkDialog.deleteBookmark`` (bundle line 69192)
    """

    command = "abd"

    entries: list[list[int]] = Field(
        validation_alias="BM", serialization_alias="BM", description="Each bookmark's [bookmark_id, notify]"
    )


class DeleteAllianceBookmarkResponse(BaseResponse):
    """
    Acknowledgement of a deleted alliance bookmark; the client reads nothing from it.

    Command: abd
    Client: ``ABDCommand.executeCommand`` (bundle line 131636)
    """

    command = "abd"


__all__ = [
    "GetBookmarksRequest",
    "GetBookmarksResponse",
    "Bookmark",
    "BookmarkAttackOrder",
    "BOOKMARK_NAME_MAX_LENGTH",
    "MAX_PLAYER_BOOKMARKS",
    "MAX_ALLIANCE_BOOKMARKS",
    "ATTACK_ORDER_MIN_SECONDS",
    "ATTACK_ORDER_MAX_SECONDS",
    "AddBookmarkRequest",
    "AddBookmarkResponse",
    "ChangeBookmarkRequest",
    "ChangeBookmarkResponse",
    "DeleteBookmarkRequest",
    "BookmarkPosition",
    "DeleteBookmarkResponse",
    "DeleteAllianceBookmarkRequest",
    "DeleteAllianceBookmarkResponse",
]
