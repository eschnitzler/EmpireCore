"""Your boosters: reading them and hiring them with rubies."""

from __future__ import annotations

from empire_core.enums import BoosterId
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
from empire_core.player.models.progress import BoosterInfoResponse, GetBoostersRequest
from empire_core.services.base import ServiceMixin

_HIRES: dict[BoosterId, tuple[type[HireRequest], type[HireResponse]]] = {
    BoosterId.INSTRUCTOR: (HireInstructorRequest, HireInstructorResponse),
    BoosterId.MARAUDER: (HireMarauderRequest, HireMarauderResponse),
    BoosterId.CARAVAN_OVERLOADER: (HireCaravanOverloaderRequest, HireCaravanOverloaderResponse),
    BoosterId.RETURNING_SPEED: (BuyReturnSpeedBoosterRequest, BuyReturnSpeedBoosterResponse),
}


class BoostersMixin(ServiceMixin):
    def get_boosts(self, *, timeout: float = 5.0) -> BoosterInfoResponse:
        """
        Request your boosters, premium account, production slots and festival; the reply also reaches
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
