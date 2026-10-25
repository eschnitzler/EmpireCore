"""
The mercenary camp's missions.

Commands:
- mpe: the mercenary missions, a login section of ``gbd`` and a reply; also the request that lists,
  starts and collects them
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from empire_core.enums import MercenaryMissionRarity, MercenaryMissionState
from empire_core.gamedata import CollectableRows, EnumOrInt
from empire_core.protocol.base import BaseRequest, BaseResponse, TimedPayload, TimedResponse, readable_list
from empire_core.protocol.js import ClientInt, ClientNumber, js_truthy

NEXT_MISSIONS_DELAY = 1
"""``CastleMercenaryData.NEXT_MISSIONS_TIMER_DELAY`` (bundle line 28881): seconds the client waits past ``NM``"""


def _is_object(entry: Any) -> bool:
    return isinstance(entry, dict)


class MercenaryMission(TimedPayload):
    """
    One mercenary mission, an entry of an ``mpe``'s ``M``.

    Client: ``CastleMercenaryMissionItemVO.fillFromParamObject`` and ``remainingTime`` (bundle lines 81134-81135)
    """

    mission_id: ClientInt = Field(validation_alias="ID", default=0, description="The mission's id")
    rewards: CollectableRows = Field(validation_alias="R", default=(), description="The rewards")
    duration_seconds: ClientNumber = Field(validation_alias="D", default=0, description="How long the mission takes")
    price: ClientNumber = Field(validation_alias="P", default=0, description="What starting the mission costs in coins")
    quality: EnumOrInt[MercenaryMissionRarity] = Field(
        validation_alias="Q",
        default=MercenaryMissionRarity.FREE,
        description="The mission's rarity",
    )
    state: EnumOrInt[MercenaryMissionState] = Field(
        validation_alias="S",
        default=MercenaryMissionState.OPEN,
        description="Where the mission stood when the values were read",
    )
    seconds: ClientNumber = Field(
        validation_alias="RD",
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
        default=0,
        description="Seconds until new missions come when the values were read",
    )
    missions: tuple[MercenaryMission, ...] = Field(
        validation_alias="M", default=(), description="The missions not collected"
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
    line 87459); ``client.castle.start_mission`` and ``collect_mission`` send it only for the first two.

    Client: ``C2SMercenaryPackageVO`` (bundle line 28889); -1 from ``CastleMercenaryData.onNewMissions``
    and ``CastleMercenaryOverviewDialog.showLoaded`` (bundle lines 28851, 51996), a mission's id from
    ``CastleMercenaryMissionItem.startMissionCallback`` and ``collectMissionRewards`` (bundle lines 87379, 87382)
    """

    command = "mpe"

    mission_id: int = Field(
        validation_alias="MID",
        default=-1,
        description="The mission to start or collect, -1 to list them",
    )


class RefreshMercenaryMissionRequest(BaseRequest):
    """
    Swap an open mercenary mission for another, for ``MercenaryConst.REFRESH_MISSION_COST`` (240) rubies.

    Command: rmm
    Payload: {"MID": mission_id}

    Client: ``C2SRefreshMercenaryMissionVO`` (bundle line 87437), sent by
    ``CastleMercenaryMissionItem.refreshMissionCallback`` (bundle line 87416) after
    ``CastleMercenaryRefreshMissionDialog`` (bundle line 87464); ``REFRESH_MISSION_COST`` (dll line 19511)
    """

    command = "rmm"

    mission_id: int = Field(validation_alias="MID", description="The open mission to swap")


class RefreshMercenaryMissionResponse(BaseResponse):
    """
    The mission was swapped; the client reads nothing from the reply.

    Command: rmm

    Client: ``RMMCommand.executeCommand`` (bundle line 125166)
    """

    command = "rmm"


__all__ = [
    "MercenaryMission",
    "MercenaryMissionsResponse",
    "MercenaryPackageRequest",
    "RefreshMercenaryMissionRequest",
    "RefreshMercenaryMissionResponse",
]
