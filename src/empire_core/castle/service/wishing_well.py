"""The ruby wishing well in your main castle: throw in rubies and a lucky penny, collect twice the rubies later."""

from __future__ import annotations

from empire_core.castle.models.wishing_well import WishingWellRequest, WishingWellResponse, wishing_well_skip_rubies
from empire_core.enums import WishingWellOption
from empire_core.services.base import ServiceMixin


class WishingWellMixin(ServiceMixin):
    def get_wishing_well(self, *, timeout: float = 5.0) -> WishingWellResponse:
        """
        Read the wishing well's level and time from the server; its reply also updates :attr:`wishing_well`.

        Client: ``CastleRubyWishingWellData.requestFreshWishingWellData`` (split.js line 110510)
        """
        return self.request(WishingWellRequest(option=WishingWellOption.UPDATE), WishingWellResponse, timeout=timeout)

    def start_wishing_well(self, *, spend_rubies: bool = False, timeout: float = 5.0) -> WishingWellResponse:
        """
        Start the wishing well: it takes its level's entry rubies and lucky pennies, and gives twice the rubies
        once its waiting time has passed. See "Spending rubies" in the guides.

        Args:
            spend_rubies: Allow the entry rubies; without it nothing is sent
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False
            CommandError: The server refused, ``NOT_ENOUGH_WISHINGWELLCOINS`` among others

        Client: ``RubyWishingWellDialog.updateArrow`` and ``onClick`` (split.js lines 266174, 266334), the entry
        rubies and lucky pennies from ``CastleRubyWishingWellVO.parseXML`` (split.js line 328993); the dialog's
        ``dialog_rubyWishingWell_desc_general`` text asks to throw in that many rubies and a lucky penny
        """
        self._require_spend_rubies(spend_rubies, "starting the wishing well throws in its entry rubies")
        request = WishingWellRequest(option=WishingWellOption.START)
        return self.request(request, WishingWellResponse, timeout=timeout, spend_rubies=spend_rubies)

    def finish_wishing_well(self, *, spend_rubies: bool = False, timeout: float = 5.0) -> WishingWellResponse:
        """
        Finish the running wishing well now, for rubies; see "Spending rubies" in the guides. Collect it after.

        Args:
            spend_rubies: Allow the rubies it costs, :func:`wishing_well_skip_rubies` of the time left; without
                it nothing is sent
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False
            CommandError: The server refused

        Client: ``RubyWishingWellDialog.updateArrow`` and ``onClick`` (split.js lines 266174, 266334)
        """
        well = self.client.state.get_wishing_well()
        price = (
            f"{wishing_well_skip_rubies(well.remaining_seconds())} rubies"
            if well is not None and well.is_running
            else "rubies"
        )
        self._require_spend_rubies(spend_rubies, f"finishing the wishing well costs {price}")
        request = WishingWellRequest(option=WishingWellOption.SKIP)
        return self.request(request, WishingWellResponse, timeout=timeout, spend_rubies=spend_rubies)

    def collect_wishing_well(self, *, timeout: float = 5.0) -> WishingWellResponse:
        """
        Collect the rubies of a finished wishing well.

        Client: ``RubyWishingWellFixedPositionBuildingVE.onMouseClick`` (split.js line 444996) and
        ``RubyWishingWellDialog.onClick`` (split.js line 266334)
        """
        return self.request(WishingWellRequest(option=WishingWellOption.COLLECT), WishingWellResponse, timeout=timeout)

    def upgrade_wishing_well(self, *, spend_rubies: bool = False, timeout: float = 5.0) -> WishingWellResponse:
        """
        Upgrade the wishing well to its next level, for the wood and stone that level costs.

        Args:
            spend_rubies: Pay the resources you lack with rubies, as the client's resource dialog does; see
                "Spending rubies" in the guides
            timeout: Timeout in seconds

        Raises:
            CommandError: The server refused, ``NOT_ENOUGH_RESOURCES`` without ``spend_rubies``

        Client: ``IsoServerCommands.upgradeBuilding`` (split.js line 328747) sends it for wod ids 601 to 611;
        with rubies, ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (split.js line 183792)
        """
        request = WishingWellRequest(option=WishingWellOption.UPGRADE, pay_with_rubies=spend_rubies)
        return self.request(request, WishingWellResponse, timeout=timeout, spend_rubies=spend_rubies)
