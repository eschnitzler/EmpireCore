import logging
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, field_validator

from empire_core.protocol.models.commanders import CommanderEffect, Equipment
from empire_core.protocol.models.movement import MovementArea, MovementOwner
from empire_core.utils.enums import MapObjectType, MovementType
from empire_core.utils.troops import count_troops

logger = logging.getLogger(__name__)

# Client: DungeonConst.BASIC_DAIMYO_TOWNSHIP_PLAYER_ID. getOwnerInfoVO files it under
# the local player's own record, so the daimyo township counts as yours.
DAIMYO_TOWNSHIP_PLAYER_ID = -815


class MovementResources(BaseModel):
    """Resources a movement carries: market goods or travel loot.

    Keys are the client's collectable server keys (``CollectableItem*VO.SERVER_KEY``).
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    wood: int = Field(default=0, alias="W")
    stone: int = Field(default=0, alias="S")
    food: int = Field(default=0, alias="F")
    coal: int = Field(default=0, alias="C")
    oil: int = Field(default=0, alias="O")
    glass: int = Field(default=0, alias="G")
    iron: int = Field(default=0, alias="I")
    aquamarine: int = Field(default=0, alias="A")
    honey: int = Field(default=0, alias="HONEY")
    mead: int = Field(default=0, alias="MEAD")
    beef: int = Field(default=0, alias="BEEF")

    @property
    def total(self) -> int:
        """Total resources in transport."""
        return sum(getattr(self, name) for name in type(self).model_fields)

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

    The raw ``gam`` reply is modelled in ``empire_core.protocol.models`` as
    ``GetMovementsResponse``: a list of ``MovementWrapper`` entries, each
    holding a ``MovementRecord``. Use those only when parsing packets by hand.

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

    target_area: MovementArea | None = Field(
        default=None, alias="TA", description="Target area row; None when it is missing or unreadable"
    )
    source_area: MovementArea | None = Field(
        default=None, alias="SA", description="Source area row; None when it is missing or unreadable"
    )

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

    commander_equipment: list[Equipment] = Field(
        default_factory=list, description="Equipment the commander wears, UM.L.EQ"
    )
    commander_effects: list[CommanderEffect] = Field(
        default_factory=list, description="The commander's area effects, UM.L.AE"
    )

    wait_total: int = Field(default=0, description="Seconds the army stays at its target, UM.TWD")
    wait_passed: int = Field(default=0, description="Seconds of that wait already passed, UM.PWD")

    force_cancelable: bool = Field(default=False, description="Wrapper FC, or set by an mfc push")

    owner: MovementOwner | None = Field(default=None, description="Owner record (O) of the movement's owner, OID")
    target_owner: MovementOwner | None = Field(default=None, description="Owner record (O) of the target's owner, TID")

    attack_type: int | None = Field(default=None, description="AttackType value, the wrapper's ATT")
    is_shadow: bool = Field(default=False, description="Shadow movement, the wrapper's SM")
    support_tool_ids: list[int] = Field(default_factory=list, description="Support tools sent along, the wrapper's AST")
    auto_skip_cooldown_type: int = Field(default=0, description="The wrapper's ASCT")
    advisor_type: int = Field(default=0, description="Attack advisor type, UM.AAT; 0 for none")
    advisor_movement_count: int = Field(default=0, description="Attacks in the advisor series, UM.AAC")
    advisor_movement_number: int = Field(default=0, description="This attack's place in the series, UM.AAN")
    advisor_is_last: bool = Field(default=False, description="Last attack of the series, UM.AAL")
    market_carriages: int = Field(default=0, description="Carriages of a market transport, MM.C")
    goods: list[tuple[str | int, int]] | list[int] = Field(
        default_factory=list, description="Raw goods or loot pairs, MM.G or the wrapper's G"
    )

    _arrival_dispatched: bool = PrivateAttr(default=False)

    @field_validator("target_area", "source_area", mode="before")
    @classmethod
    def _readable_area(cls, value: Any) -> Any:
        """Client: ``WorldmapObjectFactory.parseWorldMapArea`` (bundle line 5343) yields no area for a
        falsy row and ``BasicMapmovementVO`` falls back to a dummy, so an unreadable row costs only itself."""
        if not value:
            return None
        try:
            return MovementArea.model_validate(value)
        except ValidationError:
            logger.debug(f"Ignoring unreadable area row: {value!r}")
            return None

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
    def owner_alliance_id(self) -> int:
        """Alliance of the movement's owner, -1 if none or unknown."""
        return self.owner.alliance_id if self.owner else -1

    @property
    def target_alliance_id(self) -> int:
        """Alliance of the target's owner, -1 if none or unknown."""
        return self.target_owner.alliance_id if self.target_owner else -1

    @property
    def battle_time(self) -> float:
        """When the battle starts (Unix time): arrival plus the wait at the target.

        Client: ``BasicMapmovementVO.parseUnitMovement``.
        """
        return self.estimated_end

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

        The daimyo township counts as yours, as in the client. Armies moving
        between your own areas count as outgoing, not incoming.
        """
        return (
            self.local_player_id != -1
            and self.target_id in (self.local_player_id, DAIMYO_TOWNSHIP_PLAYER_ID)
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
