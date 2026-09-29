"""
Ranking protocol models for GGE.

Commands:
- hgh: A page of a highscore list, around a rank or a searched name
- llsp: A page of an event leaderboard, from a rank
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import Field, field_serializer, field_validator, model_validator

from empire_core.enums import RankingType
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, GGECommand
from empire_core.protocol.js import ClientInt, js_falsy, js_int
from empire_core.protocol.text import encode_json_text

logger = logging.getLogger(__name__)


class RankingEntry:
    """A ranking entry with optional global-list and highscore details.

    Global lists identify the server with ``instance_id`` and the paging key
    with ``score_id``. Neither is an owner ID; ``entity_id`` remains unknown
    (0) when the payload does not contain one.
    """

    def __init__(self, raw: list | dict) -> None:
        self.raw = raw
        self.rank: int = -1
        self.score: int = -1
        self.entity_id: int = 0
        self.name: str = ""
        self.alliance_id: int = 0
        self.alliance_name: str = ""
        self.instance_id: int | None = None
        self.score_id: int | str | None = None
        self.level: int = 0
        self.legend_level: int = 0
        self.honor: int = 0
        self.might: int = 0
        self.member_count: int = 0
        self.fame: int = 0

        try:
            # llsp/llsw format: {"R": rank, "S": score, "P": name, "A": alliance, ...}
            if isinstance(raw, dict):
                self.rank = raw.get("R", -1)
                self.score = raw.get("S", -1)
                self.name = raw.get("P", "")
                self.alliance_name = raw.get("A", "")
                self.instance_id = raw.get("I")
                self.score_id = raw.get("SI")
                return

            # hgh format: list-based entries
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
                self.level = details.get("L", 0)
                self.legend_level = details.get("LL", 0)
                self.honor = details.get("H", 0)
                self.might = details.get("MP", 0)

            elif isinstance(details, list):
                self.rank = raw[o]
                self.score = raw[o + 1]
                self.entity_id = details[0] if len(details) > 0 else 0
                self.member_count = details[2] if len(details) > 2 else 0
                self.fame = details[3] if len(details) > 3 else 0
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

        except (IndexError, ValueError, TypeError) as e:
            logger.error(f"Failed to parse RankingEntry: {raw} - Error: {e}")

    def __repr__(self) -> str:
        return f"RankingEntry(rank={self.rank}, name='{self.name}', score={self.score})"

    @classmethod
    def unranked(cls, name: str) -> "RankingEntry":
        """Create a synthetic entry for a player with no ranking score."""
        entry = cls({})
        entry.raw = []
        entry.score = 0
        entry.entity_id = 0
        entry.name = name
        entry.alliance_id = 0
        entry.alliance_name = ""
        return entry


class GetHighscoreRequest(BaseRequest):
    """
    A page of a highscore list, around a rank or a searched name.

    Payload: {"LT": list_type, "LID": league_type_id, "SV": search_value}

    The keys follow the client's order: the constructor initialises LT and LID
    before it sets SV, which it encodes as it encodes any text it sends.

    Client: ``C2SGetHighscoreVO`` (bundle line 14674)
    """

    command: ClassVar[str] = GGECommand.HGH

    list_type: RankingType = Field(alias="LT", description="The highscore list")
    league_type_id: int = Field(
        alias="LID",
        default=-1,
        description="The league, a level band (see GameData.league_type); -1 for none",
    )
    search_value: str = Field(
        alias="SV", description='A name, or a rank as text; "-1" asks for the page around your own rank'
    )

    @field_serializer("search_value")
    def _encoded_search_value(self, value: str) -> str:
        return encode_json_text(value)


class GetHighscoreResponse(BaseResponse):
    """
    Response for hgh command.

    Client: ``HGHCommand.executeCommand`` (bundle line 124377),
    ``CastleSingleplayerRankingItem.update`` (bundle line 91695),
    ``CastleAllianceRankingItem.update`` (bundle line 91645),
    ``CastleEilandAllianceRankingItem.update`` (bundle line 98076)
    """

    command: ClassVar[str] = GGECommand.HGH

    list_type: int | None = Field(alias="LT", default=None)
    league_type_id: int = Field(alias="LID", default=-1, description="League type id; -1 for none")
    last_rank: int | None = Field(alias="LR", default=None)
    search_value: str | None = Field(alias="SV", default=None)
    raw_list: list[Any] = Field(
        alias="L",
        default_factory=list,
        description=(
            "Ranking rows, kept raw: their layout depends on the list, e.g. [rank, score, owner "
            "record], [rank, owner record], [rank, score, alliance row] or [value, rank, score, "
            "alliance row]"
        ),
    )

    @field_validator("league_type_id", mode="before")
    @classmethod
    def _falsy_league_reads_as_minus_one(cls, value: Any) -> int:
        return -1 if js_falsy(value) else js_int(value)

    @property
    def entries(self) -> list[RankingEntry]:
        return [RankingEntry(item) for item in self.raw_list]


class GetRankingListRequest(BaseRequest):
    """
    A page of an event leaderboard, starting at a rank.

    Payload: {"LT": list_type, "LID": league_type_id, "M": max_results, "R": rank}

    The client pages only event leaderboards this way (score, long-term
    point, alliance mobilisation/raid and donation events), passing the
    running event's league as ``LID``. A live server answered NO_EVENT
    (145) for every list with no event running, the regular highscore
    lists included; read those with ``hgh``.

    Client: ``C2SListLeaderboardScoresPageVO`` (bundle line 76002), sent by
    ``LeaderBoardDataProvider`` (bundle line 75933), which only
    ``GlobalLeaderBoardComponent.init`` (bundle line 34989) builds, for
    ``ScoreEventGlobalLeaderBoardDialog`` and
    ``LongtermPointEventGlobalLeaderBoardDialog`` (``AGlobalLeaderBoardDialog.showLoaded``,
    bundle line 100442), ``AllianceMobilizationEventDialogLeaderboard.show``
    (bundle line 47278) and ``DonationEventDialogRanking`` (bundle line 115737)
    """

    command: ClassVar[str] = "llsp"

    list_type: RankingType = Field(alias="LT", description="The highscore list")
    league_type_id: int = Field(
        alias="LID",
        default=-1,
        description="The league, a level band (see GameData.league_type); -1 for none",
    )
    max_results: int = Field(alias="M", description="Entries per page")
    rank: int = Field(alias="R", default=1, description="The first rank on the page")


def _guarded(value: Any, kind: type | tuple[type, ...]) -> Any:
    return value if isinstance(value, kind) and not isinstance(value, bool) else None


class LeaderboardScore(BasePayload):
    """One entry of an event leaderboard page: an entry of ``llsp``'s ``L``.

    Client: ``AGlobalLeaderBoardItem`` getters (bundle lines 47303-47316) and
    ``LeaderBoardDataProvider.onScoreDataReceived`` (bundle line 75957).
    """

    rank: ClientInt = Field(alias="R", default=-1, description="Rank on the list")
    score: int | float = Field(alias="S", default=-1, description="Points")
    player_name: str = Field(alias="P", default="", description="Player name")
    alliance_name: str = Field(alias="A", default="", description="Alliance name, empty without one")
    instance_id: ClientInt | None = Field(
        alias="I", default=None, description="Game server (instance) the player is on"
    )
    score_id: int | str | None = Field(
        alias="SI", default=None, description="Paging key that search results are matched against; not an owner id"
    )

    @model_validator(mode="before")
    @classmethod
    def _getters_guard_every_key(cls, data: Any) -> Any:
        # AGlobalLeaderBoardItem's getters fall back on a missing or empty value
        if not isinstance(data, dict):
            return data
        checks: dict[str, type | tuple[type, ...]] = {"S": (int, float), "P": str, "A": str}
        return {
            key: value
            for key, value in data.items()
            if value is not None and (key not in checks or _guarded(value, checks[key]) is not None)
        }


class GetRankingListResponse(BaseResponse):
    """
    Response for llsp command.

    Client: ``LLSPCommand.executeCommand`` (bundle line 124397), ``LeaderBoardDataProvider.onScoreDataReceived``
    (bundle line 75957).
    """

    command: ClassVar[str] = "llsp"

    list_type: int | None = Field(alias="LT", default=None)
    league_type_id: int | None = Field(alias="LID", default=None, description="League type id; None for none")
    scores: list[LeaderboardScore] = Field(alias="L", default_factory=list, description="The page's entries")
    total: int = Field(alias="T", default=0, description="Number of scores on the whole list")

    @field_validator("league_type_id", mode="before")
    @classmethod
    def _falsy_league_reads_as_none(cls, value: Any) -> int | None:
        return None if js_falsy(value) else js_int(value)

    @field_validator("scores", mode="before")
    @classmethod
    def _rows_without_data_read_as_empty(cls, value: object) -> object:
        # The item getters guard with this._data?, so a row that is not an object shows its defaults
        if not isinstance(value, list):
            return []
        return [row if isinstance(row, dict) else {} for row in value]

    @property
    def entries(self) -> list[RankingEntry]:
        return [RankingEntry(score.model_dump(by_alias=True, exclude_none=True)) for score in self.scores]
