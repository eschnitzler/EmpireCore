"""
GameState - Tracks game state from server packets.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set

from empire_core.state.models import Alliance, Castle, Player
from empire_core.state.unit_models import Army
from empire_core.state.world_models import MapObject, Movement, MovementResources

logger = logging.getLogger(__name__)


class GameState:
    """
    Manages game state parsed from server packets.

    This is a simplified sync version - no async, no event emission.
    State is updated directly and can be queried at any time.
    """

    def __init__(self):
        self.local_player: Optional[Player] = None
        self.players: Dict[int, Player] = {}
        self.castles: Dict[int, Castle] = {}

        # World State
        self.map_objects: Dict[int, MapObject] = {}  # AreaID -> MapObject
        self.movements: Dict[int, Movement] = {}  # MovementID -> Movement

        # Track movement IDs we've seen (for delta detection)
        self._previous_movement_ids: Set[int] = set()

        # Armies (castle_id -> Army)
        self.armies: Dict[int, Army] = {}

        # Callbacks for specific events (optional)
        self.on_incoming_attack: Optional[Callable[[Movement], None]] = None
        self.on_movement_recalled: Optional[Callable[[Movement], None]] = None

        # Track movements that arrived normally (vs recalled)
        self._arrived_movement_ids: Set[int] = set()

    def update_from_packet(self, cmd_id: str, payload: Dict[str, Any]) -> None:
        """
        Central update router - parses packet and updates state.
        """
        if cmd_id == "gbd":
            self._handle_gbd(payload)
        elif cmd_id == "gam":
            self._handle_gam(payload)
        elif cmd_id == "dcl":
            self._handle_dcl(payload)
        elif cmd_id == "mov":
            self._handle_mov(payload)
        elif cmd_id == "atv":
            self._handle_atv(payload)
        elif cmd_id == "ata":
            self._handle_ata(payload)

    def _handle_gbd(self, data: Dict[str, Any]) -> None:
        """Handle 'Get Big Data' packet - initial login data."""
        # Player Info
        gpi = data.get("gpi", {})
        if gpi:
            pid = gpi.get("PID")
            if pid:
                if pid not in self.players:
                    self.players[pid] = Player(**gpi)
                self.local_player = self.players[pid]
                logger.info(f"Local player: {self.local_player.name} (ID: {pid})")

        # XP/Level
        gxp = data.get("gxp", {})
        if self.local_player and gxp:
            self.local_player.LVL = gxp.get("LVL", self.local_player.LVL)
            self.local_player.XP = gxp.get("XP", self.local_player.XP)

        # Currencies
        gcu = data.get("gcu", {})
        if self.local_player and gcu:
            self.local_player.gold = gcu.get("C1", 0)
            self.local_player.rubies = gcu.get("C2", 0)

        # Alliance
        gal = data.get("gal", {})
        if gal and self.local_player and gal.get("AID"):
            try:
                self.local_player.alliance = Alliance(**gal)
                self.local_player.AID = gal.get("AID")
                logger.info(f"Alliance: {self.local_player.alliance.name}")
            except Exception as e:
                logger.debug(f"Could not parse alliance: {e}")

        # Castles
        gcl = data.get("gcl", {})
        if gcl and self.local_player:
            kingdoms = gcl.get("C", [])
            for k_data in kingdoms:
                kid = k_data.get("KID", 0)
                area_infos = k_data.get("AI", [])
                for area_entry in area_infos:
                    raw_ai = area_entry.get("AI")
                    if isinstance(raw_ai, list) and len(raw_ai) > 10:
                        area_id = raw_ai[3]
                        owner_id = raw_ai[4]
                        x = raw_ai[0] if len(raw_ai) > 0 else 0
                        y = raw_ai[1] if len(raw_ai) > 1 else 0
                        name = raw_ai[10]

                        if owner_id == self.local_player.id:
                            castle = Castle(OID=area_id, N=name, KID=kid, X=x, Y=y)
                            self.castles[area_id] = castle
                            self.local_player.castles[area_id] = castle

            logger.info(f"Parsed {len(self.local_player.castles)} castles")

    def _handle_gam(self, data: Dict[str, Any]) -> None:
        """Handle 'Get Army Movements' response."""
        movements_list = data.get("M", [])
        owners_list = data.get("O", [])  # Owner info array
        current_ids: Set[int] = set()

        # Build owner lookup: OID -> {name, alliance_name}
        owner_info: Dict[int, Dict[str, str]] = {}
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
                # Don't filter by is_incoming - that's relative to local player
                if mov.is_attack and self.on_incoming_attack:
                    try:
                        self.on_incoming_attack(mov)
                    except Exception as e:
                        logger.error(f"on_incoming_attack callback error: {e}")

            self.movements[mid] = mov

        # Remove completed movements and detect recalls
        removed_ids = self._previous_movement_ids - current_ids
        for mid in removed_ids:
            # If we didn't get an arrival packet, this was a recall
            if mid not in self._arrived_movement_ids:
                recalled_mov = self.movements.get(mid)
                if recalled_mov and self.on_movement_recalled:
                    try:
                        self.on_movement_recalled(recalled_mov)
                    except Exception as e:
                        logger.error(f"on_movement_recalled callback error: {e}")
            self._arrived_movement_ids.discard(mid)
            self.movements.pop(mid, None)

        self._previous_movement_ids = current_ids

    def _handle_dcl(self, data: Dict[str, Any]) -> None:
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

    def _handle_mov(self, data: Dict[str, Any]) -> None:
        """Handle real-time movement update."""
        m_data = data.get("M", data)

        if isinstance(m_data, list):
            for item in m_data:
                if isinstance(item, dict):
                    self._update_single_movement(item)
        elif isinstance(m_data, dict):
            self._update_single_movement(m_data)

    def _handle_atv(self, data: Dict[str, Any]) -> None:
        """Handle movement arrival."""
        mid = data.get("MID")
        if mid:
            self._arrived_movement_ids.add(mid)  # Mark as arrived, not recalled
            self.movements.pop(mid, None)
            self._previous_movement_ids.discard(mid)

    def _handle_ata(self, data: Dict[str, Any]) -> None:
        """Handle attack arrival."""
        mid = data.get("MID")
        if mid:
            self._arrived_movement_ids.add(mid)  # Mark as arrived, not recalled
            self.movements.pop(mid, None)
            self._previous_movement_ids.discard(mid)

    def _parse_movement(
        self,
        m_data: Dict[str, Any],
        m_wrapper: Optional[Dict[str, Any]] = None,
        owner_info: Optional[Dict[int, Dict[str, str]]] = None,
    ) -> Optional[Movement]:
        """Parse a Movement from packet data."""
        mid = m_data.get("MID")
        if not mid:
            return None

        try:
            mov = Movement(**m_data)
            mov.last_updated = time.time()

            # Extract target coords
            if mov.target_area and isinstance(mov.target_area, list) and len(mov.target_area) >= 5:
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

            # Extract units from wrapper
            if m_wrapper:
                um_data = m_wrapper.get("UM", {})
                for uid_str, count in um_data.items():
                    try:
                        mov.units[int(uid_str)] = int(count)
                    except (ValueError, TypeError):
                        pass

                # Extract resources
                gs_data = m_wrapper.get("GS", {})
                if gs_data:
                    mov.resources = MovementResources(
                        W=gs_data.get("W", 0),
                        S=gs_data.get("S", 0),
                        F=gs_data.get("F", 0),
                    )

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

    def _update_single_movement(self, m_data: Dict[str, Any]) -> None:
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
            if mov.is_incoming and mov.is_attack and self.on_incoming_attack:
                try:
                    self.on_incoming_attack(mov)
                except Exception as e:
                    logger.error(f"on_incoming_attack callback error: {e}")
        elif existing:
            mov.created_at = existing.created_at

        self.movements[mid] = mov

    # ============================================================
    # Query Methods
    # ============================================================

    def get_all_movements(self) -> List[Movement]:
        """Get all tracked movements."""
        return list(self.movements.values())

    def get_incoming_movements(self) -> List[Movement]:
        """Get all incoming movements."""
        return [m for m in self.movements.values() if m.is_incoming]

    def get_outgoing_movements(self) -> List[Movement]:
        """Get all outgoing movements."""
        return [m for m in self.movements.values() if m.is_outgoing]

    def get_incoming_attacks(self) -> List[Movement]:
        """Get all incoming attack movements."""
        return [m for m in self.movements.values() if m.is_incoming and m.is_attack]

    def get_movement_by_id(self, movement_id: int) -> Optional[Movement]:
        """Get a specific movement by ID."""
        return self.movements.get(movement_id)
