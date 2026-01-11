import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from empire_core.utils.enums import MapObjectType, MovementType


class MapObject(BaseModel):
    """Represents an object on the world map (Castle, Resource, NPC)."""

    model_config = ConfigDict(extra="ignore")

    area_id: int = Field(default=-1, alias="AID")
    owner_id: int = Field(default=-1, alias="OID")
    type: MapObjectType = Field(default=MapObjectType.UNKNOWN, alias="T")
    level: int = Field(default=0, alias="L")

    # Location - sometimes embedded or passed separately
    x: int = Field(default=0, alias="X")
    y: int = Field(default=0, alias="Y")
    kingdom_id: int = Field(default=0, alias="KID")

    # Metadata
    name: str = Field(default="")
    owner_name: str = Field(default="")
    alliance_id: int = Field(default=-1)
    alliance_name: str = Field(default="")

    @property
    def is_player(self) -> bool:
        return self.type.is_player

    @property
    def is_npc(self) -> bool:
        return self.type.is_npc

    @property
    def is_event(self) -> bool:
        return self.type.is_event

    @property
    def is_resource(self) -> bool:
        return self.type.is_resource

    @property
    def category(self) -> str:
        if self.is_player:
            return "Player"
        if self.is_npc:
            return "NPC"
        if self.is_event:
            return "Event"
        if self.is_resource:
            return "Resource"
        return "Other"


class Army(BaseModel):
    """Represents troops in a movement or castle."""

    model_config = ConfigDict(extra="ignore")
    units: Dict[int, int] = Field(default_factory=dict)  # UnitID -> Count


class MovementResources(BaseModel):
    """Resources being transported in a movement."""

    model_config = ConfigDict(extra="ignore")

    wood: int = Field(default=0, alias="W")
    stone: int = Field(default=0, alias="S")
    food: int = Field(default=0, alias="F")

    # Special resources
    iron: int = Field(default=0, alias="I")
    glass: int = Field(default=0, alias="G")
    ash: int = Field(default=0, alias="A")
    honey: int = Field(default=0, alias="HONEY")
    mead: int = Field(default=0, alias="MEAD")
    beef: int = Field(default=0, alias="BEEF")

    @property
    def total(self) -> int:
        """Total resources in transport."""
        return self.wood + self.stone + self.food + self.iron + self.glass + self.ash

    @property
    def is_empty(self) -> bool:
        """Check if no resources are being transported."""
        return self.total == 0


class Movement(BaseModel):
    """Represents a movement (Attack, Support, Transport, etc.)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    MID: int = Field(default=-1)  # Movement ID
    T: int = Field(default=0)  # Type (11=return, etc.)
    PT: int = Field(default=0)  # Progress Time
    TT: int = Field(default=0)  # Total Time
    D: int = Field(default=0)  # Direction
    TID: int = Field(default=-1)  # Target/Owner ID
    KID: int = Field(default=0)  # Kingdom ID
    SID: int = Field(default=-1)  # Source ID
    OID: int = Field(default=-1)  # Owner ID
    HBW: int = Field(default=-1)  # ?

    # TA = Target Area (array with area details)
    # SA = Source Area (array with area details)
    target_area: Optional[List[Any]] = Field(default=None, alias="TA")
    source_area: Optional[List[Any]] = Field(default=None, alias="SA")

    # Extracted fields
    target_area_id: int = Field(default=-1)
    source_area_id: int = Field(default=-1)
    target_x: int = Field(default=-1)
    target_y: int = Field(default=-1)
    source_x: int = Field(default=-1)
    source_y: int = Field(default=-1)

    # Units in movement (UnitID -> Count)
    units: Dict[int, int] = Field(default_factory=dict)

    # Estimated army size (GS field when army not visible)
    estimated_size: int = Field(default=0)

    # Resources being transported (for transport/return movements)
    resources: MovementResources = Field(default_factory=MovementResources)

    # Target/Source names (if available)
    target_name: str = Field(default="")
    source_name: str = Field(default="")
    target_player_name: str = Field(default="")
    source_player_name: str = Field(default="")
    target_alliance_name: str = Field(default="")
    source_alliance_name: str = Field(default="")

    # Timestamps for tracking
    created_at: float = Field(default_factory=time.time)  # When we first saw this movement
    last_updated: float = Field(default_factory=time.time)  # Last update time

    # Commander raw data (from UM.L in movement wrapper)
    # These are exposed for consumers to calculate stats using dynamic effect IDs
    commander_equipment: list = Field(default_factory=list)  # EQ array from UM.L
    commander_effects: list = Field(default_factory=list)  # AE array from UM.L

    @property
    def movement_id(self) -> int:
        return self.MID

    @property
    def movement_type(self) -> int:
        return self.T

    @property
    def movement_type_enum(self) -> MovementType:
        """Get the MovementType enum value."""
        try:
            return MovementType(self.T)
        except ValueError:
            return MovementType.UNKNOWN

    @property
    def movement_type_name(self) -> str:
        """Get the name of the movement type."""
        try:
            return MovementType(self.T).name
        except ValueError:
            return f"UNKNOWN_{self.T}"

    @property
    def progress_time(self) -> int:
        return self.PT

    @property
    def total_time(self) -> int:
        return self.TT

    @property
    def time_remaining(self) -> int:
        return max(0, self.TT - self.PT)

    @property
    def progress_percent(self) -> float:
        if self.TT > 0:
            return (self.PT / self.TT) * 100
        return 0.0

    @property
    def estimated_arrival(self) -> float:
        """Estimated arrival timestamp (Unix time)."""
        return self.last_updated + self.time_remaining

    @property
    def is_incoming(self) -> bool:
        """Check if this movement is incoming to player."""
        # Type 11 is typically return movement
        return self.T != 11 and self.D == 0

    @property
    def is_outgoing(self) -> bool:
        """Check if this movement is outgoing from player."""
        return self.T != 11 and self.D == 1

    @property
    def is_returning(self) -> bool:
        """Check if this is a return movement."""
        return self.T == MovementType.RETURN

    @property
    def is_attack(self) -> bool:
        """Check if this is an attack movement."""
        # T=0 appears to be a standard attack on player castles
        # T=1 is ATTACK, T=5 is RAID, T=9 is ATTACK_CAMP, T=10 is RAID_CAMP
        return self.T in (
            0,  # Standard attack (observed in gam packets)
            MovementType.ATTACK,
            MovementType.ATTACK_CAMP,
            MovementType.RAID,
            MovementType.RAID_CAMP,
        )

    @property
    def is_transport(self) -> bool:
        """Check if this is a transport movement."""
        return self.T == MovementType.TRANSPORT

    @property
    def is_support(self) -> bool:
        """Check if this is a support movement."""
        return self.T == MovementType.SUPPORT

    @property
    def is_spy(self) -> bool:
        """Check if this is a spy/scout movement."""
        return self.T == MovementType.SPY

    @property
    def unit_count(self) -> int:
        """Total number of units in this movement (includes all unit types)."""
        return sum(self.units.values())

    @property
    def troop_count(self) -> int:
        """Count of actual troops only (excludes equipment/tools)."""
        from empire_core.utils.troops import count_troops

        return count_troops(self.units)

    def has_arrived(self) -> bool:
        """Check if movement has arrived (time remaining <= 0)."""
        return self.time_remaining <= 0

    def format_time_remaining(self) -> str:
        """Format time remaining as human-readable string."""
        remaining = self.time_remaining
        if remaining <= 0:
            return "Arrived"

        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        seconds = remaining % 60

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def __repr__(self) -> str:
        return f"Movement(id={self.MID}, type={self.movement_type_name}, from={self.source_area_id}, to={self.target_area_id}, remaining={self.format_time_remaining()})"
