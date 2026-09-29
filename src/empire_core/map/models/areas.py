"""Map protocol models.

Commands:
- gaa: Get map area/chunk
- fnm: Find NPC on map
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ConfigDict, Field, ValidationInfo, field_validator

from empire_core.enums import Kingdom
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, Position, list_or_empty, object_or_none
from empire_core.protocol.js import ClientInt

from .items import MapAreaItem, parse_area_rows
from .owners import OwnerCrest, OwnerFaction

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


class AllianceCrest(BasePayload):
    """
    An alliance's crest: a layout and its colours.

    Client: ``AllianceCrestVO.fillWithData`` (bundle line 11233).
    """

    layout_id: ClientInt = Field(alias="ACLI", default=0, description="Crest layout id")
    color_ids: list[ClientInt] = Field(
        alias="ACCS", default_factory=list, description="Colour ids, one per layout colour"
    )

    @field_validator("color_ids", mode="before")
    @classmethod
    def _stored_raw(cls, value: Any) -> Any:
        # The client stores ACCS as it arrives, so a missing list is no colours
        return list_or_empty(value)


class AllianceEmblem(BasePayload):
    """
    The alliance crest block of an owner record: its ``aee``.

    Client: ``WorldMapOwnerInfoVO.fillFromParamObject`` (bundle line 10794)
    reads only ``ACCA``, and only for a player in an alliance.
    """

    crest: AllianceCrest | None = Field(alias="ACCA", default=None, description="The alliance's current crest")

    @field_validator("crest", mode="before")
    @classmethod
    def _crest_needs_an_object(cls, value: Any) -> Any:
        return object_or_none(value)


class MapObject(BasePayload):
    """
    An owner record from a map scan's OI list.

    These describe the players who own objects in the scanned area. An AI
    row's player id matches a record's ``owner_id``; the player's own castles
    and villages are listed in ``area_positions`` and ``village_positions`` as
    ``[kingdom_id, object_id, x, y, area_type]``.

    Client: WorldMapOwnerInfoVO.fillFromParamObject
    """

    owner_id: ClientInt | None = Field(alias="OID", default=None)
    is_dummy: bool = Field(alias="DUM", default=False)
    owner_name: str | None = Field(alias="N", default=None)
    emblem: OwnerCrest | None = Field(alias="E", default=None, description="The player's crest")
    level: ClientInt = Field(alias="L", default=0)
    legendary_level: ClientInt = Field(alias="LL", default=0)
    honor: ClientInt = Field(alias="H", default=0)
    achievement_points: ClientInt = Field(alias="AVP", default=0)
    glory_points: ClientInt = Field(alias="CF", default=0)
    highest_glory_points: ClientInt = Field(alias="HF", default=0)
    prefix_title: ClientInt = Field(alias="PRE", default=0)
    suffix_title: ClientInt = Field(alias="SUF", default=0)
    current_top_x: ClientInt = Field(alias="TOPX", default=0)
    might_points: ClientInt = Field(alias="MP", default=0)
    is_ruin: bool = Field(alias="R", default=False)
    alliance_id: ClientInt | None = Field(alias="AID", default=None)
    alliance_rank: ClientInt = Field(alias="AR", default=0)
    alliance_name: str | None = Field(alias="AN", default=None)
    alliance_emblem: AllianceEmblem | None = Field(alias="aee", default=None, description="The alliance's crest")
    remaining_protection_time: ClientInt = Field(alias="RPT", default=0)
    area_positions: list[list[int]] | None = Field(alias="AP", default_factory=list)
    village_positions: list[list[int]] | None = Field(alias="VP", default_factory=list)
    is_searching_alliance: bool = Field(alias="SA", default=False)
    has_vip_flag: bool = Field(alias="VF", default=False)
    has_premium_flag: bool = Field(alias="PF", default=False)
    remaining_relocation_time: ClientInt = Field(alias="RRD", default=0)
    storm_title_id: ClientInt = Field(alias="TI", default=-1)  # -1: no title, 50-53: ranks 1-4, 54: ranks 5-10
    remaining_noob_protection: ClientInt = Field(alias="RNP", default=0)
    faction: OwnerFaction | None = Field(alias="FN", default=None, description="Faction event standing")

    @field_validator("emblem", "alliance_emblem", "faction", mode="before")
    @classmethod
    def _block_needs_an_object(cls, value: Any) -> Any:
        # The client only reads keys off these; anything that is not an object leaves its defaults
        return object_or_none(value)

    @field_validator("area_positions", "village_positions", mode="before")
    @classmethod
    def _unwrap_nested_area_positions(cls, value: object) -> object:
        """Accept the server's occasional extra wrapper around one row (seen on AP in Berimond)."""
        if not isinstance(value, list):
            return value
        return [
            entry[0] if isinstance(entry, list) and len(entry) == 1 and isinstance(entry[0], list) else entry
            for entry in value
        ]


class GetMapAreaResponse(BaseResponse):
    """
    Response containing map area data.

    Command: gaa
    Response format: {"KID": 0, "AI": [[type, x, y, location_id, player_id, ...], ...], ...}

    Use get_moving_flags() to extract the castles that are currently in transit.

    Client: ``GAACommand.executeCommand`` (bundle line 130112) reads ``OI``
    with ``parseOwnerInfoArray`` and ``AI`` with ``parseAreaInfos``.
    """

    command = "gaa"

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The kingdom the area lies in")
    items: list[MapAreaItem] = Field(alias="AI", default_factory=list, description="The area's map rows")
    owners: list[MapObject] = Field(
        alias="OI", default_factory=list, description="Owner records for the players owning the rows"
    )

    @field_validator("items", mode="before")
    @classmethod
    def _parse_rows(cls, value: Any, info: ValidationInfo) -> Any:
        items, skipped = parse_area_rows(value)
        if skipped:
            # One line per response, not per row, so a fully drifted AI array can't flood the log.
            logger.warning(
                f"Skipped {skipped}/{len(value)} unparseable AI rows in map area "
                f"response for kingdom {info.data.get('kingdom')}"
            )
        return items

    def get_ruins(self) -> list[MapObject]:
        """
        Owner records flagged as ruins.

        These have no coordinates; see :class:`MapObject`.
        """
        return [owner for owner in self.owners if owner.is_ruin]

    def get_moving_flags(self) -> dict[int, tuple[int, int]]:
        """
        Extract the castles in this area that are currently relocating.

        Only type-1 entries whose relocation flag (raw field 19) is set count;
        settled castles are ignored. Entries are keyed by the player id (raw
        field 4) so callers can match them against ``AllianceMember.player_id``.

        Returns:
            Dict mapping player_id -> (x, y) in-transit position
        """
        result: dict[int, tuple[int, int]] = {}
        for item in self.items:
            if item.is_relocating and item.player_id > 0:
                result[item.player_id] = (item.x, item.y)
        return result


# =============================================================================
# FNM - Find NPC
# =============================================================================


class FindNPCRequest(BaseRequest):
    """
    Find NPC targets on the map.

    Command: fnm
    Payload: {"NT": npc_type, "L": level, "KID": kingdom_id}

    NPC types vary by game version.
    """

    command = "fnm"

    npc_type: int = Field(alias="NT")
    level: int | None = Field(alias="L", default=None)
    kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN)


class NPCLocation(BasePayload):
    """An NPC location on the map."""

    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    npc_type: int = Field(alias="NT")
    level: int = Field(alias="L")
    npc_id: int = Field(alias="NID", default=0)

    @property
    def position(self) -> Position:
        """Get NPC position."""
        return Position(X=self.x, Y=self.y)


class FindNPCResponse(BaseResponse):
    """
    Response containing NPC locations.

    Command: fnm
    """

    command = "fnm"

    npcs: list[NPCLocation] = Field(alias="N", default_factory=list)


__all__ = [
    "GetMapAreaRequest",
    "GetMapAreaResponse",
    "MapObject",
    "AllianceCrest",
    "AllianceEmblem",
    "FindNPCRequest",
    "FindNPCResponse",
    "NPCLocation",
]
