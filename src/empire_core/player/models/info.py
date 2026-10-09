"""
Player protocol models.

Commands:
- gdi: Get detailed player info (including castle list with capture info)
- wsp: World search player (search by name)
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

from empire_core.castle.models.castles import CastleInfo, GetCastlesResponse
from empire_core.enums import Kingdom, MapItemType
from empire_core.map.models.areas import MapArea, MapObject
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, object_or_none
from empire_core.protocol.js import js_int
from empire_core.protocol.text import encode_json_text

from .profile import PlayerProfileBase

logger = logging.getLogger(__name__)

# =============================================================================
# Location Capture Info
# =============================================================================


class LocationCapture(BasePayload):
    """
    One of the player's locations that someone occupies, from the gdi castle list.

    Built from a :class:`CastleInfo` that is occupied: its ``occupier_id`` is above -1, as the
    client's ``isOccupied`` checks.

    Client: ``InteractiveMapobjectVO.parseAreaInfo`` (bundle line 3631) and
    ``CapitalMapobjectVO.parseAreaInfo`` (bundle line 18729) read the occupier
    as ``occupierID``
    """

    location_id: int = Field(default=0, description="The location's object id")
    location_type: MapItemType = Field(default=MapItemType.EMPTY, description="The location's area type")
    x: int = Field(default=0, description="Map x")
    y: int = Field(default=0, description="Map y")
    kingdom: Kingdom = Field(default=Kingdom.GREEN, description="The location's kingdom")
    capturer_id: int = Field(default=-1, description="Player id of the occupier, -1 when there is none")

    @property
    def is_being_captured(self) -> bool:
        """Whether someone occupies this location: an occupier id above -1."""
        return self.capturer_id > -1


# =============================================================================
# Player Owner Info
# =============================================================================


class PlayerOwnerInfo(PlayerProfileBase):
    """
    The gdi reply's ``O`` block: the player's owner record.

    Client: ``GDICommand.executeCommand`` (bundle line 129458) reads it with
    ``CastleOtherPlayerData.parseOwnerInfo`` (bundle line 138996)
    """


# =============================================================================
# GDI - Get Detailed Player Info
# =============================================================================


class GetPlayerInfoRequest(BaseRequest):
    """
    Get detailed player information including castle list.

    Command: gdi
    Payload: {"PID": player_id}

    Returns owner info (O) and castle list (gcl.C) with capture status.

    Client: ``C2SGetDetailPlayerInfo`` (bundle line 27021)
    """

    command = "gdi"

    player_id: int = Field(
        validation_alias="PID",
        serialization_alias="PID",
        description=(
            "A player's id, e.g. MapObject.owner_id from a map scan or client.player.search_player_by_name(), "
            "or AllianceMember.player_id"
        ),
    )

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a gdi reply is about this player: its owner record's ``OID`` is ``PID``.

        Client: ``GDICommand.executeCommand`` (bundle line 129458) reads the player from
        ``O.OID``; ``CastleSendGoodsDialog.handleCastlesList`` (line 27122) keeps only the reply
        about the player it asked for.
        """
        owner = payload.get("O") if isinstance(payload, dict) else None
        return isinstance(owner, dict) and js_int(owner.get("OID")) == self.player_id


class GetPlayerInfoResponse(BaseResponse):
    """
    Response containing detailed player information.

    Command: gdi
    Response format: {
        "O": { ...player fields... },
        "gcl": {"PID": ..., "C": [{"KID": ..., "AI": [{"AI": [...], ...}]}]}
    }

    Client: ``GDICommand.executeCommand`` (bundle line 129458) reads ``O`` with
    ``parseOwnerInfo`` and hands ``gcl`` to the same
    ``CastleListVO.parseCastleList`` as the gcl command.
    """

    command = "gdi"

    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True, extra="allow")

    owner: PlayerOwnerInfo | None = Field(validation_alias="O", serialization_alias="O", default=None)
    castle_list: GetCastlesResponse = Field(
        validation_alias="gcl",
        serialization_alias="gcl",
        default_factory=GetCastlesResponse,
        description="The player's castles, outposts and landmarks, shaped as a GetCastlesResponse",
    )

    @model_validator(mode="before")
    @classmethod
    def _fold_landmark_lists_into_gcl(cls, data: Any) -> Any:
        """
        Client: ``GDICommand.addGKLToGC``, ``addGMLToGC`` and ``addGLLToGC``
        (bundle line 129458) push each kings tower, monument and laboratory
        row of ``gkl``, ``gml`` and ``gll``, sent wrapped in one list, into
        the first kingdom of ``gcl`` before parsing it.
        """
        if not isinstance(data, dict):
            return data
        rows = [
            {"AI": entry[0]}
            for key in ("gkl", "gml", "gll")
            if isinstance(data.get(key), dict) and isinstance(data[key].get("AI"), list)
            for entry in data[key]["AI"]
            if isinstance(entry, list) and entry
        ]
        gcl = data.get("gcl")
        if not rows or not isinstance(gcl, dict) or not isinstance(gcl.get("C"), list) or not gcl["C"]:
            return data
        first = gcl["C"][0]
        if not isinstance(first, dict) or not isinstance(first.get("AI"), list):
            return data
        kingdoms = [{**first, "AI": [*first["AI"], *rows]}, *gcl["C"][1:]]
        return {**data, "gcl": {**gcl, "C": kingdoms}}

    @field_validator("castle_list", mode="before")
    @classmethod
    def _castle_list_needs_an_object(cls, value: Any) -> Any:
        return object_or_none(value) or {}

    @property
    def player_id(self) -> int:
        """Get player ID from owner info."""
        return self.owner.player_id if self.owner else 0

    @property
    def player_name(self) -> str:
        """Get player name from owner info."""
        return self.owner.name if self.owner else ""

    @property
    def alliance_id(self) -> int:
        """The player's alliance id, -1 when the player is in none or the reply has no owner."""
        return self.owner.alliance_id if self.owner else -1

    @property
    def alliance_name(self) -> str:
        """Get alliance name from owner info."""
        return self.owner.alliance_name if self.owner else ""

    @property
    def has_bird(self) -> bool:
        """Whether the player has peace protection left now; False once it has run out or without owner."""
        return self.owner.has_bird if self.owner else False

    @property
    def has_beginner_protection(self) -> bool:
        """Whether the player has beginner protection left now; False once it has run out or without owner."""
        return self.owner.has_beginner_protection if self.owner else False

    @property
    def revenge_protection_end(self) -> float | None:
        """When peace protection ends, in time.monotonic() seconds; None without protection or owner."""
        return self.owner.revenge_protection_end if self.owner else None

    def get_castles(self) -> list[CastleInfo]:
        """All castles, outposts and landmarks across all kingdoms."""
        return list(self.castle_list.castles)

    def get_location_captures(self) -> list[LocationCapture]:
        """
        Extract locations that are being captured.

        Returns:
            List of LocationCapture objects for locations with active captures.
        """
        captures = []
        for castle in self.get_castles():
            if castle.is_occupied:
                captures.append(
                    LocationCapture(
                        location_id=castle.castle_id,
                        location_type=castle.castle_type,
                        x=castle.x,
                        y=castle.y,
                        kingdom=castle.kingdom_id,
                        capturer_id=castle.occupier_id,
                    )
                )
        return captures

    def get_all_captures_by_location(self) -> dict[int, int]:
        """
        Get a mapping of location_id -> capturer_id for all captures.

        Returns:
            Dict mapping location_id to the player_id who is capturing it.
        """
        return {cap.location_id: cap.capturer_id for cap in self.get_location_captures()}


# =============================================================================
# WSP - World Search Player
# =============================================================================


class SearchPlayerRequest(BaseRequest):
    """
    Find a player by name.

    Command: wsp
    Payload: {"PN": player_name}, the name encoded as chat text

    Client: ``C2SSearchPlayerVO`` (bundle line 66000), sent by
    ``CastleWorldmapData.searchPlayerByName`` (bundle line 19009)
    """

    command = "wsp"

    player_name: str = Field(validation_alias="PN", serialization_alias="PN", description="The player's name, as typed")

    @field_serializer("player_name")
    def _encoded_name(self, value: str) -> str:
        return encode_json_text(value)


class SearchPlayerResponse(BaseResponse):
    """
    Response to a player search.

    Command: wsp

    Client: ``WSPCommand.executeCommand`` (bundle line 131619) reads ``gaa.OI``
    with ``parseOwnerInfoArray`` and ``gaa.AI`` with ``parseAreaInfos``, as the
    fnm reply does, then ``CastleWorldmapData.parseSearchInfos`` (bundle line
    19010) opens the area at ``X``/``Y``, the found player's castle.
    """

    command = "wsp"

    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True, extra="allow")

    area: MapArea = Field(
        validation_alias="gaa",
        serialization_alias="gaa",
        default_factory=MapArea,
        description="The found player's map rows and owner records",
    )
    x: int | None = Field(
        validation_alias="X", serialization_alias="X", default=None, description="Map x of the found player's castle"
    )
    y: int | None = Field(
        validation_alias="Y", serialization_alias="Y", default=None, description="Map y of the found player's castle"
    )

    @field_validator("area", mode="before")
    @classmethod
    def _area_needs_an_object(cls, value: Any) -> Any:
        return object_or_none(value) or {}

    def get_player(self) -> MapObject | None:
        """
        The found player's owner record: the owner of the area at ``X``/``Y``.

        Falls back to the first owner record when no row sits at ``X``/``Y``
        or its owner has no record, and None when there are no records.
        """
        at_position = next(
            (item for item in self.area.items if (item.x, item.y) == (self.x, self.y) and item.has_player_owner),
            None,
        )
        if at_position is not None:
            owner = next((o for o in self.area.owners if o.owner_id == at_position.owner_id), None)
            if owner is not None:
                return owner
        return self.area.owners[0] if self.area.owners else None


__all__ = [
    "GetPlayerInfoRequest",
    "GetPlayerInfoResponse",
    "PlayerOwnerInfo",
    "LocationCapture",
    "SearchPlayerRequest",
    "SearchPlayerResponse",
]
