"""Dedicated event board protocols, whose records differ from generic highscore rows."""

from __future__ import annotations

import logging
from typing import Any, ClassVar, TypeVar

from pydantic import Field, field_validator, model_validator

from empire_core.enums import RankingType
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, js_loose_equals, js_truthy

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BasePayload)


def _rows(value: Any, model: type[T]) -> tuple[T, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Expected a list of event records")
    entries = [{} if entry is None else entry for entry in value]
    return tuple(readable_list(model, entries, warn=logger, what="event records"))


class ColossusHighscoreRow(BasePayload):
    """A donor. Points are donation units, before the event's conversion rate.

    Client: ``CastleSpecialEventData.parse_CHE`` (bundle lines 139783-139790).
    """

    rank: ClientInt = Field(validation_alias="CR", description="Donor rank")
    player_name: str = Field(validation_alias="PN", description="Donor name")
    donation_points: float = Field(validation_alias="CP", description="Donated points before event conversion")
    player_id: ClientInt = Field(validation_alias="PID", description="Donor player id")


class GetColossusHighscoreRequest(BaseRequest):
    """Client: ``C2SColossusGetHighscoreVO`` (bundle lines 59205-59210)."""

    command: ClassVar[str] = "che"
    search_value: str = Field(default="-1", validation_alias="SV", description="Name or rank; -1 for your own rank")


class GetColossusHighscoreResponse(BaseResponse):
    """Client: ``CastleSpecialEventData.parse_CHE`` (bundle lines 139783-139790)."""

    command: ClassVar[str] = "che"
    own_donation_points: float = Field(validation_alias="OP", description="Your points before event conversion")
    last_rank: ClientInt = Field(validation_alias="LR", description="Last rank on the server")
    rows: tuple[ColossusHighscoreRow, ...] = Field(validation_alias="HS", description="This page's donors")

    @field_validator("rows", mode="before")
    @classmethod
    def _read_rows(cls, value: Any) -> tuple[ColossusHighscoreRow, ...]:
        return _rows(value, ColossusHighscoreRow)


class SeasonDivision(BasePayload):
    """Client: ``SeasonLeagueServer.parseDivisionInfo`` (bundle line 142655)."""

    division_id: ClientInt = Field(default=0, validation_alias="KLDID", description="Season division id")
    size: ClientInt = Field(default=0, validation_alias="KLDS", description="Players in the division")


class SeasonMedal(BasePayload):
    """A medal balance. Client: ``SeasonLeagueServer.parseMedalInfo`` (bundle lines 142656-142662)."""

    medal_id: ClientInt = Field(description="Season medal id")
    amount: ClientInt = Field(description="Medals held")

    @model_validator(mode="before")
    @classmethod
    def _row(cls, value: Any) -> Any:
        return dict(zip(("medal_id", "amount"), value, strict=False)) if isinstance(value, list) else value


class SeasonPromotionPass(BasePayload):
    """A purchased promotion pass. Client: ``SeasonLeagueServer.parsePassInfo`` (bundle line 142664)."""

    promotion_id: ClientInt = Field(description="Promotion whose pass was purchased")

    @model_validator(mode="before")
    @classmethod
    def _id(cls, value: Any) -> Any:
        return value if isinstance(value, (dict, cls)) else {"promotion_id": value}


class SeasonPasses(BasePayload):
    """Client: ``SeasonLeagueServer.parsePassInfo`` (bundle line 142664).

    Keys: ``CommKeys`` (dll.pretty lines 80786, 80796-80797).
    """

    season_enabled: bool = Field(
        default=False, validation_alias="KLP", description="Whether the season pass is enabled"
    )
    event_enabled: bool = Field(
        default=False, validation_alias="KLEPE", description="Whether the event pass is enabled"
    )
    promotions: tuple[SeasonPromotionPass, ...] = Field(
        default=(), validation_alias="KLPP", description="Purchased promotion passes"
    )

    @field_validator("season_enabled", "event_enabled", mode="before")
    @classmethod
    def _enabled(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    @field_validator("promotions", mode="before")
    @classmethod
    def _promotions(cls, value: Any) -> tuple[SeasonPromotionPass, ...]:
        return _rows(value if js_truthy(value) else [], SeasonPromotionPass)


class SeasonRank(BasePayload):
    """Client: ``SeasonLeagueServer.parseRankInfo`` (bundle line 142669)."""

    promotion_id: ClientInt = Field(default=0, validation_alias="KLRID", description="Current promotion id")
    medal_points: ClientInt = Field(default=0, validation_alias="KLMP", description="Promotion medal points")


class GetSeasonInfoRequest(BaseRequest):
    """Client: ``C2SGetSeasonInfoEventVO`` (bundle lines 142729-142733)."""

    command: ClassVar[str] = "kli"


class GetSeasonInfoResponse(BaseResponse):
    """Snapshot of the sections supplied by kli; absent sections stay None.

    Client: ``SeasonLeagueServer.parseKLI`` (bundle lines 142653-142671).
    """

    command: ClassVar[str] = "kli"
    division: SeasonDivision | None = Field(default=None, validation_alias="KLD", description="Season division")
    player_medals: tuple[SeasonMedal, ...] | None = Field(
        default=None, validation_alias="KLM", description="Your medal balances"
    )
    alliance_medals: tuple[SeasonMedal, ...] | None = Field(
        default=None, validation_alias="KLAM", description="Alliance medal balances"
    )
    passes: SeasonPasses | None = Field(default=None, validation_alias="KLSP", description="Purchased passes")
    rank: SeasonRank | None = Field(default=None, validation_alias="KLR", description="Your promotion progress")
    payout_seconds: ClientInt | None = Field(
        default=None, validation_alias="RD", description="Seconds until medal payout"
    )
    event_dialog_seen: bool | None = Field(
        default=None, validation_alias="KLSE", description="Event introduction was seen"
    )
    season_dialog_seen: bool | None = Field(
        default=None, validation_alias="KLS", description="Season introduction was seen"
    )

    @model_validator(mode="before")
    @classmethod
    def _object(cls, value: Any) -> Any:
        if isinstance(value, dict) and "raw" in value:
            raise ValueError("Unreadable season info packet")
        return value

    @field_validator("division", "passes", "rank", mode="before")
    @classmethod
    def _optional_section(cls, value: Any) -> Any:
        return value if js_truthy(value) else None

    @field_validator("player_medals", "alliance_medals", mode="before")
    @classmethod
    def _medals(cls, value: Any) -> tuple[SeasonMedal, ...] | None:
        return _rows(value, SeasonMedal) if js_truthy(value) else None

    @field_validator("event_dialog_seen", "season_dialog_seen", mode="before")
    @classmethod
    def _seen(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)


class SeasonHighscoreRank(BasePayload):
    """Client: ``SeasonLeagueServer.parseKLH`` (bundle lines 142673-142682)."""

    list_type: EnumOrInt[RankingType] = Field(description="Season highscore list")
    rank: ClientInt = Field(description="Your rank on this list")

    @model_validator(mode="before")
    @classmethod
    def _row(cls, value: Any) -> Any:
        return dict(zip(("list_type", "rank"), value, strict=False)) if isinstance(value, list) else value


class GetSeasonRanksRequest(BaseRequest):
    """Client: ``C2SGetSeasonLeagueHighscoreEventVO`` (bundle lines 142737-142741)."""

    command: ClassVar[str] = "klh"


class GetSeasonRanksResponse(BaseResponse):
    """Client: ``SeasonLeagueServer.parseKLH`` (bundle lines 142673-142682), a bare array."""

    command: ClassVar[str] = "klh"
    ranks: tuple[SeasonHighscoreRank, ...] = Field(description="Your season and current event ranks")

    @model_validator(mode="before")
    @classmethod
    def _array(cls, value: Any) -> Any:
        return {"ranks": _rows(value, SeasonHighscoreRank)} if isinstance(value, list) else value
