"""
Map protocol models.

Commands:
- gaa: Get map area/chunk
- gam: Get active movements
- fnm: Find NPC on map
- adi: Get area/target detailed info
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from .base import BaseRequest, BaseResponse, PlayerInfo, Position

# =============================================================================
# GAA - Get Map Area
# =============================================================================


class GetMapAreaRequest(BaseRequest):
    """
    Get a chunk of the map.

    Command: gaa
    Payload: {"X": x, "Y": y, "W": width, "H": height, "KID": kingdom_id}

    Returns information about all objects in the specified area.
    """

    command = "gaa"

    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    width: int = Field(alias="W", default=10)
    height: int = Field(alias="H", default=10)
    kingdom_id: int = Field(alias="KID", default=0)


class MapObject(BaseResponse):
    """An object on the map (castle, NPC, resource, etc.)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    object_type: int = Field(alias="OT")  # Type of object
    object_id: int = Field(alias="OID", default=0)
    owner_id: int | None = Field(alias="PID", default=None)
    owner_name: str | None = Field(alias="PN", default=None)
    alliance_id: int | None = Field(alias="AID", default=None)
    alliance_name: str | None = Field(alias="AN", default=None)
    level: int = Field(alias="L", default=0)
    name: str | None = Field(alias="N", default=None)

    @property
    def position(self) -> Position:
        """Get object position."""
        return Position(X=self.x, Y=self.y)


class GetMapAreaResponse(BaseResponse):
    """
    Response containing map area data.

    Command: gaa
    """

    command = "gaa"

    objects: list[MapObject] = Field(alias="O", default_factory=list)


# =============================================================================
# GAM - Get Active Movements
# =============================================================================


class GetMovementsRequest(BaseRequest):
    """
    Get all active troop movements.

    Command: gam
    Payload: {} (empty) or {"CID": castle_id}
    """

    command = "gam"

    castle_id: int | None = Field(alias="CID", default=None)


class Movement(BaseResponse):
    """An active troop movement."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    movement_id: int = Field(alias="MID")
    movement_type: int = Field(alias="MT")  # 1=attack, 2=support, 3=spy, 4=trade, etc.

    # Source
    source_x: int = Field(alias="SX")
    source_y: int = Field(alias="SY")
    source_castle_id: int = Field(alias="SCID", default=0)
    source_player_id: int = Field(alias="SPID", default=0)

    # Target
    target_x: int = Field(alias="TX")
    target_y: int = Field(alias="TY")
    target_castle_id: int | None = Field(alias="TCID", default=None)
    target_player_id: int | None = Field(alias="TPID", default=None)

    # Timing
    start_time: int = Field(alias="ST")  # Unix timestamp
    arrival_time: int = Field(alias="AT")  # Unix timestamp
    return_time: int | None = Field(alias="RT", default=None)

    # Status
    is_returning: bool = Field(alias="IR", default=False)

    @property
    def source_position(self) -> Position:
        """Get source position."""
        return Position(X=self.source_x, Y=self.source_y)

    @property
    def target_position(self) -> Position:
        """Get target position."""
        return Position(X=self.target_x, Y=self.target_y)


class GetMovementsResponse(BaseResponse):
    """
    Response containing active movements.

    Command: gam
    """

    command = "gam"

    movements: list[Movement] = Field(alias="M", default_factory=list)


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
    kingdom_id: int = Field(alias="KID", default=0)


class NPCLocation(BaseResponse):
    """An NPC location on the map."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

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


# =============================================================================
# ADI - Get Area/Target Detailed Info
# =============================================================================


class GetTargetInfoRequest(BaseRequest):
    """
    Get detailed info about a specific map location/target.

    Command: adi
    Payload: {"X": x, "Y": y, "KID": kingdom_id}
    """

    command = "adi"

    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    kingdom_id: int = Field(alias="KID", default=0)


class TargetInfo(BaseResponse):
    """Detailed information about a target location."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    object_type: int = Field(alias="OT")
    object_id: int = Field(alias="OID", default=0)

    # Owner info (if owned)
    owner: PlayerInfo | None = Field(alias="O", default=None)

    # Castle-specific
    castle_name: str | None = Field(alias="CN", default=None)
    castle_level: int | None = Field(alias="CL", default=None)

    # NPC-specific
    npc_type: int | None = Field(alias="NT", default=None)
    npc_level: int | None = Field(alias="NL", default=None)

    # Resources (for resource nodes)
    resources: int | None = Field(alias="R", default=None)


class GetTargetInfoResponse(BaseResponse):
    """
    Response containing target information.

    Command: adi
    """

    command = "adi"

    target: TargetInfo | None = Field(alias="T", default=None)


__all__ = [
    # GAA - Map Area
    "GetMapAreaRequest",
    "GetMapAreaResponse",
    "MapObject",
    # GAM - Movements
    "GetMovementsRequest",
    "GetMovementsResponse",
    "Movement",
    # FNM - Find NPC
    "FindNPCRequest",
    "FindNPCResponse",
    "NPCLocation",
    # ADI - Target Info
    "GetTargetInfoRequest",
    "GetTargetInfoResponse",
    "TargetInfo",
]
