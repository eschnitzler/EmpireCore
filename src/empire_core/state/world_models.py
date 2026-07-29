import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from empire_core.utils.enums import MapObjectType, MovementType
from empire_core.utils.troops import count_troops


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
        return (
            self.wood + self.stone + self.food + self.iron + self.glass + self.ash + self.honey + self.mead + self.beef
        )

    @property
    def is_empty(self) -> bool:
        """Check if no resources are being transported."""
        return self.total == 0


class Movement(BaseModel):
    """A live army movement (Attack, Support, Transport, ...) tracked in state.

    This is the movement type the client returns from
    :meth:`~empire_core.client.client.EmpireClient.get_movements` and passes to
    ``on_incoming_attack`` callbacks, and the one exported as
    ``empire_core.Movement``.

    .. warning::

       There is a second, unrelated class also named ``Movement`` in
       ``empire_core.protocol.models.map`` (re-exported from
       ``empire_core.protocol.models``). That one is the raw ``gam`` protocol
       payload model with different fields (``movement_id``/``movement_type``
       from ``MID``/``MT`` aliases, ``source_x``, ``arrival_time``, ...) and it
       is *not* interchangeable with this class: attribute access such as
       ``.MID``, ``.T`` or ``.time_remaining`` fails on it. Import ``Movement``
       from ``empire_core`` (this class) unless you are parsing packets by hand.

    Naming: the fields are the raw GGE wire keys (``MID``, ``T``, ``PT``, ...)
    because packet payloads are fed in unchanged; every one of them also has a
    snake_case read-only property (``movement_id``, ``movement_type``,
    ``progress_time``, ...), which is what public code should use.
    """

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
    target_area: list[Any] | None = Field(default=None, alias="TA")
    source_area: list[Any] | None = Field(default=None, alias="SA")

    # Extracted fields
    target_area_id: int = Field(default=-1)
    source_area_id: int = Field(default=-1)
    target_x: int = Field(default=-1)
    target_y: int = Field(default=-1)
    source_x: int = Field(default=-1)
    source_y: int = Field(default=-1)
    target_type: int = Field(default=-1)  # MapObjectType value from TA[0]

    # Units in movement (UnitID -> Count)
    units: dict[int, int] = Field(default_factory=dict)

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
    commander_equipment: list[Any] = Field(default_factory=list)
    commander_effects: list[Any] = Field(default_factory=list)

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
    def target_type_enum(self) -> MapObjectType:
        """The target area's object type, or ``UNKNOWN`` for unmapped IDs.

        ``target_type`` comes from ``TA[0]``, so it is interpreted with
        :class:`~empire_core.utils.enums.MapObjectType` -- *not* with
        ``MapItemType``, which describes map-scan items and disagrees on some
        IDs (see the warning on ``MapObjectType``).
        """
        try:
            return MapObjectType(self.target_type)
        except ValueError:
            return MapObjectType.UNKNOWN

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
    def direction(self) -> int:
        """Raw direction flag: 0 = incoming, 1 = outgoing."""
        return self.D

    @property
    def target_id(self) -> int:
        return self.TID

    @property
    def kingdom_id(self) -> int:
        return self.KID

    @property
    def source_id(self) -> int:
        return self.SID

    @property
    def owner_id(self) -> int:
        return self.OID

    @property
    def time_remaining(self) -> int:
        """Seconds until arrival, advancing with wall-clock time.

        Extrapolated from the last packet snapshot (TT - PT at
        ``last_updated``), so it keeps counting down between updates.
        """
        return max(0, int(round(self.estimated_arrival - time.time())))

    @property
    def progress_percent(self) -> float:
        if self.TT > 0:
            return (self.PT / self.TT) * 100
        return 0.0

    @property
    def estimated_arrival(self) -> float:
        """Estimated arrival timestamp (Unix time)."""
        return self.last_updated + max(0, self.TT - self.PT)

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
        """Count of actual troops only (excludes equipment/tools).

        Note: the first access fetches troop metadata from the GGE CDN
        (blocking HTTP, cached afterwards). If the fetch fails, all units
        are counted and the fetch is retried after a cooldown.
        """
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
