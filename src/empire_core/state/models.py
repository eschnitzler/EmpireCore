from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Resources(BaseModel):
    """Resources in a castle."""

    # Basic resources
    wood: int = 0
    stone: int = 0
    food: int = 0

    # Capacity (from dcl packet)
    wood_cap: int = 0  # MRW (Max Resource Wood)
    stone_cap: int = 0  # MRS (Max Resource Stone)
    food_cap: int = 0  # MRF (Max Resource Food)

    # Production rates (from dcl packet)
    wood_rate: float = 0.0  # RS1
    stone_rate: float = 0.0  # RS2
    food_rate: float = 0.0  # RS3

    # Safe storage
    wood_safe: float = 0.0  # SAFE_W
    stone_safe: float = 0.0  # SAFE_S
    food_safe: float = 0.0  # SAFE_F

    # Special resources
    iron: int = 0  # MRI
    honey: int = 0  # MRHONEY
    mead: int = 0  # MRMEAD
    beef: int = 0  # MRBEEF
    glass: int = 0  # MRG
    ash: int = 0  # MRA


class Building(BaseModel):
    """Represents a building in a castle."""

    id: int
    level: int = 0

    # Building status (if available)
    upgrading: bool = False
    upgrade_finish_time: int | None = None


class Alliance(BaseModel):
    """Represents an alliance/guild."""

    model_config = ConfigDict(extra="ignore")

    AID: int = Field(default=-1)  # Alliance ID
    N: str = Field(default="")  # Alliance Name
    SA: str = Field(default="")  # Short/Abbreviation (server sends 0 if none)
    R: int = Field(default=0)  # Rank

    @field_validator("SA", mode="before")
    @classmethod
    def coerce_sa_to_str(cls, v: Any) -> str:
        """Server sends 0 when there's no abbreviation."""
        if v is None or v == 0:
            return ""
        return str(v)

    @property
    def id(self) -> int:
        return self.AID

    @property
    def name(self) -> str:
        return self.N

    @property
    def abbreviation(self) -> str:
        return self.SA

    @property
    def rank(self) -> int:
        return self.R


class Castle(BaseModel):
    """A castle, outpost or metropolis owned by the logged-in player.

    Note on naming: the fields are still the raw GGE wire keys (``OID``, ``N``,
    ``KID``, ...) because packets are fed in unchanged, but every one of them has
    a snake_case read-only property (``id``, ``name``, ``kingdom_id``, ...).
    Public code should use the snake_case names: the wire keys are protocol
    detail and may become aliases in a future release.

    Not to be confused with :class:`empire_core.protocol.models.castle.CastleInfo`,
    which is the parsed *protocol* model for another player's castle.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    OID: int = Field(default=-1)  # Object ID / Area ID (AID)
    N: str = Field(default="Unknown")  # Name
    KID: int = Field(default=0)  # Kingdom ID
    X: int = Field(default=0)  # X coordinate
    Y: int = Field(default=0)  # Y coordinate

    # Castle details (from dcl packet)
    P: int = Field(default=0)  # Population
    NDP: int = Field(default=0)  # Next Day Population
    MC: int = Field(default=0)  # Max Castellans
    B: int = Field(default=0)  # Has Barracks
    WS: int = Field(default=0)  # Has Workshop
    DW: int = Field(default=0)  # Has Dwelling
    H: int = Field(default=0)  # Has Harbour

    # Python-friendly aliases
    @property
    def id(self) -> int:
        return self.OID

    @property
    def name(self) -> str:
        return self.N

    @property
    def x(self) -> int:
        return self.X

    @property
    def y(self) -> int:
        return self.Y

    @property
    def kingdom_id(self) -> int:
        return self.KID

    @property
    def population(self) -> int:
        return self.P

    @property
    def next_day_population(self) -> int:
        return self.NDP

    @property
    def max_castellans(self) -> int:
        return self.MC

    @property
    def has_barracks(self) -> bool:
        return bool(self.B)

    @property
    def has_workshop(self) -> bool:
        return bool(self.WS)

    @property
    def has_dwelling(self) -> bool:
        return bool(self.DW)

    @property
    def has_harbour(self) -> bool:
        return bool(self.H)

    resources: Resources = Field(default_factory=Resources)
    buildings: list[Building] = Field(default_factory=list)
    units: dict[int, int] = Field(default_factory=dict)

    raw_data: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @classmethod
    def from_game_data(cls, data: dict[str, Any]) -> "Castle":
        # Mapping logic for 'gcl' (Global Castle List) / 'gbd' payload
        return cls(**data)


class Player(BaseModel):
    """The logged-in player, as tracked by :class:`~empire_core.state.manager.StateManager`.

    As with :class:`Castle`, the raw GGE wire keys (``PID``, ``PN``, ``LVL``,
    ...) are the storage fields and each has a snake_case read-only property
    (``id``, ``name``, ``level``, ...). Prefer the snake_case names.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    PID: int = Field(default=-1)
    PN: str = Field(default="Unknown")
    AID: int | None = Field(default=None)

    # Levels
    LVL: int = Field(default=0)
    XP: int = Field(default=0)
    LL: int = Field(default=0)  # Legendary Level
    XPFCL: int = Field(default=0)  # XP for current level
    XPTNL: int = Field(default=0)  # XP to next level

    # Resources
    gold: int = 0  # C1 from gcu
    rubies: int = 0  # C2 from gcu

    # Global Inventory (from sce)
    inventory: dict[str, int] = Field(default_factory=dict)

    # VIP
    vip_points: int = 0  # VP
    vip_level: int = 0  # VRL
    vip_time_left: int = 0  # VRS (Seconds)

    # Alliance
    alliance: Alliance | None = None

    # Premium/VIP
    PF: int = Field(default=0)  # Premium Flag
    VF: int = Field(default=0)  # VIP Flag

    # Python-friendly properties
    @property
    def id(self) -> int:
        return self.PID

    @property
    def name(self) -> str:
        return self.PN

    @property
    def alliance_id(self) -> int | None:
        return self.AID

    @property
    def level(self) -> int:
        return self.LVL

    @property
    def xp(self) -> int:
        return self.XP

    @property
    def legendary_level(self) -> int:
        return self.LL

    @property
    def xp_for_current_level(self) -> int:
        return self.XPFCL

    @property
    def xp_to_next_level(self) -> int:
        return self.XPTNL

    @property
    def premium_flag(self) -> int:
        return self.PF

    @property
    def vip_flag(self) -> int:
        return self.VF

    @property
    def xp_progress(self) -> float:
        """Returns XP progress as a percentage (0-100)."""
        if self.XPTNL > 0:
            return (self.XPFCL / self.XPTNL) * 100
        return 0.0

    castles: dict[int, Castle] = Field(default_factory=dict)

    E: str | None = Field(default=None)

    @property
    def email(self) -> str | None:
        return self.E

    @property
    def is_premium(self) -> bool:
        """Check if user has active VIP time."""
        return self.vip_time_left > 0
