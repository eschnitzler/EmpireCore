"""Local player tracking: gpi/gxp/gcu/vip/gho/uap, alliance (gal), special currencies (sce) and events (sei)."""

import logging
import math
import time
from typing import Any

from empire_core.state.base import StateBase
from empire_core.state.models import Alliance, Player

logger = logging.getLogger(__name__)


LEVEL_CAP = 70
LEGEND_LEVEL_CAP = 950
_LEVEL_CAP_XP = LEVEL_CAP * LEVEL_CAP * 30


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    body = data.get(key)
    return body if isinstance(body, dict) else {}


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


def _as_int(value: Any, previous: int) -> int:
    """The value as an int, or ``previous`` when it is missing or unreadable."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return previous


class PlayerState(StateBase):
    def _parse_player_sections(self, data: dict[str, Any]) -> None:
        """Parse the gpi/gxp/gcu/vip/gho/uap/gac sections as ONE atomic player update.

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
        fresh: Player | None = None
        pid = None
        player = self.local_player
        gpi = _section(data, "gpi")
        if gpi:
            pid = gpi.get("PID")
            if pid is not None:
                player = self.players.get(pid)
                if player is None:
                    player = Player(**gpi)
                else:
                    fresh = Player(**gpi)
        if player is None:
            return

        merged = dict(player.__dict__)
        updated: set[str] = set()

        if fresh is not None:
            gpi_fields = fresh.model_fields_set & set(Player.model_fields)
            for field_name in gpi_fields:
                merged[field_name] = getattr(fresh, field_name)
            updated |= gpi_fields

        if gxp := _section(data, "gxp"):
            level = _as_int(gxp.get("LVL"), merged["level"])
            xp = _as_int(gxp.get("XP"), merged["xp"])
            legend, current, following = level_progress(level, xp)
            merged.update(
                level=level,
                xp=xp,
                legendary_level=legend,
                xp_for_current_level=current,
                xp_to_next_level=following,
            )
            updated |= {"level", "xp", "legendary_level", "xp_for_current_level", "xp_to_next_level"}

        if gcu := _section(data, "gcu"):
            merged["gold"] = gcu.get("C1", merged["gold"])
            merged["rubies"] = gcu.get("C2", merged["rubies"])
            updated |= {"gold", "rubies"}

        if vip := _section(data, "vip"):
            merged["vip_points"] = vip.get("VP", merged["vip_points"])
            merged["vip_level"] = vip.get("VRL", merged["vip_level"])
            merged["vip_time_left"] = vip.get("VRS", merged["vip_time_left"])
            updated |= {"vip_points", "vip_level", "vip_time_left"}

        if gho := _section(data, "gho"):
            merged["honor"] = gho.get("H", merged["honor"])
            merged["ranking"] = gho.get("RP", merged["ranking"])
            updated |= {"honor", "ranking"}

        protection = dict(merged["beginner_protection"])
        for key in ("uap", "gac"):
            uap = _section(data, key)
            if isinstance(uap.get("KID"), int) and isinstance(uap.get("NS"), int):
                protection[uap["KID"]] = uap["NS"] > 0
        if protection != merged["beginner_protection"]:
            merged["beginner_protection"] = protection
            updated.add("beginner_protection")

        if updated:
            self._swap_model_fields(player, merged, updated)

        if pid is not None:
            self.players[pid] = player
            self.local_player = player
            logger.debug(f"Local player: {player.name} (ID: {pid})")

    def _parse_special_currencies(self, data: dict[str, Any]) -> None:
        """Apply the login data's sce section (special currencies)."""
        sce = data.get("sce", [])
        if not (sce and self.local_player):
            return
        total = self._apply_special_currencies(sce)
        logger.debug(f"Parsed {total} special currencies")

    def _apply_special_currencies(self, entries: Any) -> int:
        """Merge ``[[currency_key, amount], ...]`` entries into the special currencies.

        The dict is rebuilt and swapped rather than updated in place: user
        threads read ``local_player.special_currencies`` without the lock, and
        iterating a dict the receive thread is writing raises
        "dictionary changed size during iteration".

        Client: ``CurrencyData.parseSCE``, which sets each amount on the
        generic currency with that key in the item data.

        Returns:
            The number of special currencies known afterwards.
        """
        player = self.local_player
        if player is None or not isinstance(entries, list):
            return 0
        updated = dict(player.special_currencies)
        for entry in entries:
            if isinstance(entry, list) and len(entry) >= 2:
                try:
                    updated[str(entry[0])] = int(entry[1])
                except (ValueError, TypeError):
                    logger.debug(f"Skipping malformed special currency entry: {entry!r}")
        player.special_currencies = updated
        return len(updated)

    def _parse_alliance_info(self, data: dict[str, Any]) -> None:
        """Parse alliance membership from gal sub-packet.

        Two cases are deliberately distinguished:

        * no "gal" key at all — this packet carries no alliance information,
          so existing state is left alone;
        * "gal" present without a usable AID — the server is telling us the
          player is in no alliance, so a stale alliance (left, kicked,
          disbanded) is cleared.

        The alliance and the player's AID land in one swap, since a push can
        change them while user threads read the player.

        Client: ``CastleUserData.parse_GAL``.
        """
        player = self.local_player
        if player is None or "gal" not in data:
            return

        gal = _section(data, "gal")
        try:
            aid = int(gal["AID"]) if gal.get("AID") is not None else 0
        except (TypeError, ValueError):
            aid = 0

        alliance: Alliance | None = None
        if aid > 0:
            try:
                alliance = Alliance(**gal)
            except Exception as e:
                logger.warning(f"Could not parse alliance: {e}")
                return
            logger.debug(f"Alliance: {alliance.name}")
        elif player.alliance is not None:
            logger.debug("Alliance cleared: gal section reports no alliance")

        merged = dict(player.__dict__)
        merged["alliance"] = alliance
        merged["AID"] = aid if alliance is not None else None
        self._swap_model_fields(player, merged, {"alliance", "AID"})

    def _handle_sce(self, data: Any) -> None:
        """Handle a "get special currency" push: ``[[currency_key, amount], ...]``.

        Client: ``SCECommand.exec`` / ``CurrencyData.parseSCE``.
        """
        entries = data if isinstance(data, list) else []

        if entries and self.local_player:
            self._apply_special_currencies(entries)
            self._player_updated_at = time.time()
            logger.debug(f"Updated {len(entries)} special currencies from sce")

    def _handle_sei(self, data: dict[str, Any]) -> None:
        """Handle 'Send Event Information' packet."""
        events = data.get("E", [])
        if not isinstance(events, list):
            return

        active_ids: list[int] = []
        for event in events:
            if isinstance(event, dict):
                eid = event.get("EID")
                if isinstance(eid, int):
                    active_ids.append(eid)

        self.active_event_ids = active_ids

    def get_local_player(self) -> Player | None:
        """Get a snapshot of the local player, or None before login.

        Returns a copy taken under the lock, with detached ``special_currencies``,
        ``castles`` and ``beginner_protection`` containers, so several fields can be read consistently
        while the receive thread is updating state. ``state.local_player``
        remains available for direct access but is a live object.

        The Castle objects inside the snapshot are the live ones, as with
        ``get_castles()``.
        """
        with self._lock:
            player = self.local_player
            if player is None:
                return None
            return player.model_copy(
                update={
                    "special_currencies": dict(player.special_currencies),
                    "castles": dict(player.castles),
                    "beginner_protection": dict(player.beginner_protection),
                }
            )

    def get_special_currencies(self) -> dict[str, int]:
        """Get a snapshot of the special currencies (sce currency key -> amount).

        These are the generic currencies from ``sce`` (``PTT``, ``MS1``,
        ``LWT``, ...), not items. Empty before login, or if no sce packet has
        arrived yet — use ``get_last_packet_time("sce")`` to tell those apart
        from "empty".
        """
        with self._lock:
            if self.local_player is None:
                return {}
            return dict(self.local_player.special_currencies)

    def get_player_last_updated(self) -> float | None:
        """When any local-player field was last refreshed, or ``None``.

        Player fields arrive in the login gbd and again as a push whenever the
        server changes them (gpi, gxp, gcu, vip, gal, gcl, gho, uap, glu, mir,
        sce). A stamp far in the past means no push has arrived since, not
        that the values were re-confirmed.
        """
        with self._lock:
            return self._player_updated_at
