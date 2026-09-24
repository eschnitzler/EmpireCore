import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from empire_core.utils.enums import MapObjectType, MovementType
from empire_core.utils.troops import count_troops


class MovementResources(BaseModel):
    """Resources being transported in a movement."""

    model_config = ConfigDict(extra="ignore")

    wood: int = Field(default=0, alias="W")
    stone: int = Field(default=0, alias="S")
    food: int = Field(default=0, alias="F")
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
       ``.direction``, ``.owner_id`` or ``.time_remaining`` fails on it. Import ``Movement``
       from ``empire_core`` (this class) unless you are parsing packets by hand.

    Whether a movement is yours or aimed at you depends on the local player's
    id, which state stamps on every movement as ``local_player_id``.

    Client: ``BasicMapmovementVO``, ``ArmyAttackMapmovementVO``.

    Fields are snake_case with the wire key as the alias (``movement_id`` is
    ``MID``), so a raw ``gam`` record validates unchanged and either name
    works when building one.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    movement_id: int = Field(default=-1, alias="MID", description="Movement id")
    movement_type: int = Field(default=0, alias="T", description="MovementType value")
    progress_time: int = Field(default=0, alias="PT", description="Seconds travelled at last_updated")
    total_time: int = Field(default=0, alias="TT", description="Seconds the trip takes")
    direction: int = Field(default=0, alias="D", description="1 = returning home, 0 = heading to the target")
    target_id: int = Field(default=-1, alias="TID", description="Player id owning the target area")
    kingdom_id: int = Field(default=0, alias="KID", description="Kingdom id")
    source_id: int = Field(default=-1, alias="SID", description="Player id owning the source area")
    owner_id: int = Field(default=-1, alias="OID", description="Player id owning the movement")
    horse_booster_id: int = Field(default=-1, alias="HBW", description="Horse booster item id, -1 for none")

    target_area: list[Any] | None = Field(default=None, alias="TA", description="Raw target area row")
    source_area: list[Any] | None = Field(default=None, alias="SA", description="Raw source area row")

    target_area_id: int = Field(default=-1, description="Target area id, TA[3]")
    source_area_id: int = Field(default=-1, description="Source area id, SA[3]")
    target_x: int = Field(default=-1, description="Target x, TA[1]")
    target_y: int = Field(default=-1, description="Target y, TA[2]")
    source_x: int = Field(default=-1, description="Source x, SA[1]")
    source_y: int = Field(default=-1, description="Source y, SA[2]")
    target_type: int = Field(default=-1, description="MapObjectType value, TA[0]")

    local_player_id: int = Field(default=-1, description="Player id of the receiving account, -1 if unknown")

    units: dict[int, int] = Field(default_factory=dict, description="Unit id to count, from the wrapper's GA")
    estimated_size: int = Field(default=0, description="Army size estimate, the wrapper's GS when the army is hidden")
    resources: MovementResources = Field(
        default_factory=MovementResources, description="Goods carried, the wrapper's GS when it is a dict"
    )

    target_name: str = Field(default="", description="Target area name, TA[10]")
    source_name: str = Field(default="", description="Source area name")
    target_player_name: str = Field(default="", description="From the O owner records")
    source_player_name: str = Field(default="", description="From the O owner records")
    target_alliance_name: str = Field(default="", description="From the O owner records")
    source_alliance_name: str = Field(default="", description="From the O owner records")

    created_at: float = Field(default_factory=time.time, description="When state first saw this movement")
    last_updated: float = Field(default_factory=time.time, description="When the last packet for it was applied")

    commander_equipment: list[Any] = Field(default_factory=list, description="Raw UM.L.EQ")
    commander_effects: list[Any] = Field(default_factory=list, description="Raw UM.L.AE")

    wait_total: int = Field(default=0, description="Seconds the army stays at its target, UM.TWD")
    wait_passed: int = Field(default=0, description="Seconds of that wait already passed, UM.PWD")

    force_cancelable: bool = Field(default=False, description="Set by an mfc push")

    _arrival_dispatched: bool = PrivateAttr(default=False)

    @property
    def movement_type_enum(self) -> MovementType:
        """Get the MovementType enum value."""
        try:
            return MovementType(self.movement_type)
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
            return MovementType(self.movement_type).name
        except ValueError:
            return f"UNKNOWN_{self.movement_type}"

    @property
    def time_remaining(self) -> int:
        """Seconds until arrival, advancing with wall-clock time.

        Extrapolated from the last packet snapshot (total_time - progress_time at
        ``last_updated``), so it keeps counting down between updates.
        """
        return max(0, int(round(self.estimated_arrival - time.time())))

    @property
    def progress_percent(self) -> float:
        if self.total_time > 0:
            return (self.progress_time / self.total_time) * 100
        return 0.0

    @property
    def estimated_arrival(self) -> float:
        """When the army reaches its target (Unix time)."""
        return self.last_updated + max(0, self.total_time - self.progress_time)

    @property
    def estimated_end(self) -> float:
        """When the movement is over: arrival plus whatever wait at the target is left.

        Client: ``BasicMapmovementVO._endWaitTimeStamp``.
        """
        return self.estimated_arrival + max(0, self.wait_total - self.wait_passed)

    @property
    def is_stationed(self) -> bool:
        """The army has arrived and is waiting at its target, as a support does.

        Client: ``SupportDefenceMapmovementVO.isStationed``.
        """
        now = time.time()
        return self.estimated_arrival <= now < self.estimated_end

    @property
    def is_returning(self) -> bool:
        """The army is on its way home, whatever its type."""
        return self.direction == 1

    @property
    def is_mine(self) -> bool:
        """The local player owns this movement."""
        return self.local_player_id != -1 and self.owner_id == self.local_player_id

    @property
    def is_outgoing(self) -> bool:
        """One of the local player's armies heading to its target."""
        return self.is_mine and not self.is_returning

    @property
    def is_incoming(self) -> bool:
        """Another player's army heading to one of the local player's areas.

        Armies moving between your own areas count as outgoing, not incoming.
        """
        return (
            self.local_player_id != -1
            and self.target_id == self.local_player_id
            and not self.is_mine
            and not self.is_returning
        )

    @property
    def is_attack(self) -> bool:
        """Any attack type, including NPC, alien, faction and event attacks."""
        return self.movement_type_enum.is_attack

    @property
    def is_support(self) -> bool:
        """A support (defence) army."""
        return self.movement_type_enum.is_support

    @property
    def is_siege(self) -> bool:
        """A siege or faction occupation."""
        return self.movement_type_enum.is_siege

    @property
    def is_transport(self) -> bool:
        """A market transport of resources. Troops moved between own castles are ``is_travel``."""
        return self.movement_type == MovementType.MARKET

    @property
    def is_travel(self) -> bool:
        """Troops moved between the owner's own areas.

        An army's way home also arrives as a new TRAVEL movement, with ``D == 1``.
        """
        return self.movement_type == MovementType.TRAVEL

    @property
    def is_spy(self) -> bool:
        """A spy mission."""
        return self.movement_type == MovementType.SPY

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
        return f"Movement(id={self.movement_id}, type={self.movement_type_name}, from={self.source_area_id}, to={self.target_area_id}, remaining={self.format_time_remaining()})"
