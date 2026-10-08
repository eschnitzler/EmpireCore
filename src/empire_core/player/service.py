"""
Other players' details, player search, your research and the mercenary camp.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from empire_core.enums import MercenaryMissionState
from empire_core.exceptions import CommandError, EmpireTimeoutError, PacketError
from empire_core.player.models.economy import MercenaryMission, MercenaryMissionsResponse, MercenaryPackageRequest
from empire_core.player.models.info import (
    GetPlayerInfoRequest,
    GetPlayerInfoResponse,
    SearchPlayerRequest,
    SearchPlayerResponse,
)
from empire_core.player.models.research import SkipResearchRequest, StartResearchRequest
from empire_core.services.base import BaseService

if TYPE_CHECKING:
    from empire_core.gamedata import Currency, Research


@dataclass
class PlayerDetailsBulkResult:
    """What :meth:`PlayerService.get_player_details_bulk` got for each player."""

    found: dict[int, GetPlayerInfoResponse] = field(default_factory=dict)
    """The replies, by player id."""
    failed: dict[int, CommandError | PacketError] = field(default_factory=dict)
    """Players whose request the server refused, or whose reply could not be read."""
    timed_out: list[int] = field(default_factory=list)
    """Players whose reply did not come in time."""

    @property
    def complete(self) -> bool:
        """Whether every player was found."""
        return not self.failed and not self.timed_out


class PlayerService(BaseService):
    """
    Other players' details, finding a player by name, your research and the mercenary camp's missions.

    Reached as client.player.
    """

    def get_player_info(self, player_id: int, timeout: float = 5.0) -> GetPlayerInfoResponse:
        """
        Get detailed player information (gdi), including castle list with
        capture info.

        Args:
            player_id: A player's id: ``search_player_by_name(name).get_player().owner_id``,
                an owner record's ``MapObject.owner_id`` from a map scan, or an
                ``AllianceMember.player_id`` from ``client.alliance.get_members()``
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(GetPlayerInfoRequest(player_id=player_id), GetPlayerInfoResponse, timeout=timeout)

    def get_player_details(
        self,
        player_id: int,
        timeout: float = 5.0,
    ) -> GetPlayerInfoResponse:
        """Alias for :meth:`get_player_info` (both use the 'gdi' command)."""
        return self.get_player_info(player_id, timeout=timeout)

    def get_player_details_bulk(
        self,
        player_ids: list[int],
        timeout: float = 5.0,
        send_delay: float = 0.0,
    ) -> PlayerDetailsBulkResult:
        """
        Get detailed info for several players, one gdi request after another.

        Each request waits for its own reply before the next goes out: a gdi
        error reply names no player, so only one request in flight at a time
        tells which player it belongs to. Each runs as :meth:`get_player_info`
        does, under the gdi command lock and taking only a reply whose
        ``O.OID`` is the player asked for.

        Args:
            player_ids: Player ids to fetch, found as for :meth:`get_player_info`; repeats are fetched once
            timeout: Seconds to wait for each reply
            send_delay: Seconds to wait between two requests; by default none, as
                each already waits for the one before it to be answered

        Returns:
            Which players were found, which failed and why, and which timed out

        Raises:
            ConnectionClosedError / NetworkError: the connection failed; the players fetched so far are lost
            ReceiveThreadError: called on the receive thread
        """
        result = PlayerDetailsBulkResult()
        for index, pid in enumerate(dict.fromkeys(player_ids)):
            if index and send_delay > 0:
                time.sleep(send_delay)
            try:
                response = self.get_player_info(pid, timeout=timeout)
            except EmpireTimeoutError:
                result.timed_out.append(pid)
                continue
            except (CommandError, PacketError) as e:
                result.failed[pid] = e
                continue
            result.found[pid] = response
        return result

    def search_player_by_name(
        self,
        player_name: str,
        timeout: float = 5.0,
    ) -> SearchPlayerResponse:
        return self.request(SearchPlayerRequest(player_name=player_name), SearchPlayerResponse, timeout=timeout)

    # =========================================================================
    # Research
    # =========================================================================

    def start_research(self, research: Research | int, timeout: float = 5.0) -> bool:
        """
        Start a research, paying its costs from your resources.

        Missing resources are never paid with rubies: the request sends ``PWR`` 0, as the research
        dialog does. The reply's research reaches ``client.state.get_research()``.

        Args:
            research: The research to start
            timeout: Timeout in seconds

        Client: ``ResearchInfo.buyResearch`` (bundle line 79704), ``RESCommand`` (bundle line 126872)
        """
        return self.execute(StartResearchRequest(research_id=research), timeout=timeout)

    def skip_research(self, minute_skip: Currency | str, timeout: float = 5.0) -> bool:
        """
        Shorten the running research with a minute skip from your inventory.

        The reply's research reaches ``client.state.get_research()``.

        Args:
            minute_skip: The minute skip to use, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``;
                its key (``"MS1"``) also works, for a skip newer than the generated enum
            timeout: Timeout in seconds

        Client: ``ResearchMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 79784),
        ``MSRCommand`` (bundle line 125825)
        """
        return self.execute(SkipResearchRequest(minute_skip=minute_skip), timeout=timeout)

    # =========================================================================
    # Mercenary camp
    # =========================================================================

    def list_missions(self, timeout: float = 5.0) -> MercenaryMissionsResponse:
        """
        The mercenary camp's missions, and when new ones come.

        Sends ``mpe`` with ``MID`` -1, as the client does when it opens the camp and when new missions
        are due; the reply also reaches ``client.state.get_mercenary_missions()``.

        Client: ``CastleMercenaryOverviewDialog.showLoaded`` and ``CastleMercenaryData.onNewMissions``
        (bundle lines 51996, 28851)
        """
        return self.request(MercenaryPackageRequest(), MercenaryMissionsResponse, timeout=timeout)

    def start_mission(self, mission_id: int, timeout: float = 5.0) -> bool:
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
        return self.execute(MercenaryPackageRequest(mission_id=mission_id), timeout=timeout)

    def collect_mission(self, mission_id: int, timeout: float = 5.0) -> bool:
        """
        Collect a finished mercenary mission's rewards.

        Lists the missions first and sends the collect only for a mission whose time has run out, so
        a running mission is never finished at once for rubies.

        Args:
            mission_id: A ``MercenaryMission.mission_id`` from :meth:`list_missions`
            timeout: Timeout in seconds, for each request

        Raises:
            ValueError: The missions list no such mission, or it is not collectable

        Client: ``CastleMercenaryMissionItem.showCollectButton`` and ``collectMissionRewards``
        (bundle lines 87365, 87382)
        """
        mission = self._mission(self.list_missions(timeout=timeout), mission_id)
        if mission.current_state() != MercenaryMissionState.COLLECTABLE:
            raise ValueError(f"mercenary mission {mission_id} is not collectable")
        return self.execute(MercenaryPackageRequest(mission_id=mission_id), timeout=timeout)

    @staticmethod
    def _mission(missions: MercenaryMissionsResponse, mission_id: int) -> MercenaryMission:
        mission = missions.get_mission(mission_id)
        if mission is None:
            raise ValueError(f"no mercenary mission {mission_id}")
        return mission


__all__ = ["PlayerDetailsBulkResult", "PlayerService"]
