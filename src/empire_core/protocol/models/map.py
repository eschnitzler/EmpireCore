"""
Map protocol models.

Commands:
- gaa: Get map area/chunk
- gam: Get active movements
- fnm: Find NPC on map
- adi: Get area/target detailed info
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import ConfigDict, Field

from .base import BaseRequest, BaseResponse, PlayerInfo, Position

# =============================================================================
# Map Item Types
# =============================================================================


class Kingdom(IntEnum):
    """
    Kingdom identifiers used throughout the game.

    Each kingdom has different terrain and unit types.
    """

    GREEN = 0  # Green Kingdom - basic/starter kingdom
    SANDS = 1  # Sand Kingdom - desert units
    ICE = 2  # Ice Kingdom - ice/frost units
    FIRE = 3  # Fire Kingdom - lava/fire units
    STORM = 4  # Storm Kingdom - storm/lightning units
    BERIMOND = 10  # Berimond event kingdom


class MapItemType(IntEnum):
    """
    Known map item types from the AI array.

    These are the object types returned in map scan responses.
    """

    EMPTY = 0
    CASTLE = 1  # Player main castle (also moving destination when relocating)
    EMPTY_CASTLE_SLOT = 2  # Unoccupied castle spawn point
    CAPITAL = 3  # Player capital
    OUTPOST = 4  # Player outpost
    RUIN = 5  # Abandoned ruin
    ROBBER_BARON = 6  # Robber Baron castle
    KHAN_TENT = 7  # Khan's tent (event)
    METRO = 22  # Metropolis
    MONUMENT = 26  # Alliance monument
    LABORATORY = 28  # Laboratory


# =============================================================================
# GAA - Get Map Area
# =============================================================================
# GAA - Get Map Area
# =============================================================================


class GetMapAreaRequest(BaseRequest):
    """
    Get a chunk of the map.

    Command: gaa
    Payload: {"KID": kingdom_id, "AX1": x1, "AY1": y1, "AX2": x2, "AY2": y2}

    Returns information about all objects in the specified area.

    The server allows a maximum chunk size of ~90 tiles in each dimension.
    Invalid coordinates (outside map bounds) return empty AI array.

    Example:
        request = GetMapAreaRequest(KID=0, AX1=622, AY1=235, AX2=712, AY2=325)
    """

    command = "gaa"

    kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN)
    x1: int = Field(alias="AX1")
    y1: int = Field(alias="AY1")
    x2: int = Field(alias="AX2")
    y2: int = Field(alias="AY2")


class MapAreaItem(BaseResponse):
    """
    A raw map area item from the AI array.

    AI array format: [[type, x, y, owner_id, ...], ...]

    Common types (see MapItemType enum):
    - 1: Moving castle flag (owner_id = player moving there)
    - 2: Castle
    - 3: Capital
    - 4: Outpost
    - 22: Metropolis
    - 26: Monument
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    item_type: int = 0
    x: int = 0
    y: int = 0
    owner_id: int = -1
    raw_data: list = []  # Full raw array for extended parsing

    @classmethod
    def from_list(cls, data: list) -> "MapAreaItem":
        """Parse from AI array entry."""
        return cls(
            item_type=data[0] if len(data) > 0 else 0,
            x=data[1] if len(data) > 1 else 0,
            y=data[2] if len(data) > 2 else 0,
            owner_id=data[3] if len(data) > 3 else -1,
            raw_data=data,
        )

    @property
    def is_moving_flag(self) -> bool:
        """Check if this is a castle that is being relocated (moving)."""
        # A type-1 castle with owner represents either a stationary castle or one in transit
        # To detect "moving", you need to track state changes or check movement endpoints
        return self.item_type == MapItemType.CASTLE and self.owner_id != -1

    @property
    def is_castle(self) -> bool:
        """Check if this is any player-owned location."""
        return self.item_type in (
            MapItemType.CASTLE,
            MapItemType.CAPITAL,
            MapItemType.OUTPOST,
            MapItemType.METRO,
        )

    @property
    def type_name(self) -> str:
        """Get human-readable type name."""
        try:
            return MapItemType(self.item_type).name
        except ValueError:
            return f"UNKNOWN_{self.item_type}"


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
    Response format: {"KID": 0, "AI": [[type, x, y, owner_id, ...], ...], ...}

    The AI array contains raw map items. Use get_moving_flags() to extract
    castle moving destinations.
    """

    command = "gaa"

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN)
    raw_items: list = Field(alias="AI", default_factory=list)
    objects: list[MapObject] = Field(alias="OI", default_factory=list)

    @property
    def items(self) -> list[MapAreaItem]:
        """Parse raw AI array into MapAreaItem objects."""
        return [MapAreaItem.from_list(item) for item in self.raw_items if isinstance(item, list) and len(item) >= 4]

    def get_moving_flags(self) -> dict[int, tuple[int, int]]:
        """
        Extract moving castle flags from the response.

        Returns:
            Dict mapping player_id -> (destination_x, destination_y)
        """
        result = {}
        for item in self.items:
            if item.is_moving_flag:
                result[item.owner_id] = (item.x, item.y)
        return result


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
    kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN)


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
    kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN)


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
    # Kingdom
    "Kingdom",
    # Map Item Types
    "MapItemType",
    # GAA - Map Area
    "GetMapAreaRequest",
    "GetMapAreaResponse",
    "MapAreaItem",
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
