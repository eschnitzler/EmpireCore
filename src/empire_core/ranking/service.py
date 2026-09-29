"""
Ranking service for GGE.
"""

import logging

from empire_core.enums import RankingType
from empire_core.services.base import BaseService, register_service

from .models import (
    GetHighscoreRequest,
    GetHighscoreResponse,
    GetRankingListRequest,
    GetRankingListResponse,
    RankingEntry,
)

logger = logging.getLogger(__name__)


@register_service("ranking")
class RankingService(BaseService):
    """
    Service for fetching rankings and highscores.
    """

    def get_highscore(
        self,
        list_type: RankingType,
        search_value: str,
        league_type_id: int = -1,
        timeout: float = 5.0,
    ) -> list[RankingEntry]:
        """
        Search for a highscore entry (e.g. player rank).

        Args:
            list_type: The highscore list (LT)
            search_value: Name to search for, a rank as text, or "-1" for your own rank
            league_type_id: League type id (LID); -1 for none, the client default
            timeout: Timeout in seconds

        Returns:
            List of matching entries

        Note: 'hgh' is shared with the alliance-search command, so a
        concurrent search_alliances() call can receive this response (and
        vice versa) — the protocol offers no way to correlate them.
        """
        request = GetHighscoreRequest(LT=list_type, LID=league_type_id, SV=search_value)
        return self.request(request, GetHighscoreResponse, timeout=timeout).entries

    def get_ranking_list(
        self,
        list_type: RankingType,
        rank: int,
        max_results: int,
        league_type_id: int = -1,
        timeout: float = 5.0,
    ) -> list[RankingEntry]:
        """
        Get a page of an event leaderboard, from a rank.

        Only works while the list's event runs: the client sends llsp only
        from event leaderboards, and a live server answered NO_EVENT (145)
        for every list with no event running, the regular highscore lists
        included (use :meth:`get_highscore` for those).

        Args:
            list_type: The event's highscore list (LT), e.g. ``RankingType.LONG_TERM_POINT_EVENT``
            rank: The first rank on the page
            max_results: Entries per page (M)
            league_type_id: The running event's league (LID), as the client passes it; -1 for none
            timeout: Timeout in seconds

        Returns:
            List of entries from that rank

        Raises:
            CommandError: NO_EVENT (145) when the list's event is not running

        Client: ``LeaderBoardDataProvider`` (bundle line 75933), built only by
        ``GlobalLeaderBoardComponent.init`` (bundle line 34989) for event leaderboard dialogs
        """
        request = GetRankingListRequest(LT=list_type, LID=league_type_id, M=max_results, R=rank)
        return self.request(request, GetRankingListResponse, timeout=timeout).entries
