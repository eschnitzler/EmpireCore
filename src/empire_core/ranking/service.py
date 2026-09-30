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
    GetRankingWindowRequest,
    GetRankingWindowResponse,
    LeaderboardSearchResult,
    RankingEntry,
    SearchRankingListRequest,
    SearchRankingListResponse,
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
        sub_division_id: int | None = None,
        event_id: int | None = None,
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
            league_type_id: The event's league (LID), or -1 for none, as the donation ranking sends
            sub_division_id: The alliance event subdivision (SDI), for an alliance event's subdivision ranking
            event_id: The alliance mobilisation or raid event (EID), for those events' rankings
            timeout: Timeout in seconds

        Returns:
            List of entries from that rank

        Raises:
            CommandError: NO_EVENT (145) when the list's event is not running

        Client: ``LeaderBoardDataProvider`` (bundle line 75933), built only by
        ``GlobalLeaderBoardComponent.init`` (bundle line 34989) for event leaderboard dialogs
        """
        request = GetRankingListRequest(
            LT=list_type, LID=league_type_id, M=max_results, R=rank, SDI=sub_division_id, EID=event_id
        )
        return self.request(request, GetRankingListResponse, timeout=timeout).entries

    def get_own_ranking_page(
        self,
        list_type: RankingType,
        max_results: int,
        league_type_id: int = -1,
        sub_division_id: int | None = None,
        event_id: int | None = None,
        timeout: float = 5.0,
    ) -> list[RankingEntry]:
        """
        Get the page of an event leaderboard that holds your own score.

        Args:
            list_type: The event's highscore list (LT)
            max_results: Entries per page (M)
            league_type_id: The event's league (LID), or -1 for none
            sub_division_id: The alliance event subdivision (SDI), as for :meth:`get_ranking_list`
            event_id: The alliance mobilisation or raid event (EID), as for :meth:`get_ranking_list`
            timeout: Timeout in seconds

        Returns:
            The entries on your page

        Client: ``LeaderBoardDataProvider.getCurrentPlayerPage`` (bundle line 75941)
        """
        return self.get_ranking_window(
            list_type,
            score_id="",
            max_results=max_results,
            league_type_id=league_type_id,
            sub_division_id=sub_division_id,
            event_id=event_id,
            timeout=timeout,
        )

    def get_ranking_window(
        self,
        list_type: RankingType,
        score_id: str,
        max_results: int,
        league_type_id: int | None = -1,
        sub_division_id: int | None = None,
        event_id: int | None = None,
        timeout: float = 5.0,
    ) -> list[RankingEntry]:
        """
        Get the page of an event leaderboard around a score, e.g. a search hit.

        Args:
            list_type: The event's highscore list (LT)
            score_id: A score id from :meth:`search_leaderboard` (SI); empty for your own page
            max_results: Entries per page (M)
            league_type_id: The league the score is in (LID), the search result's ``league_type_id``
            sub_division_id: The alliance event subdivision (SDI), as for :meth:`get_ranking_list`
            event_id: The alliance mobilisation or raid event (EID), as for :meth:`get_ranking_list`
            timeout: Timeout in seconds

        Returns:
            The entries on that page

        Client: ``LeaderBoardDataProvider.getCurrentSearchPage`` (bundle line 75943)
        """
        request = GetRankingWindowRequest(
            LT=list_type, LID=league_type_id, M=max_results, SI=score_id, SDI=sub_division_id, EID=event_id
        )
        return self.request(request, GetRankingWindowResponse, timeout=timeout).entries

    def search_leaderboard(
        self,
        list_type: RankingType,
        search_value: str,
        sub_division_id: int | None = None,
        event_id: int | None = None,
        timeout: float = 5.0,
    ) -> list[LeaderboardSearchResult]:
        """
        Search an event leaderboard for a name.

        Page to a hit with :meth:`get_ranking_window`, passing its
        ``league_type_id`` and one of its ``score_ids``; the client pages to
        the first hit, or to your own page when there is none.

        Args:
            list_type: The event's highscore list (LT)
            search_value: The name to search for (SV); must not be empty
            sub_division_id: The alliance event subdivision (SDI), as for :meth:`get_ranking_list`
            event_id: The alliance mobilisation or raid event (EID), as for :meth:`get_ranking_list`
            timeout: Timeout in seconds

        Returns:
            The matching score ids, grouped by league

        Raises:
            ValueError: For an empty search, which the client never sends

        Client: ``LeaderBoardDataProvider.searchLeaderBoard`` (bundle line 75942),
        ``onSearchDataReceived`` (bundle line 75952)
        """
        if not search_value:
            raise ValueError("search_value must not be empty")
        request = SearchRankingListRequest(LT=list_type, SV=search_value, SDI=sub_division_id, EID=event_id)
        return self.request(request, SearchRankingListResponse, timeout=timeout).results
