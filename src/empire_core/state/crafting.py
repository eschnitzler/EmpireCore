"""The crafting queues (crin and the crafting actions' replies) and the fusion forges (ffi)."""

from typing import Any

from empire_core.castle.models.crafting import CraftingInfoResponse, CraftingQueue
from empire_core.castle.models.fusion_forge import FusionForge, FusionForgesResponse
from empire_core.state.base import StateBase, read_section

CRAFTING_QUEUE_REPLIES = ("crst", "crca", "crqm", "crsk", "crun")


class CraftingState(StateBase):
    def _handle_crin(self, data: Any) -> None:
        """Apply a ``crin``, or a ``jaa``'s ``crai``: the queues it lists over those known.

        Client: ``CRINCommand.executeCommand`` (bundle line 123443) and ``JAACommand`` (bundle line 130249),
        ``CastleCraftingData.parseBuildingQueueData`` (bundle line 111405), which updates the queue of the same
        queue id, kingdom and castle
        """
        if (info := read_section(CraftingInfoResponse, data, "the crafting queues")) is not None:
            self._apply_crafting_queues(info.queues)

    def _handle_crafting_queue(self, data: Any) -> None:
        """Apply a crafting action's reply: the one queue it carries.

        Client: ``CRSTCommand``, ``CRCACommand``, ``CRQMCommand``, ``CRSKCommand`` and ``CRUNCommand``
        (bundle lines 123488, 123428, 123458, 123473, 123504)
        """
        if (queue := read_section(CraftingQueue, data, "a crafting queue")) is not None:
            self._apply_crafting_queues((queue,))

    def _apply_crafting_queues(self, queues: tuple[CraftingQueue, ...]) -> None:
        known = dict(self.crafting_queues or {})
        known.update(((queue.queue_id, queue.kingdom, queue.castle_id), queue) for queue in queues)
        self.crafting_queues = known

    def _handle_ffi(self, data: Any) -> None:
        """Apply an ``ffi``: the fusion forges it lists over those known.

        Client: ``FusionForgeData.parseFFI`` (bundle line 141989)
        """
        if (info := read_section(FusionForgesResponse, data, "the fusion forges")) is not None:
            self.fusion_forges = {**(self.fusion_forges or {}), **{forge.forge_id: forge for forge in info.forges}}

    def get_crafting_queues(self) -> tuple[CraftingQueue, ...] | None:
        """Every crafting queue a ``crin``, a castle join or a crafting action's reply sent, as the last one left
        it; None until one arrived.

        Their times are as of the packet that sent each queue.
        """
        with self._lock:
            return None if self.crafting_queues is None else tuple(self.crafting_queues.values())

    def get_fusion_forges(self) -> dict[int, FusionForge] | None:
        """The fusion forges by id, as the last ``ffi`` that listed each left it; None until one arrived.

        Their recharge progress is as of that packet.
        """
        with self._lock:
            return None if self.fusion_forges is None else dict(self.fusion_forges)
