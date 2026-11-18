"""Account sections: the daily reset, attack counter, officers' school, boosted global effects, gifts,
wishing well, new relics, frozen food production, your coat of arms, premium flag, credentials and message counts;
and the coat of arms symbols, name change info and account deletion."""

import time
from typing import Any

from empire_core.attack.models.counter import AttackCounterResponse
from empire_core.castle.models.wishing_well import WishingWellResponse
from empire_core.commanders.models.inventory import NewRelicsResponse
from empire_core.messages.models import MessagesSentToday
from empire_core.player.models.account import (
    BoostedGlobalEffectsResponse,
    DailyResetResponse,
    FoodProductionStatus,
    OfficerTraining,
    PlayerGiftsResponse,
    PremiumFlagResponse,
)
from empire_core.player.models.coat_of_arms import CoatOfArmsResponse, CoatOfArmsSymbolsResponse
from empire_core.player.models.credentials import AccountDeletion, CredentialsStatus, PlayerNameChangeInfoResponse
from empire_core.player.models.officers_school import TrainingProgramsResponse
from empire_core.state.base import StateBase, loaded, read_section
from empire_core.state.login_data import LoginDataResponse

ACCOUNT_SECTIONS = ("drt", "gai", "gatp", "bie", "pgl", "rww", "nrf", "DTS", "gem", "gpf", "scd", "mcd")


class AccountState(StateBase):
    def _parse_account(self, login: LoginDataResponse) -> set[str]:
        """Apply the account sections of a gbd, or the one a push or reply carries; return those not applied.

        Client: ``GBDCommand.exec`` (split.js line 651188) hands them to ``CastleTimerData.parse_DRT``,
        ``AttackCounterVO.parseParamObject``, ``OfficersSchoolData.parse_GATP``, ``GlobalEffectData.parse_GIE``,
        ``PlayerGiftData.parse_PGL``, ``CastleRubyWishingWellData.parse_RWW``, ``CastleEquipmentData.parseNRF``,
        ``CastleUserData.parse_DTS``, ``parse_GEM``, ``parse_GPF`` and ``parse_SCD`` and
        ``CastleMessageData.parse_MCD`` (split.js lines 579446, 339695, 715112, 711633, 582271, 110466,
        711934, 54274, 53945, 54052, 54264, 672695)
        """
        applied: set[str] = set()
        if login.daily_reset is not None:
            self.daily_reset = login.daily_reset
            applied.add("drt")
        if login.attack_counter is not None:
            self.attack_counter = login.attack_counter
            applied.add("gai")
        if (training := login.officer_training) is not None:
            self.officer_training = training if training.is_set else None
            applied.add("gatp")
        if login.boosted_global_effects is not None:
            self.boosted_global_effects = login.boosted_global_effects
            applied.add("bie")
        if login.gifts is not None:
            self.player_gifts = login.gifts
            applied.add("pgl")
        if login.wishing_well is not None:
            self.wishing_well = login.wishing_well
            applied.add("rww")
        if login.new_relics is not None:
            self.new_relics = login.new_relics
            applied.add("nrf")
        if login.food_production is not None:
            self.food_production = login.food_production
            applied.add("DTS")
        if login.coat_of_arms is not None:
            self.coat_of_arms = login.coat_of_arms
            applied.add("gem")
        if login.premium_flag is not None:
            self.premium_flag = login.premium_flag
            applied.add("gpf")
        if login.credentials is not None:
            self.credentials_status = login.credentials
            applied.add("scd")
        if login.messages_sent_today is not None:
            self.messages_sent_today = login.messages_sent_today
            applied.add("mcd")
        return (login.sent_sections & set(ACCOUNT_SECTIONS)) - applied

    def _handle_gus(self, data: Any) -> None:
        """Keep the premium symbols earned and unlocked.

        Client: ``GUSCommand.executeCommand`` (bundle line 125060), ``CastleCrestSymbolData.parse_gus``
        (bundle line 111596)
        """
        if (symbols := read_section(CoatOfArmsSymbolsResponse, data, "the coat of arms symbols")) is not None:
            self.coat_of_arms_symbols = symbols

    def _handle_gnci(self, data: Any) -> None:
        """Keep the name change count and cooldown.

        Client: ``GNCICommand.executeCommand`` (bundle line 120604), ``ChangePlayerNameData.parse_GNCI``
        (bundle line 145460)
        """
        if (info := read_section(PlayerNameChangeInfoResponse, data, "the name change info")) is not None:
            self.player_name_change_info = info

    def _handle_psd(self, data: Any) -> None:
        """Keep when the account is deleted.

        Client: ``PSDCommand.executeCommand`` (bundle line 131797)
        """
        if (deletion := read_section(AccountDeletion, data, "the account deletion")) is not None:
            self.account_deletion = deletion

    def _handle_gtp(self, data: Any) -> None:
        """Keep the training programs, and swap the program known for ``AT``'s.

        Without ``AT`` no program runs. With one while a program is known, the program becomes ``AT``'s
        slot and bonus with the time the known one had left: the client swaps when ``AT.TE`` is not the
        effect it holds, and holds a stand-in from its game data after a ``gatp`` (``parse_GATP`` clones
        the first effect it knows), so it swaps in effect every time. With ``AT`` and no program known,
        nothing changes, as in the client.

        Client: ``GTPCommand.executeCommand`` (bundle line 126183), ``OfficersSchoolData.parse_GTP``
        (bundle line 144715)
        """
        programs = read_section(TrainingProgramsResponse, data, "the training programs")
        if programs is None:
            return
        self.training_programs = programs
        running = programs.running
        if running is None:
            self.officer_training = None
        elif self.officer_training is not None:
            now = time.monotonic()
            self.officer_training = OfficerTraining(
                slot_id=running.slot_id,
                bonus=running.bonus,
                seconds=self.officer_training.remaining_seconds(now),
                received_at=now,
            )

    def get_daily_reset(self) -> DailyResetResponse | None:
        """When the daily reset comes, from the login data's ``drt``; None until it arrived."""
        with self._lock:
            return self.daily_reset

    def get_attack_counter(self) -> AttackCounterResponse | None:
        """Your attack counter, from the last ``gai``; None until one arrived."""
        with self._lock:
            return self.attack_counter

    def get_officer_training(self) -> OfficerTraining | None:
        """The officers' school training program running, from the last ``gatp`` and the ``gtp`` since.

        None when none runs; ``get_last_packet_time("gatp")`` tells "none runs" from "none arrived yet".
        """
        with self._lock:
            return self.officer_training

    def get_training_programs(self) -> TrainingProgramsResponse | None:
        """The officers' school's training programs, from the last ``gtp``; None until one arrived."""
        with self._lock:
            return self.training_programs

    def get_boosted_global_effects(self) -> BoostedGlobalEffectsResponse | None:
        """The global effects the running booster event boosts, from the last ``bie``; None until one arrived."""
        with self._lock:
            return self.boosted_global_effects

    def get_player_gifts(self) -> PlayerGiftsResponse | None:
        """Your gift packages and how many you may still send, from the last ``pgl``; None until one arrived."""
        with self._lock:
            return self.player_gifts

    def get_wishing_well(self) -> WishingWellResponse | None:
        """The ruby wishing well, from the last ``rww``; None until one arrived."""
        with self._lock:
            return self.wishing_well

    def get_food_production(self) -> FoodProductionStatus | None:
        """Whether your food production is frozen, from the last ``DTS``; None until one arrived."""
        with self._lock:
            return self.food_production

    def get_coat_of_arms(self) -> CoatOfArmsResponse | None:
        """Your coat of arms, from the login data's ``gem`` and the ``gem`` and ``cem`` since; None before one."""
        with self._lock:
            return self.coat_of_arms

    def get_premium_flag(self) -> PremiumFlagResponse | None:
        """Whether you own the premium flag, from the login data's ``gpf`` or the last push; None before one."""
        with self._lock:
            return self.premium_flag

    def get_coat_of_arms_symbols(self) -> CoatOfArmsSymbolsResponse | None:
        """The premium symbols earned and unlocked, from the last ``gus``; None until one arrived."""
        with self._lock:
            return self.coat_of_arms_symbols

    def get_credentials_status(self) -> CredentialsStatus | None:
        """Which of your credentials are temporary, from the last ``scd``; None until one arrived."""
        with self._lock:
            return self.credentials_status

    def get_player_name_change_info(self) -> PlayerNameChangeInfoResponse | None:
        """Your name change count and cooldown, from the last ``gnci``; None until one arrived."""
        with self._lock:
            return self.player_name_change_info

    def get_account_deletion(self) -> AccountDeletion | None:
        """When your account is deleted, from the last ``psd``; None until one arrived."""
        with self._lock:
            return self.account_deletion

    def get_messages_sent_today(self) -> MessagesSentToday | None:
        """Messages of each limited type sent today, from the last ``mcd``; None until one arrived."""
        with self._lock:
            return self.messages_sent_today

    def get_new_relics(self) -> NewRelicsResponse:
        """Whether new relics wait to be seen, from the last ``nrf``; the login data brings one.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        with self._lock:
            return loaded(self.new_relics, "New relics")
