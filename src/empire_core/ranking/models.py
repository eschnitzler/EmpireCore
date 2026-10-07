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

from pydantic import Field, ValidationError, ValidationInfo, field_serializer, field_validator, model_validator

from empire_core.enums import RankingType
from empire_core.map.models import MapObject
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    GGECommand,
    list_or_empty,
    read_or_none,
    readable_list,
)
from empire_core.protocol.js import ClientInt, js_falsy, js_int, js_loose_equals, js_string, js_truthy
from empire_core.protocol.text import encode_json_text

logger = logging.getLogger(__name__)


def _same_list(payload: Any, list_type: RankingType) -> bool:
    # Lenient: a reply without LT is taken
    if not isinstance(payload, dict) or "LT" not in payload:
        return True
    return js_loose_equals(payload["LT"], int(list_type))


def _not_skipped(payload: Any, list_type: RankingType, league_type_id: int | None) -> bool:
    # The client skips a reply only when its LT differs and its league, LID or -1, is the one asked for;
    # a reply without LT is taken
    if not isinstance(payload, dict) or "LT" not in payload or league_type_id is None:
        return True
    reply_league = -1 if js_falsy(payload.get("LID")) else payload.get("LID")
    other_list = not js_loose_equals(payload["LT"], int(list_type))
    return not (other_list and js_loose_equals(reply_league, league_type_id))


def _owner_or_none(value: Any) -> MapObject | None:
    # WorldMapOwnerInfoVO.fillFromParamObject reads keys off an object; anything else names no owner
    return read_or_none(MapObject.model_validate, value) if isinstance(value, dict) else None


class HighscoreAlliance(BasePayload):
    """
    An alliance on a highscore list: ``[alliance_id, name, member_count, fame]``.

    Client: ``AllianceHighscoreInfoVO.fillFromParamObject`` (bundle line 27680), which reads
    nothing from a value that is not an array
    """

    alliance_id: ClientInt = Field(default=0, description="Alliance id")
    name: str = Field(default="", description="Alliance name")
    member_count: ClientInt = Field(default=0, description="Number of members")
    fame: ClientInt = Field(default=0, description="The alliance's current fame points")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        return dict(zip(("alliance_id", "name", "member_count", "fame"), data, strict=False))

    @field_validator("name", mode="before")
    @classmethod
    def _text(cls, value: Any) -> Any:
        return "" if value is None else js_string(value)


class HighscorePlayerRow(BasePayload):
    """
    A player's row: ``[rank, score, owner_record, display_name?, shown_rank?]``, or ``[rank, owner_record]``
    without a score.

    Client: ``CastleHighscoreDialog.onGetHighscoreData`` (bundle lines 27559-27568),
    ``CastleGenericHighscoreDialog.onGetHighscoreData`` (bundle lines 30827-30836),
    ``CastleSingleplayerRankingItem.update`` (bundle line 91695) for the row without a score,
    ``TempServerEventDialogRankingItem.updateWithNewData`` (bundle lines 118343-118344) for the
    display name and the shown rank, which 0 leaves at ``rank``
    """

    rank: ClientInt = Field(default=0, description="Rank on the list")
    score: ClientInt = Field(default=0, description="The listed value; 0 on a row without one")
    owner: MapObject | None = Field(default=None, description="The player's owner record; None when unreadable")
    display_name: str | None = Field(
        default=None, description="The name the temporary server lists show; None when the row has none"
    )
    shown_rank: int | None = Field(
        default=None, description="The rank the previous-run and temporary server lists show; None to show rank"
    )

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        if len(data) <= 2:
            return {"rank": data[0] if data else None, "owner": data[1] if len(data) > 1 else None}
        shown = js_int(data[4]) if len(data) > 4 else 0
        return {
            "rank": data[0],
            "score": data[1],
            "owner": data[2],
            "display_name": data[3] if len(data) > 3 and isinstance(data[3], str) and data[3] else None,
            "shown_rank": shown or None,
        }

    @field_validator("owner", mode="before")
    @classmethod
    def _owner(cls, value: Any) -> Any:
        return value if isinstance(value, MapObject) else _owner_or_none(value)


class HighscoreAllianceRow(BasePayload):
    """
    An alliance's row: ``[rank, score, alliance]``.

    Client: ``CastleHighscoreDialog.onGetHighscoreData`` (bundle lines 27541-27558),
    ``CastleAllianceRankingItem.update`` (bundle line 91645), the generic alliance highscore
    dialog (bundle lines 38131-38134)
    """

    rank: ClientInt = Field(default=0, description="Rank on the list")
    score: ClientInt = Field(default=0, description="The listed value")
    alliance: HighscoreAlliance = Field(default_factory=HighscoreAlliance, description="The alliance")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        return dict(zip(("rank", "score", "alliance"), data, strict=False))

    @field_validator("alliance", mode="before")
    @classmethod
    def _alliance(cls, value: Any) -> Any:
        return value if isinstance(value, (list, HighscoreAlliance)) else {}


class HighscoreIslandRow(HighscoreAllianceRow):
    """
    A Storm Islands alliance row: ``[is_stormlord, rank, score, alliance]``.

    Client: ``CastleEilandAllianceRankingItem.update`` (bundle lines 98076-98079), shown for
    ``HighscoreConst.ALLIANCE_AQUA_POINTS`` (bundle line 98052)
    """

    is_stormlord: bool = Field(default=False, description="The alliance holds the Storm Islands")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        return {
            "is_stormlord": js_truthy(data[0]) if data else False,
            **dict(zip(("rank", "score", "alliance"), data[1:], strict=False)),
        }


class HighscoreTournamentRow(BasePayload):
    """
    A tournament row: ``[rank, score, player_id, player_name]``, with no owner record.

    Client: ``ACastleTournamentRankListItem.parseItemData`` (bundle line 59120),
    ``CastleTournamentRankListItem.parseItemData`` (bundle line 118660)
    """

    rank: ClientInt = Field(default=0, description="Rank on the list")
    score: ClientInt = Field(default=0, description="Tournament points")
    player_id: ClientInt = Field(default=0, description="The player's id")
    player_name: str = Field(default="", description="The player's name")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        return dict(zip(("rank", "score", "player_id", "player_name"), data, strict=False))

    @field_validator("player_name", mode="before")
    @classmethod
    def _text(cls, value: Any) -> Any:
        return "" if value is None else js_string(value)


HighscoreRow = HighscorePlayerRow | HighscoreAllianceRow | HighscoreIslandRow | HighscoreTournamentRow
"""One row of a ``hgh`` reply; :data:`HIGHSCORE_ROW_LAYOUTS` and the row's shape pick which."""


_RowModel = (
    type[HighscorePlayerRow] | type[HighscoreAllianceRow] | type[HighscoreIslandRow] | type[HighscoreTournamentRow]
)


HIGHSCORE_ROW_LAYOUTS: dict[int, _RowModel] = {
    RankingType.ALLIANCE_AQUA_POINTS: HighscoreIslandRow,
    RankingType.TOURNAMENT_FAME: HighscoreTournamentRow,
}
"""
The lists whose rows have a layout of their own.

Every other list's row is an alliance's when its third entry is an array, else a player's, as
``SeasonLeagueMainDialogRanksItem`` tells them apart (bundle lines 91889, 91908); the other
dialogs each read one of those two layouts.
"""


def _row_model(list_type: int | None, row: list[Any]) -> _RowModel:
    layout = HIGHSCORE_ROW_LAYOUTS.get(list_type) if list_type is not None else None
    if layout is not None:
        return layout
    return HighscoreAllianceRow if len(row) > 2 and isinstance(row[2], list) else HighscorePlayerRow


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
    A page of a highscore list, the reply to ``hgh``.

    The client has no row parser of its own: each dialog reads the rows in its list's
    layout, so the rows are read by :data:`HIGHSCORE_ROW_LAYOUTS` and their shape.

    Client: ``HGHCommand.executeCommand`` (bundle line 124377)
    """

    command: ClassVar[str] = GGECommand.HGH

    list_type: int | None = Field(alias="LT", default=None)
    league_type_id: int = Field(alias="LID", default=-1, description="League type id; -1 for none")
    last_rank: int | None = Field(alias="LR", default=None)
    search_value: str | None = Field(alias="SV", default=None)
    rows: tuple[HighscoreRow, ...] = Field(alias="L", default=(), description="The page's rows, in the list's layout")

    @field_validator("league_type_id", mode="before")
    @classmethod
    def _falsy_league_reads_as_minus_one(cls, value: Any) -> int:
        return -1 if js_falsy(value) else js_int(value)

    @field_validator("rows", mode="plain")
    @classmethod
    def _rows(cls, value: Any, info: ValidationInfo) -> tuple[HighscoreRow, ...]:
        list_type = info.data.get("list_type")
        rows: list[HighscoreRow] = []
        unreadable: list[Any] = []
        for row in value if isinstance(value, list) else ():
            if not isinstance(row, list):
                unreadable.append(row)
                continue
            try:
                rows.append(_row_model(list_type, row).model_validate(row))
            except ValidationError:
                unreadable.append(row)
        if unreadable:
            logger.warning(f"Skipped {len(unreadable)} unreadable highscore rows, first: {unreadable[0]!r:.200}")
        return tuple(rows)


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
        """Whether a reply is for this request, as the client tells.

        A reply is refused only when its ``LT`` is another list and its league
        (``LID``, or -1 without one) is the one asked for; a reply for another
        list in another league is taken, as the client takes it.

        Client: ``LeaderBoardDataProvider.onScoreDataReceived`` (bundle line 75957),
        which then adopts the reply's ``LID``
        """
        return _not_skipped(payload, self.list_type, self.league_type_id)


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
        """Whether a reply is for this request, as the client tells.

        A reply is refused only when its ``LT`` is another list and its league
        (``LID``, or -1 without one) is the one asked for; a reply for another
        list in another league is taken, as the client takes it.

        Client: ``LeaderBoardDataProvider.onScoreDataReceived`` (bundle line 75957),
        which then adopts the reply's ``LID``
        """
        return _not_skipped(payload, self.list_type, self.league_type_id)


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

        Client: ``LeaderBoardDataProvider.onSearchDataReceived`` (bundle line 75953) skips a
        reply only when its ``LT`` differs and the dialog's league is the reply's
        ``LID`` or -1. The search sends no league, so the library cannot tell the
        dialog's and refuses any other ``LT``.
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
