"""
Ranking protocol models for GGE.

Commands:
- hgh: Get highscore/ranking for a specific entity (search by name/value)
- llsp: Get large list ranking by position (global leaderboard)
- llsw: Get large list ranking by ID (find specific rank)
- slse: Search entity ID (used for season pass etc)
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, List, Optional

from pydantic import Field

from .base import BaseRequest, BaseResponse, GGECommand

logger = logging.getLogger(__name__)


class RankingType:
    """
    Known LT (List Type) values.
    Corresponds to Event IDs or Metric IDs.
    """

    # Core Alliance Metrics
    ALLIANCE_HONOR = 10
    ALLIANCE_MIGHT = 11
    DOMINION_POINTS = 12
    CARGO_POINTS = 13

    # Core Player Metrics
    PLAYER_HONOR = 5
    PLAYER_MIGHT = 6
    LEGEND_LEVEL = 7
    ACHIEVEMENTS = 1

    # Events
    FOREIGN_INVASION = 71
    BLOODCROWS = 72
    SAMURAI = 80
    NOMAD = 85
    BERIMOND = 113
    SHAPESHIFTER = 60
    HORIZON = 134
    OUTER_REALMS = 63  # 601 in some contexts?


class RankingCategory:
    """
    Common LID (List ID) values.
    Corresponds to level brackets or sub-categories.
    """

    LEVEL_70 = 6  # Standard for most events (Level 70 bracket)
    LEGENDARY_TOP = 5  # 950+ usually
    GLOBAL = 1


class RankingEntry:
    """A single entry in a ranking list."""

    def __init__(self, raw: list) -> None:
        """
        Parse ranking entry.
        Format varies by list type:
        - Format A: [Rank, Score, [ID, Name, ...]] - Simple list
        - Format B: [Rank, Score, ID, Name] - Flat format
        - Format C: [Rank, Score, {ComplexDict}] - Full player/alliance data
        """
        self.raw = raw
        self.rank: int = -1
        self.score: int = -1
        self.entity_id: int = 0
        self.name: str = ""
        self.alliance_id: int = 0
        self.alliance_name: str = ""

        try:
            # Format C: [Rank, Score, {ComplexDict}] - Player/Alliance full data
            if len(raw) >= 3 and isinstance(raw[2], dict):
                self.rank = raw[0]
                self.score = raw[1]
                details_dict = raw[2]
                self.entity_id = details_dict.get("OID", 0)  # Player ID
                self.name = details_dict.get("N", "")  # Name
                self.alliance_id = details_dict.get("AID", 0)  # Alliance ID
                self.alliance_name = details_dict.get("AN", "")  # Alliance name

            # Format A: [Rank, Score, [ID, Name, ...]]
            elif len(raw) >= 3 and isinstance(raw[2], list):
                self.rank = raw[0]
                self.score = raw[1]
                details_list = raw[2]
                self.entity_id = details_list[0] if len(details_list) > 0 else 0

                # Handle Name field (index 1) which can be string or list
                if len(details_list) > 1:
                    name_field = details_list[1]
                    if isinstance(name_field, list):
                        self.name = str(name_field[0]) if len(name_field) > 0 else ""
                    else:
                        self.name = str(name_field) if name_field is not None else ""
                else:
                    self.name = ""

            # Format B: [Rank, Score, ID, Name] (Simpler lists)
            elif len(raw) >= 4 and not isinstance(raw[2], list):
                self.rank = raw[0]
                self.score = raw[1]
                self.entity_id = raw[2]
                self.name = raw[3]

            else:
                logger.warning(f"Unknown RankingEntry format: {raw}")

        except Exception as e:
            logger.error(f"Failed to parse RankingEntry: {raw} - Error: {e}")

    def __repr__(self) -> str:
        return f"RankingEntry(rank={self.rank}, name='{self.name}', score={self.score})"


class GetHighscoreRequest(BaseRequest):
    """
    Get specific highscore entry (search).

    Command: hgh
    """

    command: ClassVar[str] = GGECommand.HGH

    list_type: int = Field(alias="LT")
    list_id: Optional[int] = Field(alias="LID", default=None)
    search_value: str = Field(alias="SV")


class GetHighscoreResponse(BaseResponse):
    """
    Response for hgh command.
    """

    command: ClassVar[str] = GGECommand.HGH

    # L: [[Rank, Score, [Details...]], ...]
    raw_list: List[Any] = Field(alias="L", default_factory=list)

    @property
    def entries(self) -> List[RankingEntry]:
        return [RankingEntry(item) for item in self.raw_list]


class GetRankingListRequest(BaseRequest):
    """
    Get global ranking list by position/rank.

    Command: llsp
    """

    command: ClassVar[str] = "llsp"

    list_type: int = Field(alias="LT")
    list_id: Optional[int] = Field(alias="LID", default=None)
    rank: int = Field(alias="R")  # Start rank?


class GetRankingListResponse(BaseResponse):
    """
    Response for llsp command.
    """

    command: ClassVar[str] = "llsp"

    # L: List of entries
    raw_list: List[Any] = Field(alias="L", default_factory=list)
    total: int = Field(alias="T", default=0)  # Total count?

    @property
    def entries(self) -> List[RankingEntry]:
        return [RankingEntry(item) for item in self.raw_list]
