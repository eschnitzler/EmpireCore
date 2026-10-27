"""Relocation, the officers' school, your hero, loot boxes and gifts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from empire_core.enums import Hero
from empire_core.player.models.account import SendGiftPackagesRequest
from empire_core.player.models.economy import GetLootBoxesRequest, LootBoxesResponse
from empire_core.player.models.hero import HeroDecisionRequest, HeroDecisionResponse
from empire_core.player.models.officers_school import (
    ActivateTrainingProgramRequest,
    ActivateTrainingProgramResponse,
    GetTrainingProgramsRequest,
    ProlongTrainingProgramRequest,
    ProlongTrainingProgramResponse,
    RerollTrainingProgramsRequest,
    RerollTrainingProgramsResponse,
    TrainingProgramsResponse,
)
from empire_core.services.base import ServiceMixin

if TYPE_CHECKING:
    from empire_core.gamedata import PackageId
    from empire_core.player.models.account import (
        BoostedGlobalEffectsResponse,
        DailyResetResponse,
        OfficerTraining,
        PlayerGiftsResponse,
    )
    from empire_core.player.models.progress import RelocationInfoResponse

# OfficersSchoolEffectVO.getCost (bundle line 144773) prices the program in this slot in rubies
_RUBY_TRAINING_SLOT = 3


class TrainingMixin(ServiceMixin):
    @property
    def relocation(self) -> RelocationInfoResponse | None:
        """Your castle relocations, from the last ``gri``; None until one arrived."""
        return self.client.state.get_relocation()

    @property
    def officer_training(self) -> OfficerTraining | None:
        """The officers' school training program running, from the last ``gatp`` and the ``gtp`` since."""
        return self.client.state.get_officer_training()

    @property
    def training_programs(self) -> TrainingProgramsResponse | None:
        """The officers' school's training programs, from the last ``gtp``; None until one arrived."""
        return self.client.state.get_training_programs()

    def get_training_programs(self, *, timeout: float = 5.0) -> TrainingProgramsResponse:
        """
        Request the officers' school's training programs: those on offer, the one running and today's counts.

        Client: ``OfficersSchoolDialogList.show`` (bundle line 85651) sends ``C2SGetTrainingProgramInfoVO``;
        ``GTPCommand.executeCommand`` (bundle line 126183)
        """
        return self.request(GetTrainingProgramsRequest(), TrainingProgramsResponse, timeout=timeout)

    def activate_training_program(self, slot_id: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Start the training program on offer in ``slot_id``.

        Slot 1's program costs coins, slot 2's the day's event currency and slot 3's rubies, so slot 3
        needs ``spend_rubies``.

        Raises:
            ValueError: Slot 3 without ``spend_rubies``
            CommandError: The server refused

        Client: ``OfficersSchoolEffectItem.onConfirmBuy`` (bundle line 85774), ``OfficersSchoolEffectVO.getCost``
        (bundle line 144773), ``ATPCommand.executeCommand`` (bundle line 126155)
        """
        self._require_spend_rubies(
            spend_rubies, "the slot 3 training program costs rubies" if slot_id == _RUBY_TRAINING_SLOT else None
        )
        self.request(ActivateTrainingProgramRequest(slot_id=slot_id), ActivateTrainingProgramResponse, timeout=timeout)

    def prolong_training_program(self, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Prolong the training program running, for rubies.

        Raises:
            ValueError: Without ``spend_rubies``
            CommandError: The server refused

        Client: ``OfficersSchoolDialogList.onBuyProlong`` (bundle line 85691),
        ``OfficersSchoolData.getC2ProlongCosts`` (bundle line 144743), ``PTPCommand.executeCommand``
        (bundle line 126198)
        """
        self._require_spend_rubies(spend_rubies, "prolonging a training program costs rubies")
        self.request(ProlongTrainingProgramRequest(), ProlongTrainingProgramResponse, timeout=timeout)

    def reroll_training_programs(
        self,
        kept_slot_ids: Sequence[int] = (),
        *,
        premium: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Replace the training programs on offer, except those in ``kept_slot_ids``.

        The reroll costs the day's event currency; a ``premium`` one costs rubies and needs ``spend_rubies``.

        Raises:
            ValueError: ``premium`` without ``spend_rubies``
            CommandError: The server refused

        Client: ``OfficersSchoolDialogList.onConfirmSoftReroll`` and ``onConfirmHardReroll`` (bundle lines
        85689-85690), ``OfficersSchoolData.sendReroll`` (bundle line 144706), ``RTPCommand.executeCommand``
        (bundle line 126211)
        """
        self._require_spend_rubies(spend_rubies, "a premium reroll costs rubies" if premium else None)
        request = RerollTrainingProgramsRequest(premium=premium, kept_slot_ids=list(kept_slot_ids))
        self.request(request, RerollTrainingProgramsResponse, timeout=timeout)

    @property
    def hero(self) -> Hero | int | None:
        """Your hero, from the last ``hdc``; None until one arrived or while you have yet to pick one."""
        return self.client.state.get_hero()

    def choose_hero(self, hero: Hero, *, timeout: float = 5.0) -> HeroDecisionResponse:
        """
        Pick your hero, the tutorial's quest character.

        Raises:
            CommandError: The server refused

        Client: ``CastleChooseHeroDialog.sendHeroIdToServer`` (bundle line 42429), ``HDCommand.executeCommand``
        (bundle line 124371)
        """
        return self.request(HeroDecisionRequest(hero=hero), HeroDecisionResponse, timeout=timeout)

    @property
    def boosted_global_effects(self) -> BoostedGlobalEffectsResponse | None:
        """The global effects the running booster event boosts, from the last ``bie``; None until one arrived."""
        return self.client.state.get_boosted_global_effects()

    @property
    def loot_boxes(self) -> LootBoxesResponse | None:
        """Your loot boxes and key progress; None until a ``gls`` arrived."""
        return self.client.state.get_loot_boxes()

    def get_loot_boxes(self, *, timeout: float = 5.0) -> LootBoxesResponse:
        """
        Request your loot boxes and key progress, as the client does when the mystery boxes open;
        the reply is also kept in :attr:`loot_boxes`.

        Client: ``RewardHubMainDialogMysteryBoxes.show`` (bundle line 92142) sends ``C2SGetLootBoxesStatus``

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(GetLootBoxesRequest(), LootBoxesResponse, timeout=timeout)

    @property
    def daily_reset(self) -> DailyResetResponse | None:
        """When the daily reset comes, from the login data's ``drt``; None until it arrived."""
        return self.client.state.get_daily_reset()

    @property
    def gifts(self) -> PlayerGiftsResponse | None:
        """Your gift packages and how many you may still send, from the last ``pgl``; None until one arrived."""
        return self.client.state.get_player_gifts()

    def send_gift_packages(
        self, receiver_id: int, package_id: PackageId, amount: int = 1, *, timeout: float = 5.0
    ) -> None:
        """
        Send another player gift packages you hold, as many as ``amount``.

        Args:
            receiver_id: The player who gets them
            package_id: The package, a ``PlayerGift.package_id`` of :attr:`gifts`
            amount: How many to send, 1 at least
            timeout: Timeout in seconds

        Raises:
            ValueError: ``amount`` is below 1
            CommandError: The server refused, ``TOO_MANY_PACKAGES_SENT_TODAY`` past the day's limit
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastlePlayerGiftSliderGiveDialog.onBtnOkClick`` (bundle line 68336) sends one to the slider's
        held amount; ``GPGCommand.executeCommand`` (bundle line 127957)
        """
        if amount < 1:
            raise ValueError("send at least one gift package")
        self.execute(
            SendGiftPackagesRequest(receiver_id=receiver_id, package_id=package_id, amount=amount), timeout=timeout
        )
