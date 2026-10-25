"""
The running events, as the state keeps them, and their scoreboards.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, TypeVar

from pydantic import ValidationError

from empire_core.enums import RankingType
from empire_core.enums.events import RaidBossCardStatus
from empire_core.events.titles import get_event_titles
from empire_core.exceptions import (
    CommandError,
    EventHasNoPointsError,
    EventNotRunningError,
    PacketError,
    ReplyMismatchError,
)
from empire_core.gamedata.ids.events import Event
from empire_core.protocol.base import BaseRequest, BaseResponse
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

if TYPE_CHECKING:
    from empire_core.gamedata import RaidBoss

from .board_models import (
    GetBattlegroundRankRequest,
    GetBattlegroundRankResponse,
    GetBattlegroundTimersRequest,
    GetBattlegroundTimersResponse,
    GetPlayerPerformanceRequest,
    GetPlayerPerformanceResponse,
    GetTemporaryServerRanksRequest,
    GetTemporaryServerRanksResponse,
)
from .faction_models import (
    BerimondBalance,
    BerimondKingdomStatus,
    BerimondPoints,
    BerimondTarget,
    GetBerimondBalanceRequest,
    GetBerimondPointsRequest,
    GetBerimondTargetsRequest,
    GetBerimondTargetsResponse,
    SelectBerimondCampRequest,
)
from .models import (
    EVENT_SCOREBOARDS,
    POINT_EVENTS,
    BerimondEvent,
    EventScores,
    GameEvent,
    GetEventPointsRequest,
    GetEventPointsResponse,
    RaidBossEvent,
    Scoreboard,
    ScoredEvent,
    SpecialEvent,
    SpecialEventInfoRequest,
)
from .status_models import (
    AbortRaidRequest,
    AbortRaidResponse,
    CancelGrandTournamentQuestRequest,
    CancelGrandTournamentQuestResponse,
    CompleteGrandTournamentQuestRequest,
    CompleteGrandTournamentQuestResponse,
    GetGrandTournamentContributionsRequest,
    GetGrandTournamentContributionsResponse,
    GetGrandTournamentStatusRequest,
    GetRaidBossStatusRequest,
    GetRaidBossStatusResponse,
    GrandTournamentContribution,
    GrandTournamentQuestStatus,
    RaidBossStatus,
    RerollGrandTournamentQuestRequest,
    RerollGrandTournamentQuestResponse,
    SelectRaidBossRequest,
    SelectRaidBossResponse,
    SkipGrandTournamentCooldownRequest,
    SkipGrandTournamentCooldownResponse,
    StartGrandTournamentQuestRequest,
    StartGrandTournamentQuestResponse,
)

QuestActionResponse = TypeVar("QuestActionResponse", bound=BaseResponse)

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

    @property
    def running(self) -> dict[int, SpecialEvent]:
        """The running events by id, in the order they started; a copy."""
        return self.client.state.get_events()

    def is_running(self, event: Event | int) -> bool:
        """Whether an event runs and has not ended."""
        return self.client.state.is_event_active(event)

    def refresh(self, *, timeout: float = 5.0) -> dict[int, SpecialEvent]:
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

    def league_id(self, event: Event | int, part: str | None = None) -> int:
        """
        The league your score is in for a running event, the ``LID`` of its sei entry; nothing is sent.

        Pass it as ``league_type_id`` to ``client.ranking.get_ranking_list``,
        ``get_own_ranking_page`` and ``get_ranking_window``, as the client's
        leaderboard dialogs do. :meth:`get_scores` reads it for you.

        Args:
            event: The event (EID)
            part: One part of the entry instead, for the invasion boards: ``SP`` (players),
                ``A`` (alliances), ``FB`` or ``FR`` (Berimond invasion's blue and red players)

        Returns:
            The league, 1 (the client's default) for a running event or part without one

        Raises:
            EventNotRunningError: The event is not running

        Client: ``AScoreEventVO.parseBasicsFromParamObject`` (bundle line 14967), defaults at
        bundle line 14965, read by ``GlobalLeaderBoardLeagueComponent`` (bundle line 100470)
        """
        found = self.client.state.get_event(event)
        if found is None:
            raise EventNotRunningError(int(event))
        if part is not None:
            entry = found.parts.get(part) if isinstance(found, ScoredEvent) else None
            return 1 if entry is None else entry.league_id
        if isinstance(found, ScoredEvent | BerimondEvent | RaidBossEvent):
            return found.league_id
        return 1

    @property
    def running_score_events(self) -> list[Event]:
        """The running events that have a scoreboard, in the order they started; nothing is sent."""
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

    def get_own_points(self, event: Event | int, *, timeout: float = 5.0) -> GetEventPointsResponse:
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
        if len(scoreboard.player_lists) > 1:
            names = " or ".join(f"RankingType.{board.name}" for board in scoreboard.player_lists)
            raise ValueError(f"{event.name} has a player board per faction; pass list_type={names}")
        if not scoreboard.player_lists:
            raise ValueError(f"{event.name} has no player board; pass alliance=True")
        return scoreboard.player_lists[0]

    def _league(self, event: Event, board: RankingType) -> int:
        # DonationEventDialogRanking (bundle line 115740) shows its board with no league;
        # AScoreEventVO (bundle line 14965) and FactionEventVO (bundle line 7353) start at league 1
        if event == 123:  # Event.DONATION_EVENT
            return -1
        return self.league_id(event, _LEAGUE_PART.get(board))

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

    def get_battleground_rank(self, alliance_id: int, *, timeout: float = 5.0) -> GetBattlegroundRankResponse:
        """Request your alliance's current battleground rank (abgph).

        Requires a running battleground event. Supply your alliance on the event server.
        Client: ``CastleAllianceBattleGroundEventDialogScoring.show`` (bundle 71907).
        """
        self._require_running(Event.ALLIANCE_BATTLE_GROUND)
        return self.request(
            GetBattlegroundRankRequest(alliance_id=alliance_id), GetBattlegroundRankResponse, timeout=timeout
        )

    def get_battleground_timers(self, *, timeout: float = 5.0) -> GetBattlegroundTimersResponse:
        """Request seconds until the next battleground tower relink and revival.

        The event must run; the server refuses unavailable server context. Timers are a reply snapshot.
        Client: ``C2SAllianceBattleGroundGetTimersVO`` (bundle 54330), ``parseTRT`` (144811).
        """
        self._require_running(Event.ALLIANCE_BATTLE_GROUND)
        return self.request(GetBattlegroundTimersRequest(), GetBattlegroundTimersResponse, timeout=timeout)

    def get_player_performance(
        self, event: Event | int, player_id: int, *, timeout: float = 5.0
    ) -> GetPlayerPerformanceResponse:
        """Request a player's event points and performance counters (gpe).

        Requires the event to run. Replies contain no player/event identity; requests for gpe are
        serialized, but a late reply after a timeout cannot be distinguished from the next request.
        Client: ``C2SGetPlayerPerformanceVO`` (bundle 34268-34272), ``GPECommand`` (127239-127248).
        """
        self._require_running(event)
        return self.request(
            GetPlayerPerformanceRequest(event_id=int(event), player_id=player_id),
            GetPlayerPerformanceResponse,
            timeout=timeout,
        )

    def get_temporary_server_ranks(self, *, timeout: float = 5.0) -> GetTemporaryServerRanksResponse:
        """Request your current temporary-server daily and overall points/ranks.

        Requires a running temporary-server event; unavailable server context raises CommandError.
        Board pages use ranking.get_highscore; tsh has no pagination or previous-run selector.
        Client: ``TempServerEventVO.parseOwnRanks`` (bundle 118163).
        """
        self._require_running(Event.TEMP_SERVER)
        return self.request(GetTemporaryServerRanksRequest(), GetTemporaryServerRanksResponse, timeout=timeout)

    def get_berimond_targets(self, *, timeout: float = 5.0) -> tuple[BerimondTarget, ...]:
        """Request special camp candidate identifiers in Battle for Berimond.

        Requires the running event. Ids refer to special camps, not map area ids;
        request map and attack details separately for a target's coordinates and eligibility.
        Client: ``FactionCapitalMapobjectVO.parseAreaInfo`` / ``FactionTowerMapobjectVO.parseAreaInfo``
        (bundle 22772-22773, 22818-22819), ``AFDCommand`` (127742-127743).
        """
        self._require_running(Event.FACTION)
        return self.request(GetBerimondTargetsRequest(), GetBerimondTargetsResponse, timeout=timeout).targets

    def get_berimond_balance(self, *, timeout: float = 5.0) -> BerimondBalance:
        """Request the red and blue faction player counts in Battle for Berimond.

        Requires the running event. This read does not require choosing or joining a faction.
        Client: ``CastleDecoShopPanel.show`` (bundle 9302), ``FGBCommand`` (127789-127791).
        """
        self._require_running(Event.FACTION)
        return self.request(GetBerimondBalanceRequest(), BerimondBalance, timeout=timeout)

    def get_berimond_points(self, *, timeout: float = 5.0) -> BerimondPoints:
        """Request the red and blue faction points in Battle for Berimond.

        Requires the running event.
        Client: ``C2SGetFactionPointsVO`` (bundle 66177), ``GFPCommand`` (127917).
        """
        self._require_running(Event.FACTION)
        return self.request(GetBerimondPointsRequest(), BerimondPoints, timeout=timeout)

    def join_berimond(
        self, camp_id: int, *, ruby_camp: bool = False, spend_rubies: bool = False, timeout: float = 5.0
    ) -> None:
        """Join Battle for Berimond with one of its prebuilt camps.

        ``ruby_camp`` takes the camp whose only price is rubies, and needs ``spend_rubies``.
        Otherwise ``spend_rubies`` pays any missing resources with rubies.

        Raises:
            EventNotRunningError: Battle for Berimond is not running
            ValueError: ``ruby_camp`` without ``spend_rubies``
            CommandError: The server refused, e.g. ``FACTION_LAST_MAN_STANDING_ACTIVE``

        Client: ``FactionEventJoinSublayer.buyCamp`` (bundle 95197),
        ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (35237),
        ``PrebuiltCastleItemVO.isPremium`` (142354), ``FSCCommand`` (127885).
        """
        self._require_running(Event.FACTION)
        self._require_spend_rubies(spend_rubies, "the ruby camp costs rubies" if ruby_camp else None)
        request = SelectBerimondCampRequest(
            camp_id=camp_id, pay_with_rubies=spend_rubies and not ruby_camp, ruby_camp=ruby_camp
        )
        self.execute(request, timeout=timeout)

    @property
    def berimond_kingdom_status(self) -> BerimondKingdomStatus | None:
        """Battle for Berimond's last kingdom status; None while it is not running or none has come."""
        event = self.client.state.get_event(Event.FACTION)
        return event.kingdom_status if event is not None else None

    def _require_running(self, event: Event | int) -> SpecialEvent:
        found = self.client.state.get_event(event)
        if found is None:
            raise EventNotRunningError(int(event))
        return found

    def get_grand_tournament_status(self, *, timeout: float = 5.0) -> GrandTournamentQuestStatus:
        """Request alliance Grand Tournament quest slots and participating member count.

        Requires the running Grand Tournament event. Successful replies also update its quest_status.
        Client: ``AllianceMobilizationEventEventVO.requestAllianceQuestStatus`` (bundle 5117).
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        return self.request(
            GetGrandTournamentStatusRequest(event_id=int(Event.GRAND_TOURNAMENT)),
            GrandTournamentQuestStatus,
            timeout=timeout,
        )

    def get_grand_tournament_contributions(self, *, timeout: float = 5.0) -> tuple[GrandTournamentContribution, ...]:
        """Request player contributions for the current alliance Grand Tournament.

        The response carries no event identity; a late reply after timeout cannot be identified.
        Client: ``AllianceMobilizationEventDialogContributions.show`` (bundle 47205), AQPCCommand (127404).
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        return self.request(
            GetGrandTournamentContributionsRequest(event_id=int(Event.GRAND_TOURNAMENT)),
            GetGrandTournamentContributionsResponse,
            timeout=timeout,
        ).contributions

    def get_raid_boss_status(self, *, timeout: float = 5.0) -> RaidBossStatus:
        """Request current alliance raid boss, health, cards and walls.

        Requires the raid event. Successful replies and bbs broadcasts update RaidBossEvent.boss_status.
        An inactive status clears the active boss fields; missing identity/stage/walls preserve prior values
        exactly where the client does. Replies carry no event or alliance identity, so a late reply after
        timeout cannot be correlated. Refusals/transport failures raise without changing the event.
        Client: ``C2SGetAllianceRaidBossStatus`` (bundle 47183-47187), raid parser (76190-76205).
        """
        self._require_running(Event.ALLIANCE_RAIDBOSS_EVENT)
        deadline = time.monotonic() + timeout
        with self.client.connection.command_lock("bse", timeout=timeout):
            packet = self.client.request_packet(
                GetRaidBossStatusRequest(), "bse", timeout=max(0.0, deadline - time.monotonic())
            )
            if packet.error_code != 0:
                raise CommandError("bse", packet.error_code, packet.payload)
            try:
                GetRaidBossStatusResponse.model_validate(packet.payload)
            except ValidationError as error:
                raise PacketError(f"Could not parse 'bse' response: {error}") from error
            status = self.client.state._raid_status_reply(packet.payload)
            if status is None:
                raise PacketError("The 'bse' reply has no matching applied raid status")
            return status

    def start_grand_tournament_quest(
        self, slot_id: int, alliance_quest_id: int, *, timeout: float = 5.0
    ) -> StartGrandTournamentQuestResponse:
        """Accept a quest, consuming an event ticket. The server checks ticket balance and assignments.

        Client: C2S quest action and dialog (bundle 75732-75735, 75830-75833).
        Returns the exact nested slot update; participant counts remain unchanged.
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        return self._request_grand_tournament_action(
            StartGrandTournamentQuestRequest(
                event_id=int(Event.GRAND_TOURNAMENT), slot_id=slot_id, alliance_quest_id=alliance_quest_id
            ),
            StartGrandTournamentQuestResponse,
            timeout=timeout,
        )

    def complete_grand_tournament_quest(self, *, timeout: float = 5.0) -> CompleteGrandTournamentQuestResponse:
        """Collect the completed active quest. The server checks completion.

        Client: C2S quest action and dialog (bundle 75705-75708, 75779).
        Returns the exact nested slot update; participant counts remain unchanged.
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        return self._request_grand_tournament_action(
            CompleteGrandTournamentQuestRequest(event_id=int(Event.GRAND_TOURNAMENT)),
            CompleteGrandTournamentQuestResponse,
            timeout=timeout,
        )

    def cancel_grand_tournament_quest(
        self, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> CancelGrandTournamentQuestResponse:
        """Cancel the active quest; its configured cancelCostC2 defaults to 199 rubies.

        Client: C2S quest action and dialog (bundle 75696-75699, 75826-75827, 111069).
        Returns the exact nested slot update; participant counts remain unchanged.
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        self._require_spend_rubies(
            spend_rubies, "Cancel the active quest; its configured cancelCostC2 defaults to 199 rubies."
        )
        return self._request_grand_tournament_action(
            CancelGrandTournamentQuestRequest(event_id=int(Event.GRAND_TOURNAMENT)),
            CancelGrandTournamentQuestResponse,
            timeout=timeout,
        )

    def reroll_grand_tournament_quest(
        self, slot_id: int, alliance_quest_id: int, *, timeout: float = 5.0
    ) -> RerollGrandTournamentQuestResponse:
        """Reroll an unassigned quest; the client shows no currency charge.

        Client: C2S quest action and dialog (bundle 75714-75717, 75855).
        Returns the exact nested slot update; participant counts remain unchanged.
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        return self._request_grand_tournament_action(
            RerollGrandTournamentQuestRequest(
                event_id=int(Event.GRAND_TOURNAMENT), slot_id=slot_id, alliance_quest_id=alliance_quest_id
            ),
            RerollGrandTournamentQuestResponse,
            timeout=timeout,
        )

    def skip_grand_tournament_cooldown(
        self, slot_id: int, alliance_quest_id: int, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> SkipGrandTournamentCooldownResponse:
        """Skip a quest slot cooldown for 999 rubies.

        Client: C2S quest action and dialog (bundle 75723-75726, 34974).
        Returns the exact nested slot update; participant counts remain unchanged.
        """
        self._require_running(Event.GRAND_TOURNAMENT)
        self._require_spend_rubies(spend_rubies, "Skip a quest slot cooldown for 999 rubies.")
        return self._request_grand_tournament_action(
            SkipGrandTournamentCooldownRequest(
                event_id=int(Event.GRAND_TOURNAMENT), slot_id=slot_id, alliance_quest_id=alliance_quest_id
            ),
            SkipGrandTournamentCooldownResponse,
            timeout=timeout,
        )

    def _request_grand_tournament_action(
        self, request: BaseRequest, response_type: type[QuestActionResponse], *, timeout: float
    ) -> QuestActionResponse:
        deadline = time.monotonic() + timeout
        with self.client.connection.command_lock("aqs", timeout=timeout):
            context = self.client.state._begin_quest_action()
            try:
                result = self.request(request, response_type, timeout=max(0.0, deadline - time.monotonic()))
                current = self.client.state._quest_action_context()
                if context != current:
                    expected = context[1] if context is not None else None
                    received = current[1] if current is not None else None
                    raise ReplyMismatchError(
                        expected if expected is not None else -1, received if received is not None else -1
                    )
                return result
            finally:
                self.client.state._end_quest_action()

    def select_raid_boss(self, boss_id: RaidBoss | int, *, timeout: float = 5.0) -> SelectRaidBossResponse:
        """Select an available raid boss and return the server acknowledgement.

        The server checks leader/co-leader permission. Known cards must be available;
        a newer boss id is supported. No ruby payment is shown by the client.
        Status is updated by bbs broadcasts; call get_raid_boss_status for a fresh snapshot.
        Client: ``AllianceRaidBossCardItem.onClick`` (current bundle 75377),
        ``canManageAllianceRaid`` (current DLL 18796), ``SRBCommand`` (bundle 127571-127580).
        """
        event = self._require_running(Event.ALLIANCE_RAIDBOSS_EVENT)
        request = SelectRaidBossRequest(boss_id=boss_id)
        if isinstance(event, RaidBossEvent) and event.boss_status is not None:
            card = next((card for card in event.boss_status.cards if card.boss_id == boss_id), None)
            if card is not None and card.status != RaidBossCardStatus.AVAILABLE:
                raise ValueError("the raid boss card is not available")
        return self.request(request, SelectRaidBossResponse, timeout=timeout)

    def abort_raid(self, *, timeout: float = 5.0) -> AbortRaidResponse:
        """Abort the active raid boss and return the server acknowledgement.

        Requires leader/co-leader permission; the server checks it. A known inactive raid
        or last playable boss cannot be aborted. No ruby payment is shown by the client.
        This acknowledgement does not clear the boss; bbs supplies the resulting status.
        Client: ``AllianceRaidBossCardItem.handleAbort``, ``updateAbortButton`` (current bundle
        75351-75365), ``isLastPlayableBoss`` (76260-76263), ``ARBCommand`` (127528-127537).
        """
        event = self._require_running(Event.ALLIANCE_RAIDBOSS_EVENT)
        if isinstance(event, RaidBossEvent) and event.boss_status is not None:
            status = event.boss_status
            if not status.active:
                raise ValueError("there is no active raid to abort")
            locked = {RaidBossCardStatus.LOCKED_FINAL_DEFEATED, RaidBossCardStatus.LOCKED_ABORTED}
            if sum(card.status not in locked for card in status.cards) <= 1:
                raise ValueError("the last playable raid boss cannot be aborted")
        return self.request(AbortRaidRequest(), AbortRaidResponse, timeout=timeout)
