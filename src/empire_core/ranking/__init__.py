"""Rankings and highscores."""

from typing import TYPE_CHECKING

from empire_core.enums import RankingType
from empire_core.ranking.event_models import (
    ColossusHighscoreRow,
    GetColossusHighscoreRequest,
    GetColossusHighscoreResponse,
    GetSeasonInfoRequest,
    GetSeasonInfoResponse,
    GetSeasonRanksRequest,
    GetSeasonRanksResponse,
    SeasonDivision,
    SeasonHighscoreRank,
    SeasonMedal,
    SeasonPasses,
    SeasonPromotionPass,
    SeasonRank,
)
from empire_core.utils.lazy import lazy_exports

from .models import (
    HIGHSCORE_ROW_LAYOUTS,
    GetHighscoreRequest,
    GetHighscoreResponse,
    GetRankingListRequest,
    GetRankingListResponse,
    GetRankingWindowRequest,
    GetRankingWindowResponse,
    HighscoreAlliance,
    HighscoreAllianceRow,
    HighscoreIslandRow,
    HighscorePlayerRow,
    HighscoreRow,
    HighscoreTournamentRow,
    LeaderboardScore,
    LeaderboardSearchResult,
    LeagueTypeId,
    SearchRankingListRequest,
    SearchRankingListResponse,
)
from .service import RankingService

if TYPE_CHECKING:
    from empire_core.gamedata import (
        Event,
        LeagueType,
    )

__all__ = [
    "ColossusHighscoreRow",
    "GetColossusHighscoreRequest",
    "GetColossusHighscoreResponse",
    "SeasonDivision",
    "SeasonMedal",
    "SeasonPromotionPass",
    "SeasonPasses",
    "SeasonRank",
    "GetSeasonInfoRequest",
    "GetSeasonInfoResponse",
    "SeasonHighscoreRank",
    "GetSeasonRanksRequest",
    "GetSeasonRanksResponse",
    "HIGHSCORE_ROW_LAYOUTS",
    "HighscoreAlliance",
    "HighscoreAllianceRow",
    "HighscoreIslandRow",
    "HighscorePlayerRow",
    "HighscoreRow",
    "HighscoreTournamentRow",
    "GetHighscoreRequest",
    "GetHighscoreResponse",
    "GetRankingListRequest",
    "LeaderboardScore",
    "GetRankingListResponse",
    "GetRankingWindowRequest",
    "GetRankingWindowResponse",
    "SearchRankingListRequest",
    "LeaderboardSearchResult",
    "LeagueTypeId",
    "SearchRankingListResponse",
    "RankingType",
    "RankingService",
    "Event",
    "LeagueType",
]


if not TYPE_CHECKING:
    __getattr__ = lazy_exports(
        __name__,
        "empire_core.gamedata.ids",
        (
            "Event",
            "LeagueType",
        ),
    )
