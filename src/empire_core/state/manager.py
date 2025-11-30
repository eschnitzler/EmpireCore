import logging
from typing import Dict, Optional, Any, List
from empire_core.state.models import Player, Castle, Resources, Building
from empire_core.state.world_models import MapObject, Movement
from empire_core.state.quest_models import DailyQuest, Quest
from empire_core.state.unit_models import Army

logger = logging.getLogger(__name__)

class GameState:
    def __init__(self):
        self.local_player: Optional[Player] = None
        self.players: Dict[int, Player] = {}
        self.castles: Dict[int, Castle] = {}
        
        # World State
        self.map_objects: Dict[int, MapObject] = {}  # AreaID -> MapObject
        self.movements: Dict[int, Movement] = {}  # MovementID -> Movement
        
        # Quests
        self.daily_quests: Optional[DailyQuest] = None
        
        # Armies (castle_id -> Army)
        self.armies: Dict[int, Army] = {}

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
                logger.info(f"GameState: Local player set to {self.local_player.name} (ID: {pid})")

        # 2. XP/Level (gxp)
        gxp = data.get("gxp", {})
        if self.local_player and gxp:
            self.local_player.LVL = gxp.get("LVL", self.local_player.LVL)
            self.local_player.XP = gxp.get("XP", self.local_player.XP)
            self.local_player.LL = gxp.get("LL", self.local_player.LL)
            self.local_player.XPFCL = gxp.get("XPFCL", self.local_player.XPFCL)
            self.local_player.XPTNL = gxp.get("XPTNL", self.local_player.XPTNL)
            logger.info(f"GameState: Level Updated - Lvl: {self.local_player.level}, LL: {self.local_player.legendary_level}, XP: {self.local_player.XP}/{self.local_player.XPTNL}")

        # 3. Currencies (gcu)
        gcu = data.get("gcu", {})
        if self.local_player and gcu:
            self.local_player.gold = gcu.get("C1", 0)
            self.local_player.rubies = gcu.get("C2", 0)
            logger.info(f"GameState: Wealth Updated - Gold: {self.local_player.gold:,}, Rubies: {self.local_player.rubies}")
        
        # 4. Alliance (gal)
        gal = data.get("gal", {})
        if gal and self.local_player and gal.get("AID"):  # Only if player has an alliance
            try:
                from empire_core.state.models import Alliance
                self.local_player.alliance = Alliance(**gal)
                self.local_player.AID = gal.get("AID")
                logger.info(f"GameState: Alliance - {self.local_player.alliance.name} [{self.local_player.alliance.abbreviation}]")
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
                        name = raw_ai[10]
                        
                        if owner_id == self.local_player.id:
                            castle = Castle(
                                OID=area_id,
                                N=name,
                                KID=kid
                            )
                            self.castles[area_id] = castle
                            self.local_player.castles[area_id] = castle
            
            logger.info(f"GameState: Parsed {len(self.local_player.castles)} castles for local player.")

    def _handle_gaa(self, data: Dict[str, Any]):
        """Handle 'Get Area' (Map Chunk) response."""
        # Payload: { "A": [ ...areas... ], "KID": 0 }
        # Area Format: [Type, X, Y, AreaID, OwnerID, ...]
        
        areas = data.get("AI", []) # Note: Payload key is 'AI' not 'A' based on logs
        if not areas:
             areas = data.get("A", []) # Fallback

        kid = data.get("KID", 0)
        
        count = 0
        for area in areas:
            if not isinstance(area, list) or len(area) < 3: continue
            
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
            
            map_obj = MapObject(
                AID=aid,
                OID=oid,
                T=atype,
                X=x,
                Y=y,
                KID=kid
            )
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
                if mov.target_area and isinstance(mov.target_area, list) and len(mov.target_area) >= 5:
                    # TA format: [type, x, y, area_id, owner_id, ...]
                    mov.target_x = mov.target_area[1]
                    mov.target_y = mov.target_area[2]
                    mov.target_area_id = mov.target_area[3]
                
                # Extract source area details if available
                if mov.source_area and isinstance(mov.source_area, list) and len(mov.source_area) >= 3:
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
                if not isinstance(castle_data, dict): continue
                
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
                    res.glass = int(castle_data.get("G", gpa_data.get("MRG", res.glass)))
                    res.ash = int(castle_data.get("A", gpa_data.get("MRA", res.ash)))
                    res.honey = int(castle_data.get("HONEY", gpa_data.get("MRHONEY", res.honey)))
                    res.mead = int(castle_data.get("MEAD", gpa_data.get("MRMEAD", res.mead)))
                    res.beef = int(castle_data.get("BEEF", gpa_data.get("MRBEEF", res.beef)))
                    
                    # Update Buildings from 'AC'
                    raw_buildings = castle_data.get("AC", [])
                    castle.buildings.clear() # Clear existing, re-add
                    for b_data in raw_buildings:
                        if isinstance(b_data, list) and len(b_data) >= 2:
                            building_id = b_data[0]
                            building_level = b_data[1]
                            castle.buildings.append(Building(id=building_id, level=building_level))
                    
                    updated_count += 1
        
        logger.info(f"GameState: Updated details for {updated_count} castles (Resources, Buildings, Population).")
    
    def _handle_dql(self, data: Dict[str, Any]):
        """Handle 'Daily Quest List' packet."""
        try:
            self.daily_quests = DailyQuest(**data)
            logger.info(f"GameState: Parsed daily quests - Level {self.daily_quests.level}, Active: {len(self.daily_quests.active_quests)}")
        except Exception as e:
            logger.debug(f"GameState: Failed to parse daily quests: {e}")
    
    def _handle_gus(self, data: Dict[str, Any]):
        """Handle 'Get Unit Stats' packet."""
        # gus format: {"U": [...units...], "P": [...production...]}
        # This gives us unit availability/stats
        units_data = data.get("U", [])
        production_data = data.get("P", [])
        
        logger.debug(f"GameState: Received unit data - {len(units_data)} units, {len(production_data)} production items")
