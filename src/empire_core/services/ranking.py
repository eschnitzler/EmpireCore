"""
Ranking service for GGE.
"""

import logging
from typing import List, Optional

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
        list_id: Optional[int] = None,
    ) -> Optional[List[RankingEntry]]:
        """
        Search for a highscore entry (e.g. player rank).

        Args:
            list_type: RankingType (LT)
            search_value: Name to search for
            list_id: Optional RankingCategory (LID)

        Returns:
            List of matching entries or None if failed
        """
        logger.debug(f"HGH Request: LT={list_type}, LID={list_id}, SV='{search_value}'")
        request = GetHighscoreRequest(
            LT=list_type,
            SV=search_value,
            LID=list_id,
        )
        response = self.send(request, wait=True)

        if not response:
            logger.warning("HGH Response: No response received")
            return None

        if isinstance(response, GetHighscoreResponse):
            logger.debug(f"HGH Response Payload: {response.raw_list}")
            return response.entries

        logger.warning(f"HGH Unexpected Response type: {type(response)}")
        return None

    def get_ranking_list(
        self,
        list_type: int,
        rank: int,
        list_id: Optional[int] = None,
    ) -> Optional[List[RankingEntry]]:
        """
        Get ranking list by position.

        Args:
            list_type: RankingType (LT)
            rank: Starting rank/position
            list_id: Optional RankingCategory (LID)

        Returns:
            List of entries around that rank
        """
        logger.debug(f"LLSP Request: LT={list_type}, LID={list_id}, R={rank}")
        request = GetRankingListRequest(
            LT=list_type,
            R=rank,
            LID=list_id,
        )
        response = self.send(request, wait=True)

        if not response:
            logger.warning("LLSP Response: No response received")
            return None

        if isinstance(response, GetRankingListResponse):
            logger.debug(f"LLSP Response Payload: {response.raw_list}")
            return response.entries

        logger.warning(f"LLSP Unexpected Response type: {type(response)}")
        return None
