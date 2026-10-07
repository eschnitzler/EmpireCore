"""A tracked army movement, with its timing and troops."""

import logging
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from empire_core.commanders.models.roster import Commander
from empire_core.enums import MapItemType, MovementType, NPCOwner
from empire_core.gamedata import SupportToolSlots, WodAmounts
from empire_core.gamedata.troops import count_troops
from empire_core.movements.models import MovementArea, MovementOwner, MovementSpy
from empire_core.protocol.base import enum_or_none, read_or_none

logger = logging.getLogger(__name__)

# Client: the NPC owners CastleNPCOwnerFactory marks isDungeonOwner (bundle lines
# 14461-14618): its standard owner list, and every id getOwner knows (14496).
DUNGEON_OWNER_IDS = frozenset(
    {
        *(NPCOwner.ROBBER_BARON - i for i in range(13)),
        *(NPCOwner.DESERT_DUNGEON - i for i in range(5)),
        NPCOwner.DESERT_BOSS_DUNGEON,
        NPCOwner.ICE_BOSS_DUNGEON,
        NPCOwner.VOLCANO_BOSS_DUNGEON,
        *range(NPCOwner.ISLAND_VILLAGE, NPCOwner.ISLAND_VILLAGE + 5),
        NPCOwner.BLUE_FACTION_KING,
        NPCOwner.RED_FACTION_KING,
        NPCOwner.KINGS_TOWER,
        NPCOwner.MONUMENT,
        NPCOwner.CLASSIC_LABORATORY,
        NPCOwner.ICE_LABORATORY,
        NPCOwner.DESERT_LABORATORY,
        NPCOwner.VOLCANO_LABORATORY,
        NPCOwner.RANDOM_DUNGEON_EVENT,
        NPCOwner.APRIL_DUNGEON_EVENT,
        NPCOwner.ST_PATRICKS_DAY_DUNGEON_EVENT,
        NPCOwner.EASTER_DUNGEON_EVENT,
        *(NPCOwner.NOMAD_CAMP - i for i in range(4)),
        NPCOwner.SAMURAI_CAMP,
        NPCOwner.TUTORIAL_DUNGEON,
        NPCOwner.THORNKING_DUNGEON,
        NPCOwner.THORNKING_VILLAGE,
        NPCOwner.THORNKING_COW_DUNGEON,
        NPCOwner.SEA_QUEEN_DUNGEON,
        NPCOwner.SEA_QUEEN_SHIPS,
        NPCOwner.TREASURE_HUNT_DUNGEON,
        NPCOwner.UNDERWORLD_DUNGEON,
        NPCOwner.UNDERWORLD_VILLAGE,
        NPCOwner.ALLIANCE_NOMAD_CAMP,
        NPCOwner.DAIMYO_CASTLE,
        NPCOwner.ALIEN_INVASION,
        NPCOwner.RED_ALIEN_INVASION,
        *(owner for owner in NPCOwner if owner.name.startswith("COLLECTOR_")),
        NPCOwner.WOLF_KING,
        NPCOwner.ARE_PORTAL,
        NPCOwner.UNKNOWN_EVENT_OWNER,
    }
)
"""
Owner ids the game counts as dungeon owners. Robber barons, kingdom dungeons,
villages and nomad camps are runs of ids (see :class:`~empire_core.enums.NPCOwner`).
"""


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
    :meth:`~empire_core.movements.service.MovementsService.get_movements` and passes to
    ``on_incoming_attack`` callbacks, and the one exported as
    ``empire_core.Movement``.

    The raw ``gam`` reply is modelled as ``empire_core.movements.GetMovementsResponse``:
    a list of ``MovementWrapper`` entries, each holding a ``MovementRecord``. Use those
    only when parsing packets by hand.

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
    horse_booster_id: int = Field(
        alias="HBW", default=-1, description="The horse booster's wod id, -1 for none or when paid with feathers"
    )

    target_area: MovementArea | None = Field(
        default=None, alias="TA", description="Target area row; None when there is none"
    )
    source_area: MovementArea | None = Field(
        default=None, alias="SA", description="Source area row; None when there is none"
    )

    target_area_id: int = Field(default=-1, description="Target area id")
    source_area_id: int = Field(default=-1, description="Source area id")
    target_x: int = Field(default=-1, description="Target x")
    target_y: int = Field(default=-1, description="Target y")
    source_x: int = Field(default=-1, description="Source x")
    source_y: int = Field(default=-1, description="Source y")
    target_type: int = Field(default=-1, description="Target area type (MapItemType)")

    local_player_id: int = Field(default=-1, description="Player id of the receiving account, -1 if unknown")

    units: WodAmounts = Field(default_factory=dict, description="Units and tools, by how many")
    estimated_size: int = Field(default=0, description="Army size estimate when the army is hidden")
    resources: MovementResources = Field(default_factory=MovementResources, description="Goods carried")

    target_name: str = Field(default="", description="Target area name")
    source_name: str = Field(default="", description="Source area name")
    target_player_name: str = Field(default="", description="Name of the target's owner")
    source_player_name: str = Field(default="", description="Name of the movement's owner")
    target_alliance_name: str = Field(default="", description="Alliance name of the target's owner")
    source_alliance_name: str = Field(default="", description="Alliance name of the movement's owner")

    created_at: float = Field(default_factory=time.time, description="When state first saw this movement")
    last_updated: float = Field(default_factory=time.time, description="When the last packet for it was applied")

    commander: Commander | None = Field(
        default=None, description="The commander leading the army, as the UM block sends it; None when there is none"
    )

    wait_total: int = Field(default=0, description="Seconds the army stays at its target")
    wait_passed: int = Field(default=0, description="Seconds of that wait already passed")

    force_cancelable: bool = Field(default=False, description="The movement can be force-cancelled")
    spy: MovementSpy | None = Field(
        default=None, description="A spy mission's type, accuracy or damage, spy count and risk; None for any other"
    )

    owner: MovementOwner | None = Field(default=None, description="Owner record of the movement's owner")
    target_owner: MovementOwner | None = Field(default=None, description="Owner record of the target's owner")

    attack_type: int | None = Field(default=None, description="AttackType value")
    is_shadow: bool = Field(default=False, description="Shadow movement")
    support_tools: SupportToolSlots = Field(
        default=(), description="Support tools sent along, as the attack sent them; None for an empty slot"
    )
    auto_skip_cooldown_type: int = Field(default=0, description="Auto-skip cooldown type (AutoSkipCooldownType)")
    advisor_type: int = Field(default=0, description="Attack advisor type; 0 for none")
    advisor_movement_count: int = Field(default=0, description="Attacks in the advisor series")
    advisor_movement_number: int = Field(default=0, description="This attack's place in the series")
    advisor_is_last: bool = Field(default=False, description="Last attack of the series")
    market_carriages: int = Field(default=0, description="Carriages of a market transport")
    goods: list[tuple[str | int, int]] | list[int] = Field(
        default_factory=list, description="Goods or loot pairs, kept raw"
    )

    @field_validator("target_area", "source_area", mode="before")
    @classmethod
    def _readable_area(cls, value: Any) -> Any:
        """Client: ``WorldmapObjectFactory.parseWorldMapArea`` (bundle line 5343) yields no area for a
        falsy row and ``BasicMapmovementVO`` falls back to a dummy, so an unreadable row costs only itself."""
        return read_or_none(MovementArea.model_validate, value) if value else None

    @property
    def movement_type_enum(self) -> MovementType | None:
        """The movement's type (``T``) as a :class:`MovementType`, None for an id the client does not define."""
        return enum_or_none(MovementType, self.movement_type)

    @property
    def target_type_enum(self) -> MapItemType | None:
        """The target area's type (``TA[0]``) as a :class:`MapItemType`, None for an id the client does not define."""
        return enum_or_none(MapItemType, self.target_type)

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

        The daimyo township counts as yours, as in the client, except for an
        alien attack, which comes only at you. Armies moving between your own
        areas count as outgoing, not incoming, and so does no occupation
        (``is_occupation``): the forces holding an area are not on their way to it.

        Client: ``ArmyAttackMapmovementVO.isAttackingMovement`` (bundle line 14389),
        ``AlienAttackMovementVO.isAttackingMovement`` (bundle line 33073). An
        occupation is a ``SiegeMapmovementVO``, which keeps
        ``BasicMapmovementVO.isAttackingMovement`` (bundle line 19438, always
        false); the movement overview's attack category (``FilterAttack``,
        ``dialog_moveOverview_catAttack``, bundle line 67996) adds one on your
        area by a clause of its own, and lists it as "Occupying forces"
        (``RenderSiege``, bundle line 67408), not as an attack under way.
        """
        if self.local_player_id == -1 or self.is_mine or self.is_returning or self.is_occupation:
            return False
        township = self.movement_type_enum is not MovementType.ALIEN_ATTACK
        return self.target_id == self.local_player_id or (township and self.target_id == NPCOwner.DAIMYO_TOWNSHIP)

    @property
    def is_attack(self) -> bool:
        """Any attack type, including NPC, alien, faction and event attacks."""
        movement_type = self.movement_type_enum
        return movement_type is not None and movement_type.is_attack

    @property
    def is_support(self) -> bool:
        """A support (defence) army."""
        movement_type = self.movement_type_enum
        return movement_type is not None and movement_type.is_support

    @property
    def is_occupation(self) -> bool:
        """An occupation: the forces holding an area a capture attack won, until it is captured or they are driven off."""
        movement_type = self.movement_type_enum
        return movement_type is not None and movement_type.is_occupation

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

        Note: without loaded game data, the first access loads it through
        ``GameData.load`` (blocking HTTP unless cached on disk). If that fails,
        all units are counted and the load is retried after a cooldown.
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
