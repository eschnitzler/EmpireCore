"""
Loot boxes and mercenary missions, as the login data and their pushes send them.

Commands:
- gls: your loot boxes and key progress, a push before and a section of ``gbd``
- mpe: the mercenary missions, a login section of ``gbd`` and a reply
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict, Field, field_validator

from empire_core.gamedata import CollectableRows, EnumOrInt
from empire_core.protocol.base import BasePayload, BaseResponse, TimedPayload, TimedResponse, readable_list
from empire_core.protocol.js import ClientInt, ClientNumber, js_truthy

MERCENARY_MISSION_COLLECTED = 3
"""``CastleMercenaryData.MISSION_STATE_COLLECTED`` (bundle line 28881): a mission the client drops"""

if TYPE_CHECKING:
    from empire_core.gamedata import LootBox, LootBoxType

NEXT_MISSIONS_DELAY = 1
"""``CastleMercenaryData.NEXT_MISSIONS_TIMER_DELAY`` (bundle line 28881): seconds the client waits past ``NM``"""


def _is_object(entry: Any) -> bool:
    return isinstance(entry, dict)


class LootBoxAmount(BasePayload):
    """
    One kind of loot box you hold: ``{"ID": loot box, "AMT": amount}``.

    Client: ``CastleLootboxData.parse_GLS`` (bundle line 112332) reads each as an ``ACollectableItemLootBoxVO``
    """

    model_config = ConfigDict(frozen=True)

    loot_box_id: EnumOrInt["LootBox"] = Field(alias="ID", default=0, description="The loot box")
    amount: ClientNumber = Field(alias="AMT", default=0, description="How many you hold")


class LootBoxKeys(BasePayload):
    """
    The keys collected towards one loot box type: ``{"ID": loot box type, "AMT": keys}``.

    Client: ``CastleLootboxData.parse_GLS`` and ``setKeyProgress`` (bundle lines 112332, 112343)
    """

    model_config = ConfigDict(frozen=True)

    loot_box_type_id: EnumOrInt["LootBoxType"] = Field(alias="ID", default=0, description="The loot box type")
    keys: ClientNumber = Field(alias="AMT", default=0, description="The keys collected")


class LootBoxesResponse(BaseResponse):
    """
    Your loot boxes, and the keys collected towards each loot box type.

    A ``gls`` lists the loot boxes whole, but key progress only for some types; the client keeps the
    others as they were, and ``client.state.get_loot_boxes()`` does the same.

    Command: gls, a push the server sends before ``gbd`` and again when they change.

    Client: ``GLSCommand`` (bundle line 124800), ``CastleLootboxData.parse_GLS`` (bundle line 112332)
    """

    model_config = ConfigDict(frozen=True)

    command = "gls"

    loot_boxes: tuple[LootBoxAmount, ...] = Field(alias="ALL", default=(), description="The loot boxes you hold")
    key_progress: tuple[LootBoxKeys, ...] = Field(
        alias="KEY", default=(), description="Keys collected per loot box type this packet lists"
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


class MercenaryMission(TimedPayload):
    """
    One mercenary mission, an entry of an ``mpe``'s ``M``.

    Client: ``CastleMercenaryMissionItemVO.fillFromParamObject`` and ``remainingTime`` (bundle lines 81134-81135),
    ``RARITY_FREE`` to ``RARITY_LEGENDARY`` (0 to 4)
    """

    mission_id: ClientInt = Field(alias="ID", default=0, description="The mission's id")
    rewards: CollectableRows = Field(alias="R", default=(), description="The rewards")
    duration_seconds: ClientNumber = Field(alias="D", default=0, description="How long the mission takes")
    price: ClientNumber = Field(alias="P", default=0, description="The mission price, 0 when free")
    quality: ClientInt = Field(alias="Q", default=0, description="The mission's rarity, 0 free to 4 legendary")
    state: ClientInt = Field(alias="S", default=0, description="0 open, 1 running, 2 ready to collect")
    seconds: ClientNumber = Field(
        alias="RD", default=0, description="Seconds the running mission still takes when the values were read"
    )

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds the mission still takes, 0 at least."""
        return max(0.0, self.seconds - self._elapsed(now)) if js_truthy(self.seconds) else 0.0


class MercenaryMissionsResponse(TimedResponse):
    """
    The mercenary camp's missions and when new ones come.

    Command: mpe, as a login section of ``gbd`` and a reply.

    Client: ``MPECommand`` (bundle line 125109), ``CastleMercenaryData.parse_MPE`` (bundle line 28824),
    which drops collected missions (state 3 and up)
    """

    command = "mpe"

    next_missions_seconds: ClientNumber = Field(
        alias="NM", default=0, description="Seconds until new missions come when the values were read"
    )
    missions: tuple[MercenaryMission, ...] = Field(alias="M", default=(), description="The missions not collected")

    @field_validator("missions", mode="before")
    @classmethod
    def _missions(cls, value: Any) -> Any:
        missions = readable_list(MercenaryMission, value, accept=_is_object)
        return tuple(mission for mission in missions if mission.state < MERCENARY_MISSION_COLLECTED)

    def remaining_next_missions_seconds(self, now: float | None = None) -> float:
        """Seconds until the client asks for new missions, 0 at least."""
        return max(0.0, self.next_missions_seconds + NEXT_MISSIONS_DELAY - self._elapsed(now))


__all__ = [
    "LootBoxAmount",
    "LootBoxKeys",
    "LootBoxesResponse",
    "MercenaryMission",
    "MercenaryMissionsResponse",
]
