"""
Highscore and leaderboard models.

Commands:
- hgh: A page of a highscore list, around a rank or a searched name
- llsp: A page of an event leaderboard, from a rank
- llsw: A page of an event leaderboard, around a score or your own rank
- slse: Search an event leaderboard for a name
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import Field, field_serializer, field_validator, model_validator

from empire_core.enums import RankingType
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, GGECommand, list_or_empty, readable_list
from empire_core.protocol.js import ClientInt, js_falsy, js_int, js_loose_equals
from empire_core.protocol.text import encode_json_text

logger = logging.getLogger(__name__)


def _same_list(payload: Any, list_type: RankingType) -> bool:
    # Lenient: a reply without LT is taken; LID is the league the server answered with, so it is not compared
    if not isinstance(payload, dict) or "LT" not in payload:
        return True
    return js_loose_equals(payload["LT"], int(list_type))


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

    The reply carries ``LT`` and ``LID``, but not always the ones asked for, so
    no reply is refused on them: the highscore dialog switches to the list and
    league the reply names (``CastleHighscoreDialog.onGetHighscoreData``, bundle
    lines 27533-27535), and offers the legend list (7) only in the level-cap
    league, falling back to honor (5) elsewhere (``setLeague``, bundle line
    27482; ``switchOverallCategory``, bundle lines 27506-27519). A live server
    answered LT 7 around your own rank ("-1", LID -1) for a league-1 player with
    LT 5 and LID 1.

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
    point, alliance mobilisation/raid and donation events), and always with
    a league: ``LeaderBoardDataProvider`` sends the league it was built with
    on every page. The score and long-term point dialogs build it with the
    event's league, the ``LID`` of the event's sei entry, and page through
    leagues 1 to the event's league count (``GlobalLeaderBoardLeagueComponent``,
    bundle line 100470; ``AScoreEventVO.parseBasicsFromParamObject``, bundle
    line 14967); the alliance mobilisation dialog passes the event's league
    (bundle line 47284); only the donation ranking passes none, so -1 (bundle
    line 115740). A live server answered NO_EVENT (145) for every list with
    no event running, the regular highscore lists included; read those with
    ``hgh``.

    Client: ``C2SListLeaderboardScoresPageVO`` (bundle line 76002), sent by
    ``LeaderBoardDataProvider`` (bundle line 75933), which only
    ``GlobalLeaderBoardComponent.init`` (bundle line 34989) builds, for
    ``ScoreEventGlobalLeaderBoardDialog`` and
    ``LongtermPointEventGlobalLeaderBoardDialog`` (``AGlobalLeaderBoardDialog.showLoaded``,
    bundle line 100442), ``AllianceMobilizationEventDialogLeaderboard.show``
    (bundle line 47278) and ``DonationEventDialogRanking`` (bundle line 115737)

    The alliance mobilisation and raid leaderboards also send ``SDI`` and
    ``EID``: ``LeaderBoardDataProvider.sendCommand`` (bundle line 75949) copies
    the ``{SDI, EID}`` (subdivision tab) or ``{EID}`` (division tab) that
    ``AllianceMobilizationEventDialogRanking.switchTab`` (bundle line 75910) and
    ``AllianceRaidEventRankingDialog.switchTab`` (bundle line 75633) show the
    leaderboard with onto every request, after the VO's own keys.
    """

    command: ClassVar[str] = GGECommand.LLSP

    list_type: RankingType = Field(alias="LT", description="The highscore list")
    league_type_id: int = Field(
        alias="LID",
        description="The event's league, a level band (see GameData.league_type); -1 for the donation ranking",
    )
    max_results: int = Field(alias="M", description="Entries per page")
    rank: int = Field(alias="R", default=1, description="The first rank on the page")
    sub_division_id: int | None = Field(
        alias="SDI", default=None, description="The alliance event subdivision, for its subdivision ranking"
    )
    event_id: int | None = Field(alias="EID", default=None, description="The alliance mobilisation or raid event")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a reply is for this list: its ``LT``, when sent, is the one asked for.

        Client: ``LeaderBoardDataProvider.onScoreDataReceived`` (bundle line 75957) compares
        the reply's ``LT`` with its own list and adopts the reply's ``LID``. Its
        test skips a reply only when the ``LT`` differs and the league matches;
        the library refuses any other ``LT``.
        """
        return _same_list(payload, self.list_type)


class GetRankingWindowRequest(BaseRequest):
    """
    A page of an event leaderboard around a score, or around your own rank.

    Payload: {"LT": list_type, "LID": league_type_id, "M": max_results, "SI": score_id}

    ``SI`` is a score id from a ``slse`` search result, or empty for the page
    holding your own score; the client encodes it as it encodes any text it
    sends. The reply is shaped like ``llsp``'s. ``LID``, ``SDI`` and ``EID``
    are sent as for ``llsp``: your own page goes with the event's league,
    a search hit's page with the hit's league. A live server refused a
    long-term point list's own page with league -1 (GENERAL_ERROR, 1) and
    answered it with the event's league.

    Client: ``C2SListLeaderboardScoresWindowVO`` (bundle line 76012), sent by
    ``LeaderBoardDataProvider.getCurrentPlayerPage`` (bundle line 75941) with no
    score id and ``getCurrentSearchPage`` (bundle line 75943) with a search result's
    league and score id
    """

    command: ClassVar[str] = GGECommand.LLSW

    list_type: RankingType = Field(alias="LT", description="The highscore list")
    league_type_id: int | None = Field(
        alias="LID",
        description=(
            "The event's league, or a search hit's, a level band (see GameData.league_type); "
            "-1 for the donation ranking, None for a hit without one"
        ),
    )
    max_results: int = Field(alias="M", description="Entries per page")
    score_id: str = Field(
        alias="SI", default="", description="The score to page around, from a search result; empty for your own"
    )
    sub_division_id: int | None = Field(
        alias="SDI", default=None, description="The alliance event subdivision, for its subdivision ranking"
    )
    event_id: int | None = Field(alias="EID", default=None, description="The alliance mobilisation or raid event")

    @field_serializer("score_id")
    def _encoded_score_id(self, value: str) -> str:
        return encode_json_text(value)

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a reply is for this list: its ``LT``, when sent, is the one asked for.

        Client: ``LeaderBoardDataProvider.onScoreDataReceived`` (bundle line 75957) compares
        the reply's ``LT`` with its own list and adopts the reply's ``LID``. Its
        test skips a reply only when the ``LT`` differs and the league matches;
        the library refuses any other ``LT``.
        """
        return _same_list(payload, self.list_type)


class SearchRankingListRequest(BaseRequest):
    """
    Search an event leaderboard for a name.

    Payload: {"LT": list_type, "SV": search_value}

    The client encodes ``SV`` as it encodes any text it sends, and sends nothing
    for an empty search. It then pages to the first hit with ``llsw``, or to
    your own page when there is none. ``SDI`` and ``EID`` are sent as for ``llsp``.

    Client: ``C2SSearchLeaderboardScoresEventVO`` (bundle line 76022), sent by
    ``LeaderBoardDataProvider.searchLeaderBoard`` (bundle line 75942)
    """

    command: ClassVar[str] = GGECommand.SLSE

    list_type: RankingType = Field(alias="LT", description="The highscore list")
    search_value: str = Field(alias="SV", description="The name to search for")
    sub_division_id: int | None = Field(
        alias="SDI", default=None, description="The alliance event subdivision, for its subdivision ranking"
    )
    event_id: int | None = Field(alias="EID", default=None, description="The alliance mobilisation or raid event")

    @field_serializer("search_value")
    def _encoded_search_value(self, value: str) -> str:
        return encode_json_text(value)

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a reply is for this list: its ``LT``, when sent, is the one asked for.

        Client: ``LeaderBoardDataProvider.onSearchDataReceived`` (bundle line 75953) compares
        the reply's ``LT`` with its own list. Its test skips a reply only when the
        ``LT`` differs and the league matches; the library refuses any other ``LT``
        and does not compare ``LID``, as the search sends none.
        """
        return _same_list(payload, self.list_type)


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
    A page of an event leaderboard, the reply to ``llsp``.

    Client: ``LLSPCommand.executeCommand`` (bundle line 124397), ``LeaderBoardDataProvider.onScoreDataReceived``
    (bundle line 75957).
    """

    command: ClassVar[str] = GGECommand.LLSP

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


class GetRankingWindowResponse(GetRankingListResponse):
    """
    A page of an event leaderboard around a score, the reply to ``llsw``.

    Client: ``LLSWCommand.executeCommand`` (bundle line 124411), which hands the
    reply to ``LeaderBoardDataProvider.onScoreDataReceived`` (bundle line 75957)
    as ``LLSPCommand`` does
    """

    command: ClassVar[str] = GGECommand.LLSW


def _score_id_text(value: Any) -> Any:
    # Numbers are read as text; the client passes a hit to llsw's text encoding, which needs text
    return str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value


class LeaderboardSearchResult(BasePayload):
    """
    The scores that matched a search in one league: an entry of ``slse``'s ``L``.

    Client: ``LeaderBoardDataProvider.onSearchDataReceived`` (bundle line 75952)
    """

    league_type_id: int | None = Field(alias="LID", default=None, description="The league the scores are in")
    score_ids: list[str] = Field(alias="L", default_factory=list, description="The matching scores' ids")

    @field_validator("score_ids", mode="before")
    @classmethod
    def _readable_score_ids(cls, value: Any) -> list[Any]:
        texts = (_score_id_text(item) for item in list_or_empty(value))
        return [item for item in texts if isinstance(item, str)]


class SearchRankingListResponse(BaseResponse):
    """
    The scores that matched a leaderboard search, the reply to ``slse``.

    The client throws on a missing ``L`` or a result that is not an object; the
    library reads those as no results, and a score id that is a number as text.

    Client: ``SLSECommand.executeCommand`` (bundle line 124440),
    ``LeaderBoardDataProvider.onSearchDataReceived`` (bundle line 75952)
    """

    command: ClassVar[str] = GGECommand.SLSE

    list_type: int | None = Field(alias="LT", default=None)
    league_type_id: int = Field(alias="LID", default=-1, description="League type id; -1 for none")
    results: list[LeaderboardSearchResult] = Field(
        alias="L", default_factory=list, description="The matches, grouped by league, in the client's order"
    )

    @field_validator("league_type_id", mode="before")
    @classmethod
    def _falsy_league_reads_as_minus_one(cls, value: Any) -> int:
        return -1 if js_falsy(value) else js_int(value)

    @field_validator("results", mode="before")
    @classmethod
    def _readable_results(cls, value: Any) -> list[LeaderboardSearchResult]:
        return readable_list(LeaderboardSearchResult, value, accept=lambda row: isinstance(row, dict), warn=logger)
