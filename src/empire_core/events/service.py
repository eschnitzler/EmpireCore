"""
The running events, as the state keeps them, and their scoreboards.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal, TypeVar

from pydantic import ValidationError

from empire_core.enums import Kingdom, RankingType, ServerType
from empire_core.enums.events import RaidBossCardStatus, WheelOfFortuneType, WorldCupVote
from empire_core.events.titles import get_event_titles
from empire_core.exceptions import (
    CommandError,
    EventHasNoPointsError,
    EventNotRunningError,
    PacketError,
    ReplyMismatchError,
)
from empire_core.gamedata import DonationItemId, EventDifficultyId, PartPayPriceId
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
    from empire_core.gamedata import PrebuiltCastle, RaidBoss, TreasureMapId

from .berimond_models import (
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
from .board_models import (
    GetHorizonRankRequest,
    GetHorizonRankResponse,
    GetHorizonTimersRequest,
    GetHorizonTimersResponse,
    GetOuterRealmsRanksRequest,
    GetOuterRealmsRanksResponse,
    GetPlayerPerformanceRequest,
    GetPlayerPerformanceResponse,
)
from .minigame_models import (
    BuyArtifactPieceRequest,
    BuyArtifactPieceResponse,
    BuyMaraudersContestPackageRequest,
    CollectorCurrencyResponse,
    ColossusCoinDepositRequest,
    ColossusCoinDepositResponse,
    ColossusDepositRequest,
    ColossusDepositResponse,
    DonateItemsRequest,
    DonateItemsResponse,
    DonationItemAmount,
    DonationItemPoints,
    FortuneTellerReadingRequest,
    FortuneTellerReadingResponse,
    GachaSpinRequest,
    GachaSpinResponse,
    GetCollectorCurrencyRequest,
    GetImperialPatronageProgressRequest,
    ImperialPatronageProgressResponse,
    SkipShadyLadyTargetRequest,
    SkipShadyLadyTargetResponse,
    ValidateShadyLadyTargetRequest,
    VoteWorldCupRequest,
    VoteWorldCupResponse,
    WheelOfFortuneBuyJackpotRequest,
    WheelOfFortuneBuyJackpotResponse,
    WheelOfFortuneChangeModeRequest,
    WheelOfFortuneChangeModeResponse,
    WheelOfFortuneIncreaseWinClassRequest,
    WheelOfFortuneIncreaseWinClassResponse,
    WheelOfFortuneSpinRequest,
    WheelOfFortuneSpinResponse,
)
from .models import (
    EVENT_SCOREBOARDS,
    POINT_EVENTS,
    BerimondEvent,
    ClaimAnnouncementRewardRequest,
    EventScores,
    GachaEvent,
    GameEvent,
    GetEventPointsRequest,
    GetEventPointsResponse,
    RiftRaidEvent,
    Scoreboard,
    ScoredEvent,
    SeasonEvent,
    ShuttingDownEvents,
    SpecialEvent,
    SpecialEventInfoRequest,
    TravelingKnightsEvent,
    WorldCupEvent,
)
from .progression_models import (
    DaimyoAreasResponse,
    DaimyoContractsResponse,
    DaimyoWarEffortsResponse,
    GetDaimyoAreasRequest,
    GetDaimyoContractsRequest,
    GetDaimyoWarEffortsRequest,
    SeasonJoinEventRequest,
    SelectEventDifficultyRequest,
    SelectEventDifficultyResponse,
    UnlockEventRequest,
    UnlockEventResponse,
)
from .season_models import JoinSeasonCampRequest, SelectSeasonCampRequest
from .special_server_models import (
    ApplyChargeCampEffectRequest,
    ApplyChargeCampEffectResponse,
    ChargeCampEffects,
    CurrentServer,
    GetChargeCampEffectsRequest,
    GetOuterRealmsCollectorPointsRequest,
    GetPreviousSpecialServerRunsRequest,
    OuterRealmsCollectorPoints,
    PreviousSpecialServerRuns,
    RerollChargeCampEffectRequest,
    RerollChargeCampEffectResponse,
    SelectSpecialServerCastleRequest,
    SelectSpecialServerCastleResponse,
    SpecialServerCastles,
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
    GetRiftRaidStatusRequest,
    GetRiftRaidStatusResponse,
    GrandTournamentContribution,
    GrandTournamentQuestStatus,
    RerollGrandTournamentQuestRequest,
    RerollGrandTournamentQuestResponse,
    RiftRaidStatus,
    SelectRaidBossRequest,
    SelectRaidBossResponse,
    SkipGrandTournamentCooldownRequest,
    SkipGrandTournamentCooldownResponse,
    StartGrandTournamentQuestRequest,
    StartGrandTournamentQuestResponse,
)

QuestActionResponse = TypeVar("QuestActionResponse", bound=BaseResponse)

# The event that runs each special server
_SPECIAL_SERVER_EVENTS = {
    ServerType.OUTER_REALMS: Event.OUTER_REALMS,
    ServerType.HORIZON: Event.BEYOND_THE_HORIZON,
}

_WOOD_COLOSSI = (Event.COLOSSUS_44, Event.COLOSSUS_57)

# The part of an event's sei entry holding a board's league; other boards use the entry's own LID
_LEAGUE_PART = {
    RankingType.WAR_OF_THE_REALMS_PLAYER: "SP",
    RankingType.WAR_OF_THE_REALMS_ALLIANCE: "A",
    RankingType.BLOODCROW_INVASION_PLAYER: "SP",
    RankingType.BLOODCROW_INVASION_ALLIANCE: "A",
    RankingType.ALLIANCE_NOMADINVASION_ALLIANCE: "A",
    RankingType.SAMURAI_ALLIANCE: "A",
    RankingType.BERIMOND_INVASION_PLAYER_BLUE: "FB",
    RankingType.BERIMOND_INVASION_PLAYER_RED: "FR",
    RankingType.BERIMOND_INVASION_ALLIANCE: "A",
}


class EventsService(BaseService):
    """
    The server's active events, your event leagues and the events' scoreboards.

    Reached as client.events.
    """

    @property
    def shutting_down(self) -> ShuttingDownEvents | None:
        """The events shutting down, whose buildings stay in your castles, from the last ``sde``; None until one
        arrived."""
        return self.client.state.get_shutting_down_events()

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
        if isinstance(found, ScoredEvent | BerimondEvent | RiftRaidEvent):
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
            event: The event, e.g. ``Event.BATTLE_FOR_BERIMOND``; those with a board are in :data:`EVENT_SCOREBOARDS`
            alliance: Read the alliance board instead of the player board
            list_type: One of the event's boards by its list, for Berimond invasion's
                player boards (``BERIMOND_INVASION_PLAYER_BLUE`` or ``BERIMOND_INVASION_PLAYER_RED``)
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
        gacha events, the Wheel of Fortune, the alliance tournament). The reply is applied to the
        event's state before this returns, so ``client.state.get_event(event)`` then holds
        them read the event's way (``own_rank``, ``own_points``, ``parts``, ...).

        Args:
            event: The event, e.g. ``Event.NOBILITY_CONTEST``
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
        if event == 123:  # Event.IMPERIAL_PATRONAGE
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

    def get_horizon_rank(self, alliance_id: int, *, timeout: float = 5.0) -> GetHorizonRankResponse:
        """Request your alliance's current Beyond the Horizon rank (abgph).

        Requires a running Beyond the Horizon event. Supply your alliance on the event server.
        Client: ``CastleAllianceBattleGroundEventDialogScoring.show`` (bundle 71907).
        """
        self._require_running(Event.BEYOND_THE_HORIZON)
        return self.request(GetHorizonRankRequest(alliance_id=alliance_id), GetHorizonRankResponse, timeout=timeout)

    def get_horizon_timers(self, *, timeout: float = 5.0) -> GetHorizonTimersResponse:
        """Request seconds until the next Beyond the Horizon tower relink and revival.

        The event must run; the server refuses unavailable server context. Timers are a reply snapshot.
        Client: ``C2SAllianceBattleGroundGetTimersVO`` (bundle 54330), ``parseTRT`` (144811).
        """
        self._require_running(Event.BEYOND_THE_HORIZON)
        return self.request(GetHorizonTimersRequest(), GetHorizonTimersResponse, timeout=timeout)

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

    def get_outer_realms_ranks(self, *, timeout: float = 5.0) -> GetOuterRealmsRanksResponse:
        """Request your current Outer Realms daily and overall points/ranks.

        Requires a running Outer Realms event; unavailable server context raises CommandError.
        Board pages use ranking.get_highscore; tsh has no pagination or previous-run selector.
        Client: ``TempServerEventVO.parseOwnRanks`` (bundle 118163).
        """
        self._require_running(Event.OUTER_REALMS)
        return self.request(GetOuterRealmsRanksRequest(), GetOuterRealmsRanksResponse, timeout=timeout)

    @property
    def current_server(self) -> CurrentServer | None:
        """The kind of server this session is on, from the last ``tse`` push; None until one arrived."""
        return self.client.state.get_current_server()

    @property
    def special_server_castles(self) -> SpecialServerCastles | None:
        """Your castles on the special servers, from the last ``tcc`` push; None until one arrived."""
        return self.client.state.get_special_server_castles()

    def select_special_server_castle(
        self,
        castle: PrebuiltCastle,
        server_type: ServerType,
        *,
        ruby_price: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Pick the pre-built castle you enter the Outer Realms or Beyond the Horizon with (tsc).

        Sent on the main server while the server's event runs. Then enter the server with
        ``client.connect_to_special_server(server_type)``, as the client connects once the pick is accepted.

        The server's castle selection prices the castle; one that costs rubies is bought at that price
        (``OC2``) and needs ``spend_rubies``. As in the client, a castle that costs nothing goes as bought
        with rubies, at 0 of them.

        Args:
            castle: The pre-built castle, one of the server's castle selection
            server_type: ``ServerType.OUTER_REALMS`` or ``ServerType.HORIZON``
            ruby_price: Buy the castle at its ruby price; it is anyway when the selection prices it in rubies
            spend_rubies: Allow spending the rubies the castle costs
            timeout: Timeout in seconds

        Raises:
            ValueError: ``server_type`` is the normal server, the server offers no such castle, it has no
                ruby price for ``ruby_price``, or it costs rubies without ``spend_rubies``
            EventNotRunningError: The server's event is not running
            CommandError: The server refused the pick

        Client: ``CastleSpecialServerPreBuildCastleSelectionDialog.onConfirmed`` (bundle lines 27953-27955),
        ``TSCCommand.executeCommand`` (bundle line 128531)
        """
        if server_type not in _SPECIAL_SERVER_EVENTS:
            raise ValueError("a castle is picked for a Outer Realms or Beyond the Horizon server")
        game_data = self._require_game_data()
        selections = (
            game_data.outer_realms_prebuilt_castles
            if server_type is ServerType.OUTER_REALMS
            else game_data.horizon_prebuilt_castles
        )
        selection, row = selections.get(castle), game_data.prebuilt_castles.get(castle)
        if selection is None or row is None:
            raise ValueError(f"prebuilt castle {int(castle)} is not in {server_type.name}'s castle selection")
        rubies = selection.cost_rubies(row)
        if ruby_price and rubies <= 0:
            raise ValueError(f"prebuilt castle {int(castle)} has no ruby price")
        self._require_spend_rubies(spend_rubies, f"the castle costs {rubies} rubies" if rubies else None)
        self._require_running(_SPECIAL_SERVER_EVENTS[server_type])
        self.request(
            SelectSpecialServerCastleRequest(
                castle_id=row.prebuilt_castle_id, ruby_castle=selection.is_ruby_castle(row), server_type=server_type
            ),
            SelectSpecialServerCastleResponse,
            timeout=timeout,
        )

    def get_outer_realms_collector_points(self, player_id: int, *, timeout: float = 5.0) -> int:
        """
        Request a player's collector points on the Outer Realms (tpc).

        Client: ``CastleCollectorEventData.getTempserverCollectorAmount`` (bundle line 134001),
        ``TPCCommand.executeCommand`` (bundle line 128516)
        """
        return self.request(
            GetOuterRealmsCollectorPointsRequest(player_id=player_id),
            OuterRealmsCollectorPoints,
            timeout=timeout,
        ).amount

    def get_charge_camp_effects(self, x: int, y: int, *, timeout: float = 5.0) -> ChargeCampEffects:
        """
        Request the Outer Realms charge camp's effect and the one a reroll offered (gce).

        Client: ``CastleTempServerEffectRerollDialog.showLoaded`` (bundle line 140279),
        ``GCECommand.executeCommand`` (bundle line 128501)
        """
        return self.request(GetChargeCampEffectsRequest(x=x, y=y), ChargeCampEffects, timeout=timeout)

    def reroll_charge_camp_effect(self, x: int, y: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Reroll the Outer Realms charge camp's effect for rubies (ccr); :meth:`get_charge_camp_effects`
        then shows the offered effect, and :meth:`apply_charge_camp_effect` takes it.

        Raises:
            ValueError: ``spend_rubies`` is False; a reroll always costs rubies
            CommandError: The server refused the reroll

        Client: ``CastleTempServerEffectRerollDialog.onClick`` (bundle line 140282), which shows the
        reroll's ``c2Cost`` (bundle line 140279); ``CCRCommand.executeCommand`` (bundle line 128488)
        """
        self._require_spend_rubies(spend_rubies, "a charge camp reroll costs rubies")
        self.request(RerollChargeCampEffectRequest(x=x, y=y), RerollChargeCampEffectResponse, timeout=timeout)

    def apply_charge_camp_effect(self, x: int, y: int, *, timeout: float = 5.0) -> None:
        """
        Take the rerolled effect in place of the Outer Realms charge camp's effect (ace).

        Client: ``CastleTempServerEffectRerollDialog.onClick`` (bundle line 140284),
        ``ACECommand.executeCommand`` (bundle line 128475)
        """
        self.request(ApplyChargeCampEffectRequest(x=x, y=y), ApplyChargeCampEffectResponse, timeout=timeout)

    def get_berimond_targets(self, *, timeout: float = 5.0) -> tuple[BerimondTarget, ...]:
        """Request special camp candidate identifiers in Battle for Berimond.

        Requires the running event. Ids refer to special camps, not map area ids;
        request map and attack details separately for a target's coordinates and eligibility.
        Client: ``FactionCapitalMapobjectVO.parseAreaInfo`` / ``FactionTowerMapobjectVO.parseAreaInfo``
        (bundle 22772-22773, 22818-22819), ``AFDCommand`` (127742-127743).
        """
        self._require_running(Event.BATTLE_FOR_BERIMOND)
        return self.request(GetBerimondTargetsRequest(), GetBerimondTargetsResponse, timeout=timeout).targets

    def get_berimond_balance(self, *, timeout: float = 5.0) -> BerimondBalance:
        """Request the red and blue faction player counts in Battle for Berimond.

        Requires the running event. This read does not require choosing or joining a faction.
        Client: ``CastleDecoShopPanel.show`` (bundle 9302), ``FGBCommand`` (127789-127791).
        """
        self._require_running(Event.BATTLE_FOR_BERIMOND)
        return self.request(GetBerimondBalanceRequest(), BerimondBalance, timeout=timeout)

    def get_berimond_points(self, *, timeout: float = 5.0) -> BerimondPoints:
        """Request the red and blue faction points in Battle for Berimond.

        Requires the running event.
        Client: ``C2SGetFactionPointsVO`` (bundle 66177), ``GFPCommand`` (127917).
        """
        self._require_running(Event.BATTLE_FOR_BERIMOND)
        return self.request(GetBerimondPointsRequest(), BerimondPoints, timeout=timeout)

    def join_berimond(self, camp: PrebuiltCastle, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """Join Battle for Berimond with one of its prebuilt camps, e.g. ``PrebuiltCastle.BERIMOND_SIMPLE_CAMP``.

        A camp whose only price is rubies is bought with them and needs ``spend_rubies``; any other is
        bought with its resources, the client's join offering no ruby price for it, and there
        ``spend_rubies`` pays the missing resources with rubies.

        Raises:
            EventNotRunningError: Battle for Berimond is not running
            ValueError: The camp is not Berimond's, needs a higher level, or costs rubies without ``spend_rubies``
            CommandError: The server refused, e.g. ``FACTION_LAST_MAN_STANDING_ACTIVE``

        Client: ``FactionEventJoinSublayer.buyCamp`` (bundle 95197) sends ``OC2`` for a camp that
        ``PrebuiltCastleItemVO.isPremium`` (142354); ``CastleResourceWaitDialogProperties.getResourceSkipCommand``
        (35237) sends ``PWR``; ``FSCCommand`` (127885).
        """
        self._require_running(Event.BATTLE_FOR_BERIMOND)
        row = self._prebuilt_castle(camp)
        if Kingdom.BERIMOND not in row.space_ids:
            raise ValueError(f"prebuilt castle {int(camp)} is no Battle for Berimond camp")
        rubies = self._castle_rubies(row, ruby_price=False)
        self._require_spend_rubies(spend_rubies, f"the camp costs {rubies} rubies" if rubies else None)
        request = SelectBerimondCampRequest(
            camp_id=row.prebuilt_castle_id, pay_with_rubies=spend_rubies and not rubies, ruby_camp=rubies > 0
        )
        self.execute(request, timeout=timeout)

    @property
    def berimond_kingdom_status(self) -> BerimondKingdomStatus | None:
        """Battle for Berimond's last kingdom status; None while it is not running or none has come."""
        event = self.client.state.get_event(Event.BATTLE_FOR_BERIMOND)
        return event.kingdom_status if event is not None else None

    def join_season_camp(self, event: Event, *, timeout: float = 5.0) -> None:
        """Enter a running season event's map at your camp there.

        Raises:
            EventNotRunningError: The event is not running
            ValueError: It is no season event, or names no map
            CommandError: The server refused

        Client: ``SeasonCampPanelButton.onButtonClicked`` (bundle line 108195) sends ``C2SJoinCampVO``
        with the running season event's map; ``JEACommand`` (bundle line 131625).
        """
        self.execute(JoinSeasonCampRequest(map_id=self._season_map(event)), timeout=timeout)

    def unlock_season_camp(
        self, camp: PrebuiltCastle, *, ruby_price: bool = False, spend_rubies: bool = False, timeout: float = 5.0
    ) -> None:
        """Start on a season event's map with one of its prebuilt camps, e.g. ``PrebuiltCastle.UNDERWORLD_SIMPLE_CAMP``.

        The camp names the map: the first of its spaces. A camp whose only price is rubies is bought with
        them; one priced in resources is bought with those, or with ``ruby_price`` at its ruby price, as the
        client's two buttons offer. Rubies spent need ``spend_rubies``; buying with resources,
        ``spend_rubies`` pays any missing ones with rubies.

        Raises:
            ValueError: The camp starts a kingdom, not a season event's map, needs a higher level, has no ruby
                price for ``ruby_price``, or costs rubies without ``spend_rubies``
            CommandError: The server refused

        Client: ``AUnlockPrebuiltCastle.buyPrebuiltCastle`` (bundle line 55482) sends ``csc`` for a castle with
        no space in ``WorldConst.WORLD_IDS``; ``UnlockPrebuiltCastleForRubies`` (bundle line 55514) sets ``OC2``
        for the castle ``CastleKingdomCastleDetails.getSublayerForCastle`` (bundle line 97911) shows as premium;
        ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (bundle line 35238) sends ``PWR``;
        ``CSCCommand`` (bundle line 128343).
        """
        row = self._prebuilt_castle(camp)
        if row.kingdom is not None or not row.space_ids:
            raise ValueError(f"prebuilt castle {int(camp)} is no season camp")
        rubies = self._castle_rubies(row, ruby_price)
        self._require_spend_rubies(spend_rubies, f"the camp costs {rubies} rubies" if rubies else None)
        request = SelectSeasonCampRequest(
            prebuilt_camp_id=row.prebuilt_castle_id,
            pay_with_rubies=spend_rubies and not rubies,
            ruby_camp=rubies > 0,
            space_id=row.space_ids[0],
        )
        self.execute(request, timeout=timeout)

    def open_season_map(self, event: Event) -> None:
        """Tell the server you opened a running season event's map, as the client does each time it shows it.

        The client reads no answer, so none is waited for.

        Raises:
            EventNotRunningError: The event is not running
            ValueError: It is no season event, or names no map

        Client: ``CastleSeasonMapScreen.show`` (bundle line 108619) sends ``C2SSeasonJoinEventVO`` with the map
        """
        self.send(SeasonJoinEventRequest(map_id=self._season_map(event)))

    def _season_map(self, event: Event) -> TreasureMapId | int:
        found = self._require_running(event)
        if not isinstance(found, SeasonEvent) or found.map_id is None:
            raise ValueError(f"{Event(event).name} is no season event with a map")
        return found.map_id

    def pay_toward_unlock(
        self,
        part_price_id: PartPayPriceId,
        *,
        wood: int = 0,
        stone: int = 0,
        coins: int = 0,
        castle_id: int = -1,
        kingdom: Kingdom = Kingdom.GREEN,
        ruby_payment: Literal["wood", "stone", "coins"] | None = None,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """Pay towards something priced in parts: a season map's obstacle, a treasure map node or a slum level.

        ``part_price_id`` is the price's row in ``GameData.part_pay_prices``, which the obstacle, node
        (``TreasureMapNodeDef.part_price_id``) or slum level names. Goods come from ``castle_id`` in
        ``kingdom``: the client pays a slum level from the joined castle, a treasure hunt node from your main
        castle in the hunt's kingdom, and a season obstacle from no castle (-1) in the green kingdom.
        ``ruby_payment`` instead pays that resource's missing amount in rubies, and needs ``spend_rubies``.

        Raises:
            ValueError: ``ruby_payment`` without ``spend_rubies``, or with goods; no goods and no ``ruby_payment``
            CommandError: The server refused; the client shows nothing for ``ALREADY_UNLOCKED`` and ``NO_EVENT``

        Client: ``CastleSlumDonateDialog.onClick`` (bundle line 87707), ``CastleTreasureMapDonateDialog.onClick``
        (bundle line 67887), ``CastleSeasonBaseRepairDialog.onClick`` (bundle line 37624),
        ``CastleTreasureMapUnlockObstacleDialog.onClick`` (bundle line 67849), ``ULECommand.executeCommand``
        (bundle line 129307)
        """
        if ruby_payment is not None:
            if wood or stone or coins:
                raise ValueError("pay either goods or one resource's missing amount in rubies")
            self._require_spend_rubies(spend_rubies, f"paying the missing {ruby_payment} costs rubies")
            wood, stone, coins = (int(ruby_payment == name) for name in ("wood", "stone", "coins"))
        elif not (wood > 0 or stone > 0 or coins > 0):
            raise ValueError("nothing to pay")
        request = UnlockEventRequest(
            castle_id=castle_id,
            kingdom=kingdom,
            wood=wood,
            stone=stone,
            coins=coins,
            part_price_id=part_price_id,
            pay_with_rubies=ruby_payment is not None,
        )
        self.request(request, UnlockEventResponse, timeout=timeout)

    def select_difficulty(
        self,
        event: Event | int,
        difficulty_id: EventDifficultyId,
        *,
        unlock_with_rubies: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """Choose a running event's difficulty.

        ``difficulty_id`` is the difficulty's row in ``GameData.event_difficulties``, or 0 for the
        event without difficulty scaling. A locked difficulty is opened with ``unlock_with_rubies`` for its
        ruby price, which needs ``spend_rubies``. The event's ``difficulty_id`` changes with its next update.

        Raises:
            EventNotRunningError: The event is not running
            ValueError: ``unlock_with_rubies`` without ``spend_rubies``
            CommandError: The server refused

        Client: ``EventDifficultyConfirmDialog.onClick`` (bundle line 98770),
        ``EventDifficultyConfirmRewardsDialog.onClick`` (bundle line 98787), ``DifficultyScalingSelectDialog.onClick``
        (bundle line 30389), ``SEDECommand.executeCommand`` (bundle line 128462)
        """
        self._require_running(event)
        self._require_spend_rubies(
            spend_rubies, "unlocking a difficulty costs its ruby price" if unlock_with_rubies else None
        )
        request = SelectEventDifficultyRequest(
            event_id=int(event), difficulty_id=difficulty_id, unlock_with_rubies=unlock_with_rubies
        )
        self.request(request, SelectEventDifficultyResponse, timeout=timeout)

    def get_daimyo_areas(self, *, timeout: float = 5.0) -> DaimyoAreasResponse:
        """Request the samurai invasion's daimyo castles and townships; the running event keeps them too.

        Raises:
            EventNotRunningError: The samurai invasion is not running
            CommandError: The server refused

        Client: ``CastleAllianceSamuraiInvasionDialogDaimyoSublayer.show`` (bundle line 99060),
        ``GDACommand.executeCommand`` (bundle line 128283)
        """
        self._require_running(Event.SAMURAI_INVASION)
        return self.request(GetDaimyoAreasRequest(), DaimyoAreasResponse, timeout=timeout)

    def get_daimyo_contracts(self, *, timeout: float = 5.0) -> DaimyoContractsResponse:
        """Request your alliance's daimyo contracts; the running samurai invasion keeps them too.

        Raises:
            EventNotRunningError: The samurai invasion is not running
            CommandError: The server refused

        Client: ``CastleAllianceSamuraiInvasionDialogDaimyoSublayer.show`` (bundle line 99060),
        ``GDCCommand.executeCommand`` (bundle line 128298)
        """
        self._require_running(Event.SAMURAI_INVASION)
        return self.request(GetDaimyoContractsRequest(), DaimyoContractsResponse, timeout=timeout)

    def get_daimyo_war_efforts(self, *, timeout: float = 5.0) -> DaimyoWarEffortsResponse:
        """Request your war efforts against the daimyo; the running samurai invasion keeps them too.

        Raises:
            EventNotRunningError: The samurai invasion is not running
            CommandError: The server refused

        Client: ``CastleAllianceSamuraiInvasionDialogDaimyoSublayer.show`` (bundle line 99060),
        ``GDWCommand.executeCommand`` (bundle line 128313)
        """
        self._require_running(Event.SAMURAI_INVASION)
        return self.request(GetDaimyoWarEffortsRequest(), DaimyoWarEffortsResponse, timeout=timeout)

    def get_previous_special_server_runs(self, *, timeout: float = 5.0) -> PreviousSpecialServerRuns:
        """Request when the Outer Realms and Beyond the Horizon last ran.

        Client: ``CastleHighscoreDialog.getGlobalServerInfo`` (bundle line 27707), ``GPRCommand.executeCommand``
        (bundle line 128892)
        """
        return self.request(GetPreviousSpecialServerRunsRequest(), PreviousSpecialServerRuns, timeout=timeout)

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

    def get_rift_raid_status(self, *, timeout: float = 5.0) -> RiftRaidStatus:
        """Request current alliance raid boss, health, cards and walls.

        Requires the raid event. Successful replies and bbs broadcasts update RiftRaidEvent.boss_status.
        An inactive status clears the active boss fields; missing identity/stage/walls preserve prior values
        exactly where the client does. Replies carry no event or alliance identity, so a late reply after
        timeout cannot be correlated. Refusals/transport failures raise without changing the event.
        Client: ``C2SGetAllianceRaidBossStatus`` (bundle 47183-47187), raid parser (76190-76205).
        """
        self._require_running(Event.RIFT_RAID)
        deadline = time.monotonic() + timeout
        with self.client.connection.command_lock("bse", timeout=timeout):
            packet = self.client.request_packet(
                GetRiftRaidStatusRequest(), "bse", timeout=max(0.0, deadline - time.monotonic())
            )
            if packet.error_code != 0:
                raise CommandError("bse", packet.error_code, packet.payload)
            try:
                GetRiftRaidStatusResponse.model_validate(packet.payload)
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
        Status is updated by bbs broadcasts; call get_rift_raid_status for a fresh snapshot.
        Client: ``AllianceRaidBossCardItem.onClick`` (current bundle 75377),
        ``canManageAllianceRaid`` (current DLL 18796), ``SRBCommand`` (bundle 127571-127580).
        """
        event = self._require_running(Event.RIFT_RAID)
        request = SelectRaidBossRequest(boss_id=boss_id)
        if isinstance(event, RiftRaidEvent) and event.boss_status is not None:
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
        event = self._require_running(Event.RIFT_RAID)
        if isinstance(event, RiftRaidEvent) and event.boss_status is not None:
            status = event.boss_status
            if not status.active:
                raise ValueError("there is no active raid to abort")
            locked = {RaidBossCardStatus.LOCKED_FINAL_DEFEATED, RaidBossCardStatus.LOCKED_ABORTED}
            if sum(card.status not in locked for card in status.cards) <= 1:
                raise ValueError("the last playable raid boss cannot be aborted")
        return self.request(AbortRaidRequest(), AbortRaidResponse, timeout=timeout)

    def claim_announcement_reward(self, *, timeout: float = 5.0) -> None:
        """
        Claim the reward of the running event announcement, the teaser for an event to come; the
        announcement's ``reward_collected`` turns True in :attr:`running`.

        Client: ``CastleEventTeaserDialog.claimRewards`` (bundle line 91443), ``CARCommand.executeCommand``
        (bundle line 125277)

        Raises:
            CommandError: The server refused the claim
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        self.execute(ClaimAnnouncementRewardRequest(), timeout=timeout)

    # Event minigames

    def spin_wheel_of_fortune(
        self, wheel: WheelOfFortuneType = WheelOfFortuneType.WHEEL_OF_FORTUNE, *, timeout: float = 5.0
    ) -> WheelOfFortuneSpinResponse:
        """
        Spin a Wheel of Fortune, paid with Wheel of Fortune tickets or a free spin; the wheel's event is updated.

        Raises:
            EventNotRunningError: The wheel's event is not running
            CommandError: The server refused, e.g. without tickets

        Client: ``C2SLuckyWheelSpinVO`` (bundle line 59783), ``LWSCommand.executeCommand`` (bundle line 128141)
        """
        self._require_running(
            Event.WHEEL_OF_UNIMAGINABLE_AFFLUENCE
            if wheel == WheelOfFortuneType.WHEEL_OF_UNIMAGINABLE_AFFLUENCE
            else Event.WHEEL_OF_FORTUNE
        )
        return self.request(WheelOfFortuneSpinRequest(wheel=wheel), WheelOfFortuneSpinResponse, timeout=timeout)

    def change_wheel_of_fortune_mode(self, *, timeout: float = 5.0) -> WheelOfFortuneChangeModeResponse:
        """
        Switch the Wheel of Fortune between normal and pro mode; the client offers it to paying players only.

        Client: ``CastleLuckyWheelDialog.changeMode`` (bundle line 116666), ``LWMCommand.executeCommand`` (bundle
        line 128122)
        """
        self._require_running(Event.WHEEL_OF_FORTUNE)
        return self.request(WheelOfFortuneChangeModeRequest(), WheelOfFortuneChangeModeResponse, timeout=timeout)

    def buy_wheel_of_fortune_jackpot(
        self, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> WheelOfFortuneBuyJackpotResponse:
        """
        Spin the Wheel of Fortune for a guaranteed jackpot, paid in rubies and tickets by the wheel's mode.

        Raises:
            ValueError: Without ``spend_rubies``
            EventNotRunningError: The Wheel of Fortune is not running

        Client: ``CastleLuckyWheelDialog.clickedBuyJackpot`` (bundle line 116659), ``LuckyWheelData.jackpotC2Price``
        (bundle line 17639), ``LWJCommand.executeCommand`` (bundle line 128105)
        """
        self._require_running(Event.WHEEL_OF_FORTUNE)
        self._require_spend_rubies(spend_rubies, "the jackpot costs rubies")
        return self.request(WheelOfFortuneBuyJackpotRequest(), WheelOfFortuneBuyJackpotResponse, timeout=timeout)

    def increase_wheel_of_fortune_win_class(
        self, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> WheelOfFortuneIncreaseWinClassResponse:
        """
        Raise the Wheel of Fortune's win class at once, paid in rubies for the spins it skips.

        Raises:
            ValueError: Without ``spend_rubies``
            EventNotRunningError: The Wheel of Fortune is not running

        Client: ``CastleLuckyWheelIncreaseWinClassDialog.clickedAccept`` (bundle line 117107),
        ``LuckyWheelData.increaseWinClassC2`` (bundle line 17628), ``LWCCommand.executeCommand`` (bundle line 128090)
        """
        self._require_running(Event.WHEEL_OF_FORTUNE)
        self._require_spend_rubies(spend_rubies, "raising the win class costs rubies")
        return self.request(
            WheelOfFortuneIncreaseWinClassRequest(), WheelOfFortuneIncreaseWinClassResponse, timeout=timeout
        )

    def pull_gacha(
        self, event: Event | int, pulls: int = 1, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> GachaSpinResponse:
        """
        Pull a gacha event's chest ``pulls`` times; the event's points and free chest are updated.

        A pull's price is the gacha level's cost list in the game data's gachas table, which the library does
        not load, so it may be rubies: the call needs ``spend_rubies``.

        Raises:
            ValueError: Without ``spend_rubies``, or ``pulls`` below 1
            EventNotRunningError: The event is not running, or is no gacha event

        Client: ``GachaComponentPull.onClick`` (bundle line 57102), ``GachaXmlVO.init`` (bundle line 113936) reads the
        cost list, ``DGECommand.executeCommand`` (bundle line 124175)
        """
        found = self._require_running(event)
        if not isinstance(found, GachaEvent):
            raise EventNotRunningError(int(event))
        self._require_spend_rubies(spend_rubies, "a gacha pull's price can be rubies")
        request = GachaSpinRequest(event_id=int(event), pulls=pulls)
        with self.client.connection.command_lock("dge", timeout=timeout):
            self.client.state._begin_gacha_spin(int(event))
            try:
                return self.request(request, GachaSpinResponse, timeout=timeout)
            finally:
                self.client.state._end_gacha_spin()

    def donate_to_colossus(
        self, castle_id: int, *, wood: int = 0, stone: int = 0, timeout: float = 5.0
    ) -> ColossusDepositResponse:
        """
        Donate wood and stone from one of your castles to the running colossus.

        Raises:
            ValueError: Neither amount is above 0, or the castle is not yours
            EventNotRunningError: No wood and stone colossus is running

        Client: ``CastleColossusDonateDialog.onDonate`` (bundle line 59308), ``CDECommand.executeCommand`` (bundle
        line 127690)
        """
        if not any(self.client.state.get_event(colossus) is not None for colossus in _WOOD_COLOSSI):
            raise EventNotRunningError(Event.COLOSSUS_44)
        if wood <= 0 and stone <= 0:
            raise ValueError("a donation needs wood or stone above 0")
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = ColossusDepositRequest(castle_id=castle_id, kingdom=kingdom, stone=stone, wood=wood)
        return self.request(request, ColossusDepositResponse, timeout=timeout)

    def donate_to_gold_colossus(self, coins: int, *, timeout: float = 5.0) -> ColossusCoinDepositResponse:
        """
        Donate coins to the running coin colossus.

        Client: ``CastleCoinColossusDonateDialog.onDonate`` (bundle line 59272), ``CCDCommand.executeCommand``
        (bundle line 127672)
        """
        self._require_running(Event.GOLD_COLOSSUS)
        return self.request(ColossusCoinDepositRequest(coins=coins), ColossusCoinDepositResponse, timeout=timeout)

    @property
    def donated_points(self) -> tuple[DonationItemPoints, ...] | None:
        """The points each imperial patronage item has earned you, from the last ``gdti`` or ``ddi``; None before
        one or while the event is not running."""
        event = self.client.state.get_event(Event.IMPERIAL_PATRONAGE)
        return event.donated_points if event is not None else None

    def get_imperial_patronage_progress(self, *, timeout: float = 5.0) -> tuple[DonationItemPoints, ...]:
        """
        Ask for the points each imperial patronage item has earned you; kept as :attr:`donated_points`.

        Client: ``DonationEventDialog`` (bundle line 39780), ``GDTICommand.executeCommand`` (bundle line 123604)
        """
        self._require_running(Event.IMPERIAL_PATRONAGE)
        return self.request(
            GetImperialPatronageProgressRequest(), ImperialPatronageProgressResponse, timeout=timeout
        ).items

    def donate_items(
        self, items: Mapping[DonationItemId, int], *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> tuple[DonationItemPoints, ...]:
        """
        Give imperial patronage items, by donation item id and amount; returns the points each has earned.

        A donation item is a resource or a currency (``GameData.donation_items``), which may be rubies: the call
        needs ``spend_rubies``.

        Raises:
            ValueError: No amount is above 0, or ``spend_rubies`` is False

        Client: ``DonationEventDialogDonate.onDonate`` (bundle line 115642), ``DDICommand.executeCommand`` (bundle
        line 123589); ``DonationEventDialogDonateItem.unfilteredAmountInInventory`` (bundle line 115730) gives
        rubies for an item whose resource is ``C2``
        """
        self._require_running(Event.IMPERIAL_PATRONAGE)
        given = tuple(
            DonationItemAmount(donation_item_id=item, amount=amount) for item, amount in items.items() if amount > 0
        )
        if not given:
            raise ValueError("a donation needs an amount above 0")
        self._require_spend_rubies(spend_rubies, "a donation item can be rubies")
        return self.request(DonateItemsRequest(items=given), DonateItemsResponse, timeout=timeout).items

    def give_marauder_packages(
        self,
        castle_id: int,
        *,
        wood_packages: int = 0,
        stone_packages: int = 0,
        food_packages: int = 0,
        timeout: float = 5.0,
    ) -> GetEventPointsResponse:
        """
        Hand resource packages from one of your castles to the marauders' contest, then read your points as the
        client does.

        A package is the event's own amount of the resource, which the sei entry does not carry.

        Raises:
            ValueError: No package count is above 0, or the castle is not yours
            EventNotRunningError: The marauders' contest is not running

        Client: ``C2SBuyBeggingKnightsPackageVO`` (bundle line 114933), sent with each amount divided by the
        package size (bundle line 114916); ``BKPCommand.executeCommand`` (bundle line 128233) asks for the points
        """
        self._require_running(Event.MARAUDERS_CONTEST)
        if max(wood_packages, stone_packages, food_packages) <= 0:
            raise ValueError("pass a package count above 0")
        request = BuyMaraudersContestPackageRequest(
            castle_id=castle_id,
            kingdom=self._require_own_castle(castle_id).kingdom_id,
            wood_packages=wood_packages,
            stone_packages=stone_packages,
            food_packages=food_packages,
        )
        self.execute(request, timeout=timeout)
        return self.get_own_points(Event.MARAUDERS_CONTEST, timeout=timeout)

    def buy_artifact_pieces(
        self, event: Event | int, pieces: int = 1, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> BuyArtifactPieceResponse:
        """
        Buy pieces of a running Traveling Knights event's artifact with rubies; the event's ``parts_found`` is updated.

        Raises:
            ValueError: Without ``spend_rubies``
            EventNotRunningError: The event is not running, or is no Traveling Knights event
            GameDataNotLoadedError: The game data, which names the event's kingdom, cannot be loaded

        Client: ``CastleArtifactBuyPieceDialog`` (bundle lines 114756, 114762) prices the pieces in rubies and sends
        the event's first kingdom (``kIDs``, ``"0"`` when missing, ``ASpecialEventVO.parseBasicsFromXmlNode``,
        bundle line 2960); ``SAPCommand.executeCommand`` (bundle line 127614)
        """
        if not isinstance(self._require_running(event), TravelingKnightsEvent):
            raise EventNotRunningError(int(event))
        self._require_spend_rubies(spend_rubies, "artifact pieces cost rubies")
        kingdoms = self._require_game_data().events[Event(int(event))].kingdoms
        kingdom = Kingdom(kingdoms[0]) if kingdoms else Kingdom.GREEN
        request = BuyArtifactPieceRequest(pieces=pieces, event_id=int(event), kingdom=kingdom)
        return self.request(request, BuyArtifactPieceResponse, timeout=timeout)

    def validate_shady_lady_target(self, *, timeout: float = 5.0) -> None:
        """
        Have the server check your Shady Lady target, as the event's dialog does when it opens; a new target
        arrives in a ``sei``.

        Client: ``CastleBountyhunterEventDialog.applyPropertiesLoaded`` (bundle line 114986),
        ``BRTCommand.executeCommand`` (bundle line 127629)
        """
        self._require_running(Event.SHADY_LADY)
        self.execute(ValidateShadyLadyTargetRequest(), timeout=timeout)

    def skip_shady_lady_target(
        self, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> SkipShadyLadyTargetResponse:
        """
        Skip your Shady Lady target for another, paid in rubies; the event's new target comes with the reply.

        Raises:
            ValueError: Without ``spend_rubies``

        Client: ``CastleBountyhunterEventDialog.onClick`` (bundle line 115004), ``targetSkipCostC2`` (bundle line
        114944), ``BSTCommand.executeCommand`` (bundle line 127642)
        """
        self._require_running(Event.SHADY_LADY)
        self._require_spend_rubies(spend_rubies, "skipping the target costs rubies")
        return self.request(SkipShadyLadyTargetRequest(), SkipShadyLadyTargetResponse, timeout=timeout)

    def buy_fortune_teller_reading(
        self, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> FortuneTellerReadingResponse:
        """
        Buy today's next fortune teller reading and return its reward.

        Each reading is priced in rubies by the game data's fortune teller classes, which the library does not
        load, so the call needs ``spend_rubies`` even for one that is free.

        Raises:
            ValueError: Without ``spend_rubies``
            GameDataNotLoadedError: The game data, which resolves the rewards, cannot be loaded

        Client: ``FortuneTellerEventDialog.onClick`` and ``updateText`` (bundle lines 59613, 59596),
        ``FortuneTellerClassVO.parseXML`` (bundle line 145167), ``CastleFortuneTellerData.parseFTL`` (bundle line
        145157)
        """
        self._require_running(Event.FORTUNE_TELLER)
        self._require_spend_rubies(spend_rubies, "a reading costs rubies")
        game_data = self._require_game_data()
        reading = self.request(FortuneTellerReadingRequest(), FortuneTellerReadingResponse, timeout=timeout)
        return reading.model_copy(update={"rewards": game_data.reward_list(reading.reward_ids)})

    def vote_world_cup(self, vote: WorldCupVote, *, timeout: float = 5.0) -> VoteWorldCupResponse:
        """
        Bet on the world cup match; no rubies are spent, the bet opens once you spent its price in the event.

        Raises:
            ValueError: You have bet already
            EventNotRunningError: The world cup is not running

        Client: ``CastleWorldCupDialog.updateState`` (bundle line 104658), ``CastleWorldCupDialogNotVotedState``
        (bundle lines 104711-104723), ``VWCCommand.executeCommand`` (bundle line 128541)
        """
        found = self._require_running(Event.WORLD_CUP)
        if isinstance(found, WorldCupEvent) and found.vote >= 0:
            raise ValueError("you have bet on this match already")
        return self.request(VoteWorldCupRequest(vote=vote), VoteWorldCupResponse, timeout=timeout)

    def get_collector_currency(self, player_id: int, *, timeout: float = 5.0) -> int:
        """
        Ask how much of the collector event's currency a player holds, as the attack dialog shows it.

        Client: ``CastleCollectorEventData.getPlayerCollectorAmount`` (bundle line 134000),
        ``PCCCommand.executeCommand`` (bundle line 127657)
        """
        request = GetCollectorCurrencyRequest(player_id=player_id)
        return self.request(request, CollectorCurrencyResponse, timeout=timeout).amount
