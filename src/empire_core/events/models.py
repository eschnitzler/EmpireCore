"""
The events that have a scoreboard, and a page of one as ``client.events.get_scores`` returns it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from empire_core.enums import RankingType
from empire_core.exceptions import ReplyMismatchError
from empire_core.gamedata.ids.events import Event
from empire_core.protocol.js import js_int, js_parse_int_or_zero, js_string
from empire_core.ranking.models import GetHighscoreResponse, GetRankingListResponse, LeaderboardScore


class Scoreboard(BaseModel):
    """The boards an event's dialogs open, and the dialog the lists come from."""

    model_config = ConfigDict(frozen=True)

    player_lists: tuple[RankingType, ...] = Field(
        description="The player boards; Berimond invasion has one per faction, blue first"
    )
    alliance_list: RankingType | None = Field(default=None, description="The alliance board, or None without one")
    is_leaderboard: bool = Field(
        default=False, description="Whether the boards are read with llsp, llsw and slse rather than hgh"
    )
    source: str = Field(description="Where the client opens the boards")

    @property
    def lists(self) -> tuple[RankingType, ...]:
        """Every board, the player boards first."""
        return (*self.player_lists, *((self.alliance_list,) if self.alliance_list is not None else ()))


EVENT_SCOREBOARDS: dict[Event, Scoreboard] = {
    Event.FACTION: Scoreboard(
        player_lists=(RankingType.FACTION_TOURNAMENT,),
        source="FactionRankingComponent.generateProperties (bundle line 95410)",
    ),
    Event.POINT_EVENT: Scoreboard(
        player_lists=(RankingType.POINT_EVENT,), source="CastlePointEventDialog (bundle line 117423)"
    ),
    Event.BEGGING_KNIGHTS: Scoreboard(
        player_lists=(RankingType.BEGGING_KNIGHTS,), source="CastleBeggingKnightsDialog (bundle line 114835)"
    ),
    Event.ALLIANCE_ALIEN_INVASION: Scoreboard(
        player_lists=(RankingType.ALLIANCE_ALIEN_INVASION_PLAYER,),
        alliance_list=RankingType.ALLIANCE_ALIEN_INVASION_ALLIANCE,
        source="CastleAllianceAlienInvasionEventDialogProperties (bundle lines 114205-114207)",
    ),
    Event.ALLIANCE_NOMAD_INVASION: Scoreboard(
        player_lists=(),
        alliance_list=RankingType.ALLIANCE_NOMADINVASION_ALLIANCE,
        source="CastleAllianceNomadInvasionPointsEventSublayer (bundle line 98542); no player board",
    ),
    Event.SAMURAI_INVASION: Scoreboard(
        player_lists=(),
        alliance_list=RankingType.SAMURAI_ALLIANCE,
        source="CastleAllianceSamuraiInvasionDialogAllianceSublayer (bundle line 98953); no player board",
    ),
    Event.LONG_TERM_POINT_EVENT: Scoreboard(
        player_lists=(RankingType.LONG_TERM_POINT_EVENT,),
        is_leaderboard=True,
        source="LongtermPointEventGlobalLeaderBoardDialog (bundle line 100413)",
    ),
    Event.FACTION_INVASION: Scoreboard(
        player_lists=(RankingType.FACTION_INVASION_PLAYER_BLUE, RankingType.FACTION_INVASION_PLAYER_RED),
        alliance_list=RankingType.FACTION_INVASION_ALLIANCE,
        source="CastleFactionInvasionEventHighscoreDialog (bundle lines 53151-53155)",
    ),
    Event.RED_ALLIANCE_ALIEN_INVASION: Scoreboard(
        player_lists=(RankingType.ALLIANCE_RED_ALIEN_INVASION_PLAYER,),
        alliance_list=RankingType.ALLIANCE_RED_ALIEN_INVASION_ALLIANCE,
        source="CastleRedAllianceAlienInvasionEventDialogProperties (bundle lines 117712-117714)",
    ),
    Event.DONATION_EVENT: Scoreboard(
        player_lists=(RankingType.DONATION_EVENT,),
        is_leaderboard=True,
        source="DonationEventDialogRanking (bundle line 115746)",
    ),
}
"""The events whose dialogs open a scoreboard.

Client: ``EventConst.EVENTTYPE_*`` (dll line 19291) for the ids; each board's dialog in its ``source``
"""


class EventScore(BaseModel):
    """
    One row of an event's scoreboard: a player, or an alliance on an alliance board.

    Client: ``CastleGenericHighscoreDialog.onGetHighscoreData`` (bundle line 30827) and
    ``CastleSingleplayerRankingItem.update`` (bundle line 91695) read a player row as
    ``[rank, points, owner]`` with ``WorldMapOwnerInfoVO.fillFromParamObject`` (bundle line 10794);
    ``CastleGenericAllianceHighscoreDialog.onGetHighscoreData`` (bundle line 38127) and
    ``CastleAllianceRankingItem.update`` (bundle line 91645) read an alliance row as
    ``[rank, points, [alliance_id, name, member_count, fame]]`` with
    ``AllianceHighscoreInfoVO.fillFromParamObject`` (bundle line 27680); a leaderboard row is a
    :class:`~empire_core.ranking.models.LeaderboardScore`
    """

    rank: int = Field(description="Rank on the board")
    points: int | float = Field(description="The event's points")
    name: str = Field(default="", description="The player's name, or the alliance's on an alliance board")
    player_id: int | None = Field(default=None, description="The player's id; None on alliance and leaderboard rows")
    alliance_id: int | None = Field(
        default=None, description="The alliance's id, 0 for a player without one; None on leaderboard rows"
    )
    alliance_name: str = Field(default="", description="The alliance's name, empty for a player without one")
    level: int | None = Field(default=None, description="The player's level; None on alliance and leaderboard rows")
    member_count: int | None = Field(default=None, description="The alliance's member count, on alliance rows")
    instance_id: int | None = Field(default=None, description="The game server the player is on, on leaderboard rows")

    @classmethod
    def from_player_row(cls, row: Any) -> EventScore | None:
        """A ``hgh`` player row, or None for one that is not a list."""
        if not isinstance(row, list) or not row:
            return None
        has_points = len(row) > 2
        owner = row[2] if has_points else row[1] if len(row) > 1 else None
        owner = owner if isinstance(owner, dict) else {}
        return cls(
            rank=js_int(row[0]),
            points=js_int(row[1]) if has_points else 0,
            name="" if owner.get("N") is None else js_string(owner["N"]),
            player_id=js_parse_int_or_zero(owner.get("OID")),
            alliance_id=js_parse_int_or_zero(owner.get("AID")),
            alliance_name=js_string(owner.get("AN") or ""),
            level=js_parse_int_or_zero(owner.get("L")),
        )

    @classmethod
    def from_alliance_row(cls, row: Any) -> EventScore | None:
        """A ``hgh`` alliance row, or None for one that is not a list."""
        if not isinstance(row, list) or not row:
            return None
        info = row[2] if len(row) > 2 and isinstance(row[2], list) else []
        name = js_string(info[1]) if len(info) > 1 and info[1] is not None else ""
        return cls(
            rank=js_int(row[0]),
            points=js_int(row[1]) if len(row) > 1 else 0,
            name=name,
            alliance_id=js_int(info[0]) if info else 0,
            alliance_name=name,
            member_count=js_int(info[2]) if len(info) > 2 else 0,
        )

    @classmethod
    def from_leaderboard(cls, score: LeaderboardScore) -> EventScore:
        """An event leaderboard row."""
        return cls(
            rank=score.rank,
            points=score.score,
            name=score.player_name,
            alliance_name=score.alliance_name,
            instance_id=score.instance_id,
        )


class EventScores(BaseModel):
    """A page of an event's scoreboard."""

    event: Event = Field(description="The event")
    list_type: RankingType = Field(description="The board read")
    league_id: int | None = Field(description="The league the page is from, as the server answered; None for none")
    total: int | None = Field(
        default=None, description="Ranked entries on the whole board (its last rank); None when not given"
    )
    scores: list[EventScore] = Field(default_factory=list, description="The page's rows, in rank order")

    @classmethod
    def from_highscore(cls, event: Event, list_type: RankingType, reply: GetHighscoreResponse) -> EventScores:
        """
        A ``hgh`` reply; rows that cannot be read are skipped.

        A reply for another of the event's boards is read as that board, as the
        dialogs adopt the list a reply names.

        Raises:
            ReplyMismatchError: The reply is for a list that is not one of the event's,
                e.g. a late reply to another ``hgh`` request

        Client: ``CastleGenericRankingComponent.onGetHighscoreData`` (bundle line 29601)
        ignores a reply for another list
        """
        board = EVENT_SCOREBOARDS.get(event)
        if reply.list_type is not None and reply.list_type != list_type:
            if board is None or reply.list_type not in board.lists:
                raise ReplyMismatchError(int(list_type), reply.list_type)
            list_type = RankingType(reply.list_type)
        alliance = board is not None and list_type == board.alliance_list
        read = EventScore.from_alliance_row if alliance else EventScore.from_player_row
        rows = [score for score in map(read, reply.raw_list) if score is not None]
        league = None if reply.league_type_id == -1 else reply.league_type_id
        last_rank = js_int(reply.last_rank) if reply.last_rank is not None else None
        return cls(event=event, list_type=list_type, league_id=league, total=last_rank, scores=rows)

    @classmethod
    def from_leaderboard(cls, event: Event, list_type: RankingType, reply: GetRankingListResponse) -> EventScores:
        """A ``llsp`` or ``llsw`` reply."""
        return cls(
            event=event,
            list_type=list_type,
            league_id=reply.league_type_id,
            total=reply.total,
            scores=[EventScore.from_leaderboard(score) for score in reply.scores],
        )
