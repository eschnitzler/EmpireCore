"""Beyond the Horizon, the Outer Realms, their charge camps and the Battle for Berimond."""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.enums import Kingdom, ServerType
from empire_core.events.service.base import EventsBaseMixin
from empire_core.gamedata.ids.events import Event

if TYPE_CHECKING:
    from empire_core.gamedata import PrebuiltCastle

from empire_core.events.berimond_models import (
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
from empire_core.events.board_models import (
    GetHorizonRankRequest,
    GetHorizonRankResponse,
    GetHorizonTimersRequest,
    GetHorizonTimersResponse,
    GetOuterRealmsRanksRequest,
    GetOuterRealmsRanksResponse,
    GetPlayerPerformanceRequest,
    GetPlayerPerformanceResponse,
)
from empire_core.events.special_server_models import (
    ApplyChargeCampEffectRequest,
    ApplyChargeCampEffectResponse,
    ChargeCampEffects,
    CurrentServer,
    GetChargeCampEffectsRequest,
    GetOuterRealmsCollectorPointsRequest,
    OuterRealmsCollectorPoints,
    RerollChargeCampEffectRequest,
    RerollChargeCampEffectResponse,
    SelectSpecialServerCastleRequest,
    SelectSpecialServerCastleResponse,
    SpecialServerCastles,
)

# The event that runs each special server
_SPECIAL_SERVER_EVENTS = {
    ServerType.OUTER_REALMS: Event.OUTER_REALMS,
    ServerType.HORIZON: Event.BEYOND_THE_HORIZON,
}


class SpecialServersMixin(EventsBaseMixin):
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
        and needs ``spend_rubies``. As in the client, a castle that costs nothing goes as bought
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
            GameDataNotLoadedError: The game data cannot be loaded
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
            GameDataNotLoadedError: The game data cannot be loaded
            StateNotLoadedError: No login has brought your level
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
