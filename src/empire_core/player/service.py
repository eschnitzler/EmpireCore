"""
Other players' details, player search, and starting your research.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from empire_core.enums import CollectableKind
from empire_core.exceptions import CommandError, EmpireTimeoutError, GameDataNotLoadedError, PacketError
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
    Other players' details, finding a player by name, and starting your research.

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

    def start_research(self, research: Research | int, *, spend_rubies: bool = False, timeout: float = 5.0) -> bool:
        """
        Start a research, paying what it costs.

        Missing resources are never paid with rubies: the request sends ``PWR`` 0, as the research
        dialog does. Some researches cost rubies themselves (``ResearchDef.cost_rubies``), and the
        client sends the same request for them; this method refuses those unless ``spend_rubies`` is
        True. Other costs, legendary tokens included, are a normal game currency and are paid. The
        reply's research reaches ``client.state.get_research()``.

        Args:
            research: The research to start
            spend_rubies: Allow a research that costs rubies, on either kind of server
            timeout: Timeout in seconds

        Raises:
            GameDataNotLoadedError: ``client.load_game_data()`` has not been called
            ValueError: The game data has no such research, or it costs rubies and ``spend_rubies`` is False

        Client: ``ResearchInfo.buyResearch`` (bundle line 79704) sends ``C2SResearchStartVO`` whatever the
        costs; ``updateBuyArea`` shows the ruby overlay when ``getFinalCosts`` holds rubies (bundle lines
        79679-79680), and ``AResearchVO.getBaseCosts`` takes the temporary server's costs there (bundle
        line 61530); ``RESCommand`` (bundle line 126872)
        """
        game_data = self.client.game_data
        if game_data is None:
            raise GameDataNotLoadedError("Starting research needs the items payload: call load_game_data() first")
        row = game_data.researches.get(research)
        if row is None:
            raise ValueError(f"the game data has no research {research!r}")
        costs = (*row.costs, *row.temp_server_costs)
        rubies = max((cost.amount for cost in costs if cost.kind is CollectableKind.RUBIES), default=0)
        if rubies > 0 and not spend_rubies:
            raise ValueError(f"research {research!r} costs {rubies} rubies; pass spend_rubies=True")
        return self.execute(StartResearchRequest(research_id=research), timeout=timeout)

    def skip_research(self, minute_skip: Currency | str, timeout: float = 5.0) -> bool:
        """
        Shorten the running research with a minute skip from your inventory.

        The reply's research reaches ``client.state.get_research()``.

        Args:
            minute_skip: The minute skip to use, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``;
                its key (``"MS1"``) also works, for a skip newer than the generated enum
            timeout: Timeout in seconds

        Raises:
            ValueError: ``minute_skip`` is no minute skip, or the special currencies hold none of it

        Client: ``ResearchMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 79784),
        ``CastleMinuteSkipDialog.showLoaded`` (bundle line 7671), ``MSRCommand`` (bundle line 125825)
        """
        self._require_minute_skip(minute_skip)
        return self.execute(SkipResearchRequest(minute_skip=minute_skip), timeout=timeout)


__all__ = ["PlayerDetailsBulkResult", "PlayerService"]
