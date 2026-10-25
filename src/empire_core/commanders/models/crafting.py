"""Equipment and gem crafting, enchanting and gem extraction, and the merchant purchases pushed in.

Commands:
- ceq: craft an item from items
- eqe: enchant an item
- ere: enchant a relic item or relic gem
- cge: craft a gem from gems
- ege: take a gem out of an item
- gnr: the relic items and relic gems not seen yet
- beq, bri, bgm: equipment, relics or gems bought from a merchant, pushed
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, js_int, js_loose_equals, js_parse_int_or_zero, js_truthy

from .equipment import Equipment, RelicGem
from .inventory import InventorySpace

if TYPE_CHECKING:
    from empire_core.gamedata import Gem

logger = logging.getLogger(__name__)

_RELIC_GEM_ROW = 6
"""Entries of a relic gem row; an item row is longer (``RelicGemVO.parseServerObject``, bundle line 22222)."""


class CraftEquipmentRequest(BaseRequest):
    """
    Craft an item from inventory items, which are used up.

    Command: ceq
    Payload: {"EX": 0 or 1, "I": [equipment_id, ...]}

    ``EX`` 1 takes the gems set in the items back into the inventory first, for rubies, or relic fragments
    for a relic gem; with 0 those gems are lost.

    Client: ``C2SCraftEquipmentVO`` (bundle line 144011), sent by ``CastleEquipmentData.craftEquipment``
    (bundle line 143898) with the crafting slots' items; ``CastleExtractGemsDialog.onClick`` (bundle line
    74272) passes 1 for its extract button, priced by ``calculateRemovalCostsForGems``
    """

    command = "ceq"

    extract_gems: bool = Field(
        validation_alias="EX", default=False, description="Take the items' gems back first; sent as 1 or 0"
    )
    equipment_ids: tuple[int, ...] = Field(validation_alias="I", description="The items used up")

    @field_serializer("extract_gems")
    def _flag(self, value: bool) -> int:
        return int(value)


class CraftEquipmentResponse(BaseResponse):
    """
    The crafted item, and your inventory space after.

    Command: ceq
    Payload: {"E": item, "esl": {...}}

    Client: ``CEQCommand.executeCommand`` (bundle line 123825), ``CastleEquipmentData.parse_CEQ``
    (bundle line 143846)
    """

    command = "ceq"

    equipment: Equipment = Field(validation_alias="E", description="The crafted item")
    inventory_space: InventorySpace | None = Field(
        validation_alias="esl", default=None, description="Your inventory space after"
    )

    @field_validator("inventory_space", mode="before")
    @classmethod
    def _space(cls, value: Any) -> Any:
        return value if js_truthy(value) else None


class EnchantEquipmentRequest(BaseRequest):
    """
    Enchant an item one level, for coins or rubies.

    Command: eqe
    Payload: {"C2": 0 or 1, "EID": equipment_id}

    Client: ``C2SEnchantEquipmentEvent`` (bundle line 115809), sent with ``C2`` 0 for the coin button and 1
    for the ruby button (bundle lines 59446-59448)
    """

    command = "eqe"

    pay_with_rubies: bool = Field(validation_alias="C2", default=False, description="Pay in rubies; sent as 1 or 0")
    equipment_id: int = Field(validation_alias="EID", description="The item")

    @field_serializer("pay_with_rubies")
    def _flag(self, value: bool) -> int:
        return int(value)


class EnchantEquipmentResponse(BaseResponse):
    """
    The enchanted item.

    Command: eqe
    Payload: {"E": item}

    The enchantment's chance failing is the ``ENCHANTING_FAILED`` refusal.

    Client: ``EQECommand.executeCommand`` (bundle line 123900)
    """

    command = "eqe"

    equipment: Equipment = Field(validation_alias="E", description="The item after")


class EnchantRelicRequest(BaseRequest):
    """
    Enchant a relic item or relic gem one level, for relic fragments and coins or rubies.

    Command: ere
    Payload: {"C2": 0 or 1, "RIID": relic_id, "EQ": 1 or 0}

    Client: ``C2SEnchantRelicItemEventVO`` (bundle line 85955), sent by ``RelicUpgradeDialog.onBuyButtonClicked``
    (bundle line 29490) with ``EQ`` 1 for an item, 0 for a relic gem (the one set in an item too), priced by
    ``RelicUpgradeDialogPayment.getCosts`` (bundle line 86002)
    """

    command = "ere"

    pay_with_rubies: bool = Field(validation_alias="C2", default=False, description="Pay in rubies; sent as 1 or 0")
    relic_id: int = Field(
        validation_alias="RIID", description="The relic item's equipment_id, or the relic gem's gem_id"
    )
    is_equipment: bool = Field(validation_alias="EQ", description="A relic item, not a relic gem; sent as 1 or 0")

    @field_serializer("pay_with_rubies", "is_equipment")
    def _flag(self, value: bool) -> int:
        return int(value)


class EnchantRelicResponse(BaseResponse):
    """
    The enchanted relic item or relic gem.

    Command: ere
    Payload: {"E": item or relic gem}

    The enchantment's chance failing is the ``ENCHANTING_FAILED`` refusal. A relic gem row has six entries,
    an item row more.

    Client: ``ERECommand.executeCommand`` (bundle line 123920); ``RelicUpgradeDialogSelector.updateItemInfo``
    (bundle line 86101) reads it with ``RelicGemVO.parseServerObject`` or ``RelicEquipmentVO.parseEquipFromArray``
    """

    command = "ere"

    equipment: Equipment | None = Field(default=None, description="The relic item after; None for a relic gem")
    relic_gem: RelicGem | None = Field(default=None, description="The relic gem after; None for an item")

    @model_validator(mode="before")
    @classmethod
    def _row(cls, value: Any) -> Any:
        if not isinstance(value, dict) or not isinstance(row := value.get("E"), list):
            return value
        return {**value, ("relic_gem" if len(row) <= _RELIC_GEM_ROW else "equipment"): row}


class CraftGemRequest(BaseRequest):
    """
    Craft a gem a level up from a gem and the gems around it, which are used up.

    Command: cge
    Payload: {"MID": gem_id, "C2": 0 or 1, "UG": [gem_id, ...]}

    ``C2`` 1 is the ruby craft.

    Client: ``C2SCraftGemVO`` (bundle line 144567), sent by ``CastleGemData.craftGem`` (bundle line 144476)
    with the centre gem and the outer slots' gems; ``CraftingGemClickHandler.handleDialogClick`` (bundle
    lines 73941-73943) passes 1 for the ruby button
    """

    command = "cge"

    gem_id: EnumOrInt["Gem"] = Field(validation_alias="MID", description="The centre gem, crafted a level up")
    pay_with_rubies: bool = Field(validation_alias="C2", default=False, description="The ruby craft; sent as 1 or 0")
    used_gem_ids: tuple[EnumOrInt["Gem"], ...] = Field(validation_alias="UG", description="The outer gems used up")

    @field_serializer("pay_with_rubies")
    def _flag(self, value: bool) -> int:
        return int(value)


class CraftGemResponse(BaseResponse):
    """
    Whether the gem craft worked, and your inventory space after.

    Command: cge
    Payload: {"S": 1 or 0, "esl": {...}}

    On success the client adds the centre gem's next level (``CastleGemData.getGemVO(upgradeId)``) to the
    inventory; on failure it shows the craft failed.

    Client: ``CGECommand.executeCommand`` (bundle line 123840), ``CastleGemData.parse_CGE`` (bundle line 144469)
    """

    command = "cge"

    crafted: bool = Field(validation_alias="S", default=False, description="Whether the craft worked")
    inventory_space: InventorySpace | None = Field(
        validation_alias="esl", default=None, description="Your inventory space after"
    )

    @field_validator("crafted", mode="before")
    @classmethod
    def _crafted(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    @field_validator("inventory_space", mode="before")
    @classmethod
    def _space(cls, value: Any) -> Any:
        return value if js_truthy(value) else None


class ExtractGemRequest(BaseRequest):
    """
    Take the gem out of an item, back into the inventory.

    Command: ege
    Payload: {"EID": equipment_id, "LID": commander_id}

    A gem costs its level's ``removalCostC2`` rubies, a relic gem ``RelicItemConst``'s relic fragments
    (``CastleExtractSocketDialog.getCosts``, bundle line 65738).

    Client: ``C2SExtractGemVO`` (bundle line 144576), sent by ``CastleGemData.extractGem`` (bundle line 144483)
    with the wearer (``CastleExtractSocketDialog.onValidConfirmClicked``, bundle line 65740), or -1 for an
    inventory item (bundle line 65686)
    """

    command = "ege"

    equipment_id: int = Field(validation_alias="EID", description="The item")
    commander_id: int = Field(validation_alias="LID", default=-1, description="The commander wearing it; -1 for none")


class ExtractGemResponse(BaseResponse):
    """
    The server took the gem out.

    Command: ege

    Client: ``EGECommand.executeCommand`` (bundle line 123886) moves the gem into the inventory
    (``CastleGemData.gemExtractionSuccess``, bundle line 144484) and asks for the equipment inventory again
    """

    command = "ege"


class GetNewRelicsRequest(BaseRequest):
    """
    Ask which relic items and relic gems you have not seen yet.

    Command: gnr
    Payload: {}

    Client: ``C2SGetNewRelicsEventVO`` (bundle line 74427), sent when the equipment dialog opens (bundle line 8801)
    """

    command = "gnr"


class NewRelicItemsResponse(BaseResponse):
    """
    The relic items and relic gems you have not seen yet, by id.

    Command: gnr
    Payload: {"E": [equipment_id, ...], "RGEM": [gem_id, ...]}

    Client: ``GNRCommand.executeCommand`` (bundle line 124029), ``CastleEquipmentData.parseGNR``
    (bundle line 143863); ``isEquipableNew`` (bundle line 143871) matches them against an item's or relic
    gem's id
    """

    command = "gnr"

    equipment_ids: tuple[int, ...] = Field(
        validation_alias="E", default=(), description="The new relic items' ``Equipment.equipment_id``"
    )
    relic_gem_ids: tuple[int, ...] = Field(
        validation_alias="RGEM", default=(), description="The new relic gems' ``RelicGem.gem_id``"
    )

    @field_validator("equipment_ids", "relic_gem_ids", mode="before")
    @classmethod
    def _ids(cls, value: Any) -> Any:
        return tuple(js_int(entry) for entry in value) if isinstance(value, list) else ()


class _MerchantPurchase(BaseResponse):
    package_id: ClientInt = Field(validation_alias="PID", default=0, description="The merchant package bought")
    event_id: ClientInt = Field(validation_alias="TID", default=0, description="The event whose merchant sold it")
    buy_type: ClientInt = Field(validation_alias="BT", default=0, description="How it was bought")


class BoughtEquipmentResponse(_MerchantPurchase):
    """
    Items bought from a merchant, pushed when they arrive.

    Command: beq, a push only: the client builds no request for it
    Payload: {"I": [item, ...], "PID": package_id, "TID": event_id, "BT": buy_type}

    Client: ``BEQCommand.executeCommand`` (bundle line 123710) shows them in
    ``CastleEquipmentMerchantEventIncomingDialog``
    """

    command = "beq"

    items: tuple[Equipment, ...] = Field(validation_alias="I", default=(), description="The items bought")

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, value: Any) -> Any:
        return readable_list(
            Equipment, value, accept=lambda row: isinstance(row, (list, tuple, dict)), warn=logger, what="items"
        )


class BoughtRelic(BasePayload):
    """
    A relic item or relic gem bought, ``[_, {"EQ": item}]`` or ``[_, {"GEM": relic_gem}]``.

    Client: ``BRICommand.parseEquipmentInventory`` (bundle line 123799), ``CollectableItemRelicVO.parseServerObject``
    (bundle line 10481)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    equipment: Equipment | None = Field(
        validation_alias="EQ", default=None, description="The relic item; None for a gem"
    )
    relic_gem: RelicGem | None = Field(
        validation_alias="GEM", default=None, description="The relic gem; None otherwise"
    )

    @model_validator(mode="before")
    @classmethod
    def _relic(cls, value: Any) -> Any:
        relic = value[1] if isinstance(value, list) and len(value) > 1 else value
        # The client reads a GEM before an EQ
        return {"GEM": relic["GEM"]} if isinstance(relic, dict) and js_truthy(relic.get("GEM")) else relic


class BoughtRelicsResponse(_MerchantPurchase):
    """
    Relic items and relic gems bought from a merchant, pushed when they arrive.

    Command: bri, a push only: the client builds no request for it
    Payload: {"I": [[_, {"EQ": item}], ...], "PID": package_id, "TID": event_id, "BT": buy_type}

    Client: ``BRICommand.executeCommand`` (bundle line 123797)
    """

    command = "bri"

    relics: tuple[BoughtRelic, ...] = Field(validation_alias="I", default=(), description="The relics bought")

    @field_validator("relics", mode="before")
    @classmethod
    def _relics(cls, value: Any) -> Any:
        return readable_list(
            BoughtRelic,
            value,
            accept=lambda row: isinstance(row, list) and len(row) > 1 and isinstance(row[1], dict),
            warn=logger,
            what="relics",
        )


class BoughtGemsResponse(_MerchantPurchase):
    """
    Gems bought from a merchant, pushed when they arrive, with your inventory space after.

    Command: bgm, a push only: the client builds no request for it
    Payload: {"GEM": [gem_id, ...], "PID": package_id, "TID": event_id, "BT": buy_type, "esl": {...}}

    Client: ``BGMCommand.executeCommand`` (bundle line 123769), ``parseGemInventory`` (bundle line 123778)
    """

    command = "bgm"

    gem_ids: tuple[EnumOrInt["Gem"], ...] = Field(validation_alias="GEM", default=(), description="The gems bought")
    inventory_space: InventorySpace | None = Field(
        validation_alias="esl", default=None, description="Your inventory space after"
    )

    @field_validator("gem_ids", mode="before")
    @classmethod
    def _gems(cls, value: Any) -> Any:
        return tuple(js_parse_int_or_zero(entry) for entry in value) if isinstance(value, list) else ()

    @field_validator("inventory_space", mode="before")
    @classmethod
    def _space(cls, value: Any) -> Any:
        return value if js_truthy(value) else None


__all__ = [
    "BoughtEquipmentResponse",
    "BoughtGemsResponse",
    "BoughtRelic",
    "BoughtRelicsResponse",
    "CraftEquipmentRequest",
    "CraftEquipmentResponse",
    "CraftGemRequest",
    "CraftGemResponse",
    "EnchantEquipmentRequest",
    "EnchantEquipmentResponse",
    "EnchantRelicRequest",
    "EnchantRelicResponse",
    "ExtractGemRequest",
    "ExtractGemResponse",
    "GetNewRelicsRequest",
    "NewRelicItemsResponse",
]
