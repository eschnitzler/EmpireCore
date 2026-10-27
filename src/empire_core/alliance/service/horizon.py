"""Beyond the Horizon."""

from __future__ import annotations

from empire_core.alliance.models.horizon import (
    ActivateAllianceTowerBuffsRequest,
    ActivateAllianceTowerBuffsResponse,
    AllianceInfluenceResponse,
    AllianceTowerBuffIncrease,
    AllianceTowerBuffs,
    CenterOfPower,
    CentersOfPowerDetailResponse,
    CentersOfPowerResponse,
    GetAllianceInfluenceRequest,
    GetAllianceTowerBuffsRequest,
    GetAllianceTowerBuffsResponse,
    GetAllianceTowerCastlesRequest,
    GetAllianceTowerCastlesResponse,
    GetAllianceTowersRequest,
    GetAllianceTowersResponse,
    GetCentersOfPowerDetailRequest,
    GetCentersOfPowerRequest,
    GetHorizonEntryRequest,
    GetHorizonPerformanceRequest,
    GetPlayerInfluenceRequest,
    HorizonEntryResponse,
    HorizonMemberPerformance,
    HorizonPerformanceResponse,
    IncreaseAllianceTowerBuffsRequest,
    IncreaseAllianceTowerBuffsResponse,
    PlayerInfluenceResponse,
)
from empire_core.alliance.service.own import OwnAllianceMixin
from empire_core.map.models.items import MapAreaItem


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
        How many capitals, metropolises and kings' towers your alliance holds, against their limits.

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
            ActivateAllianceTowerBuffsRequest(x=x, y=y), ActivateAllianceTowerBuffsResponse, timeout=timeout
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
        ).tower_buffs
