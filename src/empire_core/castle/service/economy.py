"""The brewery, private resource villages and tax."""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.castle.models.brewery import (
    BreweryProductionResponse,
    BreweryStops,
    GetBreweryProductionRequest,
    MeadShare,
    SetBreweryProductionRequest,
    SetMeadPriorityRequest,
)
from empire_core.castle.models.objects import BuildingRow
from empire_core.castle.models.tax import (
    TAX_DURATIONS,
    TAX_RUBY_COSTS,
    BribeTaxCollectorRequest,
    BribeTaxCollectorResponse,
    CollectTaxRequest,
    CollectTaxResponse,
    GetTaxInfoRequest,
    StartTaxRequest,
    StartTaxResponse,
    TaxInfo,
    TaxInfoResponse,
)
from empire_core.castle.models.villages import (
    BuyPrivateVillageRequest,
    PrivateVillage,
    RemovePrivateVillageRequest,
    UpgradePrivateVillageRequest,
)
from empire_core.services.base import ServiceMixin

if TYPE_CHECKING:
    from empire_core.gamedata import PrivateVillageType


class EconomyMixin(ServiceMixin):
    # =========================================================================
    # Brewery
    # =========================================================================

    def get_brewery_production(
        self, castle_id: int, brewery: BuildingRow, *, timeout: float = 5.0
    ) -> BreweryProductionResponse:
        """
        Read one of your castles' brewery production.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            brewery: The brewery's row, from ``join(castle_id).buildings``

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list

        Client: ``CastleBreweryShortageDialog.showLoaded`` (bundle line 138227) sends
        ``C2SGetAreaBuildingProductionVO``; ``ABPICommand.executeCommand`` (bundle line 122711)
        """
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = GetBreweryProductionRequest(
            kingdom_id=kingdom, castle_id=castle_id, wod_id=brewery.wod_id, object_id=brewery.object_id
        )
        return self.request(request, BreweryProductionResponse, timeout=timeout)

    def set_brewery_production(
        self,
        castle_id: int,
        brewery: BuildingRow,
        mead_percent: int,
        *,
        stop_at_food: int = 0,
        stop_at_honey: int = 0,
        timeout: float = 5.0,
    ) -> BreweryProductionResponse:
        """
        Set how much of one of your castles' brewery makes mead, and the stocks at which it stops.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            brewery: The brewery's row, from ``join(castle_id).buildings``
            mead_percent: The share of the brewery producing mead, in percent
            stop_at_food: Food left at which production stops
            stop_at_honey: Honey left at which production stops

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list

        Client: the brewery dialog's save button (bundle line 36458) sends ``C2SSetBreweryProductionVO``;
        ``ABPICommand.executeCommand`` (bundle line 122711)
        """
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = SetBreweryProductionRequest(
            kingdom_id=kingdom,
            castle_id=castle_id,
            wod_id=brewery.wod_id,
            object_id=brewery.object_id,
            share=MeadShare(mead_percent=mead_percent),
            stops=BreweryStops(food=stop_at_food, honey=stop_at_honey),
        )
        return self.request(request, BreweryProductionResponse, timeout=timeout)

    def set_mead_priority(self, castle_id: int, enabled: bool, *, timeout: float = 5.0) -> None:
        """
        Give one of your castles' mead production priority, or take it away.

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list

        Client: the brewery dialog's priority checkbox (bundle line 36462) sends ``C2SSetMeadPrioVO``
        for the active castle; ``BFLCommand.executeCommand`` (bundle line 122726)
        """
        kingdom = self._require_own_castle(castle_id).kingdom_id
        self.execute(SetMeadPriorityRequest(kingdom_id=kingdom, castle_id=castle_id, enabled=enabled), timeout=timeout)

    # =========================================================================
    # Private resource villages
    # =========================================================================

    def buy_private_village(self, village_type_id: PrivateVillageType, *, timeout: float = 5.0) -> None:
        """
        Buy a private resource village with resource village tokens.

        Args:
            village_type_id: The village, e.g. ``PrivateVillageType.ICE_PRIVATE_WOOD_VILLAGE_L1``

        Client: ``PrivateResourceVillageBuyDialog.onConfirm`` (bundle line 81673) sends
        ``C2SBuyPrivateResourceVillageVO`` once ``APrivateResourceVillageActionDialog.onClick`` (bundle line
        36219) found the tokens; ``BPVCommand.exec`` (bundle line 126459)
        """
        self.execute(BuyPrivateVillageRequest(village_type_id=village_type_id), timeout=timeout)

    def upgrade_private_village(self, village: PrivateVillage, *, timeout: float = 5.0) -> None:
        """
        Upgrade one of your private resource villages to the next level, with resource village tokens.

        Args:
            village: The village, a row of :attr:`villages` or :meth:`get_villages`; its id and the type of
                its current level are sent

        Client: ``PrivateResourceVillageUpgradeDialog.onConfirm`` (bundle line 81600) sends
        ``C2SUpgradePrivateResourceVillageVO``; ``UPVCommand.exec`` (bundle line 126489)
        """
        request = UpgradePrivateVillageRequest(village_type_id=village.village_type_id, village_id=village.village_id)
        self.execute(request, timeout=timeout)

    def remove_private_village(self, village: PrivateVillage, *, timeout: float = 5.0) -> None:
        """
        Remove one of your private resource villages; it is gone for good, its tokens are not returned.

        Args:
            village: The village, a row of :attr:`villages` or :meth:`get_villages`

        Client: ``PrivateResourceVillageDestroyDialog.onConfirm`` (bundle line 81568) sends
        ``C2SRemovePrivateResourceVillageVO``; ``RPVCommand.exec`` (bundle line 126474)
        """
        self.execute(RemovePrivateVillageRequest(village_id=village.village_id), timeout=timeout)

    # =========================================================================
    # Tax
    # =========================================================================

    def get_tax_info(self, *, timeout: float = 5.0) -> TaxInfo:
        """
        Read the tax collection status.

        Example:
            tax = client.castle.get_tax_info()
            print(tax.status, tax.remaining_seconds, tax.expected_income)

        Client: ``C2SGetTaxInfoVO`` (bundle line 37186), ``TXICommand`` (bundle line 128792)
        """
        return self.request(GetTaxInfoRequest(), TaxInfoResponse, timeout=timeout).tax

    def start_tax(self, tax_type: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> StartTaxResponse:
        """
        Start a tax collection.

        Tax types 0 to 6 collect for ``TAX_DURATIONS[tax_type]`` seconds. Type 0
        is free and types 1 to 4 cost a tenth of their income in coins. Types 5
        and 6 cost ``TAX_RUBY_COSTS`` rubies unless a premium account, a VIP
        level or the tax research waives it; this method refuses them unless
        ``spend_rubies`` is True, and does not check for a waiver.

        Args:
            tax_type: The tax type, 0 to 6
            spend_rubies: Allow types 5 and 6, which may spend rubies
            timeout: Timeout in seconds

        Returns:
            The reply: coins and rubies after, and the tax status.

        Raises:
            ValueError: ``tax_type`` is not 0 to 6, or costs rubies and ``spend_rubies`` is False
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SStartCollectTaxVO`` (bundle line 91088), sent by
        ``CastleCollectTaxElement.onStartTaxCollection`` (bundle line 91069), which
        shows a ruby cost when ``CollectTaxElementVO.hasC2CostWithoutPremium``
        (bundle line 91050); ``TaxConst`` (dll lines 19771-19790)
        """
        if not 0 <= tax_type < len(TAX_DURATIONS):
            raise ValueError(f"tax_type must be 0 to {len(TAX_DURATIONS) - 1}, got {tax_type}")
        if TAX_RUBY_COSTS[tax_type] > 0 and not spend_rubies:
            raise ValueError(
                f"tax type {tax_type} costs {TAX_RUBY_COSTS[tax_type]} rubies unless waived; pass spend_rubies=True"
            )
        return self.request(StartTaxRequest(tax_type=tax_type), StartTaxResponse, timeout=timeout)

    def collect_tax(self, *, timeout: float = 5.0) -> CollectTaxResponse:
        """
        Collect the tax.

        Collecting while the collection runs brings the share of its income
        earned so far; the client asks first when that is nothing.

        Returns:
            The reply: the coins collected, coins and rubies after, and the tax status.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SCollectTaxVO`` (bundle line 41083), sent by
        ``CastleCollectTaxDialog.collectTax`` (bundle line 91027) after
        ``onCollectTaxClick`` (bundle line 91015); ``TaxConst.getCollectedMoney``
        (dll line 19784); ``TXCCommand`` (bundle line 128747)
        """
        return self.request(CollectTaxRequest(), CollectTaxResponse, timeout=timeout)

    def bribe_tax_collector(
        self, *, spend_rubies: bool = False, private_offer_id: int = -1, timeout: float = 5.0
    ) -> BribeTaxCollectorResponse:
        """
        Bribe the tax collector, a tax booster bought with rubies; see "Spending rubies" in the guides.

        Its price comes with the boosters and is not worked out here, so this always needs ``spend_rubies``.

        Args:
            spend_rubies: Allow the rubies it costs; without it nothing is sent
            private_offer_id: The booster sale the bribe uses, -1 for none

        Returns:
            Coins and rubies, and the tax status after; the booster reaches ``client.state.get_boosts()``

        Raises:
            ValueError: ``spend_rubies`` is False

        Client: ``CastleBribeDialog.onClick`` (bundle line 90878) sends it once the rubies are there, with
        ``CastleBoosterSaleData.getOfferId`` (bundle line 9696); ``BTXCommand.executeCommand`` (bundle line 128770)
        """
        self._require_spend_rubies(spend_rubies, "bribing the tax collector costs rubies")
        request = BribeTaxCollectorRequest(private_offer_id=private_offer_id)
        return self.request(request, BribeTaxCollectorResponse, timeout=timeout)
