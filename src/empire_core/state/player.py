"""Local player tracking: gpi/gxp/gcu/vip/gho/uap, alliance (gal), special currencies (sce), spies and your
hero (hdc)."""

import logging
import math
import time
from typing import Any

from empire_core.alliance.models.membership import AllianceMembershipResponse
from empire_core.enums import Hero
from empire_core.gamedata import Currency
from empire_core.map.models.areas import KingdomProtection
from empire_core.player.models.account import PlayerIdentityResponse, VipStatusResponse
from empire_core.player.models.economy import CurrencyResponse, SpecialCurrenciesResponse
from empire_core.player.models.hero import HeroDecisionResponse
from empire_core.player.models.progress import ExperienceResponse, HonorResponse
from empire_core.protocol.base import BasePayload, read_or_none
from empire_core.protocol.js import js_truthy
from empire_core.spy.models import MaxSpiesResponse
from empire_core.state.base import StateBase, loaded, read_section
from empire_core.state.models import Player

logger = logging.getLogger(__name__)


LEVEL_CAP = 70
LEGEND_LEVEL_CAP = 950
_LEVEL_CAP_XP = LEVEL_CAP * LEVEL_CAP * 30


def xp_for_level(level: int) -> int:
    """Total XP at which ``level`` starts. Client: ``PlayerConst.getXPFromLevel``."""
    return min(_LEVEL_CAP_XP, level * level * 30)


def legend_level_for_xp(xp: int) -> int:
    """Legend level reached with ``xp`` total XP. Client: ``PlayerConst.getLegendLevelFromXP``."""
    past_cap = xp - _LEVEL_CAP_XP
    if past_cap < 0:
        return 0
    return min(LEGEND_LEVEL_CAP, max(1, math.floor(((past_cap + 2750) / 3000) ** (1 / 1.19))))


def xp_for_legend_level(legend_level: int) -> int:
    """Total XP at which ``legend_level`` starts. Client: ``PlayerConst.getXPFromLegendLevel``."""
    if legend_level < 1:
        return 0
    legend_level = min(LEGEND_LEVEL_CAP, legend_level)
    return math.ceil(3000 * legend_level**1.19) - 2750 + _LEVEL_CAP_XP


def level_progress(level: int, xp: int) -> tuple[int, int, int]:
    """Legend level and the XP at which the current and next level start.

    Client: ``CastleUserData.parse_GXP``, which ignores the LL, XPFCL and
    XPTNL the server sends alongside and computes them from LVL and XP.
    """
    legend = legend_level_for_xp(xp) if level >= LEVEL_CAP else 0
    if legend > 0:
        return legend, xp_for_legend_level(legend), xp_for_legend_level(legend + 1)
    return 0, xp_for_level(level), xp_for_level(level + 1)


def _sent(section: BasePayload, field: str, previous: Any) -> Any:
    """The section's field when the packet carried it, else the value held; the client would read 0."""
    return getattr(section, field) if field in section.model_fields_set else previous


# Player fields by the gpi field that fills them
_IDENTITY_FIELDS = {"PID": "player_id", "PN": "name", "E": "email", "user_id": "user_id"}


class PlayerState(StateBase):
    def _parse_player_sections(self, data: dict[str, Any]) -> list[KingdomProtection]:
        """Parse the gpi/gxp/gcu/vip/gho/uap/gac sections as ONE atomic player update.

        Returns the protection blocks read, for the events they also update.

        `local_player` is handed out to user code and read without the lock,
        so a field-by-field merge would let a reader observe a half-merged
        player. A re-login gbd spreads its fields across sections (identity
        in gpi, level/XP in gxp, currency in gcu, VIP in vip), so merging
        gpi atomically but editing the other sections' fields one at a time
        would still expose "new name, old level". The complete field mapping
        is therefore built across *all* sections first and swapped in with a
        single store (see :meth:`_swap_model_fields`), which keeps the
        identity-map behavior — references held by user code stay live —
        while never exposing an intermediate state.

        gxp, gcu, vip and gho are partial updates: a key they omit keeps its
        previous value (this packet's gpi value if it carried one, else the
        existing state) rather than resetting to zero.

        Client: ``CastleUserData.parse_GPI`` / ``parse_GXP`` / ``parse_GHO`` /
        ``parse_UAP``, ``CurrencyData.parseGCU``, ``CastleVIPData.parse_VIP``.
        """
        blocks = self._protection_blocks(data)
        pid = None
        player = self.local_player
        identity = read_section(PlayerIdentityResponse, data.get("gpi"), "the gpi section")
        if identity is not None and "player_id" in identity.model_fields_set:
            pid = identity.player_id
            player = self.players.get(pid)
            if player is None:
                player = Player(PID=pid)
        if player is None:
            return blocks

        merged = dict(player.__dict__)
        updated: set[str] = set()

        if identity is not None:
            for field_name, source in _IDENTITY_FIELDS.items():
                if source in identity.model_fields_set:
                    merged[field_name] = getattr(identity, source)
                    updated.add(field_name)

        if gxp := read_section(ExperienceResponse, data.get("gxp"), "the gxp section"):
            level = merged["level"] if gxp.level is None else gxp.level
            xp = _sent(gxp, "xp", merged["xp"])
            legend, current, following = level_progress(level, xp)
            merged.update(
                level=level,
                xp=xp,
                legendary_level=legend,
                xp_for_current_level=current,
                xp_to_next_level=following,
            )
            updated |= {"level", "xp", "legendary_level", "xp_for_current_level", "xp_to_next_level"}

        if gcu := read_section(CurrencyResponse, data.get("gcu"), "the gcu section"):
            merged["coins"] = merged["coins"] if gcu.coins is None else gcu.coins
            merged["rubies"] = merged["rubies"] if gcu.rubies is None else gcu.rubies
            updated |= {"coins", "rubies"}

        if vip := read_section(VipStatusResponse, data.get("vip"), "the vip section"):
            # parse_VIP (bundle line 47542) reads a missing key as 0; here it keeps its value,
            # so a vip without UPG never frees premium commanders already used
            merged["vip_points"] = _sent(vip, "vip_points", merged["vip_points"])
            merged["vip_level"] = _sent(vip, "vip_level", merged["vip_level"])
            merged["vip_time_left"] = _sent(vip, "vip_seconds_left", merged["vip_time_left"])
            merged["used_premium_commanders"] = _sent(vip, "used_premium_commanders", merged["used_premium_commanders"])
            updated |= {"vip_points", "vip_level", "vip_time_left", "used_premium_commanders"}

        if gho := read_section(HonorResponse, data.get("gho"), "the gho section"):
            merged["honor"] = _sent(gho, "honor", merged["honor"])
            merged["ranking"] = _sent(gho, "ranking_points", merged["ranking"])
            updated |= {"honor", "ranking"}

        beginner = dict(merged["beginner_protection"])
        protection = dict(merged["protection"])
        for block in blocks:
            beginner[block.kingdom_id] = block.is_noob_protected
            protection[block.kingdom_id] = block
        if beginner != merged["beginner_protection"]:
            merged["beginner_protection"] = beginner
            updated.add("beginner_protection")
        if protection != merged["protection"]:
            merged["protection"] = protection
            updated.add("protection")

        if updated:
            self._swap_model_fields(player, merged, updated)

        if pid is not None:
            self.players[pid] = player
            self.local_player = player
            logger.debug(f"Local player: {player.name} (ID: {pid})")
        return blocks

    @staticmethod
    def _protection_blocks(data: dict[str, Any]) -> list[KingdomProtection]:
        """The login data's ``uap`` and ``gac``, or a ``uap`` push, each for the kingdom it names.

        Client: ``GBDCommand.exec`` (bundle line 129425) hands both to ``CastleUserData.parse_UAP`` (bundle line 9906)
        """
        blocks = (read_section(KingdomProtection, data.get(key), f"the {key} protection") for key in ("uap", "gac"))
        return [block for block in blocks if block is not None and block.kingdom_id is not None]

    def _parse_special_currencies(self, data: dict[str, Any]) -> None:
        """Apply the login data's sce section (special currencies)."""
        if js_truthy(data.get("sce")) and self.local_player:
            total = self._apply_special_currencies(data["sce"])
            logger.debug(f"Parsed {total} special currencies")

    def _apply_special_currencies(self, body: Any) -> int:
        """Merge an ``sce`` body, ``[[currency_key, amount], ...]``, into the special currencies.

        The dict is rebuilt and swapped rather than updated in place: user
        threads read ``local_player.special_currencies`` without the lock, and
        iterating a dict the receive thread is writing raises
        "dictionary changed size during iteration".

        Client: ``CurrencyData.parseSCE`` (bundle line 141231); see
        :class:`SpecialCurrenciesResponse` for how each pair is read.

        Returns:
            The number of special currencies known afterwards.
        """
        player = self.local_player
        currencies = read_or_none(
            SpecialCurrenciesResponse.model_validate, body, warn=logger, what="the special currencies"
        )
        if player is None or currencies is None:
            return 0
        player.special_currencies = {**player.special_currencies, **currencies.amounts}
        return len(player.special_currencies)

    def _parse_alliance_info(self, data: dict[str, Any]) -> AllianceMembershipResponse | None:
        """Apply the gal section: your alliance membership; the section as read, None when it is no object.

        Two cases are deliberately distinguished:

        * no "gal" key at all: this packet carries no alliance information,
          so existing state is left alone;
        * "gal" present without an alliance above 0 (or null): the server is telling
          us the player is in no alliance, so a stale alliance (left, kicked,
          disbanded) is cleared.

        The alliance and the player's AID land in one swap, since a push can
        change them while user threads read the player.

        Client: ``CastleUserData.parse_GAL`` (bundle line 9876).
        """
        if "gal" not in data:
            return None
        membership = read_section(AllianceMembershipResponse, data.get("gal"), "the gal section")
        player = self.local_player
        if player is None:
            return membership

        alliance = membership if membership is not None and membership.is_member else None
        if alliance is not None:
            logger.debug(f"Alliance: {alliance.name}")
        elif player.alliance is not None:
            logger.debug("Alliance cleared: gal section reports no alliance")

        merged = dict(player.__dict__)
        merged["alliance"] = alliance
        merged["AID"] = alliance.alliance_id if alliance is not None else None
        self._swap_model_fields(player, merged, {"alliance", "AID"})
        return membership

    def _parse_max_spies(self, data: dict[str, Any]) -> None:
        """Apply a gbd's ``gms`` section, or a ``gms`` push.

        Client: ``CastleSpyData.parse_GMS`` (bundle line 139979), which skips a falsy section
        and reads ``MS`` and ``BS`` of anything else through ``int()``.
        """
        gms = data.get("gms")
        if js_truthy(gms):
            self.max_spies = MaxSpiesResponse.model_validate(gms if isinstance(gms, dict) else {})

    def _handle_sce(self, data: Any) -> None:
        """Handle a special currencies push: ``[[currency_key, amount], ...]``.

        Client: ``SCECommand.exec`` (bundle line 129774), ``CurrencyData.parseSCE`` (bundle line 141231),
        which does nothing for a falsy body
        """
        if js_truthy(data) and self.local_player:
            total = self._apply_special_currencies(data)
            self._player_updated_at = time.time()
            logger.debug(f"Special currencies known after the sce: {total}")

    def _handle_hdc(self, data: Any) -> None:
        """Keep which hero you picked, or that you have yet to pick one.

        Client: ``HDCommand.executeCommand`` (bundle line 124371), ``CastleUserData.parse_HDC`` (bundle line 10101)
        """
        if (hero := read_section(HeroDecisionResponse, data, "the hero")) is not None:
            self.hero = hero

    def get_hero(self) -> Hero | int | None:
        """Your hero, from the last ``hdc``; None until one arrived or while you have yet to pick one."""
        with self._lock:
            return self.hero.hero if self.hero is not None else None

    def get_local_player(self) -> Player:
        """Get a snapshot of the local player, which the login data brings.

        Returns a copy taken under the lock, with detached ``special_currencies``,
        ``castles``, ``beginner_protection`` and ``protection`` containers, so several fields can be read consistently
        while the receive thread is updating state. ``state.local_player``
        remains available for direct access but is a live object.

        The Castle objects inside the snapshot are the live ones, as with
        ``get_castles()``.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        with self._lock:
            player = loaded(self.local_player, "The local player")
            return player.model_copy(
                update={
                    "special_currencies": dict(player.special_currencies),
                    "castles": dict(player.castles),
                    "beginner_protection": dict(player.beginner_protection),
                    "protection": dict(player.protection),
                }
            )

    def get_special_currencies(self) -> dict[Currency | str, int]:
        """Get a snapshot of the special currencies (``Currency`` -> amount).

        These are the generic currencies from ``sce`` (``Currency.FAST_TRAVEL_FEATHERS``,
        ``Currency.SKIP_1_MINUTE``, ...), not items; a key newer than the generated
        enum is kept as its str. Empty before login, or if no sce packet has
        arrived yet — use ``get_last_packet_time("sce")`` to tell those apart
        from "empty".
        """
        with self._lock:
            if self.local_player is None:
                return {}
            return dict(self.local_player.special_currencies)

    def get_max_spies(self) -> MaxSpiesResponse:
        """The spies you own before boosts, from ``gms``; the login data brings one.

        The model is replaced, never edited, on each ``gms``, so the one returned stays as it was.
        ``client.spy.total_spies()`` adds the boosts, read from state.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        with self._lock:
            return loaded(self.max_spies, "Max spies")

    def get_player_last_updated(self) -> float | None:
        """When any local-player field was last refreshed, or ``None``.

        Player fields arrive in the login gbd and again as a push whenever the
        server changes them (gpi, gxp, gcu, vip, gal, gcl, gho, uap, glu, mir,
        sce). A stamp far in the past means no push has arrived since, not
        that the values were re-confirmed.
        """
        with self._lock:
            return self._player_updated_at
