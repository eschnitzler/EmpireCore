"""State shared by the GameState mixins: the lock, tracked data and callback dispatch."""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from empire_core.movements.tracked import Movement
from empire_core.state.models import Castle, Player

logger = logging.getLogger(__name__)

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

        # Callbacks for specific events — support multiple listeners.
        # Arrival/recall listeners are stored with a flag saying whether they
        # also take the Movement (see MovementState._accepts_movement).
        self._incoming_attack_callbacks: list[Callable[[Movement], None]] = []
        self._movement_recalled_callbacks: list[tuple[MovementEventCallback, bool]] = []
        self._movement_arrived_callbacks: list[tuple[MovementEventCallback, bool]] = []
        self._movement_removed_callbacks: list[tuple[MovementEventCallback, bool]] = []

        # One worker, so callbacks run one at a time in packet order, off the
        # receive thread. Created lazily so it survives disconnect/reconnect.
        self._callback_executor: ThreadPoolExecutor | None = None
        self._executor_lock = threading.Lock()

        # Attack movement id -> when it ends (wall clock), for every attack
        # on_incoming_attack announced. Kept across reset() so a reconnect does
        # not announce the same attack again.
        self._announced_attacks: dict[int, float] = {}

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

        self.castles: dict[int, Castle] = {}

        # World State
        self.movements: dict[int, Movement] = {}  # MovementID -> Movement

        # Active Events
        self.active_event_ids: list[int] = []
        self.event_league_ids: dict[int, int] = {}

        # Freshness bookkeeping (see the GameState docstring). Wall-clock seconds.
        self._packet_times: dict[str, float] = {}
        self._castle_details_at: dict[int, float] = {}
        self._player_updated_at: float | None = None

    def reset(self) -> None:
        """Forget everything the session sent: player, castles, movements, events and their timestamps.

        Registered callbacks stay, and so does the record of attacks already
        announced to :meth:`on_incoming_attack`. Fires no callback: a movement that is dropped
        here was not seen to arrive or be removed. The client resets its data
        the same way when the connection is lost; the next login's gbd, and the
        gam the server pushes after it (seen live), rebuild it.

        Client: ``CastleConnectionLostCommand.execute`` (bundle line 120254) runs
        ``CastleDestroyGameCommand``, whose ``destroyGameSpecificObjects``
        (line 120270) calls ``CastleModel.resetModels``; ``CastleArmyData.reset``
        (line 133620) starts the movement map over.
        """
        with self._lock:
            self._set_empty_session()

    def shutdown(self) -> None:
        """Shutdown the callback executor. Call when done with the client."""
        with self._executor_lock:
            if self._callback_executor is not None:
                self._callback_executor.shutdown(wait=False)
                self._callback_executor = None

    def _dispatch_callback(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Queue a callback on the callback thread, behind every callback queued before it."""

        def wrapped():
            try:
                callback(*args, **kwargs)
            except Exception:
                logger.exception("Callback error")

        with self._executor_lock:
            if self._callback_executor is None:
                self._callback_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gge_callback")
            executor = self._callback_executor
        try:
            executor.submit(wrapped)
        except RuntimeError:
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
