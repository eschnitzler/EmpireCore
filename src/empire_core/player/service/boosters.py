"""Your boosters: reading them, hiring them with rubies and holding a feast."""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.enums import BoosterId, Kingdom
from empire_core.player.models.boosters import (
    NO_OFFER,
    OVERSEERS,
    BuyReturnSpeedBoosterRequest,
    BuyReturnSpeedBoosterResponse,
    HireCaravanOverloaderRequest,
    HireCaravanOverloaderResponse,
    HireInstructorRequest,
    HireInstructorResponse,
    HireMarauderRequest,
    HireMarauderResponse,
    HireOverseerRequest,
    HireOverseerResponse,
    HireRequest,
    HireResponse,
)
from empire_core.player.models.feasts import HoldFeastRequest, HoldFeastResponse
from empire_core.player.models.progress import BoosterInfoResponse, GetBoostersRequest
from empire_core.services.base import ServiceMixin

if TYPE_CHECKING:
    from empire_core.gamedata import Feast

_HIRES: dict[BoosterId, tuple[type[HireRequest], type[HireResponse]]] = {
    BoosterId.INSTRUCTOR: (HireInstructorRequest, HireInstructorResponse),
    BoosterId.MARAUDER: (HireMarauderRequest, HireMarauderResponse),
    BoosterId.CARAVAN_OVERLOADER: (HireCaravanOverloaderRequest, HireCaravanOverloaderResponse),
    BoosterId.RETURNING_SPEED: (BuyReturnSpeedBoosterRequest, BuyReturnSpeedBoosterResponse),
}


class BoostersMixin(ServiceMixin):
    def get_boosts(self, *, timeout: float = 5.0) -> BoosterInfoResponse:
        """
        Request your boosters, premium account, production slots and feast; the reply also reaches
        :attr:`boosts`.

        Client: ``C2SBoosterInfoVO`` (bundle line 149206); ``BOICommand.executeCommand`` (bundle line 627667)
        """
        return self.request(GetBoostersRequest(), BoosterInfoResponse, timeout=timeout)

    def hire_booster(
        self,
        booster: BoosterId,
        *,
        spend_rubies: bool = False,
        private_offer_id: int = NO_OFFER,
        timeout: float = 5.0,
    ) -> HireResponse:
        """
        Hire a booster with rubies: the instructor, the marauder, an overseer, the caravan overloader or
        the return speed booster; see "Spending rubies" in the guides.

        Its price comes with the boosters and is not worked out here, so this always needs ``spend_rubies``.
        The tax collector is bribed with ``client.castle.bribe_tax_collector``.

        Args:
            booster: The booster to hire
            spend_rubies: Allow the rubies it costs; without it nothing is sent
            private_offer_id: The booster sale the hire uses, -1 for none
            timeout: Timeout in seconds

        Returns:
            Coins and rubies, and the boosters after; the boosters also reach :attr:`boosts`

        Raises:
            ValueError: ``spend_rubies`` is False, or no such hire
            CommandError: The server refused

        Client: ``BuyBoosterCommand.execute`` (bundle line 459673) and
        ``CastleBuyReturnSpeedBoosterDialog.onClick`` (bundle line 463069), each with
        ``CastleBoosterSaleData.getOfferId`` (bundle line 52882)
        """
        if booster == BoosterId.TAX:
            raise ValueError("the tax collector is bribed with client.castle.bribe_tax_collector")
        if booster not in OVERSEERS and booster not in _HIRES:
            raise ValueError(f"{booster!r} is not hired with rubies")
        self._require_spend_rubies(spend_rubies, f"hiring {booster!r} costs rubies")
        if booster in OVERSEERS:
            request = HireOverseerRequest(overseer=booster, private_offer_id=private_offer_id)
            return self.request(request, HireOverseerResponse, timeout=timeout, spend_rubies=spend_rubies)
        request_type, response_type = _HIRES[booster]
        return self.request(
            request_type(private_offer_id=private_offer_id), response_type, timeout=timeout, spend_rubies=spend_rubies
        )

    def hold_feast(
        self,
        feast: Feast,
        castle_id: int,
        *,
        spend_rubies: bool = False,
        private_offer_id: int = -1,
        timeout: float = 5.0,
    ) -> HoldFeastResponse:
        """
        Hold a feast for faster recruitment in every castle, paid from one of your castles' food or with
        rubies; on the feast you hold, extend it. See "Spending rubies" in the guides.

        As the client offers it: while a feast runs only that one, extended; otherwise one your level is
        in range of (``FeastDef.offered_at``), paid from a castle outside Berimond. A ruby feast needs
        ``spend_rubies``; on a food feast ``spend_rubies`` pays the food the castle lacks with rubies, as the
        client's resource dialog does after a refusal for missing food. A food feast costs its
        ``FeastDef.cost_food`` less ``client.castle.get_feast_cost_reduction()`` percent, as the dialogs show it.

        Args:
            feast: The feast, a ``Feast`` member
            castle_id: The castle that pays the food, a ``Castle.id`` from ``client.state.get_castles()``
            spend_rubies: Allow a ruby feast's price, and pay missing food with rubies
            private_offer_id: The resource merchant's private offer, which the client sends with the paid
                food, -1 for none
            timeout: Timeout in seconds

        Returns:
            The feast you hold after; it also reaches :attr:`boosts`

        Raises:
            ValueError: Another feast runs, your level is out of the feast's range, the castle is in
                Berimond, the feast is not in the game data, or it costs rubies and ``spend_rubies`` is False
            UnknownCastleError: ``castle_id`` is not in your castle list
            StateNotLoadedError: No login has brought the player or the boosters
            GameDataNotLoadedError: The game data cannot be loaded
            CommandError: The server refused, ``NOT_ENOUGH_RESOURCES`` when the castle lacks the food

        Client: ``CastleFestivalPremiumShopVO.clickedBuyButton``, ``canBeBought`` and ``isActiveFeastOutdated``
        (split.js lines 215420-215505) open the extend dialog while a feast runs, which sends its id
        (``CastleExtendFestivalDialog.onClick``, split.js line 334119), and else ``CastleFestivalDialog``, which
        lists ``getFestivalItemsByLevel(userLevel)`` (split.js line 334547) and castles outside
        ``FactionConst.KINGDOM_ID`` (split.js line 334400); ``PremiumFestivalItemVO.hasC2Costs`` (split.js line
        333252); ``CastlePrivateOfferData.getPrivateOfferMerchantID`` (split.js line 660957)
        """
        row = self._require_game_data().feasts.get(feast)
        if row is None:
            raise ValueError(f"{feast!r} is not in the game data")
        player = self.client.state.get_local_player()
        held = self.client.state.get_boosts().feast
        if held is not None and held.is_active():
            if held.feast_id != row.feast_id:
                raise ValueError(f"{held.feast_id!r} runs; the game offers only extending it")
            level = player.level + player.legendary_level
        else:
            level = player.level
        if not row.offered_at(level):
            raise ValueError(f"{feast!r} is offered from level {row.min_level} to {row.max_level}, not at {level}")
        castle = self._require_own_castle(castle_id)
        if castle.kingdom_id == Kingdom.BERIMOND:
            raise ValueError("the game offers no feast paid from a castle in Berimond")
        if row.is_ruby_priced:
            self._require_spend_rubies(spend_rubies, f"{feast!r} costs {row.cost_rubies} rubies")
        request = HoldFeastRequest(
            feast_id=row.feast_id,
            castle_id=castle.id,
            kingdom=castle.kingdom_id,
            private_offer_id=private_offer_id,
            pay_with_rubies=spend_rubies and not row.is_ruby_priced,
        )
        return self.request(request, HoldFeastResponse, timeout=timeout, spend_rubies=spend_rubies)
