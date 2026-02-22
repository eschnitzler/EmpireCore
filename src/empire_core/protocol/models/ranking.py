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
        self.raw = raw
        self.rank: int = -1
        self.score: int = -1
        self.entity_id: int = 0
        self.name: str = ""
        self.alliance_id: int = 0
        self.alliance_name: str = ""

        try:
            # Some list types prepend an extra value before [Rank, Score, details].
            # Cargo (LT=13) uses offset=1: [cargoValue, Rank, Score, {details}].
            # Detect by checking whether raw[3] is the complex field while raw[2] is not.
            o = (
                1
                if (len(raw) >= 4 and isinstance(raw[3], (dict, list)) and not isinstance(raw[2], (dict, list)))
                else 0
            )

            details = raw[o + 2] if len(raw) >= o + 3 else None

            if isinstance(details, dict):
                self.rank = raw[o]
                self.score = raw[o + 1]
                self.entity_id = details.get("OID", 0)
                self.name = details.get("N", "")
                self.alliance_id = details.get("AID", 0)
                self.alliance_name = details.get("AN", "")

            elif isinstance(details, list):
                self.rank = raw[o]
                self.score = raw[o + 1]
                self.entity_id = details[0] if len(details) > 0 else 0
                if len(details) > 1:
                    name_field = details[1]
                    if isinstance(name_field, list):
                        self.name = str(name_field[0]) if len(name_field) > 0 else ""
                    else:
                        self.name = str(name_field) if name_field is not None else ""

            elif len(raw) >= o + 4:
                self.rank = raw[o]
                self.score = raw[o + 1]
                self.entity_id = raw[o + 2]
                self.name = str(raw[o + 3]) if raw[o + 3] is not None else ""

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
