"""
The server's currently active events, and their scoreboards.
"""

from __future__ import annotations

from empire_core.enums import RankingType
from empire_core.exceptions import EventNotRunningError
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
from empire_core.utils.events import GameEvent
from empire_core.utils.events import get_active_events as _get_active_events

from .models import EVENT_SCOREBOARDS, EventScores, Scoreboard

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
        """
        Get list of currently active event IDs.

        Returns:
            List of event IDs (EID) from sei packet.
            Empty list if no events are active or not yet logged in.
        """
        return list(self.client.state.active_event_ids)  # Return copy, not reference

    def get_league_id(self, event_id: int, part: str | None = None) -> int | None:
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
            The league, or None when no sei entry for the event gave one

        Client: ``AScoreEventVO.parseBasicsFromParamObject`` (bundle line 14967),
        read by ``GlobalLeaderBoardLeagueComponent`` (bundle line 100470)
        """
        return self.client.state.get_event_league_id(event_id, part)

    def get_running_score_events(self) -> list[Event]:
        """The running events that have a scoreboard, in the order the sei packets named them."""
        return [Event(eid) for eid in self.get_active_event_ids() if eid in EVENT_SCOREBOARDS]

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
        if event not in self.get_active_event_ids():
            raise EventNotRunningError(event)
        board = self._board(event, scoreboard, alliance, list_type)
        own_league = self._league(event, board)
        locked = event is Event.FACTION and not self.client.state.is_event_unlocked(event)
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
            highscore = GetHighscoreRequest(LT=board, LID=league_id, SV=search)
            return EventScores.from_highscore(
                event, board, self.request(highscore, GetHighscoreResponse, timeout=timeout)
            )

        page: GetRankingListResponse
        if rank is not None:
            request = GetRankingListRequest(LT=board, LID=league_id, M=page_size, R=rank)
            page = self.request(request, GetRankingListResponse, timeout=timeout)
        elif name is not None:
            search_request = SearchRankingListRequest(LT=board, SV=name)
            found = self.request(search_request, SearchRankingListResponse, timeout=timeout)
            hit = next((result for result in found.results if result.score_ids), None)
            if hit is None:
                return EventScores(event=event, list_type=board, league_id=None)
            window = GetRankingWindowRequest(LT=board, LID=hit.league_type_id, M=page_size, SI=hit.score_ids[0])
            page = self.request(window, GetRankingWindowResponse, timeout=timeout)
        else:
            own = GetRankingWindowRequest(LT=board, LID=league_id, M=page_size, SI="")
            page = self.request(own, GetRankingWindowResponse, timeout=timeout)
        return EventScores.from_leaderboard(event, board, page)

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
        league = self.client.state.get_event_league_id(event, _LEAGUE_PART.get(board))
        return 1 if league is None else league

    def get_active_events(
        self,
        lang: str = "en",
        force_refresh: bool = False,
    ) -> list[GameEvent]:
        """
        Get currently active events with human-readable names resolved from the GGS CDN.

        Combines ``get_active_event_ids()`` with a CDN lookup to produce typed
        ``GameEvent`` objects. CDN data is cached after the first call.

        Args:
            lang: Language code for display names (default: "en").
            force_refresh: Force re-fetch of CDN data, bypassing the cache.

        Returns:
            List of GameEvent objects for currently active events. An empty
            list always means "no events are active" — CDN failures raise.

        Raises:
            NetworkError: The CDN fetch failed and no cached data exists, so
                the answer is unknown rather than empty.

        Example:
            events = client.events.get_active_events()
            event_names = {e.internal_name for e in events}

            if "Nomad" in event_names:
                # handle nomad event ...
                pass
        """
        event_ids = self.get_active_event_ids()
        return _get_active_events(event_ids, lang=lang, force_refresh=force_refresh)
