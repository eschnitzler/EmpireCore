"""
Map protocol models.

Commands:
- gaa: Get map area/chunk
- fnm: Find NPC on map
- adi: Get area/target detailed info
"""

from __future__ import annotations

import logging
import warnings
from enum import IntEnum

from pydantic import ConfigDict, Field, ValidationError, field_validator

from .alliance import MemberEmblem
from .base import BasePayload, BaseRequest, BaseResponse, Position

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


# Indices into an owned-location raw entry, from the client's
# InteractiveMapobjectVO.parseAreaInfo:
#   [type, x, y, object_id, player_id, keep, wall, gate, tower, moat, name,
#    attack_cooldown, sabotage_cooldown, seconds_since_espionage,
#    outpost_type, occupier_id, kingdom_id, ..., relocating_flag]
# A free castle plot is the four-field row [1, x, y, -1].
_LOCATION_ID_FIELD = 3
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

# An invasion event's camps share one row shape, which is not the castle one:
# field 4 names the camp, and fields 9 to 11 are fortification percentages
# rather than building levels.
_INVASION_CAMP_FIELD = 4
_INVASION_SCALING_FIELD = 8
_INVASION_WALL_BONUS_FIELD = 9
_INVASION_GATE_BONUS_FIELD = 10
_INVASION_MOAT_BONUS_FIELD = 11

# Types whose row carries an object id at field 3 and the owner's player id
# at field 4: every class that uses or mirrors InteractiveMapobjectVO.parseAreaInfo.
OWNED_AREA_TYPES = frozenset(
    {
        MapItemType.CASTLE,
        MapItemType.CAPITAL,
        MapItemType.OUTPOST,
        MapItemType.VILLAGE,
        MapItemType.KINGDOM_CASTLE,
        MapItemType.FACTION_CAMP,
        MapItemType.METRO,
        MapItemType.KINGS_TOWER,
        MapItemType.ISLE_RESOURCE,
        MapItemType.MONUMENT,
        MapItemType.LABORATORY,
    }
)

# Faction landmarks carry only the owner's player id, at field 3.
FACTION_LANDMARK_TYPES = frozenset(
    {
        MapItemType.FACTION_VILLAGE,
        MapItemType.FACTION_TOWER,
        MapItemType.FACTION_CAPITAL,
    }
)

INVASION_AREA_TYPES = frozenset(
    {
        MapItemType.SAMURAI_CAMP,
        MapItemType.DAIMYO_CASTLE,
        MapItemType.DAIMYO_TOWNSHIP,
    }
)


class MapAreaItem(BasePayload):
    """
    A raw map area item from the AI array.

    AI array format: [[type, x, y, location_id, player_id, ...], ...]

    For every type in ``OWNED_AREA_TYPES``, field 3 is the location
    (castle/outpost) id and field 4 the owning player's id -- see
    ``location_id`` and ``owner_id``. A faction landmark carries only the
    owner, at field 3. Every other row (an NPC camp, an event camp, a free
    plot) has no owner field, so ``owner_id`` stays -1 and ``has_owner_field``
    is False; a camp's own fields are exposed by ``victory_count`` and the
    properties beside it.

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

        if item_type in OWNED_AREA_TYPES and len(data) > _PLAYER_ID_FIELD:
            owner_id = data[_PLAYER_ID_FIELD]
        elif item_type in FACTION_LANDMARK_TYPES and len(data) > _LOCATION_ID_FIELD:
            owner_id = data[_LOCATION_ID_FIELD]
        else:
            owner_id = -1
        # An unclaimed outpost reports OUTPOST_DEFAULT_OWNER_ID (-300).
        if isinstance(owner_id, int) and not isinstance(owner_id, bool) and owner_id < 0:
            owner_id = -1

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
        ``GameData.dungeon_defense`` or
        ``empire_core.combat.npc_camp_defense``.
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

    def _invasion_field(self, index: int) -> int | None:
        """A field of an invasion event camp's row, or None for other types."""
        if self.item_type not in INVASION_AREA_TYPES or len(self.raw_data) <= index:
            return None
        value = self.raw_data[index]
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    @property
    def is_invasion_camp(self) -> bool:
        """Whether this row is an invasion event camp rather than a castle or an NPC camp."""
        return self.item_type in INVASION_AREA_TYPES

    @property
    def invasion_camp_field(self) -> int | None:
        """
        Field 4 of an invasion camp's row.

        The area type says what it means: a samurai camp counts its own defeats
        here, while a daimyo castle or township names its rank in the matching
        items table.
        """
        return self._invasion_field(_INVASION_CAMP_FIELD)

    @property
    def scaling_camp_id(self) -> int | None:
        """
        The difficulty-scaling camp this row points at, or -1 when unscaled.

        Set when the player picked a difficulty for the event, and it then
        decides the camp's level on its own.
        """
        return self._invasion_field(_INVASION_SCALING_FIELD)

    @property
    def base_wall_bonus(self) -> float | None:
        """An invasion camp's wall protection, already a percentage."""
        value = self._invasion_field(_INVASION_WALL_BONUS_FIELD)
        return None if value is None else float(value)

    @property
    def base_gate_bonus(self) -> float | None:
        """An invasion camp's gate protection, already a percentage."""
        value = self._invasion_field(_INVASION_GATE_BONUS_FIELD)
        return None if value is None else float(value)

    @property
    def base_moat_bonus(self) -> float | None:
        """An invasion camp's moat protection, already a percentage."""
        value = self._invasion_field(_INVASION_MOAT_BONUS_FIELD)
        return None if value is None else float(value)

    @property
    def player_id(self) -> int:
        """Id of the player who owns this location (raw field 4), or -1 if not reported."""
        if len(self.raw_data) <= _PLAYER_ID_FIELD:
            return -1
        value = self.raw_data[_PLAYER_ID_FIELD]
        return value if isinstance(value, int) and not isinstance(value, bool) else -1

    @property
    def location_id(self) -> int:
        """The area id of an owned location (raw field 3), or -1 for a camp or a free plot."""
        if self.item_type not in OWNED_AREA_TYPES or len(self.raw_data) <= _PLAYER_ID_FIELD:
            return -1
        value = self.raw_data[_LOCATION_ID_FIELD]
        # A bare outpost plot reports OUTPOST_DEFAULT_AREA_ID (-300).
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else -1

    @property
    def has_owner_field(self) -> bool:
        """Whether rows of this type carry an owner at all; camps do not."""
        return self.item_type in OWNED_AREA_TYPES or self.item_type in FACTION_LANDMARK_TYPES

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

    These describe the players who own objects in the scanned area. An AI
    row's player id matches a record's ``owner_id``; the player's own castles
    and villages are listed in ``area_positions`` and ``village_positions`` as
    ``[kingdom_id, object_id, x, y, area_type]``.

    Client: WorldMapOwnerInfoVO.fillFromParamObject
    """

    owner_id: int | None = Field(alias="OID", default=None)
    is_dummy: bool = Field(alias="DUM", default=False)
    owner_name: str | None = Field(alias="N", default=None)
    emblem: MemberEmblem | None = Field(alias="E", default=None)
    level: int = Field(alias="L", default=0)
    legendary_level: int = Field(alias="LL", default=0)
    honor: int = Field(alias="H", default=0)
    achievement_points: int = Field(alias="AVP", default=0)
    glory_points: int = Field(alias="CF", default=0)
    highest_glory_points: int = Field(alias="HF", default=0)
    prefix_title: int = Field(alias="PRE", default=0)
    suffix_title: int = Field(alias="SUF", default=0)
    current_top_x: int = Field(alias="TOPX", default=0)
    might_points: int = Field(alias="MP", default=0)
    is_ruin: bool = Field(alias="R", default=False)
    alliance_id: int | None = Field(alias="AID", default=None)
    alliance_rank: int = Field(alias="AR", default=0)
    alliance_name: str | None = Field(alias="AN", default=None)
    alliance_emblem: dict | None = Field(alias="aee", default=None)
    remaining_protection_time: int = Field(alias="RPT", default=0)
    area_positions: list[list[int]] | None = Field(alias="AP", default_factory=list)
    village_positions: list[list[int]] | None = Field(alias="VP", default_factory=list)
    is_searching_alliance: bool = Field(alias="SA", default=False)
    has_vip_flag: bool = Field(alias="VF", default=False)
    has_premium_flag: bool = Field(alias="PF", default=False)
    remaining_relocation_time: int = Field(alias="RRD", default=0)
    storm_title_id: int = Field(alias="TI", default=-1)  # -1: no title, 50-53: ranks 1-4, 54: ranks 5-10
    remaining_noob_protection: int = Field(alias="RNP", default=0)
    faction: dict | None = Field(alias="FN", default=None)

    @field_validator("area_positions", "village_positions", mode="before")
    @classmethod
    def _unwrap_nested_area_positions(cls, value: object) -> object:
        """Accept the server's occasional extra wrapper around one row (seen on AP in Berimond)."""
        if not isinstance(value, list):
            return value
        return [
            entry[0] if isinstance(entry, list) and len(entry) == 1 and isinstance(entry[0], list) else entry
            for entry in value
        ]


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
    owners: list[MapObject] = Field(alias="OI", default_factory=list)

    def get_ruins(self) -> list[MapObject]:
        """
        Owner records flagged as ruins.

        These have no coordinates; see :class:`MapObject`.
        """
        return [owner for owner in self.owners if owner.is_ruin]

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
    # FNM - Find NPC
    "FindNPCRequest",
    "FindNPCResponse",
    "NPCLocation",
]
