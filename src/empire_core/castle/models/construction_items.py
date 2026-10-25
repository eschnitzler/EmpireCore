"""Construction items in storage and the actions that place or disassemble them."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import ConfigDict, Field, field_validator, model_validator

from empire_core.castle.models.objects import BuildingConstructionItems, PlacedConstructionItem
from empire_core.enums import ConstructionItemMode, CurrencyId, Kingdom
from empire_core.gamedata import Collectable, EnumOrInt, RewardId
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, read_or_none, readable_list
from empire_core.protocol.js import js_number_or_none, js_parse_int

if TYPE_CHECKING:
    from empire_core.gamedata import Building, ConstructionItem

logger = logging.getLogger(__name__)


class ConstructionItemStack(BasePayload):
    """One inventory row, ``[construction item id, amount]``.

    Client: ``ConstructionItemData.updateInventory`` (bundle lines 22947-22952),
    ``CollectableItemConstructionItemVO`` (bundle line 12252),
    ``ACollectableItemVO.amount`` (bundle line 3575).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    construction_item_id: EnumOrInt["ConstructionItem"] = Field(description="The construction item")
    amount: int = Field(description="How many items are in storage")

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, value: Any) -> int:
        number = js_number_or_none(value)
        if number is None or not math.isfinite(number):
            raise ValueError("A construction item amount must be a finite number")
        return math.floor(number)

    @model_validator(mode="before")
    @classmethod
    def _row(cls, value: Any) -> Any:
        if isinstance(value, list):
            if len(value) < 2:
                raise ValueError("A construction item stack needs an item and an amount")
            return {"construction_item_id": value[0], "amount": value[1]}
        return value


class GetConstructionItemsRequest(BaseRequest):
    """Request the construction inventory.

    Client: ``C2SGetContructionItemsInventoryVO`` (bundle lines 28546-28550).
    """

    command = "gii"


class ConstructionItemInventory(BaseResponse):
    """The construction items in storage, replaced in full by each inventory reply.

    Client: ``GIICommand.executeCommand`` (bundle line 123270),
    ``ConstructionItemData.updateInventory`` (bundle lines 22947-22952).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gii"

    items: tuple[ConstructionItemStack, ...] = Field(validation_alias="CI", description="The items in storage")

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, value: Any) -> Any:
        if isinstance(value, list):
            items = [
                read_or_none(ConstructionItemStack.model_validate, row, warn=logger, what="a construction item stack")
                for row in value
            ]
            return tuple(item for item in items if item is not None)
        return value


class ConstructionItemPlacement(BasePayload):
    """The complete item placement for the joined castle.

    Client: ``AreaDataConstructionItems.updateConstructionItems`` (bundle line 131114),
    ``ABasicBuildingVO.parseConstructionItems`` (bundle lines 18000-18010).
    """

    items: tuple[BuildingConstructionItems, ...] = Field(validation_alias="CI", description="Items on each building")

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, value: Any) -> Any:
        if isinstance(value, list):
            return readable_list(BuildingConstructionItems, value, warn=logger, what="placed construction items")
        return value


class EquipConstructionItemRequest(BaseRequest):
    """Equip or replace an item on a building.

    Client: ``C2SReplaceConstructionItemVO`` (bundle lines 79234-79236).
    """

    command = "rpc"

    object_id: int = Field(validation_alias="OID", description="The building's object id")
    construction_item_id: EnumOrInt["ConstructionItem"] = Field(validation_alias="CID", description="The item to equip")
    slot: int = Field(validation_alias="SID", ge=0, description="Slot index within the item's slot type")
    mode: ConstructionItemMode = Field(
        validation_alias="M", default=ConstructionItemMode.ADD, description="How to replace an existing item"
    )
    kingdom_id: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    castle_id: int = Field(validation_alias="AID", description="The castle's id")


class EquipConstructionItemResponse(ConstructionItemPlacement, BaseResponse):
    """Items on the joined castle's buildings after equipping.

    Client: ``RPCCommand.executeCommand`` (bundle lines 123313-123314).
    """

    command = "rpc"


class RemoveConstructionItemRequest(BaseRequest):
    """Remove an equipped item into storage for its coin removal cost.

    Client: ``C2SRemoveConstructionItemVO`` (bundle lines 79282-79284),
    ``CastleConstructionItemsExtractDialog`` (bundle lines 79267-79277).
    """

    command = "cri"

    object_id: int = Field(validation_alias="OID", description="The building's object id")
    construction_item_id: EnumOrInt["ConstructionItem"] = Field(validation_alias="CID", description="The equipped item")
    slot: int = Field(validation_alias="SID", ge=0, description="Slot index within the item's slot type")
    kingdom_id: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    castle_id: int = Field(validation_alias="AID", description="The castle's id")


class RemoveConstructionItemResponse(ConstructionItemPlacement, BaseResponse):
    """Items on the joined castle's buildings after removing an item.

    Client: ``CRICommand.executeCommand`` (bundle lines 123255-123256).
    """

    command = "cri"


class DisassembleConstructionItemRequest(BaseRequest):
    """Disassemble items from storage or lost and found.

    Client: ``C2SDisassembleConstructionItemVO`` (bundle lines 79223-79227),
    ``ConstructionItemsActionProperties`` (bundle line 35689, LFID defaults to -1).
    """

    command = "dci"

    construction_item_id: EnumOrInt["ConstructionItem"] = Field(
        validation_alias="CID", description="The item to disassemble"
    )
    kingdom_id: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    castle_id: int = Field(validation_alias="AID", description="The castle's id")
    lost_and_found_id: int = Field(
        validation_alias="LFID", default=-1, description="Lost and found entry id; -1 for storage"
    )
    amount: int = Field(validation_alias="AMT", default=1, ge=1, description="How many items to disassemble")


class DisassembleConstructionItemResponse(BaseResponse):
    """Disassembled amount and the rewards drawn for temporary items.

    Permanent items' material yield is defined by the recipe, not this reply.
    Unknown reward ids remain available even if no game-data row resolves them.

    Client: ``CastleConstructionItemsDisassembleDialog.onDCIArrived`` (bundle line 35729),
    ``CastleConstructionItemsDisassembledDialog.showTempCIDisassembling`` and
    ``selectedAmountForResources`` (bundle lines 48984, 49000).
    """

    command = "dci"

    amount: int | None = Field(validation_alias="AMT", default=None, description="How many items were disassembled")
    reward_ids: tuple[RewardId, ...] = Field(validation_alias="RIDS", default=(), description="The rewards drawn")
    rewards: tuple[Collectable, ...] = Field(default=(), description="Collectables resolved from the rewards drawn")


class ConstructionItemSpaceRequest(BaseRequest):
    """Request the free construction inventory capacity.

    Client: ``C2SConstructionItemInventorySpaceLeftVO`` (bundle line 41293), sent by
    ``LostAndFoundDialog.showLoaded`` (bundle line 107119)
    """

    command = "csp"


class ConstructionItemSpace(BaseResponse):
    """Free construction inventory capacity, which may be negative.

    Client: ``CSPCommand.exec`` / ``ConstructionItemData.parse_CSP``
    (bundle 123841-123843 / 22960).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "csp"
    space_left: int = Field(validation_alias="C", description="How many more construction items fit in storage")

    @field_validator("space_left", mode="before")
    @classmethod
    def _space(cls, value: Any) -> int:
        number = js_parse_int(value)
        if number is None:
            raise ValueError("Construction item capacity must be readable as an integer")
        return number


class ExpiredConstructionItem(BasePayload):
    """A construction item that expired on a building.

    Client: ``ConstructionItemExpiredVO.parseParams`` (bundle 77661).
    """

    construction_item_id: EnumOrInt["ConstructionItem"] = Field(validation_alias="CID", description="The expired item")
    building_id: EnumOrInt["Building"] = Field(validation_alias="B", description="The building's game-data id")
    object_id: int = Field(validation_alias="OID", description="The building's object id")


class ExpiredConstructionItemArea(BasePayload):
    """The expired construction items in one castle.

    Client: ``ConstructionItemExpiredAreaVO.parseParams`` (bundle 47886-47890).
    """

    castle_id: int = Field(validation_alias="AID", description="The castle's id")
    kingdom_id: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    items: tuple[ExpiredConstructionItem, ...] = Field(validation_alias="CIL", description="The expired items")


class GetExpiredConstructionItemsRequest(BaseRequest):
    """Request expired items across your castles.

    Client: ``C2SGetAllExpiredConstructionItemsVO`` (bundle 79379-79381).
    """

    command = "aec"


class ExpiredConstructionItemsResponse(BaseResponse):
    """The complete list of castles with expired construction items.

    Client: ``AECCommand.executeCommand`` / ``ConstructionItemData.parse_AEC``
    (bundle 123264-123266 / 22985-22989). The wire body is a list.
    """

    command = "aec"
    areas: tuple[ExpiredConstructionItemArea, ...] = Field(description="Castles with expired items")

    @model_validator(mode="before")
    @classmethod
    def _areas(cls, value: Any) -> Any:
        if isinstance(value, list):
            return {"areas": value}
        return value


class MarkExpiredConstructionItemsSeenRequest(BaseRequest):
    """Mark the expired item list for a castle as viewed.

    Client: ``C2SMarkExpiredConstructionItemVO`` / assign sublayer hide / switchCastle
    (bundle 79370-79372 / 77574 / 77583).
    """

    command = "mec"
    castle_id: int = Field(validation_alias="AID", description="The castle whose expired items were viewed")


class MarkExpiredConstructionItemsSeenResponse(BaseResponse):
    """Acknowledgement that expired items were marked as viewed.

    Client: ``MECCommand.executeCommand`` (bundle 123308), which reads no fields.
    """

    command = "mec"


class MoveConstructionSlotRequest(BaseRequest):
    """Move an occupied building queue slot, within the joined castle.

    Client: ``C2SMoveConstructionItemVO`` / ``CastleBuildingListComponent.requestMoveFromServer``
    (bundle 108290-108292 / 108280-108281).
    """

    command = "mci"
    object_id: int = Field(validation_alias="OID", gt=0, description="The queued building's object id")
    new_position: int = Field(validation_alias="NS", ge=0, description="The occupied destination queue position")


class MoveConstructionSlotResponse(BaseResponse):
    """Queue move acknowledgement; the queue itself is delivered by scl.

    Client: ``MCICommand.executeCommand`` (bundle 123383).
    """

    command = "mci"

    @model_validator(mode="before")
    @classmethod
    def _body(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "raw" in value:
            raise ValueError("The construction queue acknowledgement must contain valid JSON")
        return value


class BoostConstructionItemRequest(BaseRequest):
    """Consume one explicitly selected inventory booster on a temporary construction item.

    Client: ``C2SUseBoosterConsumableOnConstructionItemVO`` (bundle 79457-79459).
    """

    command = "ubc"
    object_id: int = Field(validation_alias="OID", gt=0, description="The building's object id")
    consumable_id: CurrencyId = Field(validation_alias="SUC", description="The inventory booster to consume")
    slot: int = Field(validation_alias="SID", ge=0, description="Slot index within the item's slot type")
    kingdom_id: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    castle_id: int = Field(validation_alias="AID", description="The castle's id")
    construction_item_id: EnumOrInt["ConstructionItem"] = Field(validation_alias="CID", description="The equipped item")


class BoostConstructionItemResponse(ConstructionItemPlacement, BaseResponse):
    """The complete placement after consuming the booster.

    Client: ``UBCCommand.executeCommand`` (bundle 123350-123352).
    """

    command = "ubc"

    @model_validator(mode="before")
    @classmethod
    def _placement(cls, value: Any) -> Any:
        if isinstance(value, dict) and isinstance(value.get("CI"), list):
            for building in value["CI"]:
                BuildingConstructionItems.model_validate(building)
                if not isinstance(building, dict) or (js_number_or_none(building.get("OID")) or 0) <= 0:
                    raise ValueError("A booster reply needs valid building object ids")
                if not isinstance(building, dict) or not isinstance(building.get("CIL"), list):
                    raise ValueError("A booster reply needs complete placed item records")
                for item in building["CIL"]:
                    PlacedConstructionItem.model_validate(item)
        return value
