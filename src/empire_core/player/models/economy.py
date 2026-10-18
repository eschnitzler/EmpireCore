"""
Loot boxes, as the login data and their pushes send them, and opening them.

Commands:
- gls: your loot boxes and key progress, a push before and a section of ``gbd``
- ole: open a loot box
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import ConfigDict, Field, field_serializer, field_validator, model_validator

from empire_core.enums import MysteryBoxKey
from empire_core.gamedata import Collectable, EnumOrInt, RewardId
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    readable_list,
)
from empire_core.protocol.js import ClientNumber, js_truthy

if TYPE_CHECKING:
    from empire_core.gamedata import LootBox, LootBoxType


def _is_object(entry: Any) -> bool:
    return isinstance(entry, dict)


class LootBoxAmount(BasePayload):
    """
    One kind of loot box you hold: ``{"ID": loot box, "AMT": amount}``.

    Client: ``CastleLootboxData.parse_GLS`` (bundle line 112332) reads each as an ``ACollectableItemLootBoxVO``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    loot_box_id: EnumOrInt["LootBox"] = Field(validation_alias="ID", default=0, description="The loot box")
    amount: ClientNumber = Field(validation_alias="AMT", default=0, description="How many you hold")


class LootBoxKeys(BasePayload):
    """
    The keys collected towards one loot box type: ``{"ID": loot box type, "AMT": keys}``.

    Client: ``CastleLootboxData.parse_GLS`` and ``setKeyProgress`` (bundle lines 112332, 112343)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    loot_box_type_id: EnumOrInt["LootBoxType"] = Field(
        validation_alias="ID", default=0, description="The loot box type"
    )
    keys: ClientNumber = Field(validation_alias="AMT", default=0, description="The keys collected")


class LootBoxesResponse(BaseResponse):
    """
    Your loot boxes, and the keys collected towards each loot box type.

    A ``gls`` lists the loot boxes whole, but key progress only for some types; the client keeps the
    others as they were, and ``client.state.get_loot_boxes()`` does the same.

    Command: gls, a push the server sends before ``gbd`` and again when they change.

    Client: ``GLSCommand`` (bundle line 124800), ``CastleLootboxData.parse_GLS`` (bundle line 112332)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gls"

    loot_boxes: tuple[LootBoxAmount, ...] = Field(
        validation_alias="ALL", default=(), description="The loot boxes you hold"
    )
    key_progress: tuple[LootBoxKeys, ...] = Field(
        validation_alias="KEY",
        default=(),
        description="Keys collected per loot box type this packet lists",
    )

    @field_validator("loot_boxes", mode="before")
    @classmethod
    def _amounts(cls, value: Any) -> Any:
        return tuple(readable_list(LootBoxAmount, value, accept=_is_object))

    @field_validator("key_progress", mode="before")
    @classmethod
    def _keys(cls, value: Any) -> Any:
        return tuple(readable_list(LootBoxKeys, value, accept=_is_object))

    def amount(self, loot_box_id: LootBox | int) -> int | float:
        """How many of a loot box you hold."""
        return sum(entry.amount for entry in self.loot_boxes if entry.loot_box_id == loot_box_id)

    def keys(self, loot_box_type_id: LootBoxType | int) -> int | float:
        """The keys collected towards a loot box type, 0 when none is known."""
        return next((entry.keys for entry in self.key_progress if entry.loot_box_type_id == loot_box_type_id), 0)


class OpenLootBoxRequest(BaseRequest):
    """
    Open a loot box with a mystery box key.

    Command: ole
    Payload: {"LID": loot_box_id, "CID": key, "ALL": 1 or 0}

    The reward hub opens one box with any key held, the common key always, and every box of the kind
    with the common key only.

    Client: ``C2SOpenLootBoxVO`` (bundle line 112368), ``RewardHubDialogMysteryBoxItem.fillItem`` and
    ``onClick`` (bundle lines 92191, 92198)
    """

    command = "ole"

    loot_box_id: EnumOrInt["LootBox"] = Field(validation_alias="LID", description="The loot box to open")
    key: EnumOrInt[MysteryBoxKey] = Field(
        validation_alias="CID", default=MysteryBoxKey.COMMON, description="The key to open it with"
    )
    open_all: bool = Field(
        validation_alias="ALL", default=False, description="Open every box of the kind; sent as 1 or 0"
    )

    @field_serializer("open_all")
    def _flag(self, value: bool) -> int:
        return 1 if value else 0


def _reward_rows(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(row, list) for row in value)


class OpenLootBoxResponse(BaseResponse):
    """
    What opening a loot box gave.

    Command: ole
    Payload: {"LID": .., "LTR": rewards, "LTRR": rewards?, "KBS": key progress, "TBF": key bar fills,
              "KTR": [{"ID": key, "AMT": amount}, ..], "UKI": key used}

    The client reads ``LTRR`` over ``LTR`` when it is set, both as collectable rows, yet also hands
    ``LTR`` to the opening dialog as reward ids, which ``getHighestCategoryForRewards`` compares with
    the tombola's reward ids (bundle line 112417). Which shape the server sends is not confirmed:
    rows are read into ``rewards``, a list of ids into ``reward_ids``, and ``raw_rewards`` keeps
    ``LTR`` as sent.

    The client sets the box type's key progress to ``KBS``; it does not lower the box count, which
    the server's next ``gls`` brings.

    Client: ``OLECommand.executeCommand`` (bundle line 124819)
    """

    command = "ole"

    loot_box_id: EnumOrInt["LootBox"] = Field(validation_alias="LID", default=0, description="The loot box opened")
    rewards: tuple[Collectable, ...] = Field(default=(), description="What the boxes gave, the keys won aside")
    reward_ids: tuple[RewardId, ...] = Field(
        default=(), description="The rewards drawn, when LTR lists reward ids instead of rows"
    )
    raw_rewards: Any = Field(validation_alias="LTR", default=None, description="LTR as the server sent it")
    key_progress: ClientNumber = Field(
        validation_alias="KBS", default=0, description="The keys now collected towards the box's type"
    )
    key_bar_fills: ClientNumber = Field(
        validation_alias="TBF", default=0, description="How often the key bar filled up"
    )
    keys_won: tuple[Collectable, ...] = Field(validation_alias="KTR", default=(), description="The keys won")
    key_used: EnumOrInt[MysteryBoxKey] | None = Field(
        validation_alias="UKI", default=None, description="The key the boxes were opened with"
    )

    @model_validator(mode="before")
    @classmethod
    def _read_rewards(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        rows = data.get("LTRR") if js_truthy(data.get("LTRR")) else data.get("LTR")
        listed = data.get("LTR")
        ids = (
            [RewardId(entry) for entry in listed if isinstance(entry, int) and not isinstance(entry, bool)]
            if isinstance(listed, list) and not _reward_rows(listed)
            else []
        )
        return {**data, "rewards": Collectable.from_rows(rows) if _reward_rows(rows) else (), "reward_ids": ids}

    @field_validator("keys_won", mode="before")
    @classmethod
    def _keys(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return ()
        return tuple(
            Collectable.of_currency(entry["ID"], entry.get("AMT", 0))
            for entry in value
            if isinstance(entry, dict) and isinstance(entry.get("ID"), int)
        )


__all__ = [
    "LootBoxAmount",
    "LootBoxKeys",
    "LootBoxesResponse",
    "OpenLootBoxRequest",
    "OpenLootBoxResponse",
]
