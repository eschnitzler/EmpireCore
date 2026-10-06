"""
The running events, as the state keeps them, and their scoreboards.
"""

from __future__ import annotations

from empire_core.enums import RankingType
from empire_core.events.titles import get_event_titles
from empire_core.exceptions import EventHasNoPointsError, EventNotRunningError
from empire_core.gamedata.ids.events import Event
from empire_core.ranking.models import (
    GetHighscoreRequest,
    GetHighscoreResponse,
    GetRankingListRequest,
    GetRankingListResponse,
    GetRankingWindowRequest,
    GetRankingWindowResponse,
    SearchRankingListRequest,
    SearchRankingListResponse,
)
from empire_core.services.base import BaseService

from .models import (
    EVENT_SCOREBOARDS,
    POINT_EVENTS,
    BerimondEvent,
    EventScores,
    GameEvent,
    GetEventPointsRequest,
    GetEventPointsResponse,
    Scoreboard,
    SpecialEvent,
    SpecialEventInfoRequest,
)

# The part of an event's sei entry holding a board's league; other boards use the entry's own LID
_LEAGUE_PART = {
    RankingType.ALLIANCE_ALIEN_INVASION_PLAYER: "SP",
    RankingType.ALLIANCE_ALIEN_INVASION_ALLIANCE: "A",
    RankingType.ALLIANCE_RED_ALIEN_INVASION_PLAYER: "SP",
    RankingType.ALLIANCE_RED_ALIEN_INVASION_ALLIANCE: "A",
    RankingType.ALLIANCE_NOMADINVASION_ALLIANCE: "A",
    RankingType.SAMURAI_ALLIANCE: "A",
    RankingType.FACTION_INVASION_PLAYER_BLUE: "FB",
    RankingType.FACTION_INVASION_PLAYER_RED: "FR",
    RankingType.FACTION_INVASION_ALLIANCE: "A",
}


class EventsService(BaseService):
    """
    The server's active events, your event leagues and the events' scoreboards.

    Reached as client.events.
    """

    def get_active_event_ids(self) -> list[int]:
        """The running events' ids, in the order they started; empty before login."""
        return list(self.client.state.get_events())

    def refresh(self, timeout: float = 5.0) -> dict[int, SpecialEvent]:
        """
        Ask the server for the running events and return them once its ``sei`` is applied.

        The server's answer updates the events as any ``sei`` does; events it does not
        name keep running until a ``see`` or their time ends them. It asks for the ``sei``
        events only: the trigger events (the kingdoms league, the global effects) come with
        the login data's ``tei`` and the ``tei`` pushes.

        Raises:
            CommandError: The server refused the request
            EmpireTimeoutError: No ``sei`` within ``timeout``

        Client: ``C2SSpecialEventInfoVO`` (bundle line 37406)
        """
        self.send(SpecialEventInfoRequest(), wait=True, timeout=timeout)
        return self.client.state.get_events()

    def get_league_id(self, event_id: int, part: str | None = None) -> int:
        """
        Get the league your score is in for an event, the ``LID`` of its sei entry.

        Pass it as ``league_type_id`` to ``client.ranking.get_ranking_list``,
        ``get_own_ranking_page`` and ``get_ranking_window``, as the client's
        leaderboard dialogs do. :meth:`get_scores` reads it for you.

        Args:
            event_id: The event (EID)
            part: One part of the entry instead, for the invasion boards: ``SP`` (players),
                ``A`` (alliances), ``FB`` or ``FR`` (Berimond invasion's blue and red players)

        Returns:
            The league, 1 (the client's default) for a running event or part without one

        Raises:
            EventNotRunningError: The event is not running

        Client: ``AScoreEventVO.parseBasicsFromParamObject`` (bundle line 14967), defaults at
        bundle line 14965, read by ``GlobalLeaderBoardLeagueComponent`` (bundle line 100470)
        """
        found = self.client.state.get_event(event_id)
        if found is None:
            raise EventNotRunningError(event_id)
        if part is not None:
            parts = getattr(found, "parts", {})
            return parts[part].league_id if part in parts else 1
        league = getattr(found, "league_id", None)
        return league if isinstance(league, int) else 1

    def get_running_score_events(self) -> list[Event]:
        """The running events that have a scoreboard, in the order they started."""
        return [Event(eid) for eid in self.client.state.get_events() if eid in EVENT_SCOREBOARDS]

    def scoreboard(self, event: Event) -> Scoreboard:
        """
        The boards an event's dialogs open.

        Raises:
            ValueError: The event has no scoreboard; the message names the events that have one
        """
        board = EVENT_SCOREBOARDS.get(event) if isinstance(event, int) else None
        if board is None:
            names = ", ".join(f"Event.{e.name}" for e in EVENT_SCOREBOARDS)
            raise ValueError(f"event {event!r} has no scoreboard; these do: {names}")
        return board

    def get_scores(
        self,
        event: Event,
        *,
        alliance: bool = False,
        list_type: RankingType | None = None,
        rank: int | None = None,
        name: str | None = None,
        league_id: int | None = None,
        page_size: int = 10,
        timeout: float = 5.0,
    ) -> EventScores:
        """
        Get a page of a running event's scoreboard, the board its dialog opens.

        With neither ``rank`` nor ``name`` the page holds your own score, where the
        client's dialogs open; ``rank=1`` is the top of the board.

        Args:
            event: The event, e.g. ``Event.FACTION`` (Berimond); :data:`EVENT_SCOREBOARDS` lists those with a board
            alliance: Read the alliance board instead of the player board
            list_type: One of the event's boards by its list, for Berimond invasion's
                player boards (``FACTION_INVASION_PLAYER_BLUE`` or ``FACTION_INVASION_PLAYER_RED``)
            rank: The page from this rank (leaderboards), or the page around it (``hgh`` boards)
            name: The page around this name: ``hgh``'s search, or for a leaderboard its
                search (``slse``) and the page of the first hit
            league_id: Another of the event's leagues, whose top is then shown; by default
                your own as the sei packets gave it, 1 when they gave none (the client's
                default), and none for the donation board. While Berimond is locked to you
                (no ``UL`` in its sei entry) it opens on the top of league 1, as the client does
            page_size: Rows per page on the leaderboards (``M``); an ``hgh`` page is as long
                as the server makes it (8 rows, seen live)
            timeout: Timeout in seconds, per request

        Returns:
            The page; no rows when a leaderboard search finds no one (the client then
            shows your own page instead)

        Raises:
            EventNotRunningError: The event is not running
            ReplyMismatchError: The ``hgh`` reply is for a list that is not the event's
            ValueError: The event has no scoreboard or no such board; ``rank`` is below 1;
                ``alliance`` was given with a player board; Berimond invasion's player board was
                asked for without ``list_type``; ``rank`` and ``name`` were both given, or
                ``name`` is empty
            CommandError: The server refused the request
            EmpireTimeoutError: No answer; seen live for your own page of a player board
                with no event running

        Client: the ``hgh`` boards, ``CastleGenericHighscoreDialog`` (bundle line 30799),
        ``CastleGenericAllianceHighscoreDialog`` (bundle line 38103) and
        ``CastleGenericRankingComponent`` (bundle line 29585), send ``"-1"`` (or your rank)
        for your own page, ``"1"`` for the top and a name to search, with the board's league,
        and ``"1"`` in a league that is not yours (``scrollLeagueUp``, bundle line 30846);
        ``FactionRankingComponent.generateProperties`` (bundle line 95410) opens a locked
        Berimond (``FactionEventVO.isLocked``, bundle line 7379) on league 1 at ``"1"``;
        the leaderboards open on ``LeaderBoardDataProvider.getCurrentPlayerPage`` (bundle
        line 75941) from ``GlobalLeaderBoardComponent.onShow`` (bundle line 34990)
        """
        scoreboard = self.scoreboard(event)
        event = Event(event)
        if rank is not None and name is not None:
            raise ValueError("pass rank or name, not both")
        if rank is not None and rank < 1:
            raise ValueError("rank starts at 1")
        if name is not None and not name:
            raise ValueError("name must not be empty")
        if self.client.state.get_event(event) is None:
            raise EventNotRunningError(event)
        board = self._board(event, scoreboard, alliance, list_type)
        own_league = self._league(event, board)
        berimond = self.client.state.get_event(event)
        locked = isinstance(berimond, BerimondEvent) and not berimond.unlocked
        own_page = not locked if league_id is None else league_id == own_league
        if league_id is None:
            league_id = 1 if locked else own_league

        if not scoreboard.is_leaderboard:
            if name is not None:
                search = name
            elif rank is not None:
                search = str(rank)
            else:
                search = "-1" if own_page else "1"
            highscore = GetHighscoreRequest(list_type=board, league_type_id=league_id, search_value=search)
            return EventScores.from_highscore(
                event, board, self.request(highscore, GetHighscoreResponse, timeout=timeout)
            )

        page: GetRankingListResponse
        if rank is not None:
            request = GetRankingListRequest(list_type=board, league_type_id=league_id, max_results=page_size, rank=rank)
            page = self.request(request, GetRankingListResponse, timeout=timeout)
        elif name is not None:
            search_request = SearchRankingListRequest(list_type=board, search_value=name)
            found = self.request(search_request, SearchRankingListResponse, timeout=timeout)
            hit = next((result for result in found.results if result.score_ids), None)
            if hit is None:
                return EventScores(event=event, list_type=board, league_id=None)
            window = GetRankingWindowRequest(
                list_type=board, league_type_id=hit.league_type_id, max_results=page_size, score_id=hit.score_ids[0]
            )
            page = self.request(window, GetRankingWindowResponse, timeout=timeout)
        else:
            own = GetRankingWindowRequest(list_type=board, league_type_id=league_id, max_results=page_size, score_id="")
            page = self.request(own, GetRankingWindowResponse, timeout=timeout)
        return EventScores.from_leaderboard(event, board, page)

    def get_own_points(self, event: Event | int, timeout: float = 5.0) -> GetEventPointsResponse:
        """
        Ask the server for your rank and points in a running event.

        Works for the events in :data:`POINT_EVENTS`, those without a scoreboard too (the
        gacha events, the lucky wheel, the alliance tournament). The reply is applied to the
        event's state before this returns, so ``client.state.get_event(event)`` then holds
        them read the event's way (``own_rank``, ``own_points``, ``parts``, ...).

        Args:
            event: The event, e.g. ``Event.POINT_EVENT``
            timeout: Timeout in seconds

        Returns:
            The reply: its lists hold one value per score the event keeps, in the order
            :class:`GetEventPointsResponse` gives

        Raises:
            EventHasNoPointsError: The event keeps no rank and points (a shop or sale event);
                nothing is sent, as the server answers none (seen live)
            EventNotRunningError: The event is not running
            CommandError: The server refused the request
            EmpireTimeoutError: No answer within ``timeout``, or only one for another event

        Client: ``C2SPointEventGetPointsVO`` (bundle line 8697), sent by the event dialogs only for
        a running event (e.g. ``CastleFactionInvasionEventDialog.showLoaded``, bundle line 91529;
        ``CastleAllianceSamuraiInvasionDialogAllianceSublayer.show``, bundle line 98938);
        ``PEPCommand.exec`` (bundle line 128209)
        """
        if event not in POINT_EVENTS:
            try:
                event = Event(int(event))
            except ValueError:
                pass
            raise EventHasNoPointsError(event)
        if self.client.state.get_event(event) is None:
            raise EventNotRunningError(int(event))
        return self.request(GetEventPointsRequest(event_id=int(event)), GetEventPointsResponse, timeout=timeout)

    @staticmethod
    def _board(event: Event, scoreboard: Scoreboard, alliance: bool, list_type: RankingType | None) -> RankingType:
        if list_type is not None:
            if list_type not in scoreboard.lists:
                raise ValueError(f"{event.name} has no board {list_type!r}")
            if alliance and list_type != scoreboard.alliance_list:
                raise ValueError(f"{list_type!r} is not {event.name}'s alliance board")
            return RankingType(list_type)
        if alliance:
            if scoreboard.alliance_list is None:
                raise ValueError(f"{event.name} has no alliance board")
            return scoreboard.alliance_list
        if not scoreboard.player_lists:
            raise ValueError(f"{event.name} has no player board; pass alliance=True")
        if len(scoreboard.player_lists) > 1:
            names = " or ".join(f"RankingType.{board.name}" for board in scoreboard.player_lists)
            raise ValueError(f"{event.name} has a player board per faction; pass list_type={names}")
        return scoreboard.player_lists[0]

    def _league(self, event: Event, board: RankingType) -> int:
        # DonationEventDialogRanking (bundle line 115740) shows its board with no league;
        # AScoreEventVO (bundle line 14965) and FactionEventVO (bundle line 7353) start at league 1
        if event == 123:  # Event.DONATION_EVENT
            return -1
        return self.get_league_id(event, _LEAGUE_PART.get(board))

    def get_active_events(self, lang: str = "en", force_refresh: bool = False) -> list[GameEvent]:
        """
        The running events with their in-game titles, in the order they started.

        The titles come from the game's language CDN (see
        :func:`~empire_core.events.titles.get_event_titles`); without one, an event is
        named by its ``Event`` member, or its id when the library does not know it.
        An empty list means no event is running: a CDN outage only costs the titles.

        Args:
            lang: Language code for the titles (default: "en")
            force_refresh: Fetch the titles again even when the cached ones are fresh

        Example:
            for event in client.events.get_active_events():
                print(event.display_name, round(event.details.remaining_seconds()))
        """
        events = self.client.state.get_events()
        titles = get_event_titles(lang=lang, force_refresh=force_refresh) if events else {}
        return [
            GameEvent(
                event_id=eid,
                event=event.event,
                display_name=titles.get(eid) or (event.event.name if event.event is not None else str(eid)),
                details=event,
            )
            for eid, event in events.items()
        ]
