"""
Map protocol models.

Commands:
- gaa: Get map area/chunk
- gam: Get active movements
- fnm: Find NPC on map
- adi: Get area/target detailed info
"""

from __future__ import annotations

import logging
import warnings
from enum import IntEnum

from pydantic import ConfigDict, Field, ValidationError

from .base import BasePayload, BaseRequest, BaseResponse, PlayerInfo, Position

logger = logging.getLogger(__name__)

# =============================================================================
# Map Item Types
# =============================================================================


class Kingdom(IntEnum):
    """
    Kingdom identifiers used throughout the game.

    Each kingdom has different terrain and unit types.
    """

    GREEN = 0  # Green Kingdom - basic/starter kingdom
    SANDS = 1  # Sand Kingdom - desert units
    ICE = 2  # Ice Kingdom - ice/frost units
    FIRE = 3  # Fire Kingdom - lava/fire units
    STORM = 4  # Storm Kingdom - storm/lightning units
    BERIMOND = 10  # Berimond event kingdom


class MapItemType(IntEnum):
    """
    Map object types from the AI array.

    These mirror the game client's own ``WorldConst.AREA_TYPE_*`` constants,
    cross-checked against the client's area-type-to-map-object registration.

    Two things that are not separate types:

    - A ruin is not an item type: the client registers no ruin map object, and
      the flag lives on the owner record instead (``R`` in a scan's OI list,
      exposed as :attr:`MapObject.is_ruin`).
    - The nomad khan camp, which appears while the nomad event runs, is
      ``ALLIANCE_NOMAD_CAMP`` (``NomadKhanCampMapObjectVO``).
    """

    EMPTY = 0
    CASTLE = 1  # Player main castle (while relocating, x/y is its in-transit position)
    DUNGEON = 2  # NPC camp - what players call a robber baron castle
    ROBBER_BARON = 2  # Alias of DUNGEON
    CAPITAL = 3  # Player capital
    OUTPOST = 4  # Player outpost
    TREASURE_DUNGEON = 7
    TREASURE_CAMP = 8
    SHADOW_AREA = 9
    VILLAGE = 10
    BOSS_DUNGEON = 11
    KINGDOM_CASTLE = 12  # Player castle in another kingdom
    EXTERNAL_KINGDOM = 12  # Alias of KINGDOM_CASTLE
    EVENT_DUNGEON = 13
    NO_LANDMARK = 14
    FACTION_CAMP = 15
    FACTION_VILLAGE = 16
    FACTION_TOWER = 17
    FACTION_CAPITAL = 18
    PLAGUE_AREA = 19
    TROOP_HOSTEL = 20
    ALIEN_CAMP = 21
    METRO = 22
    KINGS_TOWER = 23
    ISLE_RESOURCE = 24
    ISLE_DUNGEON = 25
    MONUMENT = 26
    NOMAD_CAMP = 27
    LABORATORY = 28
    SAMURAI_CAMP = 29
    FACTION_INVASION_CAMP = 30
    DYNAMIC = 31  # Dynamically placed event object
    SAMURAI_ALIEN_CAMP = 33
    RED_ALIEN_CAMP = 34
    ALLIANCE_NOMAD_CAMP = 35  # Nomad khan camp
    KHAN_CAMP = 35  # Alias of ALLIANCE_NOMAD_CAMP
    KHAN_TENT = 35  # Alias of ALLIANCE_NOMAD_CAMP
    DAIMYO_CASTLE = 37
    DAIMYO_TOWNSHIP = 38
    ABG_RESOURCE_TOWER = 40
    ABG_TOWER = 41
    WOLF_KING = 42
    ARE_PORTAL = 43
    NO_OUTPOST = 99


# =============================================================================
# GAA - Get Map Area
# =============================================================================


class GetMapAreaRequest(BaseRequest):
    """
    Get a chunk of the map.

    Command: gaa
    Payload: {"KID": kingdom_id, "AX1": x1, "AY1": y1, "AX2": x2, "AY2": y2}

    Returns information about all objects in the specified area.

    The server allows a maximum chunk size of ~90 tiles in each dimension.
    Invalid coordinates (outside map bounds) return empty AI array.

    Example:
        request = GetMapAreaRequest(KID=0, AX1=622, AY1=235, AX2=712, AY2=325)
    """

    command = "gaa"

    kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN)
    x1: int = Field(alias="AX1")
    y1: int = Field(alias="AY1")
    x2: int = Field(alias="AX2")
    y2: int = Field(alias="AY2")


# Indices into a gaa type-1 (CASTLE) raw entry. The live server sends 20
# fields per castle (reverse-engineered):
#   [type, x, y, castle_id, player_id, lvl, lvl, lvl, ?, ?, name,
#    0, 0, -1, -1, -1, 0, alliance_id, [], relocating_flag]
# Note the id at field 3 is the *castle* id, which is what ``owner_id``
# exposes for type-1 entries; the player id lives at field 4.
_PLAYER_ID_FIELD = 4
_RELOCATING_FIELD = 19  # 1 while the castle is in transit, 0 when settled

# Indices into a gaa type-2 (DUNGEON) raw entry, from the client's
# DungeonMapobjectVO.parseAreaInfo:
#   [type, x, y, seconds_since_espionage, victory_count, cooldown_seconds, kingdom]
# Indices into an owned-location row, from InteractiveMapobjectVO.parseAreaInfo.
_KEEP_LEVEL_FIELD = 5
_WALL_LEVEL_FIELD = 6
_GATE_LEVEL_FIELD = 7
_TOWER_LEVEL_FIELD = 8
_MOAT_LEVEL_FIELD = 9

_DUNGEON_ESPIONAGE_FIELD = 3
_DUNGEON_VICTORY_FIELD = 4
_DUNGEON_COOLDOWN_FIELD = 5
_DUNGEON_KINGDOM_FIELD = 6


class MapAreaItem(BasePayload):
    """
    A raw map area item from the AI array.

    AI array format: [[type, x, y, location_id, player_id, ...], ...]

    Field 3 is the location (castle/outpost) id for type-1 entries and the
    player id for the capital-like types -- see ``owner_id`` and ``player_id``.
    An NPC camp (type 2) has no owner at all: its field 3 is how long ago it was
    spied, so ``owner_id`` stays -1 and the camp's own fields are exposed by
    ``victory_count`` and the properties beside it.

    Common types (see MapItemType enum):
    - 1: Player main castle (``is_relocating`` tells you if it is in transit)
    - 2: NPC camp (robber baron)
    - 3: Capital
    - 4: Outpost
    - 22: Metropolis
    - 26: Monument
    """

    item_type: int = 0
    x: int = 0
    y: int = 0
    owner_id: int = -1
    raw_data: list = []  # Full raw array for extended parsing

    @classmethod
    def from_list(cls, data: list) -> "MapAreaItem":
        """Parse from AI array entry."""
        item_type = data[0] if len(data) > 0 else 0

        if (
            item_type in (MapItemType.CAPITAL, MapItemType.OUTPOST, MapItemType.METRO, MapItemType.KINGS_TOWER)
            and len(data) > 4
        ):
            owner_id = data[4]
        elif item_type == MapItemType.DUNGEON:
            # No owner: field 3 is the espionage age, not an id.
            owner_id = -1
        else:
            owner_id = data[3] if len(data) > 3 else -1

        return cls(
            item_type=item_type,
            x=data[1] if len(data) > 1 else 0,
            y=data[2] if len(data) > 2 else 0,
            owner_id=owner_id,
            raw_data=data,
        )

    def _dungeon_field(self, index: int) -> int | None:
        """An NPC camp field, or None when this is not a camp row."""
        if self.item_type != MapItemType.DUNGEON or len(self.raw_data) <= index:
            return None
        value = self.raw_data[index]
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    @property
    def victory_count(self) -> int | None:
        """
        How many times an NPC camp has been beaten, or None for other types.

        This is what selects the camp's defenders: pass it to
        ``GameData.dungeon_defence`` or
        ``empire_core.combat.npc_camp_defence``.
        """
        return self._dungeon_field(_DUNGEON_VICTORY_FIELD)

    @property
    def seconds_since_espionage(self) -> int | None:
        """How long ago an NPC camp was spied; -1 when it never was."""
        return self._dungeon_field(_DUNGEON_ESPIONAGE_FIELD)

    @property
    def attack_cooldown_seconds(self) -> int | None:
        """An NPC camp's remaining attack cooldown; negative once it expired."""
        return self._dungeon_field(_DUNGEON_COOLDOWN_FIELD)

    @property
    def camp_kingdom_id(self) -> int | None:
        """The kingdom an NPC camp sits in, as the camp row reports it."""
        return self._dungeon_field(_DUNGEON_KINGDOM_FIELD)

    def _level_field(self, index: int, minimum: int = 0) -> int:
        """A structure level from an owned-location row."""
        if self.item_type == MapItemType.DUNGEON or len(self.raw_data) <= index:
            return 0
        value = self.raw_data[index]
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return max(value, minimum)

    @property
    def keep_level(self) -> int:
        """The defender's keep level; the client floors this at 1."""
        return self._level_field(_KEEP_LEVEL_FIELD, minimum=1)

    @property
    def wall_level(self) -> int:
        """The defender's wall level, which decides its wall protection."""
        return self._level_field(_WALL_LEVEL_FIELD, minimum=1)

    @property
    def gate_level(self) -> int:
        """The defender's gate level."""
        return self._level_field(_GATE_LEVEL_FIELD, minimum=1)

    @property
    def tower_level(self) -> int:
        """The defender's tower level."""
        return self._level_field(_TOWER_LEVEL_FIELD)

    @property
    def moat_level(self) -> int:
        """The defender's moat level, 0 when it has none."""
        return self._level_field(_MOAT_LEVEL_FIELD)

    @property
    def player_id(self) -> int:
        """Id of the player who owns this location, or -1 if not reported.

        This is raw field 4. It differs from ``owner_id``, which for type-1
        (CASTLE) entries carries the *castle* id from field 3 -- keyed by that,
        a castle cannot be matched against ``AllianceMember.player_id``.
        """
        if len(self.raw_data) <= _PLAYER_ID_FIELD:
            return -1
        value = self.raw_data[_PLAYER_ID_FIELD]
        return value if isinstance(value, int) and not isinstance(value, bool) else -1

    @property
    def is_relocating(self) -> bool:
        """True while this castle is in transit to a new position.

        Raw field 19 is a per-castle relocation flag: 0 for a settled castle,
        1 while it is moving. Only type-1 (CASTLE) entries carry it; anything
        shorter than 20 fields predates the current server format and reports
        no relocation state at all.

        While relocating, ``(x, y)`` is the in-transit position the server
        reports for the castle.
        """
        if self.item_type != MapItemType.CASTLE or len(self.raw_data) <= _RELOCATING_FIELD:
            return False
        return bool(self.raw_data[_RELOCATING_FIELD])

    @property
    def is_moving_flag(self) -> bool:
        """Deprecated alias for :attr:`is_relocating`.

        Kept for callers written against the old name. It used to return True
        for *every* owned type-1 entry, which made it useless for detecting
        relocations; it now means what its name says.
        """
        warnings.warn(
            "MapAreaItem.is_moving_flag is deprecated; use is_relocating instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.is_relocating

    @property
    def is_castle(self) -> bool:
        """Check if this is any player-owned location."""
        return self.item_type in (
            MapItemType.CASTLE,
            MapItemType.CAPITAL,
            MapItemType.OUTPOST,
            MapItemType.EXTERNAL_KINGDOM,
            MapItemType.METRO,
        )

    @property
    def capturer_id(self) -> int:
        if self.item_type == MapItemType.OUTPOST:
            return self.raw_data[15] if len(self.raw_data) > 15 else -1
        elif self.item_type in (MapItemType.CAPITAL, MapItemType.METRO):
            return self.raw_data[14] if len(self.raw_data) > 14 else -1
        return -1

    @property
    def is_being_captured(self) -> bool:
        return self.capturer_id != -1

    @property
    def type_name(self) -> str:
        """Get human-readable type name."""
        try:
            return MapItemType(self.item_type).name
        except ValueError:
            return f"UNKNOWN_{self.item_type}"


class MapObject(BasePayload):
    """
    An owner record from a map scan's OI list.

    These describe the players who own objects in the scanned area. They carry
    no coordinates - X and Y are 0 - so a record cannot be placed on the map
    from a scan alone: the AI rows in the same response were not observed to
    reference these owner IDs.
    """

    x: int = Field(alias="X", default=0)
    y: int = Field(alias="Y", default=0)
    object_type: int = Field(alias="OT", default=0)
    object_id: int = Field(alias="OID", default=0)
    owner_id: int | None = Field(alias="PID", default=None)
    owner_name: str | None = Field(alias="PN", default=None)
    alliance_id: int | None = Field(alias="AID", default=None)
    alliance_name: str | None = Field(alias="AN", default=None)
    level: int = Field(alias="L", default=0)
    name: str | None = Field(alias="N", default=None)
    is_ruin: bool = Field(alias="R", default=False)

    @property
    def resolved_owner_id(self) -> int:
        if self.owner_id is not None:
            return self.owner_id
        return self.object_id

    @property
    def resolved_owner_name(self) -> str:
        if self.owner_name:
            return self.owner_name
        return self.name or ""

    @property
    def position(self) -> Position:
        """Get object position."""
        return Position(X=self.x, Y=self.y)


class GetMapAreaResponse(BaseResponse):
    """
    Response containing map area data.

    Command: gaa
    Response format: {"KID": 0, "AI": [[type, x, y, location_id, player_id, ...], ...], ...}

    The AI array contains raw map items. Use get_moving_flags() to extract the
    castles that are currently in transit.
    """

    command = "gaa"

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN)
    raw_items: list = Field(alias="AI", default_factory=list)
    objects: list[MapObject] = Field(alias="OI", default_factory=list)

    def get_ruins(self) -> list[MapObject]:
        """
        Owner records flagged as ruins.

        These have no coordinates; see :class:`MapObject`.
        """
        return [obj for obj in self.objects if obj.is_ruin]

    @property
    def items(self) -> list[MapAreaItem]:
        """Parse raw AI array into MapAreaItem objects.

        The raw AI rows are validated lazily, so a drifted row surfaces here
        rather than at parse time. Accessors must not leak raw pydantic errors
        after parse time, so such rows are skipped and counted instead.
        """
        items: list[MapAreaItem] = []
        skipped = 0
        for row in self.raw_items:
            if not (isinstance(row, list) and len(row) >= 4):
                continue
            try:
                items.append(MapAreaItem.from_list(row))
            except ValidationError:
                skipped += 1
        if skipped:
            # One line per response, not per row, so a fully drifted AI array
            # can't flood the log.
            logger.warning(
                f"Skipped {skipped}/{len(self.raw_items)} unparseable AI rows in map area "
                f"response for kingdom {self.kingdom}"
            )
        return items

    def get_moving_flags(self) -> dict[int, tuple[int, int]]:
        """
        Extract the castles in this area that are currently relocating.

        Only type-1 entries whose relocation flag (raw field 19) is set count;
        settled castles are ignored. Entries are keyed by the player id (raw
        field 4) so callers can match them against ``AllianceMember.player_id``.

        Returns:
            Dict mapping player_id -> (x, y) in-transit position
        """
        result: dict[int, tuple[int, int]] = {}
        for item in self.items:
            if item.is_relocating and item.player_id > 0:
                result[item.player_id] = (item.x, item.y)
        return result


# =============================================================================
# GAM - Get Active Movements
# =============================================================================


class GetMovementsRequest(BaseRequest):
    """
    Get all active troop movements.

    Command: gam
    Payload: {} (empty) or {"CID": castle_id}
    """

    command = "gam"

    castle_id: int | None = Field(alias="CID", default=None)


class Movement(BasePayload):
    """An active troop movement."""

    movement_id: int = Field(alias="MID")
    movement_type: int = Field(alias="MT")  # 1=attack, 2=support, 3=spy, 4=trade, etc.

    # Source
    source_x: int = Field(alias="SX")
    source_y: int = Field(alias="SY")
    source_castle_id: int = Field(alias="SCID", default=0)
    source_player_id: int = Field(alias="SPID", default=0)

    # Target
    target_x: int = Field(alias="TX")
    target_y: int = Field(alias="TY")
    target_castle_id: int | None = Field(alias="TCID", default=None)
    target_player_id: int | None = Field(alias="TPID", default=None)

    # Timing
    start_time: int = Field(alias="ST")  # Unix timestamp
    arrival_time: int = Field(alias="AT")  # Unix timestamp
    return_time: int | None = Field(alias="RT", default=None)

    # Status
    is_returning: bool = Field(alias="IR", default=False)

    @property
    def source_position(self) -> Position:
        """Get source position."""
        return Position(X=self.source_x, Y=self.source_y)

    @property
    def target_position(self) -> Position:
        """Get target position."""
        return Position(X=self.target_x, Y=self.target_y)


class GetMovementsResponse(BaseResponse):
    """
    Response containing active movements.

    Command: gam
    """

    command = "gam"

    movements: list[Movement] = Field(alias="M", default_factory=list)


# =============================================================================
# FNM - Find NPC
# =============================================================================


class FindNPCRequest(BaseRequest):
    """
    Find NPC targets on the map.

    Command: fnm
    Payload: {"NT": npc_type, "L": level, "KID": kingdom_id}

    NPC types vary by game version.
    """

    command = "fnm"

    npc_type: int = Field(alias="NT")
    level: int | None = Field(alias="L", default=None)
    kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN)


class NPCLocation(BasePayload):
    """An NPC location on the map."""

    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    npc_type: int = Field(alias="NT")
    level: int = Field(alias="L")
    npc_id: int = Field(alias="NID", default=0)

    @property
    def position(self) -> Position:
        """Get NPC position."""
        return Position(X=self.x, Y=self.y)


class FindNPCResponse(BaseResponse):
    """
    Response containing NPC locations.

    Command: fnm
    """

    command = "fnm"

    npcs: list[NPCLocation] = Field(alias="N", default_factory=list)


# =============================================================================
# ADI - Get Area/Target Detailed Info
# =============================================================================


class GetTargetInfoRequest(BaseRequest):
    """
    Get detailed info about a specific map location/target.

    Command: adi
    Payload: {"SX": source_x, "SY": source_y, "TX": target_x, "TY": target_y, "KID": kingdom_id}

    SX/SY is the attacker's source position, TX/TY is the target position.
    """

    command = "adi"

    source_x: int = Field(alias="SX")
    source_y: int = Field(alias="SY")
    target_x: int = Field(alias="TX")
    target_y: int = Field(alias="TY")
    kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN)


class TargetInfo(BasePayload):
    """Detailed information about a target location."""

    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    object_type: int = Field(alias="OT")
    object_id: int = Field(alias="OID", default=0)

    # Owner info (if owned)
    owner: PlayerInfo | None = Field(alias="O", default=None)

    # Castle-specific
    castle_name: str | None = Field(alias="CN", default=None)
    castle_level: int | None = Field(alias="CL", default=None)

    # NPC-specific
    npc_type: int | None = Field(alias="NT", default=None)
    npc_level: int | None = Field(alias="NL", default=None)

    # Resources (for resource nodes)
    resources: int | None = Field(alias="R", default=None)


class GetTargetInfoResponse(BaseResponse):
    """
    Response containing target information.

    Command: adi
    """

    command = "adi"

    target: TargetInfo | None = Field(alias="T", default=None)


__all__ = [
    # Kingdom
    "Kingdom",
    # Map Item Types
    "MapItemType",
    # GAA - Map Area
    "GetMapAreaRequest",
    "GetMapAreaResponse",
    "MapAreaItem",
    "MapObject",
    # GAM - Movements
    "GetMovementsRequest",
    "GetMovementsResponse",
    "Movement",
    # FNM - Find NPC
    "FindNPCRequest",
    "FindNPCResponse",
    "NPCLocation",
    # ADI - Target Info
    "GetTargetInfoRequest",
    "GetTargetInfoResponse",
    "TargetInfo",
]
