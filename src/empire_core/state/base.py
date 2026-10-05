"""State shared by the GameState mixins: the lock, tracked data and callback dispatch."""

import logging
import math
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from empire_core.alliance.models.chat import ChatMessageData
from empire_core.alliance.models.info import AllianceInfo
from empire_core.castle.models.collect import MineStatus, ResourceCart
from empire_core.castle.models.permanent import PermanentCastle
from empire_core.commanders.models.roster import CommanderRoster
from empire_core.commanders.models.skills import SkillList
from empire_core.events.models import SpecialEvent
from empire_core.movements.models import MovementOwner
from empire_core.movements.tracked import Movement
from empire_core.player.models.progress import (
    AchievementsResponse,
    BoosterInfoResponse,
    FactionPointsResponse,
    GloryPointsResponse,
    MightPointsResponse,
    RelocationInfoResponse,
    ResearchInfoResponse,
    TitleRanksResponse,
)
from empire_core.spy.models import MaxSpiesResponse, PlagueMonkInfoResponse
from empire_core.state.models import Castle, CastleKey, JoinedArea, Player
from empire_core.utils.callbacks import BoundCallbacks, Registry

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


class StateBase:
    """The data every GameState mixin reads and writes, created once in ``__init__``."""

    def __init__(self):
        self._lock = threading.RLock()
        self._set_empty_session()

        self._registry = Registry(self._lock)

        # One worker, so callbacks run one at a time in packet order, off the
        # receive thread. Created lazily so it survives disconnect/reconnect.
        self._callback_executor: ThreadPoolExecutor | None = None
        self._executor_lock = threading.Lock()
        self._callbacks_pending = 0
        self._callback_queue_warn_at = 0.0

        # Rate-limit state for movement parse failure warnings
        self._movement_parse_warn_at = 0.0
        self._movement_parse_failures = 0

    def _set_empty_session(self) -> None:
        """Start the session data over: nothing received yet."""
        self.local_player: Player | None = None

        # player id -> Player. Despite the type, this only ever holds the
        # local player: nothing in the library records other players here.
        # Kept because it is part of the public surface — do not iterate it
        # expecting opponents or alliance members. Use the alliance service
        # (ain) or the commander/profile services for other players.
        self.players: dict[int, Player] = {}

        self.castles: dict[CastleKey, Castle] = {}
        # (kingdom, castle id) -> the castle's unlocked units and horses, from gpc
        self.permanent_castles: dict[CastleKey, PermanentCastle] = {}

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

        # The last joined area, and the mines and resource carts last sent for it; swapped, never edited
        self.joined_area: JoinedArea | None = None
        self.mines: dict[int, MineStatus] = {}
        self.resource_carts: list[ResourceCart] = []

        # Running events by id, in the order they started; swapped, never edited
        self.events: dict[int, SpecialEvent] = {}
        self._events_updated_at: float | None = None

        # Login sections kept as their models; each replaced, never edited, and copied when handed out
        self.commanders: CommanderRoster | None = None
        self.skills: SkillList | None = None
        self.own_alliance: AllianceInfo | None = None
        # The ain block own_alliance was read from, for the keys a later ain leaves out
        self._own_alliance_raw: dict[str, Any] | None = None
        self.alliance_chat: tuple[ChatMessageData, ...] = ()
        self.research: ResearchInfoResponse | None = None
        self.boosts: BoosterInfoResponse | None = None
        self.might: MightPointsResponse | None = None
        self.glory_points: GloryPointsResponse | None = None
        self.faction_points: FactionPointsResponse | None = None
        self.title_ranks: TitleRanksResponse | None = None
        self.achievements: AchievementsResponse | None = None
        self.relocation: RelocationInfoResponse | None = None
        self.plague_monks: PlagueMonkInfoResponse | None = None

        # Freshness bookkeeping (see the GameState docstring). Wall-clock seconds.
        self._packet_times: dict[str, float] = {}
        self._castle_details_at: dict[CastleKey, float] = {}
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

    def _handle_gbd(self, data: dict[str, Any]) -> set[str]:
        """Apply login data, or one section in the same shape, and return the sections not applied;
        :class:`GameState` implements it."""
        raise NotImplementedError

    def shutdown(self) -> None:
        """Shutdown the callback executor. Call when done with the client."""
        with self._executor_lock:
            if self._callback_executor is not None:
                self._callback_executor.shutdown(wait=False)
                self._callback_executor = None

    @property
    def callback_queue_depth(self) -> int:
        """Callbacks queued on the callback thread and not finished yet, the running one included."""
        with self._executor_lock:
            return self._callbacks_pending

    def _fire(self, callbacks: BoundCallbacks[Any], *args: Any) -> None:
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
