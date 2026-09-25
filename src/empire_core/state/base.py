"""State shared by the GameState mixins: the lock, tracked data and callback dispatch."""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from empire_core.state.models import Castle, Player
from empire_core.state.world_models import Movement

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

        # Callbacks for specific events — support multiple listeners.
        # Arrival/recall listeners are stored with a flag saying whether they
        # also take the Movement (see MovementState._accepts_movement).
        self._incoming_attack_callbacks: list[Callable[[Movement], None]] = []
        self._movement_recalled_callbacks: list[tuple[MovementEventCallback, bool]] = []
        self._movement_arrived_callbacks: list[tuple[MovementEventCallback, bool]] = []
        self._movement_removed_callbacks: list[tuple[MovementEventCallback, bool]] = []

        # Thread pool for dispatching callbacks (avoids blocking receive loop).
        # Created lazily so it survives disconnect/reconnect cycles.
        self._callback_executor: ThreadPoolExecutor | None = None
        self._executor_lock = threading.Lock()

        # Rate-limit state for movement parse failure warnings
        self._movement_parse_warn_at = 0.0
        self._movement_parse_failures = 0

        # Freshness bookkeeping (see the GameState docstring). Wall-clock seconds.
        self._packet_times: dict[str, float] = {}
        self._castle_details_at: dict[int, float] = {}
        self._player_updated_at: float | None = None

    def shutdown(self) -> None:
        """Shutdown the callback executor. Call when done with the client."""
        with self._executor_lock:
            if self._callback_executor is not None:
                self._callback_executor.shutdown(wait=False)
                self._callback_executor = None

    def _dispatch_callback(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Dispatch a callback in the thread pool."""

        def wrapped():
            try:
                callback(*args, **kwargs)
            except Exception:
                logger.exception("Callback error")

        with self._executor_lock:
            if self._callback_executor is None:
                self._callback_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gge_callback")
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
