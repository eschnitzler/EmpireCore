"""Event shops: buying a package at its fixed price, and how often you bought each."""

from __future__ import annotations

from empire_core.enums import CollectableKind, GGEError, PackageBuyType
from empire_core.events.models import PackageShopEvent
from empire_core.exceptions import CommandError, EventNotRunningError, NotEnoughSpecialCurrencyError
from empire_core.gamedata import PackageDef, PackageId
from empire_core.gamedata.ids.events import Event
from empire_core.services.base import BaseService
from empire_core.shop.models import (
    BuyEventPackageRequest,
    BuyEventPackageResponse,
    GetPackageBuyCountsRequest,
    PackageBuyCountsResponse,
)


class ShopService(BaseService):
    """
    The packages events' shops sell for a fixed price in coins, rubies or event currencies.

    Reached as client.shop.
    """

    @property
    def package_buy_counts(self) -> dict[PackageId, int] | None:
        """How often you bought each package, by package id, from the last ``gbc`` and the purchases since; None
        until one came."""
        return self.client.state.get_package_buy_counts()

    def bought_count(self, package: PackageDef) -> int:
        """
        How often you bought a package with a stock, as last read; 0 for a package without one, whose count the
        client does not keep.

        Client: ``CastleEventPackageData.parseBoughtCount`` (split.js line 670404) keeps a count only for a
        package that ``isStockLimited``
        """
        if not package.is_stock_limited:
            return 0
        return (self.package_buy_counts or {}).get(package.package_id, 0)

    def get_package_buy_counts(self, castle_id: int, *, timeout: float = 5.0) -> dict[PackageId, int]:
        """
        Ask how often you bought each package with a stock, as a shop opened in one of your castles does.

        Raises:
            UnknownCastleError: The castle is not one of yours
            CommandError: The server refused the request

        Client: ``AModernPackageShopDialogSublayer.show`` (split.js line 149614) and
        ``BuyEventPackagesComponent.requestPackageBuyCountUpdate`` (split.js line 214359)
        """
        castle = self._require_own_castle(castle_id)
        request = GetPackageBuyCountsRequest(castle_id=castle.id, kingdom=castle.kingdom_id)
        reply = self.request(request, PackageBuyCountsResponse, timeout=timeout)
        return {count.package_id: count.bought_count for count in reply.counts or ()}

    def buy_event_package(
        self,
        event: PackageShopEvent | Event,
        package: PackageDef | PackageId,
        castle_id: int,
        amount: int = 1,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> BuyEventPackageResponse:
        """
        Buy a package in a running event's shop at its price, in the kingdom of one of your castles.

        A building goes to that castle. A price in rubies needs ``spend_rubies``, which also lets the server take
        rubies for the costs you lack, as the client's resource dialog offers. A package priced by your storages
        is refused; so is more than its stock leaves, or more than one of a package the client sells one at a
        time (:meth:`PackageDef.may_be_bought_in_bulk`).

        Raises:
            EventNotRunningError: The event is not running
            ValueError: The event sells no packages or not this one, ``amount`` is below 1, above what is left or
                above 1 for a package sold one at a time, the package is priced by your storages, or it costs
                rubies and ``spend_rubies`` is False
            UnknownCastleError: The castle is not one of yours
            GameDataNotLoadedError: The game data cannot be loaded
            NotEnoughSpecialCurrencyError: You lack the event currency it costs
            CommandError: The server refused

        Client: ``AMerchantBuyDialog.onBtnOkClick``, ``getBuyType`` and ``getBuyTypeId`` (split.js lines
        214956-215018); ``ModernPackageShopBuyElementBottomMenu.onOfferAccepted`` (split.js line 367863) sends the
        amount chosen; ``CastleGenericSliderBuyDialog`` (split.js line 34317) offers more than one only where
        ``mayBeBoughtInBulk``
        """
        event_id = event.event_id if isinstance(event, PackageShopEvent) else event
        running = self.client.state.get_event(event_id)
        if running is None:
            raise EventNotRunningError(int(event_id))
        if not isinstance(running, PackageShopEvent):
            raise ValueError(f"event {running.event_id} sells no packages")
        package_id = package.package_id if isinstance(package, PackageDef) else package
        sold = next(
            (p for p in running.packages(game_data=self._require_game_data()) if p.package_id == package_id), None
        )
        if sold is None:
            raise ValueError(f"event {running.event_id} does not sell package {package_id}")
        if sold.has_custom_price:
            raise ValueError(f"package {package_id} is priced by your storages, which is not supported")
        bought = self.bought_count(sold)
        left = sold.remaining_stock(bought)
        if not 1 <= amount <= left:
            raise ValueError(f"package {package_id}: {amount} asked, {left} left to buy")
        if amount > 1 and not sold.may_be_bought_in_bulk(bought):
            raise ValueError(f"package {package_id} is bought one at a time")
        rubies = sum(cost.amount for cost in sold.costs if cost.kind is CollectableKind.RUBIES) * amount
        self._require_spend_rubies(spend_rubies, f"package {package_id} costs {rubies} rubies" if rubies > 0 else None)
        castle = self._require_own_castle(castle_id)
        request = BuyEventPackageRequest(
            package_id=package_id,
            buy_type=PackageBuyType.EVENT,
            buy_type_id=int(running.event_id),
            amount=amount,
            kingdom=castle.kingdom_id,
            castle_id=castle.id if sold.places_building else -1,
            pay_with_rubies=spend_rubies,
        )
        try:
            return self.request(request, BuyEventPackageResponse, timeout=timeout, spend_rubies=spend_rubies)
        except CommandError as e:
            if e.error is GGEError.NOT_ENOUGH_SPECIAL_CURRENCY:
                raise NotEnoughSpecialCurrencyError(e.command, e.code, e.payload) from e
            raise
