"""
Player protocol models.

Commands:
- gdi: Get detailed player info (including castle list with capture info)
- wsp: World search player (search by name)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator

from .base import BasePayload, BaseRequest, BaseResponse
from .castle import CastleInfo, GetCastlesResponse, get_location_type_name
from .map import GetMapAreaResponse, Kingdom, MapObject
from .profile import PlayerProfileBase

logger = logging.getLogger(__name__)

# =============================================================================
# Location Capture Info
# =============================================================================


class LocationCapture(BasePayload):
    """
    Information about a location being captured.

    Extracted from the gdi response's gcl.C[].AI[] arrays.
    """

    location_id: int = 0
    location_type: int = 0
    location_type_name: str = ""
    x: int = 0
    y: int = 0
    kingdom: Kingdom = Kingdom.GREEN
    capturer_id: int = -1  # Player ID of who is capturing, -1 if none

    @property
    def is_being_captured(self) -> bool:
        """Check if this location is being captured."""
        return self.capturer_id != -1


# =============================================================================
# Player Owner Info
# =============================================================================


class PlayerOwnerInfo(PlayerProfileBase):
    """
    Owner info from the gdi response's O object.

    Common profile fields (OID/N/L/LL/H/AR/CF/HF/MP/DUM/AVP/PRE/SUF/TOPX/
    SA/VF/PF/RRD/TI/RPT/AID/AN/AP/VP/E) are inherited from PlayerProfileBase.
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
    """

    command = "gdi"

    player_id: int = Field(alias="PID")


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

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    owner: PlayerOwnerInfo | None = Field(alias="O", default=None)
    castle_list: GetCastlesResponse = Field(
        alias="gcl",
        default_factory=GetCastlesResponse,
        description="The player's castles, outposts and landmarks, as the gcl command sends them",
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
        return value if isinstance(value, dict) else {}

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
        """Get alliance ID from owner info."""
        return self.owner.alliance_id if self.owner else 0

    @property
    def alliance_name(self) -> str:
        """Get alliance name from owner info."""
        return self.owner.alliance_name if self.owner else ""

    @property
    def has_bird(self) -> bool:
        """Check if player has revenge protection (bird) active."""
        return self.owner.has_bird if self.owner else False

    @property
    def bird_end_time(self) -> datetime | None:
        """When bird protection ends (UTC), or None."""
        return self.owner.bird_end_time if self.owner else None

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
            if castle.occupier_id != -1:
                try:
                    kingdom = Kingdom(castle.kingdom_id)
                except ValueError:
                    continue
                captures.append(
                    LocationCapture(
                        location_id=castle.castle_id,
                        location_type=castle.castle_type,
                        location_type_name=get_location_type_name(castle.castle_type),
                        x=castle.x,
                        y=castle.y,
                        kingdom=kingdom,
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
    command = "wsp"

    player_name: str = Field(alias="PN")


class SearchPlayerResponse(BaseResponse):
    """
    Response to a player search.

    Command: wsp

    Client: ``WSPCommand.executeCommand`` (bundle line 131619) reads ``gaa.OI``
    with ``parseOwnerInfoArray`` and ``gaa.AI`` with ``parseAreaInfos``, as a
    map area reply, then ``CastleWorldmapData.parseSearchInfos`` (bundle line
    19010) opens the area at ``X``/``Y``, the found player's castle.
    """

    command = "wsp"

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    area: GetMapAreaResponse = Field(
        alias="gaa",
        default_factory=GetMapAreaResponse,
        description="The found player's map rows and owner records",
    )
    x: int | None = Field(alias="X", default=None, description="Map x of the found player's castle")
    y: int | None = Field(alias="Y", default=None, description="Map y of the found player's castle")

    @field_validator("area", mode="before")
    @classmethod
    def _area_needs_an_object(cls, value: Any) -> Any:
        return value if isinstance(value, dict) else {}

    def get_player(self) -> MapObject | None:
        """
        The found player's owner record: the owner of the area at ``X``/``Y``.

        Falls back to the first owner record when no row sits at ``X``/``Y``
        or its owner has no record, and None when there are no records.
        """
        at_position = next(
            (item for item in self.area.items if (item.x, item.y) == (self.x, self.y) and item.owner_id >= 0),
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
