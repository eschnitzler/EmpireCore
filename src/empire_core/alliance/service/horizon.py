"""Beyond the Horizon."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from empire_core.alliance.models.horizon import (
    ActivateAllianceTowerBuffsRequest,
    ActivateAllianceTowerBuffsResponse,
    AllianceInfluenceResponse,
    AllianceTowerBuffIncrease,
    AllianceTowerBuffs,
    CenterOfPower,
    CentersOfPowerDetailResponse,
    CentersOfPowerResponse,
    CitadelsResponse,
    ConvertJadeStatuettesRequest,
    GetAllianceInfluenceRequest,
    GetAllianceTowerBuffsRequest,
    GetAllianceTowerBuffsResponse,
    GetAllianceTowerCastlesRequest,
    GetAllianceTowerCastlesResponse,
    GetAllianceTowersRequest,
    GetAllianceTowersResponse,
    GetCentersOfPowerDetailRequest,
    GetCentersOfPowerRequest,
    GetCitadelsRequest,
    GetHorizonEntryConditionsRequest,
    GetHorizonEntryRequest,
    GetHorizonPerformanceRequest,
    GetOasisSettlementRequest,
    GetPlayerInfluenceRequest,
    HorizonEntryConditionsResponse,
    HorizonEntryResponse,
    HorizonMemberPerformance,
    HorizonPerformanceResponse,
    IncreaseAllianceTowerBuffsRequest,
    IncreaseAllianceTowerBuffsResponse,
    JadePhase,
    OasisSettlementResponse,
    PlayerInfluenceResponse,
    SendOasisTradeRequest,
    SendOasisTradeResponse,
    UpgradeCitadelRequest,
)
from empire_core.alliance.service.own import OwnAllianceMixin
from empire_core.commanders.models.roster import PREMIUM_COMMANDER_ID
from empire_core.enums import Kingdom
from empire_core.gamedata import OasisTradeId, WodAmount, WodAmountMapping
from empire_core.map.models.items import MapAreaItem
from empire_core.movements.models.movement import NO_HORSE

if TYPE_CHECKING:
    from empire_core.gamedata import Horse


class HorizonMixin(OwnAllianceMixin):
    # =========================================================================
    # Beyond the Horizon
    # =========================================================================

    def get_horizon_entry(self, *, timeout: float = 5.0) -> HorizonEntryResponse:
        """
        Your alliance as Beyond the Horizon will take it: its name, member count and your rank.

        Sent on your main server, as the client does before you buy your way onto Beyond the Horizon.

        Client: ``CastleAllianceBattleGroundBuyInfoDialog.getAlliInfo`` (bundle line 45639)
        """
        return self.request(GetHorizonEntryRequest(), HorizonEntryResponse, timeout=timeout)

    @property
    def horizon_performance(self) -> list[HorizonMemberPerformance] | None:
        """Your alliance members' Beyond the Horizon performance, from the last ``gae``; None until one arrived."""
        return self.client.state.get_horizon_performance()

    def get_horizon_performance(self, *, timeout: float = 5.0) -> list[HorizonMemberPerformance]:
        """
        Your alliance members' Beyond the Horizon performance, kept as :attr:`horizon_performance`.

        Only on the Beyond the Horizon server.

        Raises:
            NotInAllianceError: You are in no alliance; nothing is sent
            CommandError: The server refused

        Client: the performance tabs' ``sendPerformanceCommand`` (bundle lines 71664, 71702)
        """
        alliance_id = self._require_local_alliance_id()
        return self.request(
            GetHorizonPerformanceRequest(alliance_id=alliance_id), HorizonPerformanceResponse, timeout=timeout
        ).members

    def get_horizon_alliance_influence(self, alliance_id: int, *, timeout: float = 5.0) -> int:
        """
        An alliance's Beyond the Horizon influence.

        Only on the Beyond the Horizon server, in alliance collector scoring.

        Client: ``CastleCollectorEventData.getABGAllianceCollectorAmount`` (bundle line 134003)
        """
        return self.request(
            GetAllianceInfluenceRequest(alliance_id=alliance_id), AllianceInfluenceResponse, timeout=timeout
        ).influence

    def get_horizon_player_influence(self, player_id: int, *, timeout: float = 5.0) -> int:
        """
        A player's Beyond the Horizon influence.

        Only on the Beyond the Horizon server, in alliance collector scoring.

        Client: ``CastleCollectorEventData.getABGCollectorAmount`` (bundle line 134002)
        """
        return self.request(
            GetPlayerInfluenceRequest(player_id=player_id), PlayerInfluenceResponse, timeout=timeout
        ).influence

    def get_centers_of_power(self, *, timeout: float = 5.0) -> CentersOfPowerResponse:
        """
        How many capitals, metropolises and royal towers your alliance holds, against their limits.

        Only on the Beyond the Horizon server, in alliance collector scoring.

        Raises:
            NotInAllianceError: You are in no alliance; nothing is sent
            CommandError: The server refused

        Client: ``CastleAllianceDialogABG.show`` (bundle line 69043)
        """
        alliance_id = self._require_local_alliance_id()
        return self.request(GetCentersOfPowerRequest(alliance_id=alliance_id), CentersOfPowerResponse, timeout=timeout)

    def get_centers_of_power_detail(self, *, timeout: float = 5.0) -> list[CenterOfPower]:
        """
        Your alliance's centers of power one by one, with the member holding each.

        Only on the Beyond the Horizon server, in alliance collector scoring.

        Raises:
            NotInAllianceError: You are in no alliance; nothing is sent
            CommandError: The server refused

        Client: ``CastleAllianceCentersOfPowerDialog.showLoaded`` (bundle line 69069)
        """
        alliance_id = self._require_local_alliance_id()
        return self.request(
            GetCentersOfPowerDetailRequest(alliance_id=alliance_id), CentersOfPowerDetailResponse, timeout=timeout
        ).centers

    def get_towers(self, alliance_id: int, *, timeout: float = 5.0) -> list[MapAreaItem]:
        """
        An alliance's towers on Beyond the Horizon, as map rows.

        Only on the Beyond the Horizon server, in tower scoring.

        Client: ``CastleAllianceInfoDialogABGTower.show`` (bundle line 66587)
        """
        return self.request(
            GetAllianceTowersRequest(alliance_id=alliance_id), GetAllianceTowersResponse, timeout=timeout
        ).towers

    def get_tower_castles(self, x: int, y: int, *, timeout: float = 5.0) -> GetAllianceTowerCastlesResponse:
        """
        The castles linked to the alliance tower at ``(x, y)``, with their owners.

        Only on the Beyond the Horizon server, in tower scoring.

        Client: ``CastleABGTowerDetailDialog.showLoaded`` (bundle line 46066)
        """
        return self.request(GetAllianceTowerCastlesRequest(x=x, y=y), GetAllianceTowerCastlesResponse, timeout=timeout)

    def get_tower_buffs(self, x: int, y: int, alliance_id: int, *, timeout: float = 5.0) -> AllianceTowerBuffs:
        """
        The buffs of the alliance tower at ``(x, y)``, held by ``alliance_id``.

        Only on the Beyond the Horizon server, in tower scoring. The buffs are as the server lists
        them; the client also shows the event's other tower effects, at level 0.

        Client: ``CastleABGTowerEffectsDialog.showLoaded`` (bundle line 71024)
        """
        return self.request(
            GetAllianceTowerBuffsRequest(x=x, y=y, alliance_id=alliance_id),
            GetAllianceTowerBuffsResponse,
            timeout=timeout,
        )

    def activate_tower_buffs(
        self, x: int, y: int, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> AllianceTowerBuffs:
        """
        Activate the buffs of the alliance tower at ``(x, y)``, for rubies; returns its buffs now.

        Only on the Beyond the Horizon server, in tower scoring. The price comes from the event's
        activation table, cheaper the nearer the tower's revival; the server charges it.

        Raises:
            ValueError: ``spend_rubies`` is False
            CommandError: The server refused

        Client: ``CastleABGTowerEffectsActivateDialog.onClick`` (bundle line 70999)
        """
        self._require_spend_rubies(spend_rubies, "activating an alliance tower's buffs costs rubies")
        return self.request(
            ActivateAllianceTowerBuffsRequest(x=x, y=y),
            ActivateAllianceTowerBuffsResponse,
            timeout=timeout,
            spend_rubies=spend_rubies,
        ).tower_buffs

    def increase_tower_buffs(
        self,
        x: int,
        y: int,
        increases: list[AllianceTowerBuffIncrease],
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> AllianceTowerBuffs:
        """
        Raise buffs of the alliance tower at ``(x, y)``, for rubies; returns its buffs now.

        Only on the Beyond the Horizon server, in tower scoring. Each increase names the buff's
        effect, its current level (a :meth:`get_tower_buffs` level) and the level to reach; each level's
        price comes from the event's tower effect table, and the server charges it.

        Raises:
            ValueError: No increase, one that does not raise its level, or ``spend_rubies`` is False
            CommandError: The server refused

        Client: ``CastleABGTowerEffectsDialog.onClick`` (bundle line 71048) sends the buffs
        ``ABGAllianceTowerBuffInfoVO.createServerEffectsArray`` (bundle line 144958) lists, and nothing
        when none is raised
        """
        if not increases:
            raise ValueError("name at least one buff to raise")
        if any(increase.level_after <= increase.level_before for increase in increases):
            raise ValueError("each increase must raise its buff's level")
        self._require_spend_rubies(spend_rubies, "raising an alliance tower's buffs costs rubies")
        return self.request(
            IncreaseAllianceTowerBuffsRequest(x=x, y=y, increases=increases),
            IncreaseAllianceTowerBuffsResponse,
            timeout=timeout,
            spend_rubies=spend_rubies,
        ).tower_buffs

    # =========================================================================
    # The Jade Desert
    # =========================================================================

    def get_horizon_entry_conditions(self, *, timeout: float = 5.0) -> HorizonEntryConditionsResponse:
        """
        The conditions for entering Beyond the Horizon that you do not meet yet; none when you may enter.

        Raises:
            CommandError: The server refused

        Client: ``CastleAllianceBattleGroundData.requestEntryConditions`` (split.js line 716008), sent whenever the
        Jade Desert event dialog's overview opens
        (``CastleAllianceBattlegroundEventJadeDialogOverview.requestJoinRequirements``, split.js line 474622)
        """
        return self.request(GetHorizonEntryConditionsRequest(), HorizonEntryConditionsResponse, timeout=timeout)

    @property
    def jade_phase(self) -> JadePhase | None:
        """The Jade Desert's scoring phase, from the ``abgi`` pushes so far; None until one arrived."""
        return self.client.state.get_jade_phase()

    def get_citadels(self, *, timeout: float = 5.0) -> CitadelsResponse:
        """
        Your alliance's Citadel and the enemy citadels in the Jade Desert.

        Only on the Beyond the Horizon server, in the Jade Desert, where the client alone sends it.

        Raises:
            CommandError: The server refused

        Client: ``CastleAllianceBattleGroundData.requestJadeCitadelInfo`` (split.js line 716001)
        """
        return self.request(GetCitadelsRequest(), CitadelsResponse, timeout=timeout)

    def upgrade_citadel(self, *, timeout: float = 5.0) -> None:
        """
        Upgrade your alliance's Citadel to its next level, for that level's Ancient Jade Statuettes.

        Only on the Beyond the Horizon server, in the Jade Desert. The price is the next
        :attr:`GameData.citadel_levels` row's costs. An upgrade can end the citadel's attack protection; the client
        asks before sending one that does.

        Raises:
            CommandError: The server refused

        Client: ``CastleAllianceBattleGroundEventJadeDialogCitadelManagement.onUpgradeClicked`` (split.js line 473840)
        """
        self.execute(UpgradeCitadelRequest(), timeout=timeout)

    def convert_jade_statuettes(self, restored_amount: int, *, timeout: float = 5.0) -> None:
        """
        Convert Ancient Jade Statuettes into ``restored_amount`` Restored Jade Statuettes before the event ends.

        Only on the Beyond the Horizon server, in the Jade Desert. Each Restored Jade Statuette takes your
        citadel level's ``early_conversion_ratio`` Ancient ones (:attr:`GameData.citadel_levels`); the conversion
        cannot be undone.

        Raises:
            ValueError: ``restored_amount`` is not above 0; nothing is sent, as in the client
            CommandError: The server refused

        Client: ``ABGJadeStatuetteConversionComponent.sendConversion`` (split.js line 474233)
        """
        if restored_amount <= 0:
            raise ValueError("convert at least one Restored Jade Statuette")
        self.execute(ConvertJadeStatuettesRequest(restored_amount=restored_amount), timeout=timeout)

    def get_oasis_settlement(
        self, x: int, y: int, kingdom: Kingdom = Kingdom.GREEN, *, timeout: float = 5.0
    ) -> OasisSettlementResponse:
        """
        The Oasis Settlement at ``(x, y)``: its level, the troops it has left to trade and its cooldown.

        Only on the Beyond the Horizon server, in the Jade Desert.

        Raises:
            CommandError: The server refused

        Client: ``AllianceBattleGroundJadeTradeDialog`` (split.js line 564457) asks when it opens
        """
        return self.request(
            GetOasisSettlementRequest(x=x, y=y, kingdom=kingdom), OasisSettlementResponse, timeout=timeout
        )

    def send_oasis_trade(
        self,
        source_x: int,
        source_y: int,
        target_x: int,
        target_y: int,
        units: WodAmountMapping | Sequence[WodAmount],
        trades: Mapping[OasisTradeId, int],
        commander_id: int,
        *,
        kingdom: Kingdom = Kingdom.GREEN,
        horse_booster_id: Horse | None = None,
        feathers: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> SendOasisTradeResponse:
        """
        Send troops and trading materials from your castle to the Oasis Settlement at ``(target_x, target_y)``.

        Only on the Beyond the Horizon server, in the Jade Desert. The client sends from your main castle there.
        ``trades`` names how often to make each of the settlement's trades (:attr:`GameData.oasis_trades`); the
        materials they cost travel with the troops.

        Rubies as for ``client.movements.send_troops``: the premium commander and a horse that costs rubies unless
        paid with feathers need ``spend_rubies``.

        Args:
            source_x: Map x of the castle the troops leave from
            source_y: Map y of the castle the troops leave from
            target_x: The settlement's map x
            target_y: The settlement's map y
            units: The units: ``{Unit.X: 100}``, or pairs one per slot
            trades: How often to make each trade, ``{OasisTradeId(10): 3}``; amounts of 0 are left out
            commander_id: The commander to lead them, a ``Commander.commander_id``; ``PREMIUM_COMMANDER_ID`` for
                the premium commander, sent as 0 with the premium flag, as the client does
            kingdom: The settlement's kingdom
            horse_booster_id: The horse, None for none; sent as none whenever feathers are used, as the client does
            feathers: Pay for the horse with feathers
            spend_rubies: Send even when the premium commander or the horse costs rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: No trade is above 0, which the client cannot send; or the horse costs rubies and
                ``spend_rubies`` is False
            PremiumCommanderCostError: The premium commander leads, may cost rubies, and ``spend_rubies`` is
                False; see ``client.commanders.premium_send``
            CommandError: The server refused the trade

        Client: ``CastlePostTradeHorseDialog.sendTradeMovement`` (split.js line 566640); the trade button is
        enabled only with a trade selected (``AllianceBattleGroundJadeTradeDialog.updateTradeButton``,
        split.js line 564758)
        """
        selected = {trade_id: amount for trade_id, amount in trades.items() if amount > 0}
        if not selected:
            raise ValueError("name at least one trade to make")
        self._require_spend_rubies(spend_rubies, self._travel_ruby_cost(horse_booster_id, feathers, 0))
        premium = commander_id == PREMIUM_COMMANDER_ID
        request = SendOasisTradeRequest(
            source_x=source_x,
            source_y=source_y,
            target_x=target_x,
            target_y=target_y,
            kingdom=kingdom,
            commander_id=0 if premium else commander_id,
            use_premium_commander=1 if premium else 0,
            horse_booster_id=NO_HORSE if feathers or horse_booster_id is None else horse_booster_id,
            feathers=1 if feathers else 0,
            units=WodAmount.slots(units),
            trades=selected,
        )
        return self.client.commanders.premium_send(
            commander_id,
            premium,
            lambda: self.request(request, SendOasisTradeResponse, timeout=timeout, spend_rubies=spend_rubies),
            spend_rubies=spend_rubies,
        )
