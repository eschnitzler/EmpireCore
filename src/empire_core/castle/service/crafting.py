"""The crafting queues and construction item crafting."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar

from empire_core.castle.models.crafting import (
    FULL_SKIP,
    CancelCraftingRequest,
    CancelCraftingResponse,
    ConstructionCraftingResponse,
    CraftConstructionItemRequest,
    CraftConstructionItemResponse,
    CraftingInfoResponse,
    CraftingQueue,
    CraftingSlot,
    GetConstructionCraftingRequest,
    GetCraftingInfoRequest,
    MoveCraftingSlotRequest,
    MoveCraftingSlotResponse,
    SkipConstructionCraftingRequest,
    SkipConstructionCraftingResponse,
    SkipCraftingRequest,
    SkipCraftingResponse,
    StartCraftingRequest,
    StartCraftingResponse,
    UnlockCraftingSlotsRequest,
    UnlockCraftingSlotsResponse,
)
from empire_core.gamedata import Currency
from empire_core.services.base import ServiceMixin

if TYPE_CHECKING:
    from empire_core.gamedata import ConstructionItemRecipeId, CraftingRecipeId

logger = logging.getLogger(__name__)

_Queue = TypeVar("_Queue", bound=CraftingQueue)


class CraftingMixin(ServiceMixin):
    # =========================================================================
    # Crafting
    # =========================================================================

    @property
    def crafting_queues(self) -> tuple[CraftingQueue, ...] | None:
        """
        Every crafting queue known, as the last ``crin`` or crafting action left it; None until one arrived.

        Each has every slot of its game-data row (:meth:`CraftingQueue.with_definition`).

        Raises:
            GameDataNotLoadedError: The game data cannot be loaded
        """
        queues = self.client.state.get_crafting_queues()
        return None if queues is None else tuple(self._laid_out(queue) for queue in queues)

    def get_crafting_queues(self, *, timeout: float = 5.0) -> tuple[CraftingQueue, ...]:
        """
        The crafting queues of the refinery and toolsmith in every castle, as the crafting dialog asks for them.

        Each has every slot of its game-data row (:meth:`CraftingQueue.with_definition`). The reply also
        reaches :attr:`crafting_queues`.

        Raises:
            GameDataNotLoadedError: The game data cannot be loaded

        Client: ``CastleCraftingData.getCraftingInfo`` (bundle line 111423), from
        ``CastleRefineryToolsmithDialog.showLoaded`` (bundle line 29337)
        """
        info = self.request(GetCraftingInfoRequest(), CraftingInfoResponse, timeout=timeout)
        return tuple(self._laid_out(queue) for queue in info.queues)

    def start_crafting(
        self, queue: CraftingQueue, recipe_id: CraftingRecipeId, *, timeout: float = 5.0
    ) -> CraftingQueue:
        """
        Start a recipe in a crafting queue, paying its costs.

        The recipe must be one the queue's building crafts, with a free unlocked slot; the queue after
        reaches :attr:`crafting_queues`.

        Args:
            queue: A queue of :attr:`crafting_queues` or :meth:`get_crafting_queues`
            recipe_id: The crafting recipe, a key of ``GameData.crafting_recipes``
            timeout: Timeout in seconds

        Raises:
            ValueError: The building is not working (``CraftingQueue.is_working``)
            CommandError: The server refused, ``NO_FREE_CONSTRUCTION_SLOT`` for a full queue

        Client: ``CastleCraftingData.startCrafting`` (bundle line 111424)
        """
        self._require_working(queue)
        request = StartCraftingRequest(
            kingdom=queue.kingdom, castle_id=queue.castle_id, object_id=queue.object_id, recipe_id=recipe_id
        )
        return self._laid_out(self.request(request, StartCraftingResponse, timeout=timeout))

    def cancel_crafting(self, queue: CraftingQueue, slot: CraftingSlot, *, timeout: float = 5.0) -> CraftingQueue:
        """
        Cancel the craft in one slot of a crafting queue.

        Args:
            queue: A queue of :attr:`crafting_queues`
            slot: One of its ``production`` or ``queue`` slots
            timeout: Timeout in seconds

        Raises:
            ValueError: The building is not working (``CraftingQueue.is_working``)

        Client: ``CastleCraftingData.cancelCrafting`` (bundle line 111426)
        """
        self._require_working(queue)
        request = CancelCraftingRequest(
            kingdom=queue.kingdom,
            castle_id=queue.castle_id,
            object_id=queue.object_id,
            slot_index=slot.index,
            slot_type=slot.slot_type,
        )
        return self._laid_out(self.request(request, CancelCraftingResponse, timeout=timeout))

    def move_crafting_slot(
        self, queue: CraftingQueue, slot: CraftingSlot, to_index: int, *, timeout: float = 5.0
    ) -> CraftingQueue:
        """
        Move a waiting craft to another waiting slot.

        Args:
            queue: A queue of :attr:`crafting_queues`
            slot: One of its ``queue`` slots
            to_index: Where the craft goes, from 0
            timeout: Timeout in seconds

        Raises:
            ValueError: The building is not working (``CraftingQueue.is_working``)

        Client: ``CastleCraftingData.moveQueueSlot`` (bundle line 111433)
        """
        self._require_working(queue)
        request = MoveCraftingSlotRequest(
            kingdom=queue.kingdom,
            castle_id=queue.castle_id,
            object_id=queue.object_id,
            from_index=slot.index,
            to_index=to_index,
        )
        return self._laid_out(self.request(request, MoveCraftingSlotResponse, timeout=timeout))

    def skip_crafting(
        self,
        queue: CraftingQueue,
        slot: CraftingSlot,
        price: int,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> CraftingQueue:
        """
        Finish the craft in one slot for rubies.

        The client prices the skip as the recipe's ``skipCostC2`` times the share of its time left, rounded
        up, and sends that price; the game data here has no crafting recipes to price it.

        Args:
            queue: A queue of :attr:`crafting_queues`
            slot: One of its ``production`` or ``queue`` slots
            price: The rubies the skip costs
            spend_rubies: Allow spending them
            timeout: Timeout in seconds

        Raises:
            ValueError: The building is not working, or ``spend_rubies`` is False

        Client: ``CastleCraftingData.skipCrafting`` (bundle line 111428), ``CraftingSlotVO.getAdjustedSkipCostC2``
        (bundle line 17012)
        """
        self._require_working(queue)
        self._require_spend_rubies(spend_rubies, f"skipping the craft costs {price} rubies")
        request = SkipCraftingRequest(
            kingdom=queue.kingdom,
            castle_id=queue.castle_id,
            object_id=queue.object_id,
            slot_index=slot.index,
            slot_type=slot.slot_type,
            price=price,
        )
        return self._laid_out(self.request(request, SkipCraftingResponse, timeout=timeout))

    def unlock_crafting_slot(self, queue: CraftingQueue, slot: CraftingSlot, *, timeout: float = 5.0) -> CraftingQueue:
        """
        Unlock a temporary slot of a crafting queue for coins.

        Every locked slot right before it is unlocked with it, as the client buys them
        (``CraftingQueue.unlock_indices``).

        Args:
            queue: A queue of :attr:`crafting_queues`
            slot: One of its locked temporary slots
            timeout: Timeout in seconds

        Raises:
            ValueError: The building is not working (``CraftingQueue.is_working``)

        Client: ``CastleCraftingData.buySlot`` (bundle line 111430), ``CraftingSlotVO.getUnlockCostC1``
        (bundle line 17009)
        """
        self._require_working(queue)
        request = UnlockCraftingSlotsRequest(
            kingdom=queue.kingdom,
            castle_id=queue.castle_id,
            object_id=queue.object_id,
            slot_indices=queue.unlock_indices(slot),
            slot_type=slot.slot_type,
        )
        return self._laid_out(self.request(request, UnlockCraftingSlotsResponse, timeout=timeout))

    @staticmethod
    def _require_working(queue: CraftingQueue) -> None:
        if not queue.is_working:
            raise ValueError(f"crafting building {queue.object_id} is {queue.building_state.name}, not working")

    def _laid_out(self, queue: _Queue) -> _Queue:
        """The queue with every slot of its game-data row; as sent when the game data has no row for it."""
        definition = self._require_game_data().crafting_queues.get(queue.queue_id)
        if definition is None:
            logger.warning("crafting queue %s is not in the game data; its slots are as sent", queue.queue_id)
            return queue
        return queue.with_definition(definition)

    def get_construction_crafting(self, *, timeout: float = 5.0) -> ConstructionCraftingResponse:
        """
        The construction item being crafted and the time left; both None while nothing is crafted.

        Client: ``CastleConstructionItemsCraftingSublayer.onGCCArrived`` (bundle line 79577)
        """
        return self.request(GetConstructionCraftingRequest(), ConstructionCraftingResponse, timeout=timeout)

    def craft_construction_item(
        self, castle_id: int, recipe_id: ConstructionItemRecipeId, *, timeout: float = 5.0
    ) -> None:
        """
        Craft a construction item from a recipe, paying its costs; one craft runs at a time.

        Args:
            castle_id: One of your castles; the client crafts in the joined castle, else the kingdom's main castle
            recipe_id: The recipe, a key of ``GameData.construction_item_recipes``
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not one of your castles
            CommandError: The server refused

        Client: ``CastleConstructionItemsCraftingSublayerProgress.onClick`` (bundle line 79926)
        """
        castle = self._require_own_castle(castle_id)
        request = CraftConstructionItemRequest(recipe_id=recipe_id, kingdom=castle.kingdom_id, castle_id=castle_id)
        self.request(request, CraftConstructionItemResponse, timeout=timeout)

    def skip_construction_crafting_time(
        self, castle_id: int, minute_skip: Currency | str, *, timeout: float = 5.0
    ) -> None:
        """
        Shorten the running construction item craft with a minute skip.

        Args:
            castle_id: The castle the craft runs in
            minute_skip: The minute skip to use, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``;
                its key (``"MS1"``) also works, for a skip newer than the generated enum
            timeout: Timeout in seconds

        Raises:
            ValueError: ``minute_skip`` is no minute skip, or the special currencies hold none of it
            UnknownCastleError: ``castle_id`` is not one of your castles

        Client: ``ConstructionItemCraftingMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 79954)
        """
        castle = self._require_own_castle(castle_id)
        self._require_minute_skip(minute_skip)
        request = SkipConstructionCraftingRequest(
            kingdom=castle.kingdom_id, castle_id=castle_id, minute_skip=minute_skip
        )
        self.request(request, SkipConstructionCraftingResponse, timeout=timeout)

    def finish_construction_crafting(self, castle_id: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Finish the running construction item craft for rubies.

        The price falls with the time left (``ConstructionConst.getFastCompleteCostC2``) and is not checked
        here, so the call always needs ``spend_rubies``.

        Raises:
            ValueError: ``spend_rubies`` is False
            UnknownCastleError: ``castle_id`` is not one of your castles

        Client: ``CastleConstructionItemsCraftingSublayerProgress.onClick`` (bundle line 79930),
        ``craftingTimer`` (bundle line 79907)
        """
        castle = self._require_own_castle(castle_id)
        self._require_spend_rubies(spend_rubies, "finishing the construction item craft costs rubies")
        request = SkipConstructionCraftingRequest(
            kingdom=castle.kingdom_id, castle_id=castle_id, finish_for_rubies=True, minute_skip=FULL_SKIP
        )
        self.request(request, SkipConstructionCraftingResponse, timeout=timeout)
