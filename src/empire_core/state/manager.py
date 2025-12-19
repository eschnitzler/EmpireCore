import logging
import time
from typing import Dict, Optional, Any, List, Callable, Awaitable, Set
from empire_core.state.models import Player, Castle, Resources, Building
from empire_core.state.world_models import MapObject, Movement, MovementResources
from empire_core.state.quest_models import DailyQuest, Quest
from empire_core.state.unit_models import Army
from empire_core.state.report_models import BattleReport, ReportManager
from empire_core.events.base import (
    MovementStartedEvent,
    MovementUpdatedEvent,
    MovementArrivedEvent,
    MovementCancelledEvent,
    IncomingAttackEvent,
    ReturnArrivalEvent,
)

logger = logging.getLogger(__name__)

# Type alias for event callback
EventCallback = Callable[[Any], Awaitable[None]]


class GameState:
    def __init__(self):
        self.local_player: Optional[Player] = None
        self.players: Dict[int, Player] = {}
        self.castles: Dict[int, Castle] = {}

        # World State
        self.map_objects: Dict[int, MapObject] = {}  # AreaID -> MapObject
        self.movements: Dict[int, Movement] = {}  # MovementID -> Movement

        # Track movement IDs we've seen (for delta detection)
        self._previous_movement_ids: Set[int] = set()

        # Event callback - will be set by client
        self._event_callback: Optional[EventCallback] = None

        # Quests
        self.daily_quests: Optional[DailyQuest] = None

        # Reports
        self.reports = ReportManager()

        # Armies (castle_id -> Army)
        self.armies: Dict[int, Army] = {}

    def set_event_callback(self, callback: EventCallback):
        """Set the callback for emitting events."""
        self._event_callback = callback

    async def _emit_event(self, event: Any):
        """Emit an event through the callback if set."""
        if self._event_callback:
            try:
                await self._event_callback(event)
            except Exception as e:
                logger.error(f"Error emitting event: {e}")

    def update_from_packet(self, cmd_id: str, payload: Dict[str, Any]):
        """
        Central update router.
        """
        if cmd_id == "gbd":
            self._handle_gbd(payload)
        elif cmd_id == "gaa":  # Get Area (Map Chunk)
            self._handle_gaa(payload)
        elif cmd_id == "gam":  # Get Army Movements
            self._handle_gam(payload)
        elif cmd_id == "dcl":  # Detailed Castle List
            self._handle_dcl(payload)
        elif cmd_id == "dql":  # Daily Quest List
            self._handle_dql(payload)
        elif cmd_id == "gus":  # Get Unit Stats
            self._handle_gus(payload)
        # Real-time movement updates
        elif cmd_id == "mov":  # Movement update
            self._handle_mov(payload)
        elif cmd_id == "atv":  # Attack/movement arrival
            self._handle_atv(payload)
        elif cmd_id == "ata":  # Attack arrived
            self._handle_ata(payload)
        elif cmd_id == "cam":  # Cancel army movement response
            self._handle_cam(payload)
        elif cmd_id == "rep":  # Battle reports
            self._handle_rep(payload)
        elif cmd_id == "red":  # Battle report details
            self._handle_red(payload)
        # Add more as needed

    def _handle_gbd(self, data: Dict[str, Any]):
        """
        Handle 'Get Big Data' packet.
        """
        # 1. Player Info (gpi)
        gpi = data.get("gpi", {})
        if gpi:
            pid = gpi.get("PID")
            if pid:
                if pid not in self.players:
                    self.players[pid] = Player(**gpi)
                self.local_player = self.players[pid]
                logger.info(
                    f"GameState: Local player set to {self.local_player.name} (ID: {pid})"
                )

        # 2. XP/Level (gxp)
        gxp = data.get("gxp", {})
        if self.local_player and gxp:
            self.local_player.LVL = gxp.get("LVL", self.local_player.LVL)
            self.local_player.XP = gxp.get("XP", self.local_player.XP)
            self.local_player.LL = gxp.get("LL", self.local_player.LL)
            self.local_player.XPFCL = gxp.get("XPFCL", self.local_player.XPFCL)
            self.local_player.XPTNL = gxp.get("XPTNL", self.local_player.XPTNL)
            logger.info(
                f"GameState: Level Updated - Lvl: {self.local_player.level}, LL: {self.local_player.legendary_level}, XP: {self.local_player.XP}/{self.local_player.XPTNL}"
            )

        # 3. Currencies (gcu)
        gcu = data.get("gcu", {})
        if self.local_player and gcu:
            self.local_player.gold = gcu.get("C1", 0)
            self.local_player.rubies = gcu.get("C2", 0)
            logger.info(
                f"GameState: Wealth Updated - Gold: {self.local_player.gold:,}, Rubies: {self.local_player.rubies}"
            )

        # 4. Alliance (gal)
        gal = data.get("gal", {})
        if (
            gal and self.local_player and gal.get("AID")
        ):  # Only if player has an alliance
            try:
                from empire_core.state.models import Alliance

                self.local_player.alliance = Alliance(**gal)
                self.local_player.AID = gal.get("AID")
                logger.info(
                    f"GameState: Alliance - {self.local_player.alliance.name} [{self.local_player.alliance.abbreviation}]"
                )
            except Exception as e:
                logger.debug(f"GameState: Could not parse alliance data: {e}")

        # 5. Castles (gcl)
        gcl = data.get("gcl", {})
        if gcl and self.local_player:
            kingdoms = gcl.get("C", [])
            for k_data in kingdoms:
                kid = k_data.get("KID", 0)
                area_infos = k_data.get("AI", [])
                for area_entry in area_infos:
                    # 'AI' entry is a list
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

            logger.info(
                f"GameState: Parsed {len(self.local_player.castles)} castles for local player."
            )

    def _handle_gaa(self, data: Dict[str, Any]):
        """Handle 'Get Area' (Map Chunk) response."""
        # Payload: { "A": [ ...areas... ], "KID": 0 }
        # Area Format: [Type, X, Y, AreaID, OwnerID, ...]

        areas = data.get("AI", [])  # Note: Payload key is 'AI' not 'A' based on logs
        if not areas:
            areas = data.get("A", [])  # Fallback

        kid = data.get("KID", 0)

        count = 0
        for area in areas:
            if not isinstance(area, list) or len(area) < 3:
                continue

            # Verified Indices:
            # 0: Type (T)
            # 1: X
            # 2: Y
            # 3: AreaID (AID) - Optional
            # 4: OwnerID (OID) - Optional

            atype = area[0]
            x = area[1]
            y = area[2]

            aid = -1
            oid = -1

            if len(area) > 3:
                aid = area[3]
            if len(area) > 4:
                oid = area[4]

            map_obj = MapObject(AID=aid, OID=oid, T=atype, X=x, Y=y, KID=kid)
            # Only store if it has a valid ID or we want to store by coordinate
            # Usually map objects have AID. Empty spots might not.
            if aid != -1:
                self.map_objects[aid] = map_obj

            count += 1

        logger.debug(f"GameState: Parsed {count} map objects in K{kid}")

    def _handle_gam(self, data: Dict[str, Any]):
        """Handle 'Get Army Movements' response."""
        # Payload structure from capture:
        # { "M": [ { "M": {...movement data...}, "UM": {...}, "GS": ..., "AST": [], "ATT": 0 } ], "O": [...] }

        movements_list = data.get("M", [])

        count = 0
        for m_wrapper in movements_list:
            if not isinstance(m_wrapper, dict):
                continue

            # Movement data is nested under "M" key
            m_data = m_wrapper.get("M", {})
            if not m_data:
                continue

            mid = m_data.get("MID")
            if not mid:
                continue

            try:
                # Create movement with main data
                mov = Movement(**m_data)

                # Extract target area details if available
                if (
                    mov.target_area
                    and isinstance(mov.target_area, list)
                    and len(mov.target_area) >= 5
                ):
                    # TA format: [type, x, y, area_id, owner_id, ...]
                    mov.target_x = mov.target_area[1]
                    mov.target_y = mov.target_area[2]
                    mov.target_area_id = mov.target_area[3]

                # Extract source area details if available
                if (
                    mov.source_area
                    and isinstance(mov.source_area, list)
                    and len(mov.source_area) >= 3
                ):
                    # SA format: [type, x, y, ...]
                    mov.source_x = mov.source_area[1]
                    mov.source_y = mov.source_area[2]
                    if len(mov.source_area) >= 4:
                        mov.source_area_id = mov.source_area[3]

                self.movements[mid] = mov
                count += 1

            except Exception as e:
                logger.debug(f"GameState: Failed to parse movement {mid}: {e}")

        if count > 0:
            logger.info(f"GameState: Parsed {count} active movements.")
        else:
            logger.debug("GameState: No active movements.")

    def _handle_dcl(self, data: Dict[str, Any]):
        """Handle 'Detailed Castle List' response."""
        # Payload structure usually: { "C": [ { "KID": 0, "AI": [ ... ] } ] }
        # Similar to gcl but with more info.
        # AI entry is a dict in dcl? Or list?
        # In pygge dcl seems to be used for resources/production.

        # Based on logs/structure:
        # dcl -> C -> [ { KID, AI: [ { AID: ..., W: ..., S: ..., F: ..., ... } ] } ]
        # Here AI elements are Dicts, unlike gcl where they were Lists.

        kingdoms = data.get("C", [])
        updated_count = 0

        for k_data in kingdoms:
            # kid = k_data.get("KID", 0) # Not always needed if we match by AID
            area_infos = k_data.get("AI", [])
            for castle_data in area_infos:
                if not isinstance(castle_data, dict):
                    continue

                aid = castle_data.get("AID")
                if aid and aid in self.castles:
                    castle = self.castles[aid]

                    # Get the nested gpa (game play area) data which has most details
                    gpa_data = castle_data.get("gpa", {})

                    # Update basic castle info (from gpa if available, fallback to top level)
                    castle.P = gpa_data.get("P", castle_data.get("P", castle.P))
                    castle.NDP = gpa_data.get("NDP", castle_data.get("NDP", castle.NDP))
                    castle.MC = gpa_data.get("MC", castle_data.get("MC", castle.MC))
                    castle.B = castle_data.get("B", castle.B)
                    castle.WS = castle_data.get("WS", castle.WS)
                    castle.DW = castle_data.get("DW", castle.DW)
                    castle.H = castle_data.get("H", castle.H)

                    # Update Resources (top level has current values)
                    res = castle.resources
                    res.wood = int(castle_data.get("W", res.wood))
                    res.stone = int(castle_data.get("S", res.stone))
                    res.food = int(castle_data.get("F", res.food))

                    # Resource capacities and rates (from gpa)
                    res.wood_cap = int(gpa_data.get("MRW", res.wood_cap))
                    res.stone_cap = int(gpa_data.get("MRS", res.stone_cap))
                    res.food_cap = int(gpa_data.get("MRF", res.food_cap))

                    # Production rates (from gpa)
                    res.wood_rate = float(gpa_data.get("RS1", res.wood_rate))
                    res.stone_rate = float(gpa_data.get("RS2", res.stone_rate))
                    res.food_rate = float(gpa_data.get("RS3", res.food_rate))

                    # Safe storage (from gpa)
                    res.wood_safe = float(gpa_data.get("SAFE_W", res.wood_safe))
                    res.stone_safe = float(gpa_data.get("SAFE_S", res.stone_safe))
                    res.food_safe = float(gpa_data.get("SAFE_F", res.food_safe))

                    # Special resources (from top level and gpa)
                    res.iron = int(castle_data.get("I", gpa_data.get("MRI", res.iron)))
                    res.glass = int(
                        castle_data.get("G", gpa_data.get("MRG", res.glass))
                    )
                    res.ash = int(castle_data.get("A", gpa_data.get("MRA", res.ash)))
                    res.honey = int(
                        castle_data.get("HONEY", gpa_data.get("MRHONEY", res.honey))
                    )
                    res.mead = int(
                        castle_data.get("MEAD", gpa_data.get("MRMEAD", res.mead))
                    )
                    res.beef = int(
                        castle_data.get("BEEF", gpa_data.get("MRBEEF", res.beef))
                    )

                    # Update Buildings from 'AC'
                    raw_buildings = castle_data.get("AC", [])
                    castle.buildings.clear()  # Clear existing, re-add
                    for b_data in raw_buildings:
                        if isinstance(b_data, list) and len(b_data) >= 2:
                            building_id = b_data[0]
                            building_level = b_data[1]
                            castle.buildings.append(
                                Building(id=building_id, level=building_level)
                            )

                    # Update Units from 'UN'
                    # UN format: {unit_id_str: count}
                    raw_units = castle_data.get("UN", {})
                    castle.units.clear()
                    for uid_str, count in raw_units.items():
                        try:
                            uid = int(uid_str)
                            castle.units[uid] = int(count)
                        except (ValueError, TypeError):
                            pass

                    # Update global armies state for UnitManager
                    self.armies[aid] = Army(units=castle.units.copy())

                    updated_count += 1

        logger.info(
            f"GameState: Updated details for {updated_count} castles (Resources, Buildings, Population)."
        )

    def _handle_dql(self, data: Dict[str, Any]):
        """Handle 'Daily Quest List' packet."""
        try:
            self.daily_quests = DailyQuest(**data)
            logger.info(
                f"GameState: Parsed daily quests - Level {self.daily_quests.level}, Active: {len(self.daily_quests.active_quests)}"
            )
        except Exception as e:
            logger.debug(f"GameState: Failed to parse daily quests: {e}")

    def _handle_gus(self, data: Dict[str, Any]):
        """Handle 'Get Unit Stats' packet."""
        # gus format: {"U": [...units...], "P": [...production...]}
        # This gives us unit availability/stats
        units_data = data.get("U", [])
        production_data = data.get("P", [])

        logger.debug(
            f"GameState: Received unit data - {len(units_data)} units, {len(production_data)} production items"
        )

    # ============================================================
    # Real-time Movement Packet Handlers
    # ============================================================

    def _parse_movement_from_data(
        self, m_data: Dict[str, Any], m_wrapper: Optional[Dict[str, Any]] = None
    ) -> Optional[Movement]:
        """
        Parse a Movement object from raw packet data.

        Args:
            m_data: The core movement data dict (contains MID, T, PT, TT, etc.)
            m_wrapper: Optional wrapper containing additional data (UM for units, etc.)

        Returns:
            Movement object or None if parsing fails
        """
        mid = m_data.get("MID")
        if not mid:
            return None

        try:
            # Create movement with main data
            mov = Movement(**m_data)
            mov.last_updated = time.time()

            # Extract target area details if available
            if (
                mov.target_area
                and isinstance(mov.target_area, list)
                and len(mov.target_area) >= 5
            ):
                # TA format: [type, x, y, area_id, owner_id, ...]
                mov.target_x = mov.target_area[1]
                mov.target_y = mov.target_area[2]
                mov.target_area_id = mov.target_area[3]
                # Try to get name if available (index 10+)
                if len(mov.target_area) > 10:
                    mov.target_name = (
                        str(mov.target_area[10]) if mov.target_area[10] else ""
                    )

            # Extract source area details if available
            if (
                mov.source_area
                and isinstance(mov.source_area, list)
                and len(mov.source_area) >= 3
            ):
                # SA format: [type, x, y, area_id, ...]
                mov.source_x = mov.source_area[1]
                mov.source_y = mov.source_area[2]
                if len(mov.source_area) >= 4:
                    mov.source_area_id = mov.source_area[3]
                if len(mov.source_area) > 10:
                    mov.source_name = (
                        str(mov.source_area[10]) if mov.source_area[10] else ""
                    )

            # Parse units from wrapper if available
            if m_wrapper:
                um_data = m_wrapper.get("UM", {})
                if um_data:
                    # UM format: {"620": 50, "621": 25, ...} (unit_id -> count)
                    for unit_id_str, count in um_data.items():
                        try:
                            unit_id = int(unit_id_str)
                            mov.units[unit_id] = int(count)
                        except (ValueError, TypeError):
                            pass

                # Parse resources if this is a transport/return
                gs_data = m_wrapper.get("GS", {})
                if gs_data and isinstance(gs_data, dict):
                    mov.resources = MovementResources(
                        W=gs_data.get("W", 0),
                        S=gs_data.get("S", 0),
                        F=gs_data.get("F", 0),
                        I=gs_data.get("I", 0),
                        G=gs_data.get("G", 0),
                        A=gs_data.get("A", 0),
                    )

            return mov

        except Exception as e:
            logger.debug(f"GameState: Failed to parse movement {mid}: {e}")
            return None

    def _handle_gam_with_events(self, data: Dict[str, Any]) -> List[Any]:
        """
        Handle 'Get Army Movements' response with delta detection.
        Returns list of events to emit.
        """
        events_to_emit = []
        movements_list = data.get("M", [])

        current_movement_ids: Set[int] = set()
        new_movements: List[Movement] = []

        for m_wrapper in movements_list:
            if not isinstance(m_wrapper, dict):
                continue

            m_data = m_wrapper.get("M", {})
            if not m_data:
                continue

            mid = m_data.get("MID")
            if not mid:
                continue

            current_movement_ids.add(mid)

            mov = self._parse_movement_from_data(m_data, m_wrapper)
            if not mov:
                continue

            # Check if this is a new movement
            is_new = mid not in self._previous_movement_ids

            if is_new:
                # Preserve created_at for new movements
                mov.created_at = time.time()
                new_movements.append(mov)

                # Create MovementStartedEvent
                event = MovementStartedEvent(
                    movement_id=mov.MID,
                    movement_type=mov.T,
                    movement_type_name=mov.movement_type_name,
                    source_area_id=mov.source_area_id,
                    target_area_id=mov.target_area_id,
                    is_incoming=mov.is_incoming,
                    is_outgoing=mov.is_outgoing,
                    total_time=mov.TT,
                    unit_count=mov.unit_count,
                )
                events_to_emit.append(event)

                # If incoming attack, emit special alert
                if mov.is_incoming and mov.is_attack:
                    attack_event = IncomingAttackEvent(
                        movement_id=mov.MID,
                        attacker_id=mov.OID,
                        attacker_name=mov.source_player_name,
                        target_area_id=mov.target_area_id,
                        target_name=mov.target_name,
                        time_remaining=mov.time_remaining,
                        unit_count=mov.unit_count,
                        source_x=mov.source_x,
                        source_y=mov.source_y,
                    )
                    events_to_emit.append(attack_event)
                    logger.warning(
                        f"INCOMING ATTACK! Movement {mov.MID} - {mov.time_remaining}s remaining"
                    )
            else:
                # Existing movement - preserve created_at, update rest
                existing = self.movements.get(mid)
                if existing:
                    mov.created_at = existing.created_at

                # Emit update event if progress changed significantly
                if existing and abs(mov.PT - existing.PT) >= 1:
                    event = MovementUpdatedEvent(
                        movement_id=mov.MID,
                        movement_type=mov.T,
                        movement_type_name=mov.movement_type_name,
                        source_area_id=mov.source_area_id,
                        target_area_id=mov.target_area_id,
                        is_incoming=mov.is_incoming,
                        is_outgoing=mov.is_outgoing,
                        progress_time=mov.PT,
                        total_time=mov.TT,
                        time_remaining=mov.time_remaining,
                        progress_percent=mov.progress_percent,
                    )
                    events_to_emit.append(event)

            self.movements[mid] = mov

        # Detect removed movements (arrived or cancelled)
        removed_ids = self._previous_movement_ids - current_movement_ids
        for mid in removed_ids:
            old_mov = self.movements.get(mid)
            if old_mov:
                # Movement completed/arrived
                event = MovementArrivedEvent(
                    movement_id=old_mov.MID,
                    movement_type=old_mov.T,
                    movement_type_name=old_mov.movement_type_name,
                    source_area_id=old_mov.source_area_id,
                    target_area_id=old_mov.target_area_id,
                    is_incoming=old_mov.is_incoming,
                    is_outgoing=old_mov.is_outgoing,
                    was_incoming=old_mov.is_incoming,
                    was_outgoing=old_mov.is_outgoing,
                )
                events_to_emit.append(event)

                # If it was a returning movement with loot
                if old_mov.is_returning and not old_mov.resources.is_empty:
                    return_event = ReturnArrivalEvent(
                        movement_id=old_mov.MID,
                        castle_id=old_mov.target_area_id,
                        units=old_mov.units.copy(),
                        resources_wood=old_mov.resources.wood,
                        resources_stone=old_mov.resources.stone,
                        resources_food=old_mov.resources.food,
                        total_loot=old_mov.resources.total,
                    )
                    events_to_emit.append(return_event)

                # Remove from movements dict
                del self.movements[mid]
                logger.debug(f"GameState: Movement {mid} arrived/completed")

        # Update previous movement IDs for next comparison
        self._previous_movement_ids = current_movement_ids

        if new_movements:
            logger.info(f"GameState: {len(new_movements)} new movement(s) detected")

        return events_to_emit

    def _handle_mov(self, data: Dict[str, Any]):
        """
        Handle real-time 'mov' (Movement Update) packet.
        This is pushed by server when movement status changes.
        """
        # mov packet structure varies - could be single movement or list
        # Common formats:
        # 1. {"M": {...movement_data...}} - single movement
        # 2. {"M": [{...}, {...}]} - list of movements

        m_data = data.get("M", data)

        if isinstance(m_data, list):
            # Multiple movements
            for item in m_data:
                if isinstance(item, dict):
                    self._process_single_movement_update(item)
        elif isinstance(m_data, dict):
            # Single movement
            self._process_single_movement_update(m_data)

        logger.debug(f"GameState: Processed mov packet")

    def _process_single_movement_update(self, m_data: Dict[str, Any]):
        """Process a single movement update from a mov packet."""
        mid = m_data.get("MID")
        if not mid:
            return

        # Check if movement already exists
        existing = self.movements.get(mid)

        mov = self._parse_movement_from_data(m_data)
        if not mov:
            return

        if existing:
            # Preserve created_at from existing
            mov.created_at = existing.created_at
        else:
            # New movement
            mov.created_at = time.time()
            self._previous_movement_ids.add(mid)
            logger.info(f"GameState: New movement detected via mov packet: {mid}")

        self.movements[mid] = mov

    def _handle_atv(self, data: Dict[str, Any]):
        """
        Handle 'atv' (Attack/Army Arrival) packet.
        This is pushed when an army arrives at its destination.
        """
        # atv packet typically contains:
        # MID - Movement ID that arrived
        # AID - Area ID where it arrived
        # Result data (battle outcome, loot, etc.)

        mid = data.get("MID")
        if not mid:
            logger.debug("GameState: atv packet without MID")
            return

        # Remove movement from tracking
        old_mov = self.movements.pop(mid, None)
        self._previous_movement_ids.discard(mid)

        if old_mov:
            logger.info(
                f"GameState: Movement {mid} ({old_mov.movement_type_name}) arrived at {old_mov.target_area_id}"
            )
        else:
            logger.debug(f"GameState: atv for unknown movement {mid}")

    def _handle_ata(self, data: Dict[str, Any]):
        """
        Handle 'ata' (Attack Arrived) packet.
        Similar to atv but specifically for attacks.
        """
        mid = data.get("MID")
        aid = data.get("AID")  # Target area

        if mid:
            old_mov = self.movements.pop(mid, None)
            self._previous_movement_ids.discard(mid)

            if old_mov:
                logger.info(
                    f"GameState: Attack {mid} arrived at area {aid or old_mov.target_area_id}"
                )

    def _handle_cam(self, data: Dict[str, Any]):
        """
        Handle 'cam' (Cancel Army Movement) response.
        Called when we or someone else cancels a movement.
        """
        mid = data.get("MID")
        success = data.get("S", 0)  # Success flag

        if mid and success:
            old_mov = self.movements.pop(mid, None)
            self._previous_movement_ids.discard(mid)

            if old_mov:
                logger.info(f"GameState: Movement {mid} cancelled/recalled")
        elif mid and not success:
            logger.warning(f"GameState: Failed to cancel movement {mid}")

    # ============================================================
    # Movement Query Methods
    # ============================================================

    def get_all_movements(self) -> List[Movement]:
        """Get all tracked movements."""
        return list(self.movements.values())

    def get_incoming_movements(self) -> List[Movement]:
        """Get all incoming movements (attacks, supports, etc.)."""
        return [m for m in self.movements.values() if m.is_incoming]

    def get_outgoing_movements(self) -> List[Movement]:
        """Get all outgoing movements."""
        return [m for m in self.movements.values() if m.is_outgoing]

    def get_returning_movements(self) -> List[Movement]:
        """Get all returning movements."""
        return [m for m in self.movements.values() if m.is_returning]

    def get_incoming_attacks(self) -> List[Movement]:
        """Get all incoming attack movements."""
        return [m for m in self.movements.values() if m.is_incoming and m.is_attack]

    def get_movements_to_castle(self, castle_id: int) -> List[Movement]:
        """Get all movements targeting a specific castle."""
        return [m for m in self.movements.values() if m.target_area_id == castle_id]

    def get_movements_from_castle(self, castle_id: int) -> List[Movement]:
        """Get all movements originating from a specific castle."""
        return [m for m in self.movements.values() if m.source_area_id == castle_id]

    def get_next_arrival(self) -> Optional[Movement]:
        """Get the movement that will arrive soonest."""
        movements = list(self.movements.values())
        if not movements:
            return None
        return min(movements, key=lambda m: m.time_remaining)

    def get_movement_by_id(self, movement_id: int) -> Optional[Movement]:
        """Get a specific movement by ID."""
        return self.movements.get(movement_id)

    def _handle_rep(self, data: Dict[str, Any]):
        """
        Handle 'Battle Reports' packet.
        """
        reports_data = data.get("R", [])
        if not isinstance(reports_data, list):
            return

        for report_data in reports_data:
            try:
                # Parse basic report info
                report = BattleReport(**report_data)
                self.reports.add_battle_report(report)
                logger.debug(f"Parsed battle report {report.report_id}")
            except Exception as e:
                logger.error(f"Failed to parse battle report: {e}")

        logger.info(f"GameState: Parsed {len(reports_data)} battle reports")

    def _handle_red(self, data: Dict[str, Any]):
        """
        Handle 'Battle Report Details' packet.
        """
        try:
            report_id = data.get("RID")
            if report_id and report_id in self.reports.battle_reports:
                # Update existing report with detailed data
                report = self.reports.battle_reports[report_id]

                # Parse detailed battle data
                battle_data = data.get("B", {})

                # Parse attacker
                if "A" in battle_data:
                    attacker_data = battle_data["A"]
                    if isinstance(attacker_data, dict):
                        # This would need more detailed parsing based on actual packet structure
                        # For now, just log that we received detailed data
                        logger.debug(
                            f"Received detailed battle data for report {report_id}"
                        )

                logger.debug(f"Updated battle report {report_id} with details")
        except Exception as e:
            logger.error(f"Failed to parse battle report details: {e}")
