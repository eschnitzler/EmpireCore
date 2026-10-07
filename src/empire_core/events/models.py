"""
The running events as the state keeps them, the events that have a scoreboard, and a page of one
as ``client.events.get_scores`` returns it.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, NoReturn, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SerializeAsAny

from empire_core.enums import RankingType
from empire_core.exceptions import ReplyMismatchError
from empire_core.gamedata import EnumOrInt, RewardId
from empire_core.gamedata.ids.events import Event
from empire_core.map.models.areas import MapObject
from empire_core.protocol.base import BaseRequest, BaseResponse, GGECommand
from empire_core.protocol.js import (
    ClientInt,
    js_int,
    js_loose_equals,
    js_number,
    js_number_or_none,
    js_parse_int,
    js_same_number,
    js_string,
    js_truthy,
)
from empire_core.quests.models import Quest
from empire_core.ranking.models import (
    GetHighscoreResponse,
    GetRankingListResponse,
    HighscoreAllianceRow,
    HighscoreRow,
    HighscoreTournamentRow,
    LeaderboardScore,
)

if TYPE_CHECKING:
    from empire_core.gamedata import Event, GlobalEffect, QuestId, RaidBoss


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
    def from_highscore_row(cls, row: HighscoreRow) -> EventScore:
        """A ``hgh`` row: a player's, or an alliance's on an alliance board."""
        if isinstance(row, HighscoreAllianceRow):
            return cls(
                rank=row.rank,
                points=row.score,
                name=row.alliance.name,
                alliance_id=row.alliance.alliance_id,
                alliance_name=row.alliance.name,
                member_count=row.alliance.member_count,
            )
        if isinstance(row, HighscoreTournamentRow):
            return cls(rank=row.rank, points=row.score, name=row.player_name, player_id=row.player_id)
        owner = row.owner or MapObject()
        return cls(
            rank=row.rank,
            points=row.score,
            name=owner.owner_name or "",
            player_id=owner.owner_id or 0,
            alliance_id=owner.alliance_id or 0,
            alliance_name=owner.alliance_name,
            level=owner.level,
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
        A ``hgh`` reply.

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
        rows = [EventScore.from_highscore_row(row) for row in reply.rows]
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


# The running events, as client.state.get_events() holds them

_DAY = 86400.0


_K = TypeVar("_K")
_V = TypeVar("_V")


class ReadOnlyDict(dict[_K, _V]):
    """A dict that refuses changes, so an event model handed out never changes."""

    def _refuse(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise TypeError("an event's mappings are read-only; the state replaces the event instead")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _refuse  # type: ignore[assignment]

    def __reduce__(self) -> tuple[Any, ...]:
        return (type(self), (dict(self),))

    def __copy__(self) -> ReadOnlyDict[_K, _V]:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> ReadOnlyDict[_K, _V]:
        return self


def _frozen(value: Any) -> Any:
    """A read-only copy: dicts as ReadOnlyDict, lists as tuples, all the way down."""
    if isinstance(value, dict):
        return ReadOnlyDict({key: _frozen(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_frozen(item) for item in value)
    return value


_Raw = Annotated[dict[str, Any], AfterValidator(_frozen)]
_Parts = Annotated[dict[str, "EventPart"], AfterValidator(ReadOnlyDict)]


def _now(now: float | None) -> float:
    return time.monotonic() if now is None else now


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_score(values: dict[str, Any], entry: dict[str, Any]) -> None:
    for key, field in (("LID", "league_id"), ("OR", "own_rank"), ("ST", "sub_type"), ("OP", "own_points")):
        if js_truthy(entry.get(key)):
            values[field] = js_int(entry[key])
    if js_truthy(entry.get("SC")):
        values["point_scale"] = js_int(entry["SC"])
    if js_truthy(entry.get("LRSI")):
        values["leaderboard_reward_set_id"] = js_int(entry["LRSI"])


def _first(values: Any, index: int) -> Any:
    return values[index] if isinstance(values, list) and len(values) > index else None


def _with_points(model: Any, ranks: Any, points: Any, maxima: Any, index: int = 0) -> Any:
    update: dict[str, Any] = {}
    if (rank := _first(ranks, index)) is not None:
        update["own_rank"] = js_int(rank)
    if (point := _first(points, index)) is not None:
        update["own_points"] = js_int(point)
    if (most := _first(maxima, index)) is not None:
        update["max_points"] = js_int(most)
    return model.model_copy(update=update) if update else model


class _ScoreFields(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    league_id: int = Field(default=1, alias="LID", description="Your league")
    own_rank: int = Field(default=-1, alias="OR", description="Your rank, -1 while unranked")
    own_points: int = Field(default=0, alias="OP", description="Your points")
    max_points: int = Field(default=0, description="The most points the event counts, from the pep pushes")
    sub_type: int = Field(default=0, alias="ST", description="The score's sub type")
    point_scale: int = Field(
        default=1, alias="SC", description="The factor the reward thresholds after the first scale by"
    )
    leaderboard_reward_set_id: int = Field(default=0, alias="LRSI", description="The leaderboard's reward set")


class EventPart(_ScoreFields):
    """
    One score of an event with several: an invasion's player or alliance score, or a raid's own score.

    Client: ``ALeagueTypeScoreEventVO.parseBasicsFromParamObject`` (bundle line 10260) over
    ``AScoreEventVO.parseBasicsFromParamObject`` (bundle line 14967), defaults at bundle line 14965;
    ``AScoreEventVO.setRankAndPoints`` (bundle line 15044) for a ``pep``
    """

    reward_set_id: int = Field(default=0, alias="RSID", description="The reward set")

    @classmethod
    def parse(cls, entry: Any, previous: EventPart | None = None, sub_type: int = 0) -> EventPart:
        """A part read from its entry, over ``previous`` when the client keeps the part."""
        entry = _dict(entry)
        values: dict[str, Any] = dict(previous) if previous is not None else {"sub_type": sub_type}
        _read_score(values, entry)
        values["reward_set_id"] = js_int(entry.get("RSID"))
        return cls(**values)


class SpecialEvent(BaseModel):
    """
    A running event, as its ``sei`` (or ``tei``) entries left it.

    Events the library has no class for keep only these fields and the entries in ``raw``.

    Client: ``ASpecialEventVO`` (bundle lines 2953-3049): ``parseBasicsFromParamObject`` (bundle
    line 2958) sets the end from ``RS`` when it is truthy, ``isActive`` (bundle line 3039);
    ``SpecialEventSeasonLeagueComponent.parseServerData`` (bundle line 64551) reads ``KL``
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    # Whether the class's parseParamObject reaches ASpecialEventVO's, which reads KL
    _reads_kl: ClassVar[bool] = True
    # The parts the class rebuilds from every entry, so a part an entry lacks is gone
    _rebuilt_parts: ClassVar[tuple[str, ...]] = ()
    is_trigger: ClassVar[bool] = False
    """Whether the event is a trigger event (``tei``): the kingdoms league or a global effect event."""

    event_id: int = Field(alias="EID", description="The event's id")
    event: Event | None = Field(default=None, description="The event, None for an id the event table lacks")
    end_time: float = Field(
        default=0.0, description="When the event ends, in time.monotonic() seconds; inf while it has no end"
    )
    updated_at: float = Field(default=0.0, description="When an entry for the event was last applied, wall clock")
    kingdoms_league_mode: bool = Field(
        default=False, alias="KL", description="Whether the event runs in the kingdoms league's season mode"
    )
    raw: _Raw = Field(
        default_factory=ReadOnlyDict,
        description="The event's entries merged, the last one's keys winning; read-only, lists as tuples",
    )

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds until the event ends, 0 once it has."""
        return max(0.0, self.end_time - _now(now))

    def is_active(self, now: float | None = None) -> bool:
        """Whether the event has not ended yet."""
        return self.end_time > _now(now)

    @classmethod
    def from_entry(
        cls,
        event_id: int,
        entry: dict[str, Any],
        previous: SpecialEvent | None,
        now: float,
        events: Mapping[int, SpecialEvent],
    ) -> SpecialEvent:
        """
        The event an entry makes of ``previous``, or of nothing for a new event.

        Fields the entry reads only when it has them keep their value from ``previous``;
        ``events`` are the other running events.
        """
        values: dict[str, Any] = dict(previous) if previous is not None else {}
        values.update(event_id=event_id, event=_EVENT_IDS.get(event_id))
        cls._read(values, entry, now, events)
        raw = {**previous.raw, **entry} if previous is not None else dict(entry)
        for part in cls._rebuilt_parts:
            if part not in entry:
                raw.pop(part, None)
        values.update(raw=raw, updated_at=time.time())
        return cls(**values)

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        if js_truthy(remaining := entry.get("RS")) and (seconds := js_number_or_none(remaining)) is not None:
            values["end_time"] = now + seconds
        if cls._reads_kl:
            values["kingdoms_league_mode"] = js_truthy(entry.get("KL"))

    @classmethod
    def accepts(cls, entry: dict[str, Any]) -> bool:
        """Whether the client reads the entry at all, rather than failing on it and leaving the event as it was."""
        return True

    def with_points(self, ranks: Any, points: Any, maxima: Any) -> SpecialEvent:
        """The event after a ``pep`` with these ``OR``, ``OP`` and ``PT``; unchanged for an event without a score."""
        return self


class ScoredEvent(SpecialEvent, _ScoreFields):
    """
    An event with a score of your own.

    Client: ``AScoreEventVO.parseBasicsFromParamObject`` (bundle line 14967), defaults at bundle line
    14965; ``setRankAndPoints`` (bundle line 15044) for a ``pep``
    """

    difficulty_id: int = Field(
        default=-1, alias="EDID", description="The difficulty chosen, -1 before one is; 0 without difficulty scaling"
    )
    difficulty_scaling: bool = Field(default=False, alias="EASE", description="Whether the event scales its difficulty")
    parts: _Parts = Field(default_factory=ReadOnlyDict, description="The event's scores by their entry key; read-only")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        if entry.get("EDID") is not None:
            values["difficulty_id"] = js_int(entry["EDID"])
        scaling = entry.get("EASE") is not None and js_int(entry["EASE"]) == 1
        values["difficulty_scaling"] = scaling
        if not scaling:
            values["difficulty_id"] = 0
        _read_score(values, entry)

    def with_points(self, ranks: Any, points: Any, maxima: Any) -> SpecialEvent:
        return _with_points(self, ranks, points, maxima)  # type: ignore[no-any-return]


class PointEvent(ScoredEvent):
    """
    The nobility contest, and the base of :class:`LuckyWheelEvent`: the lucky wheels keep the same score
    (``LuckyWheelEventVO`` holds a ``LuckyWheelPointEventTypeScoreEventVO``, an
    ``APointEventTypeScoreEventVO``; bundle lines 59673, 117131).

    Client: ``APointEventTypeScoreEventVO.parseBasicsFromParamObject`` (bundle line 59997)
    """

    point_event_type: int = Field(default=-1, alias="PET", description="Which contest it is")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        if js_truthy(entry.get("PET")):
            values["point_event_type"] = js_int(entry["PET"])


class LeagueScoredEvent(ScoredEvent):
    """
    A score event whose rewards come from a reward set.

    Client: ``ALeagueTypeScoreEventVO.parseBasicsFromParamObject`` (bundle line 10260)
    """

    reward_set_id: int = Field(default=0, alias="RSID", description="The reward set")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["reward_set_id"] = js_int(entry.get("RSID"))


class BeggingKnightsEvent(LeagueScoredEvent):
    """
    The marauders' contest.

    Client: ``BeggingKnightsEventVO.parseBasicsFromParamObject`` (bundle line 114780)
    """

    total_hours: int = Field(default=0, alias="TH", description="The contest's length in hours")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["total_hours"] = js_int(entry.get("TH"))


class LongTermPointEvent(LeagueScoredEvent):
    """
    The grand nobility prize.

    Client: ``LongTermPointEventEventVO.parseParamObject`` (bundle line 116555)
    """

    upcoming_event_ids: tuple[EnumOrInt["Event"], ...] = Field(
        default=(), alias="UE", description="The events whose points count towards it"
    )

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        if js_truthy(upcoming := entry.get("UE")) and isinstance(upcoming, list):
            values["upcoming_event_ids"] = [js_int(eid) for eid in upcoming]


class GachaEvent(LeagueScoredEvent):
    """
    A gacha event.

    Client: ``AGachaEventVO.parseGachaEvent`` (bundle line 15371)
    """

    free_chest_reset_time: float = Field(
        default=0.0, alias="FCRT", description="When the free chest comes back, in time.monotonic() seconds"
    )

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        if js_truthy(reset := entry.get("FCRT")) and (seconds := js_number_or_none(reset)) is not None:
            values["free_chest_reset_time"] = now + seconds


class InvasionEvent(ScoredEvent):
    """
    An invasion: its player and alliance scores are its ``parts``.

    Client: ``SamuraiInvasionEventVO.parseData`` (bundle line 55680) and ``FactionInvasionEventVO.parseData``
    (bundle line 116044) rebuild every part from every entry; ``setRankAndPoints`` (bundle lines 55701,
    116056) give a ``pep``'s first rank and points to the first part, and so on
    """

    # Each part's key and sub type, in the order a pep counts them
    _parts: ClassVar[tuple[tuple[str, int], ...]] = (("SP", 0), ("A", 1))
    _pep_reads_maxima: ClassVar[bool] = False

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["parts"] = cls._read_parts(dict(values.get("parts") or {}), entry)

    @classmethod
    def _read_parts(cls, parts: dict[str, EventPart], entry: dict[str, Any]) -> dict[str, EventPart]:
        return {key: EventPart.parse(entry.get(key), sub_type=sub_type) for key, sub_type in cls._parts}

    def with_points(self, ranks: Any, points: Any, maxima: Any) -> SpecialEvent:
        parts = dict(self.parts)
        for index, (key, _) in enumerate(self._parts):
            if key in parts:
                parts[key] = _with_points(parts[key], ranks, points, maxima if self._pep_reads_maxima else None, index)
        return self.model_copy(update={"parts": ReadOnlyDict(parts)})


class SamuraiInvasionEvent(InvasionEvent):
    """The samurai invasion. Client: ``SamuraiInvasionEventVO.parseData`` (bundle line 55680)"""

    _rebuilt_parts = ("SP", "A")


class FactionInvasionEvent(InvasionEvent):
    """
    The Berimond invasion: ``FB`` and ``FR`` are the blue and red players' scores, ``A`` the alliance's.

    Client: ``FactionInvasionEventVO.parseData`` (bundle line 116044), ``setRankAndPoints`` (bundle line 116056)
    """

    _parts = (("FB", 2), ("FR", 3), ("A", 1))
    _rebuilt_parts = ("FB", "FR", "A")
    _pep_reads_maxima = True


class AlienInvasionEvent(InvasionEvent):
    """
    The war of the realms (71) and the Bloodcrow invasion (103); a part is rebuilt only from an entry that has it.

    Client: ``AAlienInvasionEventVO.parseData`` and ``parseParamObject`` (bundle lines 58910, 58918),
    ``setRankAndPoints`` (bundle line 58926)
    """

    target_zone_id: int = Field(default=0, alias="TZID", description="The zone the invasion targets")
    source_zone_id: int = Field(default=0, alias="SZID", description="The zone the invasion comes from")
    use_reroll: bool = Field(default=False, alias="CRE", description="Whether camps can be rerolled")
    reroll_currency_keys: tuple[str, ...] = Field(default=(), alias="RCKS", description="The currencies a reroll costs")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["use_reroll"] = js_loose_equals(entry.get("CRE"), 1)
        if js_truthy(keys := entry.get("RCKS")) and isinstance(keys, list):
            values["reroll_currency_keys"] = [js_string(key) for key in keys]
        values["target_zone_id"] = js_int(entry.get("TZID"))
        values["source_zone_id"] = js_int(entry.get("SZID"))

    @classmethod
    def _read_parts(cls, parts: dict[str, EventPart], entry: dict[str, Any]) -> dict[str, EventPart]:
        for key, sub_type in cls._parts:
            if js_truthy(entry.get(key)):
                parts[key] = EventPart.parse(entry[key], sub_type=sub_type)
        return parts


class NomadInvasionEvent(InvasionEvent):
    """
    The nomad invasion: ``SP`` and ``A`` (rebuilt from an entry that has them) and, while the khan
    camp runs (``ACE``), the camp's score ``AC``.

    The client shows the khan camp's level (from the items' ``allianceInvasionCamps`` row of
    ``khan_camp_id``) as that part's points; the state has no game data, so ``parts["AC"]``
    keeps the points the entry sent.

    Client: ``AllianceNomadInvasionEventVO.parseData`` (bundle lines 114287-114288), whose constructor
    (bundle line 114286) starts both scores; ``setRankAndPoints`` (bundle line 114310)
    """

    alliance_rage: int = Field(default=0, description="The khan camp's alliance rage")
    player_rage: int = Field(default=0, description="Your current rage points on the khan camp")
    player_total_rage: int = Field(default=0, description="Your total rage points on the khan camp")
    khan_camp_id: int | None = Field(default=None, description="The khan camp, None before one is sent")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        camp = entry.get("AC")
        if js_loose_equals(entry.get("ACE"), 1) and js_truthy(camp):
            camp = _dict(camp)
            values["alliance_rage"] = js_int(camp.get("AR"))
            values["player_rage"] = js_int(camp.get("PCRP"))
            values["player_total_rage"] = js_int(camp.get("PTRP"))
            values["khan_camp_id"] = js_int(camp.get("ACID"))

    @classmethod
    def _read_parts(cls, parts: dict[str, EventPart], entry: dict[str, Any]) -> dict[str, EventPart]:
        for key, sub_type in cls._parts:
            if js_truthy(entry.get(key)):
                parts[key] = EventPart.parse(entry[key], sub_type=sub_type)
            else:
                parts.setdefault(key, EventPart())
        if js_loose_equals(entry.get("ACE"), 1):
            camp = entry.get("AC")
            source = camp if js_truthy(camp) else {"LID": 1, "RSID": entry.get("RSID")}
            parts["AC"] = EventPart.parse(source, sub_type=16)
        return parts


class BerimondEvent(SpecialEvent):
    """
    Battle for Berimond. Your rank and points come only from ``pep`` pushes and start over with each entry.

    Client: ``FactionEventVO.parseData`` (bundle line 7354) builds the league scores anew,
    ``parseParamObject`` and ``loadFactionDataFromParamObject`` (bundle lines 7364-7365), the
    defaults at bundle line 7353; ``setRankAndPoints`` (bundle line 7461)
    """

    league_id: int = Field(default=1, alias="LID", description="Your league")
    unlocked: bool = Field(default=False, alias="UL", description="Whether Berimond is open to you")
    reward_set_id: int = Field(default=0, alias="RSID", description="The reward set")
    own_rank: int = Field(default=-1, description="Your rank, -1 while unranked; from the pep pushes")
    own_points: int = Field(default=0, description="Your points, from the pep pushes")
    faction_id: int = Field(default=0, description="Your faction")
    main_camp_id: int = Field(default=0, description="Your faction's main camp")
    faction_protection_status: int = Field(default=0, description="Your faction protection's status")
    faction_protection_end: float | None = Field(
        default=0.0, description="When your faction protection ends, in time.monotonic() seconds"
    )
    beginner_protection_end: float = Field(
        default=0.0, description="When your beginner protection ends, in time.monotonic() seconds"
    )

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["own_rank"], values["own_points"] = -1, 0
        values["reward_set_id"] = js_int(entry.get("RSID"))
        values["unlocked"] = js_truthy(entry.get("UL"))
        if js_truthy(faction := entry.get("FN")):
            faction = _dict(faction)
            values["faction_id"] = js_int(faction.get("FID"))
            values["main_camp_id"] = js_int(faction.get("MC"))
            protection = 0 if faction.get("PMT") is None else js_number_or_none(faction["PMT"])
            values["faction_protection_end"] = None if protection is None else now + protection
            values["faction_protection_status"] = js_int(faction.get("PMS"))
            if js_truthy(beginner := faction.get("NS")) and (seconds := js_number_or_none(beginner)) is not None:
                values["beginner_protection_end"] = now + seconds
        if js_truthy(entry.get("LID")):
            values["league_id"] = js_int(entry["LID"])

    def with_points(self, ranks: Any, points: Any, maxima: Any) -> SpecialEvent:
        return _with_points(self, ranks, points, None)  # type: ignore[no-any-return]


class RaidBossEvent(SpecialEvent):
    """
    The alliance raid boss: ``score`` is your own score, the alliance's is in ``alliance_points``.

    Client: ``AllianceRaidbossEventEventVO.parseData`` and ``parseParamObject`` (bundle lines 9109-9110),
    defaults at bundle line 9108; ``setRankAndPoints`` (bundle line 9117); ``PEPCommand.exec`` (bundle
    lines 128215-128216) for ``BLPP``
    """

    _reads_kl = False

    score: EventPart = Field(default_factory=EventPart, description="Your score; its points are the entry's SP.OP")
    league_id: int = Field(default=0, description="Your alliance's league, from the entry's A")
    alliance_points: int = Field(default=0, description="Your alliance's points, from the entry's A and the pep pushes")
    alliance_rank: int = Field(default=0, description="Your alliance's rank, from the pep pushes")
    subdivision_id: int = Field(default=0, description="Your alliance's subdivision, from the entry's A")
    division_round_id: int = Field(default=0, alias="DRI", description="The division round")
    raid_boss_ids: tuple[EnumOrInt["RaidBoss"], ...] = Field(
        default=(), alias="RBIDS", description="The bosses that can be fought"
    )
    boss_level_points: int = Field(default=0, alias="BLPP", description="The points on the current boss level")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        ids = entry.get("RBIDS")
        values["raid_boss_ids"] = [js_int(boss) for boss in ids] if isinstance(ids, list) else []
        if entry.get("BLPP") is not None:
            values["boss_level_points"] = js_int(entry["BLPP"])
        own = {**entry, "OP": _dict(entry.get("SP")).get("OP")}
        values["score"] = EventPart.parse(own, values.get("score"))
        if js_truthy(alliance := entry.get("A")):
            alliance = _dict(alliance)
            values["alliance_points"] = js_int(alliance.get("OP"))
            values["league_id"] = js_int(alliance.get("LID"))
            values["subdivision_id"] = js_int(alliance.get("SDI"))
        values["division_round_id"] = js_int(entry.get("DRI"))

    def with_points(self, ranks: Any, points: Any, maxima: Any) -> SpecialEvent:
        update: dict[str, Any] = {"score": _with_points(self.score, ranks, points, None)}
        if isinstance(points, list) and len(points) > 1:
            update["alliance_points"] = js_int(points[1])
            update["alliance_rank"] = js_int(_first(ranks, 1))
        return self.model_copy(update=update)


class TempServerEvent(SpecialEvent):
    """
    A temporary server.

    Client: ``TempServerEventVO.parseParamObject`` (bundle line 118162), defaults at bundle line 118161
    """

    _reads_kl = False

    daily_reset_time: float = Field(
        default=0.0, alias="RD", description="When the daily scores reset, in time.monotonic() seconds"
    )
    setting_id: int | None = Field(default=None, alias="TSID", description="The server's settings")
    castle_bought: bool = Field(default=False, alias="IPS", description="Whether you have a castle there")
    is_cross_play: bool = Field(default=False, alias="ICSE", description="Whether the server is a cross-play one")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        if js_truthy(reset := entry.get("RD")) and (seconds := js_number_or_none(reset)) is not None:
            values["daily_reset_time"] = now + seconds
        if js_truthy(entry.get("TSID")):
            values["setting_id"] = js_int(entry["TSID"])
        values["castle_bought"] = js_loose_equals(entry["IPS"], 1) if entry.get("IPS") is not None else True
        if js_truthy(entry.get("ICSE")):
            values["is_cross_play"] = js_loose_equals(entry["ICSE"], 1)


class DonationEvent(SpecialEvent):
    """
    Imperial patronage.

    Client: ``DonationEventEventVO.parseParamObject`` (bundle line 115502)
    """

    _reads_kl = False

    setting_id: int | None = Field(default=None, alias="DSI", description="The donation settings")
    leaderboard_reward_set_id: int | None = Field(
        default=None, alias="LRSI", description="The leaderboard's reward set"
    )

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["setting_id"] = None if entry.get("DSI") is None else js_int(entry["DSI"])
        values["leaderboard_reward_set_id"] = None if entry.get("LRSI") is None else js_int(entry["LRSI"])


class KingdomsLeagueEvent(SpecialEvent):
    """
    The kingdoms league, a trigger event. It runs while it has more than a day left; on its last
    day it ends with the season event (the running event with ``kingdoms_league_mode``), and
    without one it runs on at one day and has ended at none.

    Client: ``SeasonLeagueEventVO.parseParamObject`` and ``endTimestamp`` (bundle lines 118059-118063),
    ``SeasonLeagueData.getActiveSeasonEventVO`` (bundle line 142582)
    """

    is_trigger = True

    remaining_days: int = Field(default=0, alias="KLRD", description="Days left")
    original_days: int = Field(default=0, alias="KLRT", description="The league's length in days")
    reward_set_id: int = Field(default=0, alias="RSID", description="The reward set")
    has_alliance_ranking: bool = Field(default=False, alias="KLARE", description="Whether alliances are ranked too")
    league_type_id: int = Field(default=0, alias="KLLID", description="The league type")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["remaining_days"] = js_int(entry.get("KLRD"))
        values["original_days"] = js_int(entry.get("KLRT"))
        values["reward_set_id"] = js_int(entry.get("RSID"))
        values["has_alliance_ranking"] = js_loose_equals(entry.get("KLARE"), 1)
        values["league_type_id"] = js_int(entry.get("KLLID") or 0)
        values["end_time"] = cls._end(values["remaining_days"], events, now, values.get("event_id"))

    @staticmethod
    def _end(days: int, events: Mapping[int, SpecialEvent], now: float, own_id: int | None) -> float:
        if days > 1:
            return math.inf
        season = next((e for e in events.values() if e.kingdoms_league_mode and e.event_id != own_id), None)
        if season is not None:
            return season.end_time
        return math.inf if days == 1 else now + days * _DAY

    def end_with(self, events: Mapping[int, SpecialEvent], now: float) -> float:
        """When the league ends while ``events`` run."""
        return self._end(self.remaining_days, events, now, self.event_id)

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds until the league ends; its days left while it has no end."""
        if math.isinf(self.end_time):
            return max(0.0, self.remaining_days * _DAY)
        return super().remaining_seconds(now)


class GlobalEffectTimer(BaseModel):
    """One global effect of a global effect event."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    effect_id: EnumOrInt["GlobalEffect"] = Field(description="The global effect")
    end_time: float = Field(description="When it ends, in time.monotonic() seconds")
    strength: int = Field(description="Its strength, -1 for the effect's own")
    seen: bool = Field(description="Whether you have seen it")


class GlobalEffectEvent(SpecialEvent):
    """
    The global effects running, a trigger event that ends with the last of them.

    Client: ``GlobalEffectEventVO.parseParamObject`` (bundle lines 116399-116413)
    """

    is_trigger = True

    effects: tuple[GlobalEffectTimer, ...] = Field(default=(), alias="GE", description="The effects")
    seen_effect_ids: tuple[EnumOrInt["GlobalEffect"], ...] = Field(
        default=(), alias="SGE", description="The effects you have seen"
    )

    @classmethod
    def accepts(cls, entry: dict[str, Any]) -> bool:
        # parseParamObject reads SGE.indexOf and each effect's [0] as it goes, so an effect
        # without an SGE list, or a null effect, throws and parseServerEventData drops the entry
        effects = entry.get("GE")
        if not isinstance(effects, list) or not effects:
            return True
        return isinstance(entry.get("SGE"), (list, str)) and all(effect is not None for effect in effects)

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        seen = entry.get("SGE")
        seen_ids = [js_int(effect) for effect in seen] if isinstance(seen, list) else []
        effects, end = [], 0.0
        listed = entry.get("GE")
        for effect in listed if isinstance(listed, list) else ():
            if not isinstance(effect, list) or len(effect) < 2:
                continue
            # seconds * 1000 in JavaScript: null counts as 0, NaN never wins
            seconds = 0 if effect[1] is None else js_number_or_none(effect[1])
            if seconds is None:
                continue
            effect_id = js_int(effect[0])
            strength = js_int(effect[2] if len(effect) > 2 else None)
            effects.append(
                GlobalEffectTimer(
                    effect_id=effect_id, end_time=now + seconds, strength=strength, seen=effect_id in seen_ids
                )
            )
            end = max(end, now + seconds)
        values.update(effects=effects, seen_effect_ids=seen_ids, end_time=end)


class GlobalEffectBoost(BaseModel):
    """A global effect a boost event can strengthen."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    effect_id: EnumOrInt["GlobalEffect"] = Field(alias="GEID", description="The global effect")
    boost_value: float = Field(alias="BV", description="How much the boost adds")
    cost: int = Field(alias="C2", description="The boost's price in rubies")


class GlobalEffectBuffEvent(SpecialEvent):
    """
    The global effect boost, a trigger event that ends when the global effect event running as it
    arrived ends (at once without one).

    Client: ``GlobalEffectBuffEventVO.parseParamObject`` (bundle lines 116381-116383),
    ``getBoostValues`` (bundle line 116384)
    """

    is_trigger = True

    boosts: tuple[GlobalEffectBoost, ...] = Field(default=(), alias="GEB", description="The effects it boosts")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        boosts = entry.get("GEB")
        values["boosts"] = [
            GlobalEffectBoost(
                effect_id=js_int(b.get("GEID")), boost_value=js_number(b.get("BV")), cost=js_int(b.get("C2"))
            )
            for b in (boosts if isinstance(boosts, list) else ())
            if isinstance(b, dict)
        ]
        effects = events.get(Event.GLOBAL_EFFECT)
        values["end_time"] = max(effects.end_time, now) if effects is not None else 0.0

    def boost_value(self, effect_id: GlobalEffect | int) -> float:
        """
        What the boost adds to a global effect's strength: the first matching boost's, 0 for one it lists none for.

        Client: ``GlobalEffectBuffEventVO.getBoostValueForGlobalEffect`` (bundle line 116390)
        """
        return next((boost.boost_value for boost in self.boosts if boost.effect_id == effect_id), 0.0)


class AllianceTournamentEvent(ScoredEvent):
    """
    The alliance tournament: your own score, and your alliance's in ``parts["A"]``, which the ``pep`` pushes update.

    Client: ``AlliTournamentEventVO.parseData`` (bundle line 114401) reads ``A`` into its
    ``ALeagueTypeScoreEventVO`` (kept from entry to entry), ``setRankAndPoints`` (bundle line 114412)
    """

    @classmethod
    def accepts(cls, entry: dict[str, Any]) -> bool:
        # AlliTournamentEventVO.parseData (bundle line 114401) hands n.A to its score, which throws without it
        return entry.get("A") is not None

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        parts = dict(values.get("parts") or {})
        parts["A"] = EventPart.parse(entry["A"], parts.get("A"))
        values["parts"] = parts

    def with_points(self, ranks: Any, points: Any, maxima: Any) -> SpecialEvent:
        alliance = _with_points(self.parts.get("A", EventPart()), ranks, points, None)
        return self.model_copy(update={"parts": ReadOnlyDict({**self.parts, "A": alliance})})


class AllianceMobilizationEvent(ScoredEvent):
    """
    The alliance mobilisation: ``parts["SP"]`` is your score and ``parts["A"]`` your alliance's,
    both rebuilt from every entry in the league of ``A.LID`` with the entry's ``RSID``.

    The client keeps an alliance score per league of the event's league types, and none for a
    league outside them; the state has no game data, so it keeps the one for your league
    whenever ``A.LID`` is 1 or more.

    Client: ``AllianceMobilizationEventEventVO.parseData`` (bundle lines 5074-5081),
    ``setRankAndPoints`` (bundle line 5101)
    """

    _rebuilt_parts = ("SP", "A")

    subdivision_id: int = Field(default=0, description="Your alliance's subdivision, from the entry's A")
    division_round_id: int = Field(default=0, alias="DRI", description="The division round")

    @classmethod
    def accepts(cls, entry: dict[str, Any]) -> bool:
        # parseData reads A.LID and writes SP.LID, so a missing A or SP throws
        return entry.get("A") is not None and entry.get("SP") is not None

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        alliance, own = _dict(entry["A"]), _dict(entry["SP"])
        league, reward_set = js_int(alliance.get("LID")), js_int(entry.get("RSID"))
        values["league_id"] = league
        values["subdivision_id"] = js_int(alliance.get("SDI"))
        values["division_round_id"] = js_int(entry.get("DRI"))
        parts = {"SP": EventPart.parse({**own, "LID": league, "RSID": reward_set})}
        if league >= 1:
            parts["A"] = EventPart.parse({**alliance, "LID": league, "RSID": reward_set}, sub_type=1)
        values["parts"] = parts

    def with_points(self, ranks: Any, points: Any, maxima: Any) -> SpecialEvent:
        parts = dict(self.parts)
        for index, key in enumerate(("SP", "A")):
            if key in parts:
                parts[key] = _with_points(parts[key], ranks, points, None, index)
        return self.model_copy(update={"parts": ReadOnlyDict(parts)})


class LuckyWheelEvent(PointEvent):
    """
    The lucky wheel (15) and the sale days lucky wheel (89): a point event score and the wheel's state.

    The client keeps the wheel's win class and its progress as sent; the library reads them as numbers.

    Client: ``LuckyWheelEventVO.parseData``, ``parseParamObject`` and ``setRankAndPoints`` (bundle lines
    59674, 59686, 59687), ``LuckyWheelData.parseBasics`` (bundle line 17562); ``SaleDaysLuckyWheelEventVO``
    (bundle line 117842) reads the same
    """

    _reads_kl = False

    has_visited_pro_mode: bool = Field(default=False, alias="HVPM", description="Whether you opened the pro mode")
    has_free_spin: bool = Field(default=False, alias="HFS", description="Whether a free spin is waiting")
    pro_mode: bool = Field(default=False, alias="PMA", description="Whether the pro mode is on")
    win_class: int = Field(default=0, alias="CWC", description="The wheel's current win class")
    win_class_progress: float = Field(default=0.0, alias="WCP", description="The progress towards the next win class")
    jackpot_set_id: int = Field(default=0, alias="JSID", description="The next jackpot set")
    jackpot_spin_set_id: int = Field(default=0, alias="JHID", description="The jackpot set of the next jackpot spin")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values.update(
            has_visited_pro_mode=js_truthy(entry.get("HVPM")),
            has_free_spin=js_truthy(entry.get("HFS")),
            pro_mode=js_truthy(entry.get("PMA")),
            win_class=js_int(entry.get("CWC")),
            win_class_progress=js_number(entry.get("WCP")),
            jackpot_set_id=js_int(entry.get("JSID")),
            jackpot_spin_set_id=js_int(entry.get("JHID")),
        )

    def with_points(self, ranks: Any, points: Any, maxima: Any) -> SpecialEvent:
        return _with_points(self, ranks, points, None)  # type: ignore[no-any-return]


class ArtifactEvent(SpecialEvent):
    """
    An artifact event: the parts of the artifact you have found.

    Client: ``ArtifactEventVO.parseBasicsFromParamObject`` and ``parseParamObject`` (bundle lines 59141, 59161)
    """

    _reads_kl = False

    artifact_league_id: int = Field(default=0, alias="ALID", description="Your artifact league")
    parts_found: int = Field(default=0, alias="PF", description="The artifact parts you have found")
    skin_id: int = Field(default=0, alias="SID", description="The event's skin")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["artifact_league_id"] = js_int(entry.get("ALID"))
        values["parts_found"] = js_int(entry.get("PF"))
        values["skin_id"] = js_int(entry.get("SID"))


class SeasonEvent(SpecialEvent):
    """
    A season event: the Thornking (2), the Sea Queen (4) or the Underworld (64).

    Client: ``ASeasonEventVO.parseParamObject`` (bundle line 31376); ``ThornkingEventVO``,
    ``SeaqueenEventVO`` and ``UnderworldEventVO.parseParamObject`` (bundle lines 118454, 117975, 118678)
    read ``UL.MID`` first, the Thornking's through ``int()`` and the others' as sent; the library
    reads every one through ``int()``
    """

    _reads_kl = False

    unlocked: bool = Field(default=False, description="Whether the event is open to you, from UL.UL")
    reward_id: int | None = Field(default=None, alias="RID", description="The reward the event's end gives")
    finished: bool = Field(default=False, alias="F", description="Whether you have finished the event")
    map_id: int | None = Field(default=None, description="The event's treasure map, from UL.MID")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        if js_truthy(unlock := entry.get("UL")):
            unlock = _dict(unlock)
            if js_truthy(unlock.get("MID")):
                values["map_id"] = js_int(unlock["MID"])
            values["unlocked"] = js_truthy(unlock.get("UL"))
        if js_truthy(entry.get("RID")):
            values["reward_id"] = js_int(entry["RID"])
        values["finished"] = js_int(entry.get("F")) == 1


class FameBoosterEvent(SpecialEvent):
    """The fame booster. Client: ``FameboosterEventVO.parseParamObject`` (bundle line 116103)"""

    _reads_kl = False

    bonus_percent: int = Field(default=0, alias="GBP", description="The extra glory, in percent")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["bonus_percent"] = js_int(entry.get("GBP"))


class AllianceBonusEvent(SpecialEvent):
    """
    An alliance payment bonus: the prime alliance bonus (45) or the alliance payment bonus (55).

    Client: ``PrimeAlliBonusEventVO`` and ``AlliPaymentBonusEventVO.parseParamObject`` (bundle lines 117469, 114367)
    """

    _reads_kl = False

    bonus_percent: int = Field(default=0, alias="APP", description="The bonus, in percent")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["bonus_percent"] = js_int(entry.get("APP"))


class DiscountSaleEvent(SpecialEvent):
    """
    A prime sale with one discount: the relic enchanter sale (88) or the season pass sale (599).

    Client: ``RelicEnchanterPrimeSaleEventVO`` and ``SeasonPassPrimeSaleEventVO.parseParamObject``
    (bundle lines 117746, 118084)
    """

    _reads_kl = False

    discount: int = Field(default=0, alias="DIS", description="The discount, in percent")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["discount"] = js_int(entry.get("DIS"))


class SkipForFreeEvent(SpecialEvent):
    """Free skips. Client: ``SkipForFreeEventVO.parseParamObject`` (bundle line 118150)"""

    _reads_kl = False

    free_skip_seconds: int = Field(
        default=0, alias="SEC", description="A wait this long or shorter is skipped for free"
    )

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["free_skip_seconds"] = js_int(entry.get("SEC"))


class GiftEvent(SpecialEvent):
    """The Goodgame gift. Client: ``GGSGiftEventVO.parseParamObject`` (bundle line 116370)"""

    _reads_kl = False

    collected: bool = Field(default=False, alias="AC", description="Whether you have collected the gift")
    skin_id: int | None = Field(default=None, alias="SID", description="The gift's skin, None before one is sent")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["collected"] = js_number(entry.get("AC")) > 0
        if js_truthy(entry.get("SID")):
            values["skin_id"] = js_parse_int(entry["SID"])


class FortuneTellerEvent(SpecialEvent):
    """The fortune teller. Client: ``FortuneTellerEventVO.parseParamObject`` (bundle line 116134)"""

    tries: int = Field(default=0, alias="FTDC", description="Today's readings")
    daily_reset_time: float | None = Field(
        default=None, alias="STR", description="When the readings reset, in time.monotonic() seconds; None without STR"
    )

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["tries"] = js_int(entry.get("FTDC"))
        seconds = js_number_or_none(entry.get("STR"))
        values["daily_reset_time"] = None if seconds is None else now + seconds


class TournamentRank(BaseModel):
    """
    One place of the tournament of fame's ranking: ``[rank, fame points, owner record]``.

    Client: ``TournamentEventVO.parseParamObject`` (bundle line 118596), ``CastleOtherPlayerData.parseOwnerInfo``
    (bundle line 138996), which reads nothing from a record without an ``OID``
    """

    model_config = ConfigDict(frozen=True)

    rank: int = Field(description="The place")
    fame_points: int = Field(description="The fame the player has earned, read through int()")
    owner: MapObject | None = Field(default=None, description="The player; None for a record without an OID")

    @classmethod
    def from_row(cls, row: list[Any]) -> TournamentRank:
        """A ranking row; a missing fame or owner reads as 0 or None."""
        record = row[2] if len(row) > 2 else None
        owner = MapObject.model_validate(record) if isinstance(record, dict) and js_truthy(record.get("OID")) else None
        return cls(rank=js_int(row[0]), fame_points=js_int(row[1] if len(row) > 1 else None), owner=owner)


class TournamentEvent(SpecialEvent):
    """
    The tournament of fame: the ranking, your place and the fame you have earned.

    Client: ``TournamentEventVO.parseParamObject`` (bundle lines 118593-118598)
    """

    _reads_kl = False

    own_rank: int = Field(default=0, alias="OR", description="Your rank")
    own_fame_points: int = Field(default=0, alias="OEP", description="The fame you have earned")
    booby_prize_min_fame: int = Field(default=0, alias="MFB", description="The fame the consolation prize needs")
    ranking: tuple[TournamentRank, ...] = Field(
        default=(),
        alias="R",
        description="The ranking by place; an entry's rows replace the places they name, the others stay",
    )

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        values["own_rank"] = js_int(entry.get("OR"))
        values["own_fame_points"] = js_int(entry.get("OEP"))
        values["booby_prize_min_fame"] = js_int(entry.get("MFB"))
        rows = entry.get("R")
        if isinstance(rows, list):
            places = {place.rank: place for place in values.get("ranking", ())}
            for row in rows:
                if isinstance(row, list) and row:
                    place = TournamentRank.from_row(row)
                    places[place.rank] = place
            values["ranking"] = tuple(sorted(places.values(), key=lambda place: place.rank))


class CampaignEvent(SpecialEvent):
    """
    A time-limited campaign: its quests, in the order they open, and its end reward.

    A ``cqs`` push reads its campaign over it again (see :meth:`with_campaign`). The client turns
    ``RIDS`` into the rewards' collectables at once (``rewardData.getListByIdArray``); the game data
    is loaded only on request here, so the ids are kept, and ``data.reward_list(event.reward_ids)``
    gives the same list.

    Client: ``TimeLimitedCampaignEventEventVO.parseParamObject`` and ``sortByOrder`` (bundle lines
    118536-118549), which sorts by ``ST`` and then ``CQID``, a quest without ``ST`` last
    """

    _reads_kl = False

    reward_ids: tuple[RewardId, ...] = Field(
        default=(),
        alias="RIDS",
        description="The campaign's rewards; GameData.reward_list gives what they hold",
    )
    reward_collected: bool = Field(default=False, alias="COL", description="Whether you collected the end reward")
    end_reward_value: int = Field(default=0, alias="ERV", description="The end reward's value")
    quests: tuple[Quest, ...] = Field(default=(), alias="CQS", description="The campaign's quests, in campaign order")

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        cls._read_campaign(values, entry, now)

    @staticmethod
    def _read_campaign(values: dict[str, Any], entry: dict[str, Any], now: float) -> None:
        ids, listed = entry.get("RIDS"), entry.get("CQS")
        quests = (
            [Quest.from_entry(quest, now) for quest in listed if isinstance(quest, dict)]
            if isinstance(listed, list)
            else []
        )
        quests.sort(
            key=lambda quest: (quest.campaign_timestamp is None, quest.campaign_timestamp or 0, quest.campaign_quest_id)
        )
        values.update(
            reward_ids=[RewardId(js_int(rid)) for rid in ids] if isinstance(ids, list) else [],
            reward_collected=js_loose_equals(entry.get("COL"), 1),
            end_reward_value=js_int(entry.get("ERV")),
            quests=quests,
        )

    def with_campaign(self, data: dict[str, Any], now: float) -> CampaignEvent:
        """The event after a ``cqs`` push with this payload. Client: ``parseCQS`` (bundle line 118555)"""
        values: dict[str, Any] = dict(self)
        self._read_campaign(values, data, now)
        values["updated_at"] = time.time()
        return type(self)(**values)


class CampaignQuestEvent(SpecialEvent):
    """
    The time-limited campaign's quest event; its end is the end of the campaign quests it names.

    Client: ``TimeLimitedCampaignQuestEventEventVO.parseParamObject`` (bundle line 118576);
    ``CastleQuestVO.remainingSeconds`` (bundle line 52592)
    """

    _reads_kl = False

    quest_ids: tuple[EnumOrInt["QuestId"], ...] = Field(
        default=(), alias="CQS", description="The campaign quests it times, each QID read through int()"
    )

    @classmethod
    def accepts(cls, entry: dict[str, Any]) -> bool:
        # parseParamObject reads CQS.length
        return entry.get("CQS") is not None

    @classmethod
    def _read(
        cls, values: dict[str, Any], entry: dict[str, Any], now: float, events: Mapping[int, SpecialEvent]
    ) -> None:
        super()._read(values, entry, now, events)
        listed = entry["CQS"]
        values["quest_ids"] = [js_int(_dict(quest).get("QID")) for quest in listed] if isinstance(listed, list) else []


_EVENT_IDS: dict[int, Event] = {int(e): e for e in Event}

EVENT_CLASSES: dict[Event, type[SpecialEvent]] = {
    Event.FACTION: BerimondEvent,
    Event.POINT_EVENT: PointEvent,
    Event.BEGGING_KNIGHTS: BeggingKnightsEvent,
    Event.LONG_TERM_POINT_EVENT: LongTermPointEvent,
    Event.ALLIANCE_ALIEN_INVASION: AlienInvasionEvent,
    Event.RED_ALLIANCE_ALIEN_INVASION: AlienInvasionEvent,
    Event.ALLIANCE_NOMAD_INVASION: NomadInvasionEvent,
    Event.SAMURAI_INVASION: SamuraiInvasionEvent,
    Event.FACTION_INVASION: FactionInvasionEvent,
    Event.ALLIANCE_RAIDBOSS_EVENT: RaidBossEvent,
    Event.TEMP_SERVER: TempServerEvent,
    Event.DONATION_EVENT: DonationEvent,
    Event.GACHA_DECO2X2: GachaEvent,
    Event.CHRISTMAS_GACHA: GachaEvent,
    Event.EASTER_GACHA: GachaEvent,
    Event.SUMMER_GACHA: GachaEvent,
    Event.ANNIVERSARY_GACHA: GachaEvent,
    Event.HALLOWEEN_GACHA: GachaEvent,
    Event.BLACK_FRIDAY_GACHA: GachaEvent,
    Event.CARNIVAL_GACHA: GachaEvent,
    Event.SEASON_LEAGUE: KingdomsLeagueEvent,
    Event.GLOBAL_EFFECT: GlobalEffectEvent,
    Event.GLOBAL_EFFECT_BUFF: GlobalEffectBuffEvent,
    Event.ALLI_TOURNAMENT: AllianceTournamentEvent,
    Event.ALLIANCE_MOBILIZATION_EVENT: AllianceMobilizationEvent,
    Event.LUCKY_WHEEL: LuckyWheelEvent,
    Event.SALE_DAYS_LUCKY_WHEEL: LuckyWheelEvent,
    **dict.fromkeys(
        (Event.ARTIFACT_19, Event.ARTIFACT_23, Event.ARTIFACT_29, Event.ARTIFACT_30, Event.ARTIFACT_67), ArtifactEvent
    ),
    **dict.fromkeys((Event.THORNKING, Event.SEAQUEEN, Event.UNDERWORLD), SeasonEvent),
    Event.FAMEBOOSTER: FameBoosterEvent,
    Event.PRIME_ALLI_BONUS: AllianceBonusEvent,
    Event.ALLI_PAYMENT_BONUS: AllianceBonusEvent,
    Event.RELIC_ENCHANTER_PRIME_SALE: DiscountSaleEvent,
    Event.SEASON_PASS_PRIME_SALE: DiscountSaleEvent,
    Event.SKIP_FOR_FREE: SkipForFreeEvent,
    Event.GGS_GIFT: GiftEvent,
    Event.FORTUNE_TELLER: FortuneTellerEvent,
    Event.TOURNAMENT: TournamentEvent,
    Event.TIME_LIMITED_CAMPAIGN_EVENT: CampaignEvent,
    Event.TIME_LIMITED_CAMPAIGN_QUEST_EVENT: CampaignQuestEvent,
}
"""The model each event's entries are read into; any other event is a plain :class:`SpecialEvent`.

Client: ``CastleSpecialEventFactory.createByEventType`` (bundle line 61602) picks the class from the
event's ``eventType``
"""


POINT_EVENTS: frozenset[Event] = frozenset(
    {
        Event.FACTION,
        Event.LUCKY_WHEEL,
        Event.ALLI_TOURNAMENT,
        Event.POINT_EVENT,
        Event.BEGGING_KNIGHTS,
        Event.ALLIANCE_ALIEN_INVASION,
        Event.ALLIANCE_NOMAD_INVASION,
        Event.SAMURAI_INVASION,
        Event.LONG_TERM_POINT_EVENT,
        Event.FACTION_INVASION,
        Event.SALE_DAYS_LUCKY_WHEEL,
        Event.RED_ALLIANCE_ALIEN_INVASION,
        Event.GACHA_DECO2X2,
        Event.CHRISTMAS_GACHA,
        Event.EASTER_GACHA,
        Event.ALLIANCE_MOBILIZATION_EVENT,
        Event.SUMMER_GACHA,
        Event.ANNIVERSARY_GACHA,
        Event.HALLOWEEN_GACHA,
        Event.ALLIANCE_RAIDBOSS_EVENT,
        Event.BLACK_FRIDAY_GACHA,
        Event.CARNIVAL_GACHA,
    }
)
"""The events that keep your rank and points, the ones a ``pep`` is answered for.

Client: ``CastleSpecialEventFactory.createByEventType`` (bundle line 61602) builds each event as
its ``eventType`` + ``EventVO``; these are the classes with a ``setRankAndPoints``, which
``PEPCommand.exec`` (bundle line 128213) calls: ``AScoreEventVO`` (bundle line 15044) and its
subclasses (the nobility contest, marauders, long-term points, alliance tournament (bundle line
114412), the invasions (bundle lines 55701, 58926, 114310, 116056), the alliance mobilisation
(bundle line 5101) and the gacha events, ``AGachaEventVO``, bundle line 15372), ``FactionEventVO``
(bundle line 7461), ``AllianceRaidbossEventEventVO`` (bundle line 9117) and ``LuckyWheelEventVO``
(bundle line 59687) with ``SaleDaysLuckyWheelEventVO`` (bundle line 117863). Every other event
class is an ``ASpecialEventVO`` (bundle line 2953) without one.
"""


def event_class(event_id: int) -> type[SpecialEvent]:
    """The model an event's entries are read into."""
    return EVENT_CLASSES.get(_EVENT_IDS.get(event_id), SpecialEvent)  # type: ignore[arg-type]


class SpecialEventInfoRequest(BaseRequest):
    """
    Ask for the running events; the server answers with a ``sei``.

    Command: sei
    Payload: {}

    Client: ``C2SSpecialEventInfoVO`` (bundle lines 37406-37407), which has no fields; sent
    after a temporary server castle is bought (bundle line 24305)
    """

    command = "sei"


class GetEventPointsRequest(BaseRequest):
    """
    Ask for your rank and points in a running event; the server answers with a ``pep``.

    Command: pep
    Payload: {"EID": event_id}

    Client: ``C2SPointEventGetPointsVO`` (bundle lines 8697-8698), sent as an event's dialog opens
    (e.g. ``CastlePointEventDialog``, bundle line 117419; ``FactionEventRankingsSublayer.show``,
    bundle line 95328) and after a marauders' contest payment (``BKPCommand``, bundle line 128199)
    """

    command = "pep"

    event_id: int = Field(alias="EID", description="The event, e.g. Event.POINT_EVENT")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a pep reply is about this event: its ``EID``, when sent, is the one asked for.

        Client: ``PEPCommand.exec`` (bundle line 128213) applies a reply to the event its ``EID`` names
        """
        if not isinstance(payload, dict) or "EID" not in payload:
            return True
        return js_same_number(payload["EID"], self.event_id)


class GetEventPointsResponse(BaseResponse):
    """
    Your rank and points in an event, pushed as you score and sent in answer to a :class:`GetEventPointsRequest`.

    ``OR``, ``OP`` and ``PT`` are lists, one value per score the event keeps, in this order:

    - a score event (nobility contest, marauders, long-term points, gacha): your own
      (``AScoreEventVO.setRankAndPoints``, bundle line 15044)
    - the alliance tournament: your alliance's, the first only (``AlliTournamentEventVO``, bundle line 114412)
    - Berimond and the lucky wheel: your own, the first only (``FactionEventVO``, bundle line 7461, into your
      league; ``LuckyWheelEventVO``, bundle line 59687)
    - the alien, red alien, nomad and samurai invasions and the alliance mobilisation: yours, then your
      alliance's; ``PT`` may be sent, these events do not read it (bundle lines 58926, 114310, 55701, 5101)
    - the Berimond invasion: blue players, red players, then your alliance, ``PT`` per part (bundle line 116056)
    - the alliance raid boss: yours, then your alliance's (bundle line 9117), and ``BLPP``

    Client: ``PEPCommand.exec`` (bundle lines 128213-128216), which hands the lists to the event's
    ``setRankAndPoints``; the state applies them the same way (``client.state.get_event``)
    """

    command: ClassVar[str] = GGECommand.PEP

    event_id: ClientInt = Field(alias="EID", description="The event")
    own_ranks: list[ClientInt] = Field(
        default_factory=list, alias="OR", description="Your ranks, one per score in the order above; -1 unranked"
    )
    own_points: list[ClientInt] = Field(
        default_factory=list, alias="OP", description="Your points, one per score in the order above"
    )
    max_points: list[ClientInt] | None = Field(
        default=None, alias="PT", description="The most points each score counts; None when not sent"
    )
    boss_level_points: ClientInt | None = Field(
        default=None, alias="BLPP", description="The points on the raid boss's current level; None for other events"
    )


class GameEvent(BaseModel):
    """A running event with its in-game title."""

    model_config = ConfigDict(frozen=True)

    event_id: int = Field(description="The event's id")
    event: Event | None = Field(default=None, description="The event, None for an id the event table lacks")
    display_name: str = Field(
        description="The in-game title; without one, the event's Event name, or its id for an unknown event"
    )
    details: SerializeAsAny[SpecialEvent] = Field(
        description="The running event, as client.state.get_event() gives it, dumped with its own fields"
    )
