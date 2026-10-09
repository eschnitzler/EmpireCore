"""
Loot boxes and mercenary missions, as the login data and their pushes send them.

Commands:
- gls: your loot boxes and key progress, a push before and a section of ``gbd``
- mpe: the mercenary missions, a login section of ``gbd`` and a reply; also the request that lists,
  starts and collects them
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import ConfigDict, Field, field_validator

from empire_core.enums import MercenaryMissionRarity, MercenaryMissionState
from empire_core.gamedata import CollectableRows, EnumOrInt
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    TimedPayload,
    TimedResponse,
    readable_list,
)
from empire_core.protocol.js import ClientInt, ClientNumber, js_truthy

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

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    loot_box_id: EnumOrInt["LootBox"] = Field(
        validation_alias="ID", serialization_alias="ID", default=0, description="The loot box"
    )
    amount: ClientNumber = Field(
        validation_alias="AMT", serialization_alias="AMT", default=0, description="How many you hold"
    )


class LootBoxKeys(BasePayload):
    """
    The keys collected towards one loot box type: ``{"ID": loot box type, "AMT": keys}``.

    Client: ``CastleLootboxData.parse_GLS`` and ``setKeyProgress`` (bundle lines 112332, 112343)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    loot_box_type_id: EnumOrInt["LootBoxType"] = Field(
        validation_alias="ID", serialization_alias="ID", default=0, description="The loot box type"
    )
    keys: ClientNumber = Field(
        validation_alias="AMT", serialization_alias="AMT", default=0, description="The keys collected"
    )


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
        validation_alias="ALL", serialization_alias="ALL", default=(), description="The loot boxes you hold"
    )
    key_progress: tuple[LootBoxKeys, ...] = Field(
        validation_alias="KEY",
        serialization_alias="KEY",
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


class MercenaryMission(TimedPayload):
    """
    One mercenary mission, an entry of an ``mpe``'s ``M``.

    Client: ``CastleMercenaryMissionItemVO.fillFromParamObject`` and ``remainingTime`` (bundle lines 81134-81135)
    """

    mission_id: ClientInt = Field(
        validation_alias="ID", serialization_alias="ID", default=0, description="The mission's id"
    )
    rewards: CollectableRows = Field(
        validation_alias="R", serialization_alias="R", default=(), description="The rewards"
    )
    duration_seconds: ClientNumber = Field(
        validation_alias="D", serialization_alias="D", default=0, description="How long the mission takes"
    )
    price: ClientNumber = Field(
        validation_alias="P", serialization_alias="P", default=0, description="What starting the mission costs in coins"
    )
    quality: EnumOrInt[MercenaryMissionRarity] = Field(
        validation_alias="Q",
        serialization_alias="Q",
        default=MercenaryMissionRarity.FREE,
        description="The mission's rarity",
    )
    state: EnumOrInt[MercenaryMissionState] = Field(
        validation_alias="S",
        serialization_alias="S",
        default=MercenaryMissionState.OPEN,
        description="Where the mission stood when the values were read",
    )
    seconds: ClientNumber = Field(
        validation_alias="RD",
        serialization_alias="RD",
        default=0,
        description="Seconds the running mission still takes when the values were read",
    )

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds the mission still takes, 0 at least."""
        return max(0.0, -self.seconds_past_end(now)) if js_truthy(self.seconds) else 0.0

    def seconds_past_end(self, now: float | None = None) -> float:
        """
        Seconds since the mission's time ran out, below 0 while it still runs.

        Client: ``CastleMercenaryMissionItemVO.remainingTime`` (bundle line 81135), negated and not clamped
        """
        return self._elapsed(now) - self.seconds

    def current_state(self, now: float | None = None) -> MercenaryMissionState | int:
        """
        Where the mission stands now: a started mission whose time has run out is collectable.

        Client: ``CastleMercenaryData.parse_MPE`` and ``onMissionFinished`` (bundle lines 28829-28830, 28850)
        """
        if self.state == MercenaryMissionState.STARTED and self.remaining_seconds(now) <= 0:
            return MercenaryMissionState.COLLECTABLE
        return self.state


class MercenaryMissionsResponse(TimedResponse):
    """
    The mercenary camp's missions and when new ones come.

    Command: mpe, as a login section of ``gbd`` and a reply.

    Client: ``MPECommand`` (bundle line 125109), ``CastleMercenaryData.parse_MPE`` (bundle line 28824),
    which drops collected missions (state 3 and up)
    """

    command = "mpe"

    next_missions_seconds: ClientNumber = Field(
        validation_alias="NM",
        serialization_alias="NM",
        default=0,
        description="Seconds until new missions come when the values were read",
    )
    missions: tuple[MercenaryMission, ...] = Field(
        validation_alias="M", serialization_alias="M", default=(), description="The missions not collected"
    )

    @field_validator("missions", mode="before")
    @classmethod
    def _missions(cls, value: Any) -> Any:
        missions = readable_list(MercenaryMission, value, accept=_is_object)
        return tuple(mission for mission in missions if mission.state < MercenaryMissionState.COLLECTED)

    def remaining_next_missions_seconds(self, now: float | None = None) -> float:
        """Seconds until the client asks for new missions, 0 at least."""
        return max(0.0, self.next_missions_seconds + NEXT_MISSIONS_DELAY - self._elapsed(now))

    def get_mission(self, mission_id: int) -> MercenaryMission | None:
        """The mission with this id; None when the reply does not list it."""
        return next((mission for mission in self.missions if mission.mission_id == mission_id), None)

    def current_mission_state(self, now: float | None = None) -> MercenaryMissionState | int:
        """
        The furthest any mission stands now: ``OPEN`` while none runs or waits to be collected.

        Client: ``CastleMercenaryData.currentMissionState`` (bundle line 28853), the highest state
        ``parse_MPE`` read (bundle line 28829), collectable once ``onMissionFinished`` fired (bundle line 28850)
        """
        return max((mission.current_state(now) for mission in self.missions), default=MercenaryMissionState.OPEN)


class MercenaryPackageRequest(BaseRequest):
    """
    List the mercenary missions, or start or collect one.

    Command: mpe
    Payload: {"MID": mission_id}

    ``MID`` -1 lists the missions. A mission's id starts an open mission, collects a collectable one, and
    finishes a running one at once for rubies (``CastleMercenarySkipMissionDialog.confirmSkip``, bundle
    line 87459); ``client.player.start_mission`` and ``collect_mission`` send it only for the first two.

    Client: ``C2SMercenaryPackageVO`` (bundle line 28889); -1 from ``CastleMercenaryData.onNewMissions``
    and ``CastleMercenaryOverviewDialog.showLoaded`` (bundle lines 28851, 51996), a mission's id from
    ``CastleMercenaryMissionItem.startMissionCallback`` and ``collectMissionRewards`` (bundle lines 87379, 87382)
    """

    command = "mpe"

    mission_id: int = Field(
        validation_alias="MID",
        serialization_alias="MID",
        default=-1,
        description="The mission to start or collect, -1 to list them",
    )


__all__ = [
    "LootBoxAmount",
    "LootBoxKeys",
    "LootBoxesResponse",
    "MercenaryMission",
    "MercenaryMissionsResponse",
    "MercenaryPackageRequest",
]
