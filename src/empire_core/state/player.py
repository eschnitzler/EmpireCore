"""Local player tracking: gpi/gxp/gcu/vip, alliance (gal), inventory (sce) and events (sei)."""

import logging
import time
from typing import Any

from empire_core.state.base import StateBase
from empire_core.state.models import Alliance, Player

logger = logging.getLogger(__name__)


class PlayerState(StateBase):
    def _parse_player_sections(self, data: dict[str, Any]) -> None:
        """Parse the gpi/gxp/gcu/vip sub-packets as ONE atomic player update.

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

        gxp, gcu and vip are partial updates: a key they omit keeps its
        previous value (this packet's gpi value if it carried one, else the
        existing state) rather than resetting to zero.
        """
        fresh: Player | None = None
        pid = None
        player = self.local_player
        gpi = data.get("gpi", {})
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

        if gxp := data.get("gxp", {}):
            merged["LVL"] = gxp.get("LVL", merged["LVL"])
            merged["XP"] = gxp.get("XP", merged["XP"])
            updated |= {"LVL", "XP"}

        if gcu := data.get("gcu", {}):
            merged["gold"] = gcu.get("C1", merged["gold"])
            merged["rubies"] = gcu.get("C2", merged["rubies"])
            updated |= {"gold", "rubies"}

        if vip := data.get("vip", {}):
            merged["vip_points"] = vip.get("VP", merged["vip_points"])
            merged["vip_level"] = vip.get("VRL", merged["vip_level"])
            merged["vip_time_left"] = vip.get("VRS", merged["vip_time_left"])
            updated |= {"vip_points", "vip_level", "vip_time_left"}

        if updated:
            self._swap_model_fields(player, merged, updated)

        if pid is not None:
            self.players[pid] = player
            self.local_player = player
            logger.debug(f"Local player: {player.name} (ID: {pid})")

    def _parse_inventory(self, data: dict[str, Any]) -> None:
        """Parse inventory items from sce sub-packet."""
        sce = data.get("sce", [])
        if not (sce and self.local_player):
            return
        total = self._apply_inventory_items(sce)
        logger.debug(f"Parsed {total} inventory items")

    def _apply_inventory_items(self, items: Any) -> int:
        """Merge ``[[item_id, count], ...]`` entries into the inventory.

        The dict is rebuilt and swapped rather than updated in place: user
        threads read ``local_player.inventory`` without the lock, and
        iterating a dict the receive thread is writing raises
        "dictionary changed size during iteration".

        Returns:
            The number of items in the inventory afterwards.
        """
        player = self.local_player
        if player is None or not isinstance(items, list):
            return 0
        updated = dict(player.inventory)
        for item in items:
            if isinstance(item, list) and len(item) >= 2:
                try:
                    updated[str(item[0])] = int(item[1])
                except (ValueError, TypeError):
                    logger.debug(f"Skipping malformed inventory entry: {item!r}")
        player.inventory = updated
        return len(updated)

    def _parse_alliance_info(self, data: dict[str, Any]) -> None:
        """Parse alliance membership from gal sub-packet.

        Two cases are deliberately distinguished:

        * no "gal" key at all — this packet carries no alliance information,
          so existing state is left alone;
        * "gal" present without a usable AID — the server is telling us the
          player is in no alliance, so a stale alliance (left, kicked,
          disbanded) is cleared.
        """
        if self.local_player is None or "gal" not in data:
            return

        raw_gal = data.get("gal")
        # A null or non-dict gal section carries no alliance -> treat as empty
        gal: dict[str, Any] = raw_gal if isinstance(raw_gal, dict) else {}
        try:
            aid = int(gal["AID"]) if gal.get("AID") is not None else 0
        except (TypeError, ValueError):
            aid = 0

        if aid <= 0:
            if self.local_player.alliance is not None:
                logger.debug("Alliance cleared: gal section reports no alliance")
            self.local_player.alliance = None
            self.local_player.AID = None
            return

        try:
            self.local_player.alliance = Alliance(**gal)
            self.local_player.AID = aid
            logger.debug(f"Alliance: {self.local_player.alliance.name}")
        except Exception as e:
            logger.warning(f"Could not parse alliance: {e}")

    def _handle_sce(self, data: Any) -> None:
        """Handle Server Client Exchange (Inventory Update)."""
        # data might be a list directly: [["PTT", 123]]
        # or a dict if wrapped?
        items = data if isinstance(data, list) else []

        if items and self.local_player:
            self._apply_inventory_items(items)
            self._player_updated_at = time.time()
            logger.debug(f"Updated {len(items)} inventory items from sce")

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

        Returns a copy taken under the lock, with detached ``inventory`` and
        ``castles`` containers, so several fields can be read consistently
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
                    "inventory": dict(player.inventory),
                    "castles": dict(player.castles),
                }
            )

    def get_inventory(self) -> dict[str, int]:
        """Get a snapshot of the global inventory (item id -> count).

        Empty before login, or if no sce packet has arrived yet — use
        ``get_last_packet_time("sce")`` to tell those apart from "empty".
        """
        with self._lock:
            if self.local_player is None:
                return {}
            return dict(self.local_player.inventory)

    def get_player_last_updated(self) -> float | None:
        """When any local-player field was last refreshed, or ``None``.

        Most player fields (gold, rubies, VIP, level, alliance) only ever
        arrive inside a gbd/lli, i.e. at login; only the inventory is pushed
        during a session (sce). A stamp far in the past means the numbers are
        from login, not that they were re-confirmed.
        """
        with self._lock:
            return self._player_updated_at
