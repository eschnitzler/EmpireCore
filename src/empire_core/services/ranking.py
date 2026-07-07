"""
Ranking service for GGE.
"""

import logging

from empire_core.protocol.models import (
    GetHighscoreRequest,
    GetHighscoreResponse,
    GetRankingListRequest,
    GetRankingListResponse,
    RankingEntry,
)
from empire_core.services.base import BaseService, register_service

logger = logging.getLogger(__name__)


@register_service("ranking")
class RankingService(BaseService):
    """
    Service for fetching rankings and highscores.
    """

    def get_highscore(
        self,
        list_type: int,
        search_value: str,
        list_id: int | None = None,
        timeout: float = 5.0,
    ) -> list[RankingEntry]:
        """
        Search for a highscore entry (e.g. player rank).

        Args:
            list_type: RankingType (LT)
            search_value: Name to search for
            list_id: Optional RankingCategory (LID)
            timeout: Timeout in seconds

        Returns:
            List of matching entries

        Note: 'hgh' is shared with the alliance-search command, so a
        concurrent search_alliances() call can receive this response (and
        vice versa) — the protocol offers no way to correlate them.
        """
        request = GetHighscoreRequest(
            LT=list_type,
            SV=search_value,
            LID=list_id,
        )
        return self.request(request, GetHighscoreResponse, timeout=timeout).entries

    def get_ranking_list(
        self,
        list_type: int,
        rank: int,
        list_id: int | None = None,
        timeout: float = 5.0,
    ) -> list[RankingEntry]:
        """
        Get ranking list by position.

        Args:
            list_type: RankingType (LT)
            rank: Starting rank/position
            list_id: Optional RankingCategory (LID)
            timeout: Timeout in seconds

        Returns:
            List of entries around that rank
        """
        request = GetRankingListRequest(
            LT=list_type,
            R=rank,
            LID=list_id,
        )
        return self.request(request, GetRankingListResponse, timeout=timeout).entries
