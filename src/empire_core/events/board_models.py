"""Own-rank and performance reads for event servers."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import Field, field_validator

from empire_core.enums.events import PerformanceStatistic
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, js_int

logger = logging.getLogger(__name__)


class GetHorizonRankRequest(BaseRequest):
    """Client: ``C2SAllianceBattleGroundGetOwnRanksVO`` (bundle lines 71938-71942)."""

    command: ClassVar[str] = "abgph"
    alliance_id: int = Field(validation_alias="AID", description="Your alliance id")


class GetHorizonRankResponse(BaseResponse):
    """Client: ``AllianceBattleGroundEventVO.parseOwnRanks`` (bundle line 114240)."""

    command: ClassVar[str] = "abgph"
    alliance_rank: ClientInt = Field(validation_alias="R", description="Your alliance's rank")


class GetHorizonTimersRequest(BaseRequest):
    """Client: ``C2SAllianceBattleGroundGetTimersVO`` (bundle lines 54330-54334)."""

    command: ClassVar[str] = "trt"


class GetHorizonTimersResponse(BaseResponse):
    """Client: ``CastleAllianceBattleGroundData.parseTRT`` (bundle line 144811).

    Keys: ``CommKeys`` (dll.pretty lines 80880-80881).
    """

    command: ClassVar[str] = "trt"
    relink_seconds: float = Field(validation_alias="STNL", description="Seconds until the next tower relink")
    revive_seconds: float = Field(validation_alias="STNR", description="Seconds until the next tower revival")


class PlayerPerformanceStatistic(BasePayload):
    """Client: ``PlayerPerformanceVO.getPerformanceData`` (bundle lines 27997-28001)."""

    statistic_id: EnumOrInt[PerformanceStatistic] = Field(validation_alias="PSI", description="Performance statistic")
    amount: float = Field(validation_alias="AMT", description="Statistic amount")


class GetPlayerPerformanceRequest(BaseRequest):
    """Client: ``C2SGetPlayerPerformanceVO`` (bundle lines 34268-34272)."""

    command: ClassVar[str] = "gpe"
    player_id: int = Field(validation_alias="PID", description="Player whose performance is requested")
    event_id: int = Field(validation_alias="EID", description="Event whose performance is requested")


class GetPlayerPerformanceResponse(BaseResponse):
    """Client: ``PlayerPerformanceVO.parseData`` and ``getPerformanceData`` (bundle 27996-28001)."""

    command: ClassVar[str] = "gpe"
    points: float = Field(validation_alias="AMT", description="Player's current event points")
    statistics: tuple[PlayerPerformanceStatistic, ...] = Field(
        default=(), validation_alias="PST", description="Player's performance counters"
    )

    @field_validator("statistics", mode="before")
    @classmethod
    def _statistics(cls, value: Any) -> tuple[PlayerPerformanceStatistic, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("Expected player statistics list")
        entries = [{} if entry is None else entry for entry in value]
        return tuple(readable_list(PlayerPerformanceStatistic, entries, warn=logger, what="player statistics"))

    def amount(self, statistic: PerformanceStatistic | int) -> float:
        """The first matching counter, or 0 when the server supplied none, as in the client."""
        return next((item.amount for item in self.statistics if item.statistic_id == statistic), 0)


class GetOuterRealmsRanksRequest(BaseRequest):
    """Client: ``C2STemporaryServerHighscoreVO`` (bundle lines 60050-60054)."""

    command: ClassVar[str] = "tsh"


class GetOuterRealmsRanksResponse(BaseResponse):
    """Client: ``TempServerEventVO.parseOwnRanks`` (bundle line 118163)."""

    command: ClassVar[str] = "tsh"
    daily_points: ClientInt = Field(validation_alias="DHS", description="Your daily points")
    daily_rank: ClientInt = Field(validation_alias="DR", description="Your daily rank; 0 when unranked")
    overall_points: ClientInt = Field(validation_alias="HS", description="Your overall points")
    overall_rank: ClientInt = Field(validation_alias="R", description="Your overall rank; 0 when unranked")

    @field_validator("daily_rank", "overall_rank", mode="before")
    @classmethod
    def _rank(cls, value: Any) -> int:
        return max(0, js_int(value))
