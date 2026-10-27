"""Alliance diplomacy, the newsletter and donations."""

from __future__ import annotations

from empire_core.alliance.models.aqua import (
    AllianceMemberAquaPoints,
    AllianceMemberAquaPointsRequest,
    AllianceMemberAquaPointsResponse,
)
from empire_core.alliance.models.diplomacy import (
    AllianceDonation,
    ChangeDiplomacyRequest,
    ChangeDiplomacyResponse,
    DonateRequest,
    DonateResponse,
    DonationResourcesResponse,
    GetDonationResourcesRequest,
    RefuseDiplomacyRequest,
    RefuseDiplomacyResponse,
    SendNewsletterRequest,
    SetAutoWarRequest,
    SetAutoWarResponse,
)
from empire_core.alliance.models.forge import (
    RELIC_FORGE_MIN_LEGEND_LEVEL,
    ForgeCraftRequest,
    ForgeCraftResponse,
    relic_forge_ruby_cost,
)
from empire_core.alliance.models.info import AllianceInfo
from empire_core.alliance.service.own import OwnAllianceMixin, _echoed
from empire_core.enums import DiplomacyStatus


class DiplomacyMixin(OwnAllianceMixin):
    # =========================================================================
    # Diplomacy, Newsletter and Donations
    # =========================================================================

    def change_diplomacy(
        self, alliance_id: int, new_status: DiplomacyStatus, tribute: int = 0, *, timeout: float = 5.0
    ) -> ChangeDiplomacyResponse:
        """
        Change or propose your alliance's relation with another alliance.

        Args:
            alliance_id: The other alliance, e.g. ``AllianceDiplomacyStatus.alliance_id``
            new_status: The relation to change to
            tribute: Only to accept a peace offer: ``PeaceOffer.tribute`` as the offer states it

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleAllianceInfoDialogDiplomacy.updateButtons`` (bundle line 72349) offers
        each change from the other alliance's status to your own
        """
        request = ChangeDiplomacyRequest(alliance_id=alliance_id, new_status=new_status, tribute=tribute)
        with self._own_alliance():
            return self.request(request, ChangeDiplomacyResponse, timeout=timeout)

    def refuse_diplomacy(self, alliance_id: int, *, timeout: float = 5.0) -> AllianceInfo | None:
        """
        Refuse another alliance's diplomacy request or peace offer.

        Returns:
            The other alliance after the refusal

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            PacketError: The reply carries no alliance
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``ARDCommand.executeCommand`` (bundle line 121574) reads the reply's ``A``;
        ``CastleAllianceDialogDiplomacy`` opens the dialogs that refuse (bundle lines 69323, 69352)
        """
        with self._own_alliance():
            response = self.request(
                RefuseDiplomacyRequest(alliance_id=alliance_id), RefuseDiplomacyResponse, timeout=timeout
            )
        return _echoed(response.alliance, "ard")

    def set_auto_war(self, enabled: bool, *, timeout: float = 5.0) -> bool:
        """
        Turn auto war on or off.

        Returns:
            Whether auto war is on afterwards

        Raises:
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        request = SetAutoWarRequest(auto_war=1 if enabled else 0)
        with self._own_alliance():
            return self.request(request, SetAutoWarResponse, timeout=timeout).auto_war

    def send_newsletter(self, subject: str, text: str, *, timeout: float = 5.0) -> None:
        """
        Send the alliance newsletter to every member.

        Args:
            subject: The subject (the client's field takes 20 characters)
            text: The text; the client does not send an empty one

        Raises:
            ValueError: ``text`` is empty
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
        """
        if not text:
            raise ValueError("a newsletter needs text")
        with self._own_alliance():
            self.execute(SendNewsletterRequest.create(subject, text), timeout=timeout)

    def donate(
        self, castle_id: int, donation: AllianceDonation, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> DonateResponse:
        """
        Donate resources from one of your castles to the alliance treasury.

        Donating ``AllianceDonation.rubies`` spends them; see "Spending rubies" in the guides.

        Args:
            castle_id: The donating castle, a ``Castle.id`` from ``client.state.get_castles()``
            donation: The amounts; the client sends nothing when every amount is 0
            spend_rubies: Allow a donation of rubies
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list
            ValueError: every amount is 0, or rubies are donated and ``spend_rubies`` is False
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleAllianceDonateDialog.onDonateForAlliance`` (bundle line 45576) sends
        the picked castle's ``objectId`` and ``kingdomID``
        """
        request = DonateRequest.create(castle_id, self._require_own_castle(castle_id).kingdom_id, donation)
        if not request.resources:
            raise ValueError("a donation needs an amount above 0")
        self._require_spend_rubies(
            spend_rubies, f"donating {donation.rubies} rubies spends them" if donation.rubies > 0 else None
        )
        with self._own_alliance():
            return self.request(request, DonateResponse, timeout=timeout)

    def get_donation_resources(self, castle_id: int, *, timeout: float = 5.0) -> DonationResourcesResponse:
        """
        What one of your castles has to donate: its resources, and your special currencies.

        Both are applied to state as the client applies them.

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``

        Client: ``CastleAllianceDonateDialog.selectCastle`` (bundle line 45573) sends the picked castle's
        ``objectId`` and ``kingdomID``
        """
        request = GetDonationResourcesRequest(
            castle_id=castle_id, kingdom=self._require_own_castle(castle_id).kingdom_id
        )
        with self._own_alliance():
            return self.request(request, DonationResourcesResponse, timeout=timeout)

    def get_member_aqua_points(self, *, timeout: float = 5.0) -> list[AllianceMemberAquaPoints]:
        """
        Your alliance members' aqua points, in the order the server lists them.

        Client: ``CastleEilandRankingDialogPlayer.requestHighscoreData`` (bundle line 98145) asks with
        your alliance's id
        """
        alliance_id = self._require_local_alliance_id()
        with self._own_alliance():
            return self.request(
                AllianceMemberAquaPointsRequest(alliance_id=alliance_id),
                AllianceMemberAquaPointsResponse,
                timeout=timeout,
            ).members

    def forge(
        self, *, pay_with_rubies: bool = False, spend_rubies: bool = False, timeout: float = 5.0
    ) -> ForgeCraftResponse:
        """
        Craft in the alliance forge: an equipment item, a gem or a relic gem.

        Below legend level 1 the alliance forge crafts when your alliance's ``is_able_to_forge`` allows it.
        From legend level 1 the relic forge crafts instead, paid in coins, or in rubies with
        ``pay_with_rubies``; its price rises with each craft of the day (:func:`relic_forge_coin_cost`,
        :func:`relic_forge_ruby_cost`). Your alliance and a crafted gem are applied to state.

        Raises:
            ValueError: The forge cannot craft now, rubies are asked below legend level 1, or rubies
                are spent without ``spend_rubies``
            NotInAllianceError: You are in no alliance (nothing is sent), or the server answered ``ALLI_NOT_FOUND``
            CommandError: The server refused

        Client: ``CastleAllianceDialog`` picks the forge by legend level (bundle line 4911);
        ``CastleAllianceDialogForge.isAllowedToCraft`` (bundle line 45123), and
        ``CastleAllianceDialogForgeHigh`` (bundle lines 69578-69599), which allows every craft and prices it
        by the alliance's uses of the day
        """
        alliance_id = self._require_local_alliance_id()
        alliance = self.client.state.get_own_alliance()
        if alliance is None or alliance.alliance_id != alliance_id:
            raise ValueError("your alliance's details have not arrived; read them with get_alliance_info first")
        relic_forge = self.client.state.get_local_player().legendary_level >= RELIC_FORGE_MIN_LEGEND_LEVEL
        if pay_with_rubies and not relic_forge:
            raise ValueError(f"only the relic forge, from legend level {RELIC_FORGE_MIN_LEGEND_LEVEL}, takes rubies")
        if not relic_forge and not alliance.is_able_to_forge:
            raise ValueError("the alliance forge cannot craft now")
        self._require_spend_rubies(
            spend_rubies,
            f"the relic forge costs {relic_forge_ruby_cost(alliance.hard_relic_forge_uses)} rubies"
            if pay_with_rubies
            else None,
        )
        with self._own_alliance():
            return self.request(ForgeCraftRequest(pay_with_rubies=pay_with_rubies), ForgeCraftResponse, timeout=timeout)
