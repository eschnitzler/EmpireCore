"""
GameState - Tracks game state from server packets.
"""

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from empire_core.state.models import Alliance, Castle, Player
from empire_core.state.unit_models import Army
from empire_core.state.world_models import MapObject, Movement, MovementResources

logger = logging.getLogger(__name__)


class GameState:
    """
    Manages game state parsed from server packets.

    This is a simplified sync version - no async, no event emission.
    State is updated directly and can be queried at any time.

    Callbacks are dispatched in a thread pool to avoid blocking the receive loop.
    This allows callbacks to make blocking calls (like waiting for responses).
    """

    def __init__(self):
        self.local_player: Player | None = None
        self.players: dict[int, Player] = {}
        self.castles: dict[int, Castle] = {}

        # World State
        self.map_objects: dict[int, MapObject] = {}  # AreaID -> MapObject
        self.movements: dict[int, Movement] = {}  # MovementID -> Movement

        # Track movement IDs we've seen (for delta detection)
        self._previous_movement_ids: set[int] = set()

        # Armies (castle_id -> Army)
        self.armies: dict[int, Army] = {}

        # Active Events
        self.active_event_ids: list[int] = []

        # Callbacks for specific events — support multiple listeners
        self._incoming_attack_callbacks: list[Callable[[Movement], None]] = []
        self._movement_recalled_callbacks: list[Callable[[int], None]] = []
        self._movement_arrived_callbacks: list[Callable[[int], None]] = []

        # Track movements that arrived normally (vs recalled)
        self._arrived_movement_ids: set[int] = set()

        # Thread pool for dispatching callbacks (avoids blocking receive loop)
        self._callback_executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="gge_callback"
        )

    def shutdown(self) -> None:
        """Shutdown the callback executor. Call on disconnect."""
        self._callback_executor.shutdown(wait=False)

    def _dispatch_callback(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Dispatch a callback in the thread pool."""

        def wrapped():
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Callback error: {e}")

        self._callback_executor.submit(wrapped)

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
            getattr(self, handler_name)(payload)

    # ----------------------------------------------------------------
    # Callback registration helpers
    # ----------------------------------------------------------------

    def on_incoming_attack(self, callback: Callable[[Movement], None]) -> None:  # type: ignore[misc]
        """Register a callback for incoming attack movements."""
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
        if not pid:
            return
        if pid not in self.players:
            self.players[pid] = Player(**gpi)
        self.local_player = self.players[pid]
        logger.debug(f"Local player: {self.local_player.name} (ID: {pid})")

    def _parse_xp(self, data: dict[str, Any]) -> None:
        """Parse XP and level from gxp sub-packet."""
        gxp = data.get("gxp", {})
        if self.local_player and gxp:
            self.local_player.LVL = gxp.get("LVL", self.local_player.LVL)
            self.local_player.XP = gxp.get("XP", self.local_player.XP)

    def _parse_currencies(self, data: dict[str, Any]) -> None:
        """Parse gold and rubies from gcu sub-packet."""
        gcu = data.get("gcu", {})
        if self.local_player and gcu:
            self.local_player.gold = gcu.get("C1", 0)
            self.local_player.rubies = gcu.get("C2", 0)

    def _parse_inventory(self, data: dict[str, Any]) -> None:
        """Parse inventory items from sce sub-packet."""
        sce = data.get("sce", [])
        if not (sce and self.local_player):
            return
        for item in sce:
            if isinstance(item, list) and len(item) >= 2:
                self.local_player.inventory[str(item[0])] = int(item[1])
        logger.debug(f"Parsed {len(self.local_player.inventory)} inventory items")

    def _parse_vip(self, data: dict[str, Any]) -> None:
        """Parse VIP status from vip sub-packet."""
        vip = data.get("vip", {})
        if self.local_player and vip:
            self.local_player.vip_points = vip.get("VP", 0)
            self.local_player.vip_level = vip.get("VRL", 0)
            self.local_player.vip_time_left = vip.get("VRS", 0)

    def _parse_alliance_info(self, data: dict[str, Any]) -> None:
        """Parse alliance membership from gal sub-packet."""
        gal = data.get("gal", {})
        if not (gal and self.local_player and gal.get("AID")):
            return
        try:
            self.local_player.alliance = Alliance(**gal)
            self.local_player.AID = gal.get("AID")
            logger.debug(f"Alliance: {self.local_player.alliance.name}")
        except Exception as e:
            logger.warning(f"Could not parse alliance: {e}")

    def _parse_castles(self, data: dict[str, Any]) -> None:
        """Parse castle list from gcl sub-packet."""
        gcl = data.get("gcl", {})
        if not (gcl and self.local_player):
            return
        for k_data in gcl.get("C", []):
            kid = k_data.get("KID", 0)
            for area_entry in k_data.get("AI", []):
                raw_ai = area_entry.get("AI")
                if isinstance(raw_ai, list) and len(raw_ai) > 10:
                    x, y, area_id, owner_id, name = raw_ai[1], raw_ai[2], raw_ai[3], raw_ai[4], raw_ai[10]
                    if owner_id == self.local_player.id:
                        castle = Castle(OID=area_id, N=name, KID=kid, X=x, Y=y)
                        self.castles[area_id] = castle
                        self.local_player.castles[area_id] = castle
        logger.debug(f"Parsed {len(self.local_player.castles)} castles")

    def _handle_gam(self, data: dict[str, Any]) -> None:
        """Handle 'Get Army Movements' response."""
        movements_list = data.get("M", [])
        owners_list = data.get("O", [])  # Owner info array
        current_ids: set[int] = set()

        # Build owner lookup: OID -> {name, alliance_name}
        owner_info: dict[int, dict[str, str]] = {}
        for owner in owners_list:
            if isinstance(owner, dict):
                oid = owner.get("OID")
                if oid:
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
            if not mid:
                continue

            current_ids.add(mid)
            mov = self._parse_movement(m_data, m_wrapper, owner_info)
            if not mov:
                continue

            is_new = mid not in self._previous_movement_ids

            if is_new:
                mov.created_at = time.time()

                # Trigger callback for attacks (server pushes gam for alliance attacks)
                if mov.is_attack:
                    for cb in list(self._incoming_attack_callbacks):
                        self._dispatch_callback(cb, mov)
            else:
                # Dispatch callback for updates to existing attacks too
                if mov.is_attack:
                    for cb in list(self._incoming_attack_callbacks):
                        self._dispatch_callback(cb, mov)

            self.movements[mid] = mov

        # Don't remove movements here - wait for explicit arrival (atv/ata) or recall (mrm)
        # packets so we can properly dispatch callbacks with full movement data
        self._previous_movement_ids = current_ids
        self._arrived_movement_ids.clear()

    def _handle_dcl(self, data: dict[str, Any]) -> None:
        """Handle 'Detailed Castle List' response."""
        kingdoms = data.get("C", [])

        for k_data in kingdoms:
            area_infos = k_data.get("AI", [])
            for castle_data in area_infos:
                if not isinstance(castle_data, dict):
                    continue

                aid = castle_data.get("AID")
                if aid and aid in self.castles:
                    castle = self.castles[aid]

                    # Update resources
                    res = castle.resources
                    res.wood = int(castle_data.get("W", res.wood))
                    res.stone = int(castle_data.get("S", res.stone))
                    res.food = int(castle_data.get("F", res.food))

                    # Update units from AC array
                    # AC: [[unit_id, count], ...]
                    ac = castle_data.get("AC", [])
                    if ac:
                        castle.units.clear()
                        for u_data in ac:
                            if isinstance(u_data, list) and len(u_data) >= 2:
                                uid = u_data[0]
                                count = u_data[1]
                                castle.units[uid] = count

    def _handle_mov(self, data: dict[str, Any]) -> None:
        """Handle real-time movement update."""
        m_data = data.get("M", data)

        if isinstance(m_data, list):
            for item in m_data:
                if isinstance(item, dict):
                    self._update_single_movement(item)
        elif isinstance(m_data, dict):
            self._update_single_movement(m_data)

    def _handle_movement_arrived(self, data: dict[str, Any]) -> None:
        """Handle movement or attack arrival (atv/ata share identical logic)."""
        mid = data.get("MID")
        if mid:
            self._arrived_movement_ids.add(mid)
            for cb in list(self._movement_arrived_callbacks):
                self._dispatch_callback(cb, mid)
            self.movements.pop(mid, None)
            self._previous_movement_ids.discard(mid)

    def _handle_mrm(self, data: dict[str, Any]) -> None:
        """Handle movement recall (mrm = Move Recall Movement)."""
        mid = data.get("MID")
        if mid:
            for cb in list(self._movement_recalled_callbacks):
                self._dispatch_callback(cb, mid)
            self.movements.pop(mid, None)
            self._previous_movement_ids.discard(mid)

    def _handle_sce(self, data: Any) -> None:
        """Handle Server Client Exchange (Inventory Update)."""
        # data might be a list directly: [["PTT", 123]]
        # or a dict if wrapped?
        items = data if isinstance(data, list) else []

        if items and self.local_player:
            for item in items:
                if isinstance(item, list) and len(item) >= 2:
                    key = str(item[0])
                    val = int(item[1])
                    self.local_player.inventory[key] = val
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
        if not mid:
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
        except Exception as e:
            logger.debug(f"Failed to parse movement {mid}: {e}")
            return None

    def _update_single_movement(self, m_data: dict[str, Any]) -> None:
        """Update a single movement from real-time packet."""
        mid = m_data.get("MID")
        if not mid:
            return

        existing = self.movements.get(mid)
        mov = self._parse_movement(m_data)
        if not mov:
            return

        is_new = existing is None
        if is_new:
            mov.created_at = time.time()
            self._previous_movement_ids.add(mid)

            # Trigger callback for new incoming attacks
            # Dispatch in thread pool to avoid blocking receive loop
            if mov.is_incoming and mov.is_attack:
                for cb in list(self._incoming_attack_callbacks):
                    self._dispatch_callback(cb, mov)
        elif existing:
            # Preserve metadata from existing movement that real-time packets don't include
            mov.created_at = existing.created_at
            mov.source_player_name = existing.source_player_name or mov.source_player_name
            mov.source_alliance_name = existing.source_alliance_name or mov.source_alliance_name
            mov.target_player_name = existing.target_player_name or mov.target_player_name
            mov.target_alliance_name = existing.target_alliance_name or mov.target_alliance_name
            # Preserve units if the update doesn't have them
            if not mov.units and existing.units:
                mov.units = existing.units

        self.movements[mid] = mov

    # ============================================================
    # Query Methods
    # ============================================================

    def get_all_movements(self) -> list[Movement]:
        """Get all tracked movements."""
        return list(self.movements.values())

    def get_incoming_movements(self) -> list[Movement]:
        """Get all incoming movements."""
        return [m for m in self.movements.values() if m.is_incoming]

    def get_outgoing_movements(self) -> list[Movement]:
        """Get all outgoing movements."""
        return [m for m in self.movements.values() if m.is_outgoing]

    def get_incoming_attacks(self) -> list[Movement]:
        """Get all incoming attack movements."""
        return [m for m in self.movements.values() if m.is_incoming and m.is_attack]

    def get_movement_by_id(self, movement_id: int) -> Movement | None:
        """Get a specific movement by ID."""
        return self.movements.get(movement_id)
