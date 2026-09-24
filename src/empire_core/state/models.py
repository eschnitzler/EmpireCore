from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from empire_core.protocol.models.castle import (
    DetailedCastleInfo,
    ResourceProduction,
    SafeAmount,
    StorageCapacity,
)


class Resources(BaseModel):
    """A castle's resources: stock, storage capacity, hourly production and plunder-safe amount.

    Filled from the castle's ``dcl`` entry. Client: ``DetailedCastleVO.parseData``.
    """

    wood: int = Field(default=0, description="Stock, W")
    stone: int = Field(default=0, description="Stock, S")
    food: int = Field(default=0, description="Stock, F")
    coal: int = Field(default=0, description="Stock, C")
    oil: int = Field(default=0, description="Stock, O")
    glass: int = Field(default=0, description="Stock, G")
    iron: int = Field(default=0, description="Stock, I")
    aquamarine: int = Field(default=0, description="Stock, A")
    honey: int = Field(default=0, description="Stock, HONEY")
    mead: int = Field(default=0, description="Stock, MEAD")
    beef: int = Field(default=0, description="Stock, BEEF")

    capacity: StorageCapacity = Field(default_factory=StorageCapacity, description="Storage cap, gpa MR<key>")
    production: ResourceProduction = Field(
        default_factory=ResourceProduction, description="Production per hour, gpa D<key> / 10"
    )
    safe: SafeAmount = Field(default_factory=SafeAmount, description="Amount safe from plunder, gpa SAFE_<key>")

    @property
    def wood_cap(self) -> int:
        return self.capacity.wood

    @property
    def stone_cap(self) -> int:
        return self.capacity.stone

    @property
    def food_cap(self) -> int:
        return self.capacity.food

    @property
    def wood_rate(self) -> float:
        return self.production.wood

    @property
    def stone_rate(self) -> float:
        return self.production.stone

    @property
    def food_rate(self) -> float:
        return self.production.food

    @property
    def wood_safe(self) -> float:
        return self.safe.wood

    @property
    def stone_safe(self) -> float:
        return self.safe.stone

    @property
    def food_safe(self) -> float:
        return self.safe.food


class Building(BaseModel):
    """Represents a building in a castle."""

    id: int
    level: int = 0

    # Building status (if available)
    upgrading: bool = False
    upgrade_finish_time: int | None = None


class Alliance(BaseModel):
    """The local player's alliance membership, from the ``gal`` login section.

    Client: ``CastleUserData.parse_GAL``.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: int = Field(default=-1, alias="AID", description="Alliance id; 0 or less means no alliance")
    name: str = Field(
        default="",
        validation_alias=AliasChoices("AN", "N", "name"),
        description="Alliance name. The client reads AN; live servers send N",
    )
    rank: int = Field(default=0, alias="R", description="The player's rank in the alliance")
    current_fame: int = Field(default=0, alias="ACF", description="The alliance's current fame")
    is_searching: bool = Field(default=False, alias="SA", description="The player is looking for an alliance")

    @field_validator("is_searching", mode="before")
    @classmethod
    def _searching_flag(cls, value: Any) -> bool:
        try:
            return int(value) == 1
        except (TypeError, ValueError):
            return False


class Castle(BaseModel):
    """A castle, outpost or metropolis owned by the logged-in player.

    Name, position and kingdom come from the castle list (``gcl``); everything
    else from the castle's ``dcl`` entry, kept whole as ``details`` and
    ``None`` until one has been received.

    Not to be confused with :class:`empire_core.protocol.models.castle.CastleInfo`,
    which is the parsed *protocol* model for another player's castle.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: int = Field(default=-1, alias="OID", description="Castle (area) id")
    name: str = Field(default="Unknown", alias="N", description="Castle name")
    kingdom_id: int = Field(default=0, alias="KID", description="Kingdom id")
    x: int = Field(default=0, alias="X", description="Map x")
    y: int = Field(default=0, alias="Y", description="Map y")

    resources: Resources = Field(default_factory=Resources, description="Filled from dcl")
    buildings: list[Building] = Field(default_factory=list)
    units: dict[int, int] = Field(default_factory=dict, description="Units stationed here, dcl AC")
    details: DetailedCastleInfo | None = Field(default=None, description="The castle's last dcl entry")

    raw_data: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @property
    def population(self) -> int:
        """gpa P."""
        area = self.details.production_area if self.details else None
        return area.population if area else 0

    @property
    def neutral_deco_points(self) -> int:
        """gpa NDP."""
        area = self.details.production_area if self.details else None
        return area.neutral_deco_points if area else 0

    @property
    def defence(self) -> int:
        """dcl D."""
        return self.details.defense_value if self.details else 0

    @property
    def market_carriages(self) -> int:
        """dcl MC: the castle's total market carriages."""
        return self.details.market_carriages if self.details else 0

    @property
    def has_barracks(self) -> bool:
        return bool(self.details and self.details.has_barracks)

    @property
    def has_siege_workshop(self) -> bool:
        return bool(self.details and self.details.has_siege_workshop)

    @property
    def has_defense_workshop(self) -> bool:
        return bool(self.details and self.details.has_defense_workshop)

    @property
    def has_hospital(self) -> bool:
        return bool(self.details and self.details.has_hospital)

    @property
    def stronghold_units(self) -> dict[int, int]:
        """Units in the stronghold, dcl SHI."""
        return self.details.stronghold_units if self.details else {}

    @classmethod
    def from_game_data(cls, data: dict[str, Any]) -> "Castle":
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
