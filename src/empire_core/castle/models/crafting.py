"""The crafting queues of the refinery and toolsmith buildings, and the construction item crafting.

Commands:
- crin: the crafting queues of every castle
- crst, crca, crqm, crsk, crun: start, cancel, reorder, skip and unlock in a crafting queue
- gcc: the running construction item craft
- cic: craft a construction item
- sci: shorten the running construction item craft
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import (
    ConfigDict,
    Field,
    ValidatorFunctionWrapHandler,
    field_serializer,
    field_validator,
    model_validator,
)

from empire_core.enums import BuildingState, CraftingSlotType, Kingdom
from empire_core.gamedata import ConstructionItemRecipeId, CraftingQueueId, CraftingRecipeId, EnumOrInt, EnumOrStr
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, EmpireModel
from empire_core.protocol.js import js_int, js_parse_int, js_truthy

from .objects import _building_state

if TYPE_CHECKING:
    from typing_extensions import Self

    from empire_core.gamedata import ConstructionItem, CraftingQueueDef, Currency

logger = logging.getLogger(__name__)

FULL_SKIP = "-"
"""The ``MST`` of a construction item craft finished for rubies rather than shortened by a minute skip.

Client: ``CastleConstructionItemsCraftingSublayerProgress.onClick`` (bundle line 79930)
"""


_NOT_WORKING = frozenset(
    {
        BuildingState.INITIAL,
        BuildingState.BUILD_IN_PROGRESS,
        BuildingState.BUILD_STOPPED,
        BuildingState.DISASSEMBLE_IN_PROGRESS,
        BuildingState.DISASSEMBLE_STOPPED,
    }
)


class CraftingSlot(EmpireModel):
    """
    One slot of a crafting queue.

    The permanent slots come first, then the temporary ones, which craft only while unlocked. A queue the
    castle service hands out has every slot of its ``GameData.crafting_queues`` row
    (:meth:`CraftingQueue.with_definition`); one read straight off the wire has only the slots the server
    listed, none of them temporary, since only the game data tells which are.

    Client: ``CraftingQueueVO.parseServerData`` (bundle line 29278); ``CraftingSlotVO.isFilled`` and
    ``isLocked`` (bundle lines 17002-17003)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    index: int = Field(description="The slot's place among the slots of its kind, from 0")
    slot_type: CraftingSlotType = Field(description="Whether the slot crafts now or waits")
    recipe_id: CraftingRecipeId | None = Field(
        default=None, description="The crafting recipe in the slot; None while empty"
    )
    remaining_seconds: int | None = Field(
        default=None, description="Seconds until the craft is done; None when not sent, the recipe's full time"
    )
    unlock_seconds: int | None = Field(
        default=None,
        description="Seconds a temporary slot stays unlocked, locked at 0 or less; None for a permanent slot",
    )
    booster_value: int = Field(default=0, description="The booster value of the slot")

    @property
    def is_temporary(self) -> bool:
        """Whether the slot must be unlocked to craft."""
        return self.unlock_seconds is not None

    @property
    def is_locked(self) -> bool:
        """Whether the slot is temporary and not unlocked now."""
        return self.unlock_seconds is not None and self.unlock_seconds <= 0

    @property
    def is_filled(self) -> bool:
        """Whether a craft runs in the slot."""
        return self.recipe_id is not None and (self.remaining_seconds is None or self.remaining_seconds > 0)


def _slots(value: Any, slot_type: CraftingSlotType) -> Any:
    if not isinstance(value, dict):
        return value if isinstance(value, (list, tuple)) else ()
    recipes, times, boosters = ([js_int(entry) for entry in value.get(key) or []] for key in ("CRID", "RCT", "BV"))
    return tuple(
        {
            "index": index,
            "slot_type": slot_type,
            "recipe_id": recipes[index] if index < len(recipes) and recipes[index] > 0 else None,
            "remaining_seconds": times[index] if index < len(times) else None,
            "booster_value": boosters[index] if index < len(boosters) else 0,
        }
        for index in range(max(len(recipes), len(times), len(boosters)))
    )


def _unlock_times(value: Any) -> tuple[int, ...]:
    return tuple(js_int(entry) for entry in value.get("RUT") or []) if isinstance(value, dict) else ()


def _laid_out(
    sent: tuple[CraftingSlot, ...],
    unlock_seconds: tuple[int, ...],
    slot_type: CraftingSlotType,
    permanent: int,
    temporary: int,
) -> tuple[CraftingSlot, ...]:
    count = permanent + temporary
    if len(sent) > count or len(unlock_seconds) > temporary:
        logger.warning(
            "%d %s crafting slots and %d unlock times sent for %d and %d in the game data; the rest are dropped",
            len(sent),
            slot_type.value,
            len(unlock_seconds),
            count,
            temporary,
        )
    unlocks = iter(unlock_seconds)
    return tuple(
        (sent[index] if index < len(sent) else CraftingSlot(index=index, slot_type=slot_type)).model_copy(
            update={"unlock_seconds": next(unlocks, 0) if index >= permanent else None}
        )
        for index in range(count)
    )


class CraftingQueue(BasePayload):
    """
    One crafting building's queue in one castle.

    Client: ``CastleCraftingData.parseBuildingQueueData`` (bundle line 111405), which keeps one queue per
    queue id, kingdom and castle
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    kingdom: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    castle_id: int = Field(validation_alias="AID", description="The castle")
    building_state: BuildingState = Field(
        validation_alias="S", default=BuildingState.INITIAL, description="What the crafting building is doing"
    )
    queue_id: CraftingQueueId = Field(
        validation_alias="CQID", description="The crafting queue, one per kind of crafting building"
    )
    object_id: int = Field(validation_alias="OID", description="The crafting building's object id in the castle")
    production: tuple[CraftingSlot, ...] = Field(
        validation_alias="PS", default=(), description="The slots crafting now, from the first"
    )
    queue: tuple[CraftingSlot, ...] = Field(
        validation_alias="QS", default=(), description="The slots waiting behind them, from the first"
    )
    production_unlock_seconds: tuple[int, ...] = Field(
        default=(),
        description="The ``PS`` ``RUT``: seconds each unlocked temporary crafting slot stays unlocked, in slot order",
    )
    queue_unlock_seconds: tuple[int, ...] = Field(
        default=(),
        description="The ``QS`` ``RUT``: seconds each unlocked temporary waiting slot stays unlocked, in slot order",
    )

    @model_validator(mode="before")
    @classmethod
    def _unlocks(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "PS" not in value and "QS" not in value:
            return value
        return {
            "production_unlock_seconds": _unlock_times(value.get("PS")),
            "queue_unlock_seconds": _unlock_times(value.get("QS")),
            **value,
        }

    @field_validator("building_state", mode="before")
    @classmethod
    def _state(cls, value: Any) -> BuildingState:
        return _building_state(value)

    @field_validator("production", mode="before")
    @classmethod
    def _production(cls, value: Any) -> Any:
        return _slots(value, CraftingSlotType.PRODUCTION)

    @field_validator("queue", mode="before")
    @classmethod
    def _queue(cls, value: Any) -> Any:
        return _slots(value, CraftingSlotType.QUEUE)

    @property
    def is_working(self) -> bool:
        """Whether the building is built and not being taken down, so that the client lets it craft.

        Client: ``IsoBuildingStateEnum.isFunctionally`` (bundle line 3432)
        """
        return self.building_state not in _NOT_WORKING

    def with_definition(self, definition: CraftingQueueDef) -> Self:
        """
        The queue with every slot of its game-data definition, as the client lays it out.

        The server leaves out the empty slots at the end and the locked temporary ones, and sends unlock times
        for unlocked temporary slots only. The client first builds the definition's slots, the permanent ones,
        then one temporary slot per unlock cost, and fills them in order: a recipe, time and booster per slot,
        an unlock time per temporary slot. A temporary slot left without one is locked. Slots past the
        definition's are dropped, as the client drops them.

        Client: ``CraftingQueueVO`` (bundle lines 29265-29277), ``CraftingQueueVO.parseServerData``
        (bundle line 29278)
        """
        return self.model_copy(
            update={
                "production": _laid_out(
                    self.production,
                    self.production_unlock_seconds,
                    CraftingSlotType.PRODUCTION,
                    definition.permanent_production_slots,
                    len(definition.production_slot_unlock_coins),
                ),
                "queue": _laid_out(
                    self.queue,
                    self.queue_unlock_seconds,
                    CraftingSlotType.QUEUE,
                    definition.permanent_queue_slots,
                    len(definition.queue_slot_unlock_coins),
                ),
            }
        )

    def slots(self, slot_type: CraftingSlotType) -> tuple[CraftingSlot, ...]:
        """The slots of one kind."""
        return self.production if slot_type is CraftingSlotType.PRODUCTION else self.queue

    def unlock_indices(self, slot: CraftingSlot) -> tuple[int, ...]:
        """The slots unlocking a slot buys: it and every locked slot right before it, first to last.

        Client: ``CastleCraftingData.buySlot`` (bundle line 111430), ``CraftingSlotVO.previousSlot``
        (bundle line 17017)
        """
        slots = self.slots(slot.slot_type)
        first = slot.index
        while first > 0 and slots[first - 1].is_locked:
            first -= 1
        return tuple(range(first, slot.index + 1))


class GetCraftingInfoRequest(BaseRequest):
    """
    Ask for the crafting queues of every castle.

    Command: crin
    Payload: {}

    Client: ``C2SCraftingInfoVO`` (bundle line 111480), sent by ``CastleCraftingData.getCraftingInfo``
    (bundle line 111423) when the refinery or toolsmith dialog opens (bundle line 29337)
    """

    command = "crin"


class CraftingInfoResponse(BaseResponse):
    """
    Crafting queues: every castle's, or one building's.

    Command: crin
    Payload: {"CAI": [{"CE": [...], "CBI": [queue, ...]}, ...]}, or one queue

    The ``CE`` crafting effects are not read.

    Client: ``CRINCommand.executeCommand`` (bundle line 123443) reads ``CAI``, an area or a list of areas,
    with ``CastleCraftingData.parseAllQueueData`` and ``parseAreaQueueData`` (bundle lines 111397-111404),
    else the payload as one queue
    """

    command = "crin"

    queues: tuple[CraftingQueue, ...] = Field(default=(), description="The queues sent")

    @model_validator(mode="before")
    @classmethod
    def _queues(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "queues" in value:
            return value
        areas = value.get("CAI")
        if not js_truthy(areas):
            return {"queues": [value]}
        rows = [
            row
            for area in (areas if isinstance(areas, list) else [areas])
            if js_truthy(area) and isinstance(area, dict)
            for row in area.get("CBI") or []
        ]
        return {"queues": rows}


class _CraftingQueueReply(CraftingQueue, BaseResponse):
    """A crafting action's reply: the building's queue after it."""


class StartCraftingRequest(BaseRequest):
    """
    Start a recipe in a crafting queue.

    Command: crst
    Payload: {"KID": kingdom, "AID": castle_id, "OID": object_id, "PWR": 0, "CRID": recipe_id}

    ``PWR`` is 0: the client never sends 1.

    Client: ``C2CraftingStartVO`` (bundle line 47683), sent by ``CastleCraftingData.startCrafting``
    (bundle line 111424) after ``CostHelper.validateCostBuyCommand`` checks the recipe's costs
    """

    command = "crst"

    kingdom: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    castle_id: int = Field(validation_alias="AID", description="The castle")
    object_id: int = Field(validation_alias="OID", description="The crafting building")
    pay_with_rubies: int = Field(validation_alias="PWR", default=0, description="Always 0")
    recipe_id: CraftingRecipeId = Field(validation_alias="CRID", description="The crafting recipe")


class StartCraftingResponse(_CraftingQueueReply):
    """
    The queue after a recipe started.

    Command: crst

    Client: ``CRSTCommand.executeCommand`` (bundle line 123488); a ``NO_FREE_CONSTRUCTION_SLOT`` refusal the
    client ignores
    """

    command = "crst"


class _SlotRequest(BaseRequest):
    kingdom: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    castle_id: int = Field(validation_alias="AID", description="The castle")
    object_id: int = Field(validation_alias="OID", description="The crafting building")


class CancelCraftingRequest(_SlotRequest):
    """
    Cancel the craft in one slot.

    Command: crca
    Payload: {"KID": kingdom, "AID": castle_id, "OID": object_id, "S": slot_index, "ST": slot_type}

    Client: ``C2SCraftingCancelVO`` (bundle line 111471), sent by ``CastleCraftingData.cancelCrafting``
    (bundle line 111426)
    """

    command = "crca"

    slot_index: int = Field(validation_alias="S", description="The slot, from 0")
    slot_type: CraftingSlotType = Field(validation_alias="ST", description="Whether it crafts or waits")


class CancelCraftingResponse(_CraftingQueueReply):
    """
    The queue after a craft was cancelled.

    Command: crca

    Client: ``CRCACommand.executeCommand`` (bundle line 123428)
    """

    command = "crca"


class MoveCraftingSlotRequest(_SlotRequest):
    """
    Move a waiting craft to another place in the queue.

    Command: crqm
    Payload: {"KID": kingdom, "AID": castle_id, "OID": object_id, "OS": from_index, "NS": to_index}

    Client: ``C2SCraftingQueueMoveVO`` (bundle line 111488), sent by ``CastleCraftingData.moveQueueSlot``
    (bundle line 111433) for a waiting slot dragged in the toolsmith dialog (bundle line 29418)
    """

    command = "crqm"

    from_index: int = Field(validation_alias="OS", description="The waiting slot moved, from 0")
    to_index: int = Field(validation_alias="NS", description="Where it goes, from 0")


class MoveCraftingSlotResponse(_CraftingQueueReply):
    """
    The queue after a waiting craft moved.

    Command: crqm

    Client: ``CRQMCommand.executeCommand`` (bundle line 123458)
    """

    command = "crqm"


class SkipCraftingRequest(_SlotRequest):
    """
    Finish the craft in one slot for rubies.

    Command: crsk
    Payload: {"KID": kingdom, "AID": castle_id, "OID": object_id, "S": slot_index, "ST": slot_type, "PC2": price}

    Client: ``C2SCraftingSkipVO`` (bundle line 111453), sent by ``CastleCraftingData.skipCrafting``
    (bundle line 111428) with ``CraftingSlotVO.getAdjustedSkipCostC2`` (bundle line 17012): the recipe's
    ``skipCostC2`` times the share of its time left, rounded up
    """

    command = "crsk"

    slot_index: int = Field(validation_alias="S", description="The slot, from 0")
    slot_type: CraftingSlotType = Field(validation_alias="ST", description="Whether it crafts or waits")
    price: int = Field(validation_alias="PC2", description="The rubies the skip costs, as the client prices it")


class SkipCraftingResponse(_CraftingQueueReply):
    """
    The queue after a craft was finished for rubies.

    Command: crsk

    Client: ``CRSKCommand.executeCommand`` (bundle line 123473)
    """

    command = "crsk"


class UnlockCraftingSlotsRequest(_SlotRequest):
    """
    Unlock temporary slots of a crafting queue for coins.

    Command: crun
    Payload: {"KID": kingdom, "AID": castle_id, "OID": object_id, "S": [slot_index, ...], "ST": slot_type}

    Client: ``C2SCraftingUnlockVO`` (bundle line 111462), sent by ``CastleCraftingData.buySlot``
    (bundle line 111430) with the slot bought and every locked slot before it, first to last
    """

    command = "crun"

    slot_indices: tuple[int, ...] = Field(validation_alias="S", description="The slots, from 0, first to last")
    slot_type: CraftingSlotType = Field(validation_alias="ST", description="Whether they craft or wait")


class UnlockCraftingSlotsResponse(_CraftingQueueReply):
    """
    The queue after slots were unlocked.

    Command: crun

    Client: ``CRUNCommand.executeCommand`` (bundle line 123504)
    """

    command = "crun"


class GetConstructionCraftingRequest(BaseRequest):
    """
    Ask for the running construction item craft.

    Command: gcc
    Payload: {}

    Client: ``C2SGetConstructionCraftingInfoVO`` (bundle line 49099), sent when the running craft's timer
    runs out (``CastleConstructionItemsCraftingSublayerProgress.craftingTimer``, bundle line 79907)
    """

    command = "gcc"


class ConstructionCraftingResponse(BaseResponse):
    """
    The construction item being crafted, and the time left.

    Command: gcc
    Payload: {"CID": construction_item_id, "RS": seconds}, or {} while nothing is crafted

    Client: ``GCCCommand`` (bundle line 123017) dispatches ``GCC_ARRIVED``;
    ``CastleConstructionItemsCraftingSublayer.onGCCArrived`` (bundle lines 79577-79581) reads ``CID``
    through ``parseInt`` and ``RS``, -1 when either is missing
    """

    command = "gcc"

    construction_item_id: EnumOrInt["ConstructionItem"] | None = Field(
        validation_alias="CID", default=None, description="The construction item being crafted; None for none"
    )
    remaining_seconds: int | None = Field(
        validation_alias="RS", default=None, description="Seconds until the craft is done; None while none runs"
    )

    @field_validator("construction_item_id", mode="before")
    @classmethod
    def _item(cls, value: Any) -> Any:
        item = None if value is None else js_parse_int(value)
        return None if item is None or item < 0 else item

    @field_validator("remaining_seconds", mode="before")
    @classmethod
    def _seconds(cls, value: Any) -> Any:
        return None if value is None or js_int(value) < 0 else js_int(value)


class CraftConstructionItemRequest(BaseRequest):
    """
    Craft a construction item from a recipe.

    Command: cic
    Payload: {"RID": recipe_id, "KID": kingdom, "AID": castle_id}

    Client: ``C2SCraftConstructionItemVO`` (bundle line 79943), sent by
    ``CastleConstructionItemsCraftingSublayerProgress.onClick`` (bundle line 79926) for the joined castle
    when it is yours, else the main castle of the kingdom
    """

    command = "cic"

    recipe_id: ConstructionItemRecipeId = Field(validation_alias="RID", description="The construction item recipe")
    kingdom: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    castle_id: int = Field(validation_alias="AID", description="The castle")


class CraftConstructionItemResponse(BaseResponse):
    """
    The server accepted a construction item craft.

    Command: cic

    Client: ``CICCommand`` (bundle line 122736) dispatches ``CIC_ARRIVED``;
    ``CastleConstructionItemsCraftingSublayerProgress.onCICArrived`` (bundle line 79925) reads only the
    status and asks for the construction inventory again
    """

    command = "cic"


class SkipConstructionCraftingRequest(BaseRequest):
    """
    Shorten the running construction item craft with a minute skip, or finish it for rubies.

    Command: sci
    Payload: {"KID": kingdom, "AID": castle_id, "PWR": 0 or 1, "MST": minute_skip}

    A minute skip goes with ``PWR`` 0; ``MST`` ``"-"`` with ``PWR`` 1 finishes the craft for rubies.

    Client: ``C2SMinuteSkipCraftingVO`` (bundle line 49274), built by
    ``ConstructionItemCraftingMinuteSkipProperties`` (bundle lines 79954-79955) for the joined castle
    """

    command = "sci"

    kingdom: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    castle_id: int = Field(validation_alias="AID", description="The castle")
    finish_for_rubies: bool = Field(validation_alias="PWR", default=False, description="Finish the craft for rubies")
    minute_skip: EnumOrStr["Currency"] = Field(
        validation_alias="MST",
        description='The minute skip used, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``; ``"-"`` to finish '
        "for rubies",
    )

    @field_validator("minute_skip", mode="wrap")
    @classmethod
    def _full_skip(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        return FULL_SKIP if value == FULL_SKIP else handler(value)

    @field_serializer("finish_for_rubies")
    def _flag(self, value: bool) -> int:
        return int(value)


class SkipConstructionCraftingResponse(BaseResponse):
    """
    The server accepted a construction item craft skip.

    Command: sci

    Client: ``SCICommand.executeCommand`` (bundle line 123264) reads only the status; the crafting dialog
    then asks for the construction inventory again (bundle line 79532)
    """

    command = "sci"


__all__ = [
    "FULL_SKIP",
    "CancelCraftingRequest",
    "CancelCraftingResponse",
    "ConstructionCraftingResponse",
    "CraftConstructionItemRequest",
    "CraftConstructionItemResponse",
    "CraftingInfoResponse",
    "CraftingQueue",
    "CraftingSlot",
    "GetConstructionCraftingRequest",
    "GetCraftingInfoRequest",
    "MoveCraftingSlotRequest",
    "MoveCraftingSlotResponse",
    "SkipConstructionCraftingRequest",
    "SkipConstructionCraftingResponse",
    "SkipCraftingRequest",
    "SkipCraftingResponse",
    "StartCraftingRequest",
    "StartCraftingResponse",
    "UnlockCraftingSlotsRequest",
    "UnlockCraftingSlotsResponse",
]
