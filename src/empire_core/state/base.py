"""State shared by the GameState mixins: the lock, tracked data and callback dispatch."""

import logging
import math
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from pydantic import BaseModel

from empire_core.alliance.models.battleground import BattlegroundMemberPerformance
from empire_core.alliance.models.chat import ChatMessageData
from empire_core.alliance.models.gifts import AllianceGift
from empire_core.alliance.models.help import AllianceHelpRequest
from empire_core.alliance.models.info import AllianceInfo
from empire_core.attack.models.alien_camps import AlienRerollCountsResponse
from empire_core.attack.models.counter import AttackCounterResponse
from empire_core.castle.models.collect import MineStatus, ResourceCart
from empire_core.castle.models.construction_items import (
    ConstructionItemInventory,
    ConstructionItemSpace,
    ExpiredConstructionItemsResponse,
)
from empire_core.castle.models.crafting import CraftingQueue
from empire_core.castle.models.fusion_forge import FusionForge
from empire_core.castle.models.hunter import HunterInfo
from empire_core.castle.models.kingdoms import KingdomInfoResponse
from empire_core.castle.models.landmarks import (
    KingsTowerListResponse,
    LaboratoryListResponse,
    LaboratoryResetResponse,
    MonumentListResponse,
    MonumentResetResponse,
)
from empire_core.castle.models.mercenaries import MercenaryMissionsResponse
from empire_core.castle.models.objects import BuildingConstructionItems
from empire_core.castle.models.permanent import PermanentCastle
from empire_core.castle.models.research import ResearchInfoResponse
from empire_core.castle.models.storage import DecorationStorage
from empire_core.castle.models.tax import TaxInfo
from empire_core.castle.models.upkeep import ConstructionItemExpiryResponse, ResourcePoolResponse
from empire_core.castle.models.villages import VillageListResponse
from empire_core.castle.models.wishing_well import WishingWellResponse
from empire_core.commanders.models.inventory import GemInventoryResponse, InventorySpace, NewRelicsResponse
from empire_core.commanders.models.roster import CommanderRoster
from empire_core.commanders.models.skills import SkillList
from empire_core.enums import Kingdom
from empire_core.events.models import ShuttingDownEvents, SpecialEvent
from empire_core.events.special_server_models import CurrentServer, SpecialServerCastles
from empire_core.events.status_models import RaidBossStatus
from empire_core.exceptions import StateNotLoadedError
from empire_core.map.models.treasure_maps import TreasureMap
from empire_core.map.models.world import ServerInfoResponse
from empire_core.messages.models import MessageInfo, MessagesSentToday
from empire_core.movements.models import MovementOwner
from empire_core.movements.tracked import Movement
from empire_core.player.models.account import (
    BoostedGlobalEffectsResponse,
    DailyResetResponse,
    FoodProductionStatus,
    OfficerTraining,
    PlayerGiftsResponse,
)
from empire_core.player.models.aqua import StormIslandsInfo
from empire_core.player.models.coat_of_arms import CoatOfArmsResponse, CoatOfArmsSymbolsResponse
from empire_core.player.models.credentials import AccountDeletion, CredentialsStatus, PlayerNameChangeInfoResponse
from empire_core.player.models.economy import LootBoxesResponse
from empire_core.player.models.hero import HeroDecisionResponse
from empire_core.player.models.officers_school import TrainingProgramsResponse
from empire_core.player.models.progress import (
    AchievementsResponse,
    BoosterInfoResponse,
    FactionPointsResponse,
    GloryPointsResponse,
    MightPointsResponse,
    RelocationInfoResponse,
    TitleRanksResponse,
)
from empire_core.protocol.base import read_or_none
from empire_core.quests.models import DailyQuests, Quest, QuestBook
from empire_core.rewards.models import ActivityChestInfo
from empire_core.spy.models import MaxSpiesResponse, PlagueMonkInfoResponse
from empire_core.state.models import Castle, JoinedArea, Player
from empire_core.utils.callbacks import BoundEvent, Registry

logger = logging.getLogger(__name__)

# Callbacks are never dropped, so a slow one lets the queue grow without bound;
# past this depth a warning says so, at most once per interval.
CALLBACK_QUEUE_WARN_DEPTH = 1000
CALLBACK_QUEUE_WARN_INTERVAL = 60.0

# Arrival/recall listeners may take just the movement id (the original
# signature) or the id plus the Movement that was removed from state. Which
# one is called is decided per callback from its signature, so existing
# ``Callable[[int], None]`` handlers keep working unchanged.
MovementEventCallback = Callable[[int], Any] | Callable[[int, Movement | None], Any]


_M = TypeVar("_M", bound=BaseModel)
_T = TypeVar("_T")


def read_section(model: type[_M], body: Any, what: str) -> _M | None:
    """A section block read as ``model``; None, with a warning, when it is no object or does not validate."""
    return read_or_none(model.model_validate, body, warn=logger, what=what) if isinstance(body, dict) else None


def loaded(value: _T | None, what: str) -> _T:
    """``value`` of a section the login data always brings; :class:`StateNotLoadedError` while none has arrived."""
    if value is None:
        raise StateNotLoadedError(f"{what} not loaded: log in first")
    return value


class StateBase:
    """The data every GameState mixin reads and writes, created once in ``__init__``."""

    def __init__(self):
        self._lock = threading.RLock()
        # Distinguish leaving and rejoining the same castle while an action waits for CI.
        self.area_revision = 0
        self.membership_revision = 0
        self._alliance_info_read_revision: int | None = None
        self._set_empty_session()

        # Wakes the thread that advances the movements as one falls due; started with the first
        self._movement_clock = threading.Condition(self._lock)
        self._movement_clock_thread: threading.Thread | None = None
        self._movement_clock_at = math.inf

        self._registry = Registry(self._lock)

        # One worker, so callbacks run one at a time in packet order, off the
        # receive thread. Created lazily so it survives disconnect/reconnect.
        self._callback_executor: ThreadPoolExecutor | None = None
        self._executor_lock = threading.Lock()
        self._callbacks_pending = 0
        self._callback_queue_warn_at = 0.0

        # Kept when the session drops, as the client keeps them
        self.alliance_help: tuple[AllianceHelpRequest, ...] = ()
        self.activity_chest: ActivityChestInfo | None = None

        # Rate-limit state for movement parse failure warnings
        self._movement_parse_warn_at = 0.0
        self._movement_parse_failures = 0

    def _set_empty_session(self) -> None:
        """Start the session data over: nothing received yet."""
        self.membership_revision += 1
        self.local_player: Player | None = None

        # player id -> Player. Despite the type, this only ever holds the
        # local player: nothing in the library records other players here.
        # Kept because it is part of the public surface — do not iterate it
        # expecting opponents or alliance members. Use the alliance service
        # (ain) or the commander/profile services for other players.
        self.players: dict[int, Player] = {}

        self.castles: dict[int, Castle] = {}
        # castle id -> the castle's unlocked units and horses, from gpc
        self.permanent_castles: dict[int, PermanentCastle] = {}

        # World State
        self.movements: dict[int, Movement] = {}  # MovementID -> Movement
        # Arrival and end (wall clock) of each movement, taken when it is stored;
        # the ids whose arrival is behind them; the earliest time one is due.
        self._movement_times: dict[int, tuple[float, float]] = {}
        self._arrival_dispatched: set[int] = set()
        self._next_movement_due = math.inf

        # Spies owned before boosts, from gms
        self.max_spies: MaxSpiesResponse | None = None
        # Owner records (O) from every movement packet so far, by player id
        self._owner_records: dict[int, MovementOwner] = {}

        # The server info pushed when the connection opened, which names the world map's size
        self.server_info: ServerInfoResponse | None = None

        # The last joined area, and the mines and resource carts last sent for it; swapped, never edited
        self.area_revision += 1
        self.placed_construction_items: tuple[BuildingConstructionItems, ...] | None = None
        self._packet_sequence = 0
        self._placed_construction_item_sequence = 0
        self._construction_item_reply_order: dict[str, tuple[object, int]] = {}
        self.joined_area: JoinedArea | None = None
        self.mines: dict[int, MineStatus] = {}
        self.resource_carts: list[ResourceCart] = []

        # Running events by id, in the order they started; swapped, never edited
        self.events: dict[int, SpecialEvent] = {}
        self._events_updated_at: float | None = None
        self._raid_boss_receipt: tuple[dict[str, Any], RaidBossStatus] | None = None
        # The client keeps one set of counts for every alien invasion (CastleAlienRerollData)
        self.alien_reroll_counts: AlienRerollCountsResponse | None = None
        self.shutting_down_events: ShuttingDownEvents | None = None
        self.current_server: CurrentServer | None = None
        self.special_server_castles: SpecialServerCastles | None = None

        # The officers' school's programs, the hunter, the open citizen judgement and your hero; each replaced
        self.training_programs: TrainingProgramsResponse | None = None
        self.hunter: HunterInfo | None = None
        self.judgement_id: int | None = None
        self.hero: HeroDecisionResponse | None = None

        # Your coat of arms and its symbols, credentials, name change, account deletion, message counts; each replaced
        self.coat_of_arms: CoatOfArmsResponse | None = None
        self.coat_of_arms_symbols: CoatOfArmsSymbolsResponse | None = None
        self.credentials_status: CredentialsStatus | None = None
        self.player_name_change_info: PlayerNameChangeInfoResponse | None = None
        self.account_deletion: AccountDeletion | None = None
        self.messages_sent_today: MessagesSentToday | None = None

        # Active quests by id, the quest book and the daily quests; each replaced, never edited
        self.quests: dict[int, Quest] = {}
        self.quest_book: QuestBook | None = None
        self.daily_quests: DailyQuests | None = None

        # Login sections kept as their models; each replaced, never edited, and copied when handed out
        self.commanders: CommanderRoster | None = None
        self.skills: SkillList | None = None
        self.own_alliance: AllianceInfo | None = None
        # The ain block own_alliance was read from, for the keys a later ain leaves out
        self._own_alliance_raw: dict[str, Any] | None = None
        self._alliance_field_order: dict[str, int] = {}
        self._alliance_reply_order: dict[str, tuple[dict[str, Any], int]] = {}
        self.alliance_chat: tuple[ChatMessageData, ...] = ()
        self.alliance_gifts: tuple[AllianceGift, ...] = ()
        # The mailbox by message id, in the order the messages first arrived; swapped, never edited
        self.mailbox: dict[int, MessageInfo] = {}
        self.pending_rewards: int | None = None
        self.research: ResearchInfoResponse | None = None
        self.boosts: BoosterInfoResponse | None = None
        self.might: MightPointsResponse | None = None
        self.glory_points: GloryPointsResponse | None = None
        self.faction_points: FactionPointsResponse | None = None
        self.title_ranks: TitleRanksResponse | None = None
        self.achievements: AchievementsResponse | None = None
        self.relocation: RelocationInfoResponse | None = None
        self.plague_monks: PlagueMonkInfoResponse | None = None
        self.daily_reset: DailyResetResponse | None = None
        self.attack_counter: AttackCounterResponse | None = None
        self.officer_training: OfficerTraining | None = None
        self.boosted_global_effects: BoostedGlobalEffectsResponse | None = None
        self.player_gifts: PlayerGiftsResponse | None = None
        self.wishing_well: WishingWellResponse | None = None
        self.new_relics: NewRelicsResponse | None = None
        self.food_production: FoodProductionStatus | None = None
        self.gems: GemInventoryResponse | None = None
        self.loot_boxes: LootBoxesResponse | None = None
        self.inventory_space: InventorySpace | None = None
        self.kingdoms: KingdomInfoResponse | None = None
        self.mercenary_missions: MercenaryMissionsResponse | None = None
        self.tax: TaxInfo | None = None
        self.construction_items: ConstructionItemInventory | None = None
        self.construction_item_space: ConstructionItemSpace | None = None
        self.expired_construction_items: ExpiredConstructionItemsResponse | None = None
        self.construction_item_expiry: ConstructionItemExpiryResponse | None = None
        self.resource_pool: ResourcePoolResponse | None = None
        # The decoration storages by storage id, each replaced whole by the sin that names it
        self.decoration_storages: dict[int, DecorationStorage] = {}
        self.laboratories: LaboratoryListResponse | None = None
        self.laboratory_reset: LaboratoryResetResponse | None = None
        self.kings_towers: KingsTowerListResponse | None = None
        self.monuments: MonumentListResponse | None = None
        self.monument_reset: MonumentResetResponse | None = None
        self.villages: VillageListResponse | None = None
        self.aqua_points: int | float | None = None
        # Treasure maps by map id, swapped, never edited; the treasure hunt's current map
        self.treasure_maps: dict[int, TreasureMap] | None = None
        self.treasure_hunt_map_id: int | None = None
        self.storm_islands: StormIslandsInfo | None = None
        # The crafting queues by queue id, kingdom and castle, and the fusion forges by id; swapped, never edited
        self.crafting_queues: dict[tuple[int, Kingdom, int], CraftingQueue] | None = None
        self.fusion_forges: dict[int, FusionForge] | None = None
        self.battleground_performance: tuple[BattlegroundMemberPerformance, ...] | None = None

        # Freshness bookkeeping (see the GameState docstring). Wall-clock seconds.
        self._packet_times: dict[str, float] = {}
        self._castle_details_at: dict[int, float] = {}
        self._player_updated_at: float | None = None

    def reset(self) -> None:
        """Forget all the session sent: player, castles, joined area, movements, events, login sections, timestamps.

        Registered callbacks stay, and so does the record of attacks and occupations
        already announced to :meth:`on_incoming_attack` and :meth:`on_occupation_started`.
        Fires no callback: a movement that is dropped here was not seen to
        arrive or be removed. The client resets its data
        the same way when the connection is lost; the next login's gbd, and the
        gam the server pushes after it (seen live), rebuild it.

        Client: ``CastleConnectionLostCommand.execute`` (bundle line 120254) runs
        ``CastleDestroyGameCommand``, whose ``destroyGameSpecificObjects``
        (line 120270) calls ``CastleModel.resetModels``; ``CastleArmyData.reset``
        (line 133620) starts the movement map over.
        """
        with self._lock:
            self._set_empty_session()
            self._movement_clock.notify()

    def _handle_gbd(self, data: dict[str, Any]) -> set[str]:
        """Apply login data, or one section in the same shape, and return the sections not applied;
        :class:`GameState` implements it."""
        raise NotImplementedError

    def _forget_treasure_map_of(self, event: SpecialEvent) -> None:
        """Drop the treasure map of an event that ended; :class:`TreasureMapState` implements it."""
        raise NotImplementedError

    def _handle_gam(self, data: dict[str, Any]) -> None:
        """Apply a ``gam`` block of movements; :class:`MovementState` implements it."""
        raise NotImplementedError

    def shutdown(self) -> None:
        """Stop the movement clock and shut the callback executor down. Call when done with the client.

        Each starts again when next needed, so a client logged in again keeps working. Until this
        runs (``client.close()`` runs it), the movement clock's thread keeps the state and its callbacks
        in memory until the last movement it knows of has passed.
        """
        with self._lock:
            self._movement_clock_thread = None
            self._movement_clock.notify()
        with self._executor_lock:
            if self._callback_executor is not None:
                self._callback_executor.shutdown(wait=False)
                self._callback_executor = None

    @property
    def callback_queue_depth(self) -> int:
        """Callbacks queued on the callback thread and not finished yet, the running one included."""
        with self._executor_lock:
            return self._callbacks_pending

    def _fire(self, callbacks: BoundEvent[Any], *args: Any) -> None:
        """Queue every callback of an event on the callback thread, as registered now."""
        for callback in callbacks.calls():
            self._dispatch_callback(callback, *args)

    def _dispatch_callback(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Queue a callback on the callback thread, behind every callback queued before it."""

        def wrapped():
            try:
                callback(*args, **kwargs)
            except Exception:
                logger.exception("Callback error")
            finally:
                with self._executor_lock:
                    self._callbacks_pending -= 1

        with self._executor_lock:
            if self._callback_executor is None:
                self._callback_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gge_callback")
            executor = self._callback_executor
            self._callbacks_pending += 1
            depth = self._callbacks_pending
            warn = depth > CALLBACK_QUEUE_WARN_DEPTH and time.monotonic() >= self._callback_queue_warn_at
            if warn:
                self._callback_queue_warn_at = time.monotonic() + CALLBACK_QUEUE_WARN_INTERVAL
        if warn:
            logger.warning(
                f"{depth} state callbacks are waiting on the callback thread: a callback is slower than "
                "the packets that queue them; none is dropped, so memory and delivery lag grow"
            )
        try:
            executor.submit(wrapped)
        except RuntimeError:
            with self._executor_lock:
                self._callbacks_pending -= 1
            # Executor shut down concurrently; drop the callback but say so.
            logger.warning("Callback dropped: executor is shut down")

    @staticmethod
    def _swap_model_fields(model: Player | Castle, merged: dict[str, Any], updated: set[str]) -> None:
        """Swap a live pydantic model's complete field dict with one store.

        Player and Castle objects are handed out to user code and read
        without the lock, so their fields are never edited one at a time.
        ``merged`` must be the complete new ``__dict__``, built beforehand;
        the single store is the same mechanism pydantic's own
        `model_construct` uses, so no intermediate state is ever observable.
        """
        object.__setattr__(model, "__dict__", merged)
        model.__pydantic_fields_set__.update(updated)
