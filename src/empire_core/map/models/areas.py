"""Map protocol models.

Commands:
- gaa: Get map area/chunk
- fnm: Find the next map object of a type
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ConfigDict, Field, ValidationInfo, field_validator, model_validator

from empire_core.enums import Kingdom, MapItemType, PeaceModeStatus
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    enum_or_none,
    object_or_none,
    readable_list,
)
from empire_core.protocol.js import ClientInt, ParseInt, js_loose_equals, js_parse_int, js_truthy

from .items import MapAreaItem, parse_area_rows
from .owners import AllianceEmblem, OwnerCastlePosition, OwnerCrest, OwnerFaction

logger = logging.getLogger(__name__)


# =============================================================================
# GAA - Get Map Area
# =============================================================================


class GetMapAreaRequest(BaseRequest):
    """
    Get the map rows of a rectangle of one kingdom.

    Command: gaa
    Payload: {"KID": kingdom, "AX1": x1, "AY1": y1, "AX2": x2, "AY2": y2}

    The client asks for at most 100 tiles a side: it clamps ``AX2`` to
    ``AX1 + 99`` once the span passes 100, and ``AY2`` the same way.

    Client: ``C2SGetAreasVO`` (bundle line 65991), built by
    ``CastleWorldmapData.updateAreaRange`` (bundle line 19006)
    """

    command = "gaa"

    kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The kingdom to read")
    x1: int = Field(alias="AX1", description="First corner's map x")
    y1: int = Field(alias="AY1", description="First corner's map y")
    x2: int = Field(alias="AX2", description="Second corner's map x")
    y2: int = Field(alias="AY2", description="Second corner's map y")


class MapObject(BasePayload):
    """
    An owner record: one player named by the rows of a map reply's ``OI`` list.

    A row's ``owner_id`` (or a relocating castle's ``occupier_id``) matches a
    record's ``owner_id``. The player's castles and villages, wherever they
    are, are listed in ``castle_positions`` and ``village_positions``.

    The client reads most numbers through ``parseInt`` and skips a record
    with no ``OID``. It reads ``aee`` only for a player in an alliance; this
    model reads it whenever it is sent.

    Client: ``WorldMapOwnerInfoVO.fillFromParamObject`` (bundle line 10794),
    ``CastleOtherPlayerData.parseOwnerInfo`` (bundle line 138996)
    """

    owner_id: int | None = Field(alias="OID", default=None, description="Player id; negative for an NPC")
    is_dummy: bool = Field(alias="DUM", default=False, description="The record stands in for a player not loaded")

    @model_validator(mode="before")
    @classmethod
    def _dummy_keeps_only_its_id(cls, data: Any) -> Any:
        # CastleOtherPlayerData.parseOwnerInfo (bundle line 139000): a record with a truthy DUM becomes a
        # dummy player with just its id, and fillFromParamObject never reads the rest
        if isinstance(data, dict) and js_truthy(data.get("DUM")):
            return {"OID": data.get("OID"), "N": "", "DUM": 1}
        return data

    owner_name: str | None = Field(alias="N", default=None, description="Player name")
    emblem: OwnerCrest | None = Field(alias="E", default=None, description="The player's crest")
    level: ParseInt = Field(alias="L", default=0, description="Player level")
    legendary_level: ParseInt = Field(alias="LL", default=0, description="Legendary level")
    honor: ParseInt = Field(alias="H", default=0, description="Honor")
    achievement_points: ParseInt = Field(alias="AVP", default=0, description="Achievement points")
    prefix_title: int | None = Field(alias="PRE", default=None, description="Title id shown before the name")
    suffix_title: int | None = Field(alias="SUF", default=None, description="Title id shown after the name")
    current_top_x: ParseInt = Field(alias="TOPX", default=0, description="Top-ranking placement marker")
    might_points: ParseInt = Field(alias="MP", default=0, description="Might points")
    is_ruin: bool = Field(alias="R", default=False, description="The player's castles are ruins")
    alliance_id: int | None = Field(alias="AID", default=None, description="Alliance id; negative for none")
    alliance_rank: ParseInt = Field(alias="AR", default=0, description="Rank in the alliance")
    alliance_name: str = Field(alias="AN", default="", description="Alliance name")
    alliance_emblem: AllianceEmblem | None = Field(alias="aee", default=None, description="The alliance's crest")
    remaining_protection_time: ParseInt = Field(alias="RPT", default=0, description="Seconds of peace protection left")
    castle_positions: list[OwnerCastlePosition] = Field(
        alias="AP", default_factory=list, description="The player's castles"
    )
    village_positions: list[OwnerCastlePosition] = Field(
        alias="VP", default_factory=list, description="The player's villages"
    )
    is_searching_alliance: bool = Field(alias="SA", default=False, description="Looking for an alliance")
    has_vip_flag: bool = Field(alias="VF", default=False, description="VIP flag")
    has_premium_flag: bool = Field(alias="PF", default=False, description="Premium flag")
    remaining_relocation_time: ParseInt = Field(
        alias="RRD", default=0, description="Seconds until the player's castle relocation ends"
    )
    remaining_noob_protection: ParseInt = Field(
        alias="RNP", default=0, description="Seconds of beginner protection left"
    )
    faction: OwnerFaction | None = Field(alias="FN", default=None, description="Faction event standing")
    via_refer_a_friend: bool = Field(alias="IRF", default=False, description="Joined through refer-a-friend")

    @field_validator("owner_id", "alliance_id", mode="before")
    @classmethod
    def _parse_int_or_none(cls, value: Any) -> Any:
        return js_parse_int(value)

    @field_validator("is_dummy", mode="before")
    @classmethod
    def _one(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    @field_validator("is_ruin", mode="before")
    @classmethod
    def _parsed_one(cls, value: Any) -> bool:
        return js_parse_int(value) == 1

    @field_validator("is_searching_alliance", "has_vip_flag", "has_premium_flag", mode="before")
    @classmethod
    def _truthy(cls, value: Any) -> bool:
        return js_truthy(value)

    @field_validator("via_refer_a_friend", mode="before")
    @classmethod
    def _parsed_truthy(cls, value: Any) -> bool:
        return bool(js_parse_int(value))

    @field_validator("alliance_name", mode="before")
    @classmethod
    def _name_or_empty(cls, value: Any) -> Any:
        return value if js_truthy(value) else ""

    @field_validator("emblem", "alliance_emblem", "faction", mode="before")
    @classmethod
    def _block_needs_an_object(cls, value: Any) -> Any:
        # The client only reads keys off these; anything that is not an object leaves its defaults
        return object_or_none(value)

    @field_validator("castle_positions", "village_positions", mode="before")
    @classmethod
    def _position_rows(cls, value: Any) -> Any:
        """
        Rows as ``WorldMapOwnerInfoVO.parsePosList`` (bundle line 10795) reads them.

        A row the server wraps in one extra list (seen on AP in Berimond) is
        unwrapped, which the client does not do; a row that still cannot be
        read is skipped instead of failing the record.
        """
        if not isinstance(value, list):
            return []
        unwrapped = [
            entry[0] if isinstance(entry, list) and len(entry) == 1 and isinstance(entry[0], list) else entry
            for entry in value
        ]
        return readable_list(OwnerCastlePosition, unwrapped)


def _owner_records(value: Any) -> list[MapObject]:
    """``CastleOtherPlayerData.parseOwnerInfo`` (bundle line 138996) skips a record without an ``OID``."""
    return readable_list(
        MapObject,
        value,
        accept=lambda record: isinstance(record, dict),
        keep=lambda record: js_truthy(record.get("OID")),
        warn=logger,
        what="owner records",
    )


class KingdomProtection(BasePayload):
    """
    The player's own protection in one kingdom: a ``uap`` block.

    ``PMS`` and ``PMT`` mean the peace mode outside Berimond and the faction
    protection in Berimond, as the client reads them. The client acts on the
    block only for the kingdom it is in.

    Client: ``CastleUserData.parse_UAP`` (bundle lines 9899-9906), which hands a
    Berimond block to ``FactionEventVO.parse_uap`` (bundle line 7366)
    """

    kingdom_id: int | None = Field(alias="KID", default=None, description="The kingdom this protection is for")
    noob_protection_seconds: ClientInt = Field(
        alias="NS", default=0, description="Seconds of beginner protection left in that kingdom"
    )
    protection_status: ClientInt = Field(
        alias="PMS",
        default=0,
        description="Peace mode status (see peace_mode_status), or in Berimond the faction protection status",
    )
    protection_seconds: ClientInt = Field(
        alias="PMT", default=0, description="Seconds left of the peace mode stage, or in Berimond of faction protection"
    )

    @property
    def is_noob_protected(self) -> bool:
        """Whether the player still has beginner protection there."""
        return self.noob_protection_seconds > 0

    @property
    def peace_mode_status(self) -> PeaceModeStatus | None:
        """``protection_status`` as a peace mode stage; None for a value the client does not define."""
        return enum_or_none(PeaceModeStatus, self.protection_status)


class MapArea(BasePayload):
    """
    Map rows and the owner records of the players they name: the ``gaa`` block of a find reply.

    Client: ``FNMCommand.executeCommand`` (bundle line 40185) reads ``gaa.OI``
    with ``parseOwnerInfoArray`` and ``gaa.AI`` with ``parseAreaInfos``.
    """

    items: list[MapAreaItem] = Field(alias="AI", default_factory=list, description="The map rows")
    owners: list[MapObject] = Field(alias="OI", default_factory=list, description="Owner records for the rows")

    @field_validator("items", mode="before")
    @classmethod
    def _parse_rows(cls, value: Any) -> Any:
        items, skipped = parse_area_rows(value)
        if skipped:
            logger.warning(f"Skipped {skipped}/{len(value)} unparseable map rows")
        return items

    @field_validator("owners", mode="before")
    @classmethod
    def _parse_owners(cls, value: Any) -> Any:
        return _owner_records(value)


class GetMapAreaResponse(BaseResponse):
    """
    The map rows of a rectangle, the owner records of the players they name, and the player's own protection.

    Command: gaa
    Response format: {"KID": 0, "AI": [[type, x, y, ...], ...], "OI": [{...}, ...],
    "uap": {"KID": .., "NS": .., "PMS": .., "PMT": ..}}

    Each row is read in the reply's kingdom (see :class:`MapAreaItem`). A scan
    moves the session off the castle it had joined, so castle-scoped reads
    after it must join the castle again (``client.army`` methods do).

    Client: ``GAACommand.executeCommand`` (bundle line 130112) reads ``uap``
    with ``parse_UAP``, ``OI`` with ``parseOwnerInfoArray`` and ``AI`` with
    ``parseAreaInfos``.
    """

    command = "gaa"

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The kingdom the area lies in")
    items: list[MapAreaItem] = Field(alias="AI", default_factory=list, description="The area's map rows")
    owners: list[MapObject] = Field(
        alias="OI", default_factory=list, description="Owner records for the players the rows name"
    )
    protection: KingdomProtection | None = Field(
        alias="uap", default=None, description="The player's own protection in the kingdom"
    )

    @field_validator("items", mode="before")
    @classmethod
    def _parse_rows(cls, value: Any, info: ValidationInfo) -> Any:
        kingdom = info.data.get("kingdom", Kingdom.GREEN)
        items, skipped = parse_area_rows(value, kingdom)
        if skipped:
            # One line per response, not per row, so a fully drifted AI array can't flood the log.
            logger.warning(
                f"Skipped {skipped}/{len(value)} unparseable AI rows in map area response for kingdom {kingdom}"
            )
        return items

    @field_validator("owners", mode="before")
    @classmethod
    def _parse_owners(cls, value: Any) -> Any:
        return _owner_records(value)

    @field_validator("protection", mode="before")
    @classmethod
    def _protection_needs_an_object(cls, value: Any) -> Any:
        return object_or_none(value)

    def get_ruins(self) -> list[MapObject]:
        """Owner records flagged as ruins; their castles are in each record's ``castle_positions``."""
        return [owner for owner in self.owners if owner.is_ruin]

    def get_moving_flags(self) -> dict[int, tuple[int, int]]:
        """
        The castles in this area that are on the move, by the relocating player's id.

        See :attr:`MapAreaItem.is_relocating`; the owner record with that id
        says how long the relocation has left. Whether ``(x, y)`` is where the
        castle comes from or where it goes is not settled by the client.

        Returns:
            Dict mapping player_id -> (x, y)
        """
        return {
            item.occupier_id: (item.x, item.y)
            for item in self.items
            if item.is_relocating and item.occupier_id is not None
        }


# =============================================================================
# FNM - Find the next map object
# =============================================================================


class FindNextMapObjectRequest(BaseRequest):
    """
    Find the nearest map object of one area type, as the client's "show me" and "jump to" buttons do.

    Command: fnm
    Payload: {"T": area_type, "KID": kingdom, "LMIN": min_level, "LMAX": max_level, "NID": owner_id}

    The client asks this for robber baron camps (DUNGEON with LMIN and LMAX 1,
    bundle line 143000), alien camps (bundle lines 114204, 117711), faction
    invasion, samurai and nomad camps and the alliance raid portal, naming the
    NPC owner of the camps it wants (bundle lines 75451, 91575, 98463, 98544,
    98951), and Berimond faction camps with LMIN -3 (bundle line 54675); quest
    jumps default LMIN to -3 too (bundle line 97692). What LMIN -3 asks for is
    not settled by the client. The server answers NO_PLAYER_FOUND (153) when
    nothing matches.

    Client: ``C2SFindNextMapObjectVO`` (bundle line 8970), whose key order the
    fields follow
    """

    command = "fnm"

    area_type: MapItemType = Field(alias="T", description="The area type to look for")
    kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The kingdom to look in")
    min_level: int = Field(alias="LMIN", default=-1, description="Lowest level to match, -1 for any")
    max_level: int = Field(alias="LMAX", default=-1, description="Highest level to match, -1 for any")
    owner_id: int = Field(alias="NID", default=-1, description="The NPC owner to match, -1 for any")


class FindNextMapObjectResponse(BaseResponse):
    """
    Where the object found lies, with the map rows around it.

    Command: fnm
    Payload: {"gaa": {"AI": [...], "OI": [...]}, "X": x, "Y": y}

    Client: ``FNMCommand.executeCommand`` (bundle line 40185), which centres
    the map on ``X``/``Y`` with ``CastleWorldmapData.parseSearchInfos``
    (bundle line 19010).
    """

    command = "fnm"

    x: int = Field(alias="X", default=0, description="Map x of the object found")
    y: int = Field(alias="Y", default=0, description="Map y of the object found")
    area: MapArea = Field(alias="gaa", default_factory=MapArea, description="The map rows around it")

    @field_validator("area", mode="before")
    @classmethod
    def _area_needs_an_object(cls, value: Any) -> Any:
        return value if isinstance(value, (dict, MapArea)) else {}

    def found(self) -> MapAreaItem | None:
        """The row at ``(x, y)``, when the reply includes it."""
        return next((item for item in self.area.items if (item.x, item.y) == (self.x, self.y)), None)


__all__ = [
    "GetMapAreaRequest",
    "GetMapAreaResponse",
    "MapArea",
    "MapObject",
    "KingdomProtection",
    "FindNextMapObjectRequest",
    "FindNextMapObjectResponse",
]
