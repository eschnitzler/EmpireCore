"""The mercenary camp's missions."""

from __future__ import annotations

from empire_core.castle.models.mercenaries import (
    MercenaryMission,
    MercenaryMissionsResponse,
    MercenaryPackageRequest,
    RefreshMercenaryMissionRequest,
)
from empire_core.enums import MercenaryMissionState
from empire_core.protocol.js import js_truthy
from empire_core.services.base import ServiceMixin

# MercenaryConst.REFRESH_MISSION_COST (dll line 19511)
_REFRESH_MISSION_RUBIES = 240

# a started mission's RD is rounded, and a collect sent while time remains is a ruby skip
_COLLECT_MARGIN_SECONDS = 2


class MercenaryCampMixin(ServiceMixin):
    # =========================================================================
    # Mercenary camp
    # =========================================================================

    def list_missions(self, *, timeout: float = 5.0) -> MercenaryMissionsResponse:
        """
        The mercenary camp's missions, and when new ones come.

        Sends ``mpe`` with ``MID`` -1, as the client does when it opens the camp and when new missions
        are due; the reply also reaches ``client.state.get_mercenary_missions()``.

        Client: ``CastleMercenaryOverviewDialog.showLoaded`` and ``CastleMercenaryData.onNewMissions``
        (bundle lines 51996, 28851)
        """
        return self.request(MercenaryPackageRequest(), MercenaryMissionsResponse, timeout=timeout)

    def start_mission(self, mission_id: int, *, timeout: float = 5.0) -> None:
        """
        Start an open mercenary mission, paying its price in coins.

        Lists the missions first and decides from that reply, as the client decides from its mission
        state: only an open mission starts, and only while no mission runs or waits to be collected.
        While one runs the client would first finish it for rubies; that is left out.

        Args:
            mission_id: A ``MercenaryMission.mission_id`` from :meth:`list_missions`
            timeout: Timeout in seconds, for each request

        Raises:
            ValueError: The missions list no such mission, it is not open, or another mission runs
                or waits to be collected

        Client: ``CastleMercenaryMissionItem.startMission``, ``showStartAndRefreshButton`` and
        ``startMissionCallback`` (bundle lines 87377, 87361, 87379)
        """
        missions = self.list_missions(timeout=timeout)
        mission = self._mission(missions, mission_id)
        if mission.current_state() != MercenaryMissionState.OPEN:
            raise ValueError(f"mercenary mission {mission_id} is not open")
        if missions.current_mission_state() != MercenaryMissionState.OPEN:
            raise ValueError("another mercenary mission runs or waits to be collected")
        self.execute(MercenaryPackageRequest(mission_id=mission_id), timeout=timeout)

    def collect_mission(self, mission_id: int, *, timeout: float = 5.0) -> None:
        """
        Collect a finished mercenary mission's rewards.

        The collect is the same ``mpe`` as the ruby skip of a running mission, which costs
        ``ceil(remaining seconds / 60 * 5)`` rubies. So this lists the missions first and sends the
        collect only for one the server lists as collectable, as started with no ``RD`` (finished for
        the client, and a skip of it would cost 0 rubies), or as started with its time run out at
        least two seconds ago, since ``RD`` is rounded. A started mission whose ``RD`` still counts
        down is refused. Another session can still change the mission between the list and the
        send; that window is not closed.

        Args:
            mission_id: A ``MercenaryMission.mission_id`` from :meth:`list_missions`
            timeout: Timeout in seconds, for each request

        Raises:
            ValueError: The missions list no such mission, or it is not collectable by that rule

        Client: ``CastleMercenaryMissionItem.showCollectButton`` and ``collectMissionRewards``
        (bundle lines 87365, 87382); ``CastleMercenaryMissionItemVO.fillFromParamObject`` sets no end
        time without ``RD`` (bundle line 81134); ``CastleMercenarySkipMissionDialog.confirmSkip`` (bundle
        line 87459) sends the same id, ``MercenaryConst.getSkipC2Cost`` (dll line 19508)
        """
        mission = self._mission(self.list_missions(timeout=timeout), mission_id)
        finished = mission.state == MercenaryMissionState.STARTED and (
            not js_truthy(mission.seconds) or mission.seconds_past_end() >= _COLLECT_MARGIN_SECONDS
        )
        if mission.state != MercenaryMissionState.COLLECTABLE and not finished:
            raise ValueError(f"mercenary mission {mission_id} is not collectable")
        self.execute(MercenaryPackageRequest(mission_id=mission_id), timeout=timeout)

    def refresh_mission(self, mission_id: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Swap an open mercenary mission for another, for ``REFRESH_MISSION_COST`` (240) rubies; see
        "Spending rubies" in the guides.

        Lists the missions first and decides from that reply, as the client decides from its mission
        state: only an open mission is swapped, and only while no mission waits to be collected.

        Args:
            mission_id: A ``MercenaryMission.mission_id`` from :meth:`list_missions`
            spend_rubies: Allow the rubies it costs; without it nothing is sent
            timeout: Timeout in seconds, for each request

        Raises:
            ValueError: ``spend_rubies`` is False, the missions list no such mission, it is not open, or a
                mission waits to be collected

        Client: ``CastleMercenaryMissionItem.updateButtons`` and ``showStartAndRefreshButton`` (bundle lines
        87390, 87396), ``refreshMissionCallback`` (bundle line 87416); ``RMMCommand.executeCommand`` (bundle
        line 125166); ``MercenaryConst.REFRESH_MISSION_COST`` (dll line 19511)
        """
        self._require_spend_rubies(spend_rubies, f"refreshing a mission costs {_REFRESH_MISSION_RUBIES} rubies")
        missions = self.list_missions(timeout=timeout)
        mission = self._mission(missions, mission_id)
        if mission.current_state() != MercenaryMissionState.OPEN:
            raise ValueError(f"mercenary mission {mission_id} is not open")
        if missions.current_mission_state() >= MercenaryMissionState.COLLECTABLE:
            raise ValueError("a mercenary mission waits to be collected")
        self.execute(RefreshMercenaryMissionRequest(mission_id=mission_id), timeout=timeout)

    @staticmethod
    def _mission(missions: MercenaryMissionsResponse, mission_id: int) -> MercenaryMission:
        mission = missions.get_mission(mission_id)
        if mission is None:
            raise ValueError(f"no mercenary mission {mission_id}")
        return mission
