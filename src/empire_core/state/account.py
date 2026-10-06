"""Account sections: the daily reset, attack counter, officers' school, boosted global effects, gifts,
wishing well and new relics."""

import time
from typing import Any

from empire_core.attack.models.counter import AttackCounterResponse
from empire_core.castle.models.wishing_well import WishingWellResponse
from empire_core.commanders.models.inventory import NewRelicsResponse
from empire_core.player.models.account import (
    BoostedGlobalEffectsResponse,
    DailyResetResponse,
    OfficerTraining,
    PlayerGiftsResponse,
)
from empire_core.protocol.js import js_int, js_truthy
from empire_core.state.base import StateBase, read_section

ACCOUNT_SECTIONS = ("drt", "gai", "gatp", "bie", "pgl", "rww", "nrf")


class AccountState(StateBase):
    def _parse_account(self, data: dict[str, Any]) -> set[str]:
        """Apply the account sections of a gbd, or the one a push or reply carries; return those not applied.

        Client: ``GBDCommand.exec`` (bundle line 129381) calls ``parse_DRT``, ``parse_GATP``,
        ``parse_GIE`` (with ``bie``), ``parse_RWW`` and ``parseNRF``, and ``parse_PGL`` and the attack
        counter's ``parseParamObject`` only when ``pgl`` and ``gai`` are truthy
        """
        applied: set[str] = set()
        if js_truthy(drt := data.get("drt")):
            if (reset := read_section(DailyResetResponse, drt, "the daily reset")) is not None:
                self.daily_reset = reset
                applied.add("drt")
        if js_truthy(gai := data.get("gai")):
            if (counter := read_section(AttackCounterResponse, gai, "the attack counter")) is not None:
                self.attack_counter = counter
                applied.add("gai")
        if "gatp" in data and self._apply_officer_training(data["gatp"]):
            applied.add("gatp")
        bie = data.get("bie")
        if isinstance(bie, dict) and js_truthy(bie.get("GE")):
            if (boosted := read_section(BoostedGlobalEffectsResponse, bie, "the boosted global effects")) is not None:
                self.boosted_global_effects = boosted
                applied.add("bie")
        pgl = data.get("pgl")
        if isinstance(pgl, dict) and js_truthy(pgl.get("G")):
            if (gifts := read_section(PlayerGiftsResponse, pgl, "the gift packages")) is not None:
                self.player_gifts = gifts
                applied.add("pgl")
        if js_truthy(rww := data.get("rww")):
            if (well := read_section(WishingWellResponse, rww, "the wishing well")) is not None:
                self.wishing_well = well
                applied.add("rww")
        if "nrf" in data and (relics := read_section(NewRelicsResponse, data["nrf"], "the new relics")) is not None:
            self.new_relics = relics
            applied.add("nrf")
        return {section for section in ACCOUNT_SECTIONS if section in data} - applied

    def _apply_officer_training(self, body: Any) -> bool:
        """Read a ``gatp``: any block drops the program known, and one the client takes as running sets it.

        Client: ``OfficersSchoolData.parse_GATP`` (bundle line 144606)
        """
        if not js_truthy(body):
            self.officer_training = None
            return True
        training = read_section(OfficerTraining, body, "the officers' school training")
        if training is None:
            return False
        self.officer_training = training if training.is_set else None
        return True

    def _handle_gtp(self, data: Any) -> None:
        """Handle the training programs: ``AT`` is the program running, the offered ones are not read.

        Without ``AT`` no program runs. With one while a program is known, the program becomes ``AT``'s
        slot and bonus with the time the known one had left: the client swaps when ``AT.TE`` is not the
        effect it holds, and holds a stand-in from its game data after a ``gatp`` (``parse_GATP`` clones
        the first effect it knows), so it swaps in effect every time. With ``AT`` and no program known,
        nothing changes, as in the client.

        Client: ``GTPCommand.executeCommand`` (bundle line 126146), ``OfficersSchoolData.parse_GTP`` and
        ``parseOfficerEffectVO`` (bundle lines 144609-144614, 144631)
        """
        if not isinstance(data, dict):
            return
        running = data.get("AT")
        if not js_truthy(running):
            self.officer_training = None
        elif self.officer_training is not None and isinstance(running, dict):
            now = time.monotonic()
            self.officer_training = OfficerTraining(
                slot_id=js_int(running.get("S")),
                bonus=running.get("E"),
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

    def get_new_relics(self) -> NewRelicsResponse | None:
        """Whether new relics wait to be seen, from the last ``nrf``; None until one arrived."""
        with self._lock:
            return self.new_relics
