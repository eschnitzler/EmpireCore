"""
GameState - Tracks game state from server packets.
"""

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from empire_core.state.models import Alliance, Castle, Player
from empire_core.state.world_models import Movement, MovementResources

logger = logging.getLogger(__name__)

# Movements whose estimated arrival is this many seconds in the past are
# considered stale and pruned (their atv/ata packet was probably missed).
STALE_MOVEMENT_GRACE = 300.0

# A drifted movement schema would fail on every packet, so the warning is
# rate-limited to one per this interval; the rest go to debug.
MOVEMENT_PARSE_WARN_INTERVAL = 60.0


class GameState:
    """
    Manages game state parsed from server packets.

    State is mutated by the network receive thread and read from user
    threads, so all mutation and snapshot reads are guarded by a lock.

    The public attributes stay readable directly, but callers that read
    several fields at once (or iterate a container) should use the snapshot
    accessors — ``get_local_player()``, ``get_inventory()``, ``get_castles()``,
    ``get_all_movements()`` — which copy under the lock. Mutation paths swap
    containers instead of editing them in place, so an unlocked reader that
    already holds one never sees it change underneath.

    Callbacks are dispatched in a thread pool to avoid blocking the receive
    loop. This allows callbacks to make blocking calls (like waiting for
    responses).
    """

    def __init__(self):
        self._lock = threading.RLock()

        self.local_player: Player | None = None

        # player id -> Player. Despite the type, this only ever holds the
        # local player: nothing in the library records other players here.
        # Kept because it is part of the public surface — do not iterate it
        # expecting opponents or alliance members. Use the alliance service
        # (ain) or the lords/profile services for other players.
        self.players: dict[int, Player] = {}

        self.castles: dict[int, Castle] = {}

        # World State
        self.movements: dict[int, Movement] = {}  # MovementID -> Movement

        # Active Events
        self.active_event_ids: list[int] = []

        # Callbacks for specific events — support multiple listeners
        self._incoming_attack_callbacks: list[Callable[[Movement], None]] = []
        self._movement_recalled_callbacks: list[Callable[[int], None]] = []
        self._movement_arrived_callbacks: list[Callable[[int], None]] = []

        # Thread pool for dispatching callbacks (avoids blocking receive loop).
        # Created lazily so it survives disconnect/reconnect cycles.
        self._callback_executor: ThreadPoolExecutor | None = None
        self._executor_lock = threading.Lock()

        # Rate-limit state for movement parse failure warnings
        self._movement_parse_warn_at = 0.0
        self._movement_parse_failures = 0

    def shutdown(self) -> None:
        """Shutdown the callback executor. Call when done with the client."""
        with self._executor_lock:
            if self._callback_executor is not None:
                self._callback_executor.shutdown(wait=False)
                self._callback_executor = None

    def _dispatch_callback(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Dispatch a callback in the thread pool."""

        def wrapped():
            try:
                callback(*args, **kwargs)
            except Exception:
                logger.exception("Callback error")

        with self._executor_lock:
            if self._callback_executor is None:
                self._callback_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gge_callback")
            executor = self._callback_executor
        try:
            executor.submit(wrapped)
        except RuntimeError:
            # Executor shut down concurrently; drop the callback but say so.
            logger.warning("Callback dropped: executor is shut down")

    _DISPATCH: dict[str, str] = {
        "gbd": "_handle_gbd",
        "lli": "_handle_gbd",
        "gam": "_handle_gam",
        "dcl": "_handle_dcl",
        "mov": "_handle_mov",
        "atv": "_handle_movement_arrived",
        "ata": "_handle_movement_arrived",
        "mrm": "_handle_mrm",
        "sce": "_handle_sce",
        "sei": "_handle_sei",
    }

    def update_from_packet(self, cmd_id: str, payload: dict[str, Any]) -> None:
        """Central update router — parses packet and updates state."""
        handler_name = self._DISPATCH.get(cmd_id)
        if handler_name:
            with self._lock:
                getattr(self, handler_name)(payload)

    # ----------------------------------------------------------------
    # Callback registration helpers
    # ----------------------------------------------------------------

    def on_incoming_attack(self, callback: Callable[[Movement], None]) -> None:  # type: ignore[misc]
        """Register a callback for new hostile attack movements.

        Fires once per newly seen attack that is not the local player's own
        outgoing attack (i.e. attacks on you or on alliance members the
        server pushes gam updates for).
        """
        self._incoming_attack_callbacks.append(callback)

    def remove_incoming_attack_callback(self, callback: Callable[[Movement], None]) -> None:
        """Unregister an incoming attack callback."""
        self._incoming_attack_callbacks.remove(callback)

    def on_movement_recalled(self, callback: Callable[[int], None]) -> None:  # type: ignore[misc]
        """Register a callback for recalled movements."""
        self._movement_recalled_callbacks.append(callback)

    def remove_movement_recalled_callback(self, callback: Callable[[int], None]) -> None:
        """Unregister a movement recalled callback."""
        self._movement_recalled_callbacks.remove(callback)

    def on_movement_arrived(self, callback: Callable[[int], None]) -> None:  # type: ignore[misc]
        """Register a callback for arrived movements."""
        self._movement_arrived_callbacks.append(callback)

    def remove_movement_arrived_callback(self, callback: Callable[[int], None]) -> None:
        """Unregister a movement arrived callback."""
        self._movement_arrived_callbacks.remove(callback)

    # ----------------------------------------------------------------
    # Packet handlers
    # ----------------------------------------------------------------

    def _handle_gbd(self, data: dict[str, Any]) -> None:
        """Handle 'Get Big Data' packet — initial login data."""
        self._parse_player_info(data)
        self._parse_xp(data)
        self._parse_currencies(data)
        self._parse_inventory(data)
        self._parse_vip(data)
        self._parse_alliance_info(data)
        self._parse_castles(data)
        if dcl := data.get("dcl"):
            self._handle_dcl(dcl)
        if sei := data.get("sei"):
            self._handle_sei(sei)

    def _parse_player_info(self, data: dict[str, Any]) -> None:
        """Parse player identity from gpi sub-packet."""
        gpi = data.get("gpi", {})
        if not gpi:
            return
        pid = gpi.get("PID")
        if pid is None:
            return
        existing = self.players.get(pid)
        if existing is None:
            self.players[pid] = Player(**gpi)
        else:
            # Merge fresh data into the existing object so references held
            # by user code see the update (identity-map behavior).
            self._merge_player(existing, Player(**gpi))
        self.local_player = self.players[pid]
        logger.debug(f"Local player: {self.local_player.name} (ID: {pid})")

    @staticmethod
    def _merge_player(existing: Player, fresh: Player) -> None:
        """Apply the fields `fresh` explicitly set onto `existing`, atomically.

        `local_player` is handed out to user code and read without the lock,
        so a field-by-field merge would let a reader observe a half-merged
        player (new name, old level). The complete field mapping is built
        first and swapped in with a single store — the same mechanism
        pydantic's own `model_construct` uses — which keeps the identity-map
        behavior (references held by user code stay live) while never
        exposing an intermediate state.
        """
        updated = fresh.model_fields_set & set(Player.model_fields)
        merged = dict(existing.__dict__)
        for field_name in updated:
            merged[field_name] = getattr(fresh, field_name)
        object.__setattr__(existing, "__dict__", merged)
        existing.__pydantic_fields_set__.update(updated)

    def _parse_xp(self, data: dict[str, Any]) -> None:
        """Parse XP and level from gxp sub-packet."""
        gxp = data.get("gxp", {})
        if self.local_player and gxp:
            self.local_player.LVL = gxp.get("LVL", self.local_player.LVL)
            self.local_player.XP = gxp.get("XP", self.local_player.XP)

    def _parse_currencies(self, data: dict[str, Any]) -> None:
        """Parse gold and rubies from gcu sub-packet.

        A gcu that omits a key is a partial update, not "you now have 0" —
        previous values are preserved, as _parse_xp does.
        """
        gcu = data.get("gcu", {})
        if self.local_player and gcu:
            self.local_player.gold = gcu.get("C1", self.local_player.gold)
            self.local_player.rubies = gcu.get("C2", self.local_player.rubies)

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

    def _parse_vip(self, data: dict[str, Any]) -> None:
        """Parse VIP status from vip sub-packet.

        Missing keys keep their previous values (see _parse_currencies).
        """
        vip = data.get("vip", {})
        if self.local_player and vip:
            self.local_player.vip_points = vip.get("VP", self.local_player.vip_points)
            self.local_player.vip_level = vip.get("VRL", self.local_player.vip_level)
            self.local_player.vip_time_left = vip.get("VRS", self.local_player.vip_time_left)

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

    def _parse_castles(self, data: dict[str, Any]) -> None:
        """Parse castle list from gcl sub-packet.

        A gcl carrying a castle section ("C") is authoritative: castles it
        does not list are no longer owned, even when it lists none at all
        (the player just lost their last castle). A gcl without that section
        says nothing about ownership and leaves the castle list alone.
        """
        gcl = data.get("gcl")
        if not isinstance(gcl, dict) or self.local_player is None:
            return
        kingdoms = gcl.get("C")
        if not isinstance(kingdoms, list):
            return

        owned: dict[int, Castle] = {}
        for k_data in kingdoms:
            if not isinstance(k_data, dict):
                continue
            kid = k_data.get("KID", 0)
            for area_entry in k_data.get("AI", []):
                if not isinstance(area_entry, dict):
                    continue
                raw_ai = area_entry.get("AI")
                if isinstance(raw_ai, list) and len(raw_ai) > 10:
                    x, y, area_id, owner_id, name = raw_ai[1], raw_ai[2], raw_ai[3], raw_ai[4], raw_ai[10]
                    if owner_id == self.local_player.id:
                        existing = self.castles.get(area_id)
                        if existing is not None:
                            existing.N = name
                            existing.KID = kid
                            existing.X = x
                            existing.Y = y
                            owned[area_id] = existing
                        else:
                            castle = Castle(OID=area_id, N=name, KID=kid, X=x, Y=y)
                            self.castles[area_id] = castle
                            owned[area_id] = castle

        # Drop castles no longer owned (lost/traded since the last update)
        for stale_id in set(self.castles) - set(owned):
            self.castles.pop(stale_id, None)
        # Swap, don't mutate: user threads hold local_player.castles unlocked
        self.local_player.castles = owned
        logger.debug(f"Parsed {len(owned)} castles")

    def _handle_gam(self, data: dict[str, Any]) -> None:
        """Handle 'Get Army Movements' response."""
        movements_list = data.get("M", [])
        owners_list = data.get("O", [])  # Owner info array

        # Build owner lookup: OID -> {name, alliance_name}
        owner_info: dict[int, dict[str, str]] = {}
        for owner in owners_list:
            if isinstance(owner, dict):
                oid = owner.get("OID")
                if oid is not None:
                    owner_info[oid] = {
                        "name": owner.get("N", ""),
                        "alliance_name": owner.get("AN", ""),
                    }

        for m_wrapper in movements_list:
            if not isinstance(m_wrapper, dict):
                continue

            m_data = m_wrapper.get("M", {})
            if not m_data:
                continue

            mid = m_data.get("MID")
            if mid is None:
                continue

            mov = self._parse_movement(m_data, m_wrapper, owner_info)
            if not mov:
                continue

            self._store_movement(mov)

        # Don't remove movements absent from this packet - wait for explicit
        # arrival (atv/ata) or recall (mrm) packets so we can properly dispatch
        # callbacks with full movement data. Missed arrivals are handled by
        # _prune_stale_movements, which runs *after* storing so a movement this
        # packet refreshed is never dropped and re-created (which would re-fire
        # the incoming-attack callback for an attack already alerted on).
        self._prune_stale_movements()

    def _store_movement(self, mov: Movement) -> None:
        """Insert or merge a parsed movement; fire callbacks for new attacks."""
        mid = mov.MID
        existing = self.movements.get(mid)

        if existing is None:
            mov.created_at = time.time()
            # Alert on new hostile attacks. The server also pushes gam for
            # attacks on alliance members; exclude only our own outgoing
            # attacks so those alliance alerts still fire.
            own_attack = self.local_player is not None and mov.OID == self.local_player.PID
            if mov.is_attack and not own_attack:
                for cb in list(self._incoming_attack_callbacks):
                    self._dispatch_callback(cb, mov)
        else:
            # Preserve metadata that later packets may not include
            mov.created_at = existing.created_at
            mov.source_player_name = mov.source_player_name or existing.source_player_name
            mov.source_alliance_name = mov.source_alliance_name or existing.source_alliance_name
            mov.target_player_name = mov.target_player_name or existing.target_player_name
            mov.target_alliance_name = mov.target_alliance_name or existing.target_alliance_name
            if not mov.units and existing.units:
                mov.units = existing.units

        self.movements[mid] = mov

    @staticmethod
    def _is_stale(mov: Movement, now: float | None = None) -> bool:
        """True if the movement's arrival packet was evidently missed."""
        if now is None:
            now = time.time()
        return now > mov.estimated_arrival + STALE_MOVEMENT_GRACE

    def _prune_stale_movements(self) -> None:
        """Drop movements whose arrival packet was evidently missed.

        Runs on every path that inserts movements (gam, pushed mov) and on the
        list queries, because a consumer driven by push callbacks may never
        call gam and would otherwise keep seeing attacks that already landed.
        Cost is O(len(movements)) — the same order as the queries themselves.
        """
        now = time.time()
        stale = [mid for mid, m in self.movements.items() if self._is_stale(m, now)]
        for mid in stale:
            del self.movements[mid]
        if stale:
            logger.debug(f"Pruned {len(stale)} stale movements: {stale}")

    def _handle_dcl(self, data: dict[str, Any]) -> None:
        """Handle 'Detailed Castle List' response."""
        kingdoms = data.get("C", [])

        for k_data in kingdoms:
            area_infos = k_data.get("AI", [])
            for castle_data in area_infos:
                if not isinstance(castle_data, dict):
                    continue

                aid = castle_data.get("AID")
                if aid is None or aid not in self.castles:
                    continue
                castle = self.castles[aid]

                try:
                    # Build replacements first, then swap them in. get_castles()
                    # hands out live Castle objects, so editing them in place is
                    # visible to readers mid-update (torn resources, or
                    # dictionary-changed-size while iterating units).
                    res = castle.resources
                    castle.resources = res.model_copy(
                        update={
                            "wood": int(castle_data.get("W", res.wood)),
                            "stone": int(castle_data.get("S", res.stone)),
                            "food": int(castle_data.get("F", res.food)),
                        }
                    )

                    # Update units from AC array
                    # AC: [[unit_id, count], ...]
                    ac = castle_data.get("AC", [])
                    if ac:
                        new_units: dict[int, int] = {}
                        for u_data in ac:
                            if isinstance(u_data, list) and len(u_data) >= 2:
                                new_units[u_data[0]] = u_data[1]
                        castle.units = new_units
                except (ValueError, TypeError) as e:
                    # One malformed castle entry must not abort the rest
                    logger.debug(f"Skipping malformed dcl entry for castle {aid}: {e}")

    def _handle_mov(self, data: dict[str, Any]) -> None:
        """Handle real-time movement update."""
        m_data = data.get("M", data)

        if isinstance(m_data, list):
            for item in m_data:
                if isinstance(item, dict):
                    self._update_single_movement(item)
        elif isinstance(m_data, dict):
            self._update_single_movement(m_data)

        # Pushed movements are an insertion path of their own, so prune here
        # too: a consumer driven by push callbacks may never call gam. After
        # storing, so this packet's own movements survive (see _handle_gam).
        self._prune_stale_movements()

    def _handle_movement_arrived(self, data: dict[str, Any]) -> None:
        """Handle movement or attack arrival (atv/ata share identical logic)."""
        mid = data.get("MID")
        if mid is not None:
            for cb in list(self._movement_arrived_callbacks):
                self._dispatch_callback(cb, mid)
            self.movements.pop(mid, None)

    def _handle_mrm(self, data: dict[str, Any]) -> None:
        """Handle movement recall (mrm = Move Recall Movement)."""
        mid = data.get("MID")
        if mid is not None:
            for cb in list(self._movement_recalled_callbacks):
                self._dispatch_callback(cb, mid)
            self.movements.pop(mid, None)

    def _handle_sce(self, data: Any) -> None:
        """Handle Server Client Exchange (Inventory Update)."""
        # data might be a list directly: [["PTT", 123]]
        # or a dict if wrapped?
        items = data if isinstance(data, list) else []

        if items and self.local_player:
            self._apply_inventory_items(items)
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

    def _parse_movement(
        self,
        m_data: dict[str, Any],
        m_wrapper: dict[str, Any] | None = None,
        owner_info: dict[int, dict[str, str]] | None = None,
    ) -> Movement | None:
        """Parse a Movement from packet data."""
        mid = m_data.get("MID")
        if mid is None:
            return None

        try:
            mov = Movement(**m_data)
            mov.last_updated = time.time()

            # Extract target coords
            if mov.target_area and isinstance(mov.target_area, list) and len(mov.target_area) >= 5:
                mov.target_type = mov.target_area[0]
                mov.target_x = mov.target_area[1]
                mov.target_y = mov.target_area[2]
                mov.target_area_id = mov.target_area[3]
                if len(mov.target_area) > 10:
                    mov.target_name = str(mov.target_area[10]) if mov.target_area[10] else ""

            # Extract source coords
            if mov.source_area and isinstance(mov.source_area, list) and len(mov.source_area) >= 3:
                mov.source_x = mov.source_area[1]
                mov.source_y = mov.source_area[2]
                if len(mov.source_area) >= 4:
                    mov.source_area_id = mov.source_area[3]

            # Extract units from wrapper (GA = Garrison Army at wrapper level)
            if m_wrapper:
                ga_data = m_wrapper.get("GA", {})

                # GA contains unit arrays in L (left), M (melee), R (ranged), RW (ranged wall)
                # Each is a list of [unit_id, count] pairs
                for key in ("L", "M", "R", "RW"):
                    unit_list = ga_data.get(key, [])
                    if isinstance(unit_list, list):
                        for item in unit_list:
                            if isinstance(item, (list, tuple)) and len(item) >= 2:
                                try:
                                    unit_id = int(item[0])
                                    count = int(item[1])
                                    mov.units[unit_id] = mov.units.get(unit_id, 0) + count
                                except (ValueError, TypeError):
                                    pass

                # Extract resources or estimated size from GS field
                # GS is an int when army not visible (estimated size)
                # GS is a dict when transporting resources
                gs_data = m_wrapper.get("GS")
                if isinstance(gs_data, int):
                    mov.estimated_size = gs_data
                elif isinstance(gs_data, dict):
                    mov.resources = MovementResources(
                        W=gs_data.get("W", 0),
                        S=gs_data.get("S", 0),
                        F=gs_data.get("F", 0),
                    )

                # Extract commander data from UM.L (Lord/commander info)
                um_data = m_wrapper.get("UM", {})
                if isinstance(um_data, dict):
                    lord_data = um_data.get("L", {})
                    if isinstance(lord_data, dict):
                        mov.commander_equipment = lord_data.get("EQ", [])
                        mov.commander_effects = lord_data.get("AE", [])

            # Extract owner names and alliances from owner_info
            if owner_info:
                # Attacker info (OID = owner of the movement)
                attacker_id = mov.OID
                if attacker_id in owner_info:
                    mov.source_player_name = owner_info[attacker_id].get("name", "")
                    mov.source_alliance_name = owner_info[attacker_id].get("alliance_name", "")

                # Defender info (TID = target player)
                defender_id = mov.TID
                if defender_id in owner_info:
                    mov.target_player_name = owner_info[defender_id].get("name", "")
                    mov.target_alliance_name = owner_info[defender_id].get("alliance_name", "")

            return mov
        except Exception:
            self._log_movement_parse_failure(mid)
            return None

    def _log_movement_parse_failure(self, mid: Any) -> None:
        """Report a dropped movement loudly, but at most once a minute.

        Movements — including the incoming attacks this library exists to
        alert on — disappear silently when the schema drifts, so the failure
        must be visible at the default level with a traceback. Schema drift
        fails on every packet, so the warning is rate-limited and the
        suppressed count is reported with the next one.
        """
        self._movement_parse_failures += 1
        now = time.time()
        if now < self._movement_parse_warn_at:
            logger.debug(f"Failed to parse movement {mid} (warning rate-limited)")
            return

        suppressed = self._movement_parse_failures - 1
        self._movement_parse_failures = 0
        self._movement_parse_warn_at = now + MOVEMENT_PARSE_WARN_INTERVAL
        extra = f" ({suppressed} further failures suppressed)" if suppressed else ""
        logger.exception(f"Failed to parse movement {mid} — it is being dropped, incoming attacks may be missed{extra}")

    def _update_single_movement(self, m_data: dict[str, Any]) -> None:
        """Update a single movement from real-time packet."""
        mov = self._parse_movement(m_data)
        if not mov:
            return
        self._store_movement(mov)

    # ============================================================
    # Query Methods
    # ============================================================

    def get_all_movements(self) -> list[Movement]:
        """Get all tracked movements (stale ones pruned first)."""
        with self._lock:
            self._prune_stale_movements()
            return list(self.movements.values())

    def get_incoming_movements(self) -> list[Movement]:
        """Get all incoming movements."""
        with self._lock:
            self._prune_stale_movements()
            return [m for m in self.movements.values() if m.is_incoming]

    def get_outgoing_movements(self) -> list[Movement]:
        """Get all outgoing movements."""
        with self._lock:
            self._prune_stale_movements()
            return [m for m in self.movements.values() if m.is_outgoing]

    def get_incoming_attacks(self) -> list[Movement]:
        """Get all incoming attack movements.

        Attacks whose arrival packet was missed are pruned, so this never
        reports an attack that landed more than STALE_MOVEMENT_GRACE ago.
        """
        with self._lock:
            self._prune_stale_movements()
            return [m for m in self.movements.values() if m.is_incoming and m.is_attack]

    def get_movement_by_id(self, movement_id: int) -> Movement | None:
        """Get a specific movement by ID."""
        with self._lock:
            mov = self.movements.get(movement_id)
            if mov is None:
                return None
            # O(1) staleness check: don't turn a point lookup into a full scan
            if self._is_stale(mov):
                del self.movements[movement_id]
                return None
            return mov

    def get_castles(self) -> list[Castle]:
        """Get a snapshot of the player's castles."""
        with self._lock:
            return list(self.castles.values())

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

        Empty before login, or if no sce packet has arrived yet.
        """
        with self._lock:
            if self.local_player is None:
                return {}
            return dict(self.local_player.inventory)
