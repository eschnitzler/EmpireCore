"""Map area items: the rows of a map area, one per map object."""

from __future__ import annotations

import warnings
from typing import Any, cast

from pydantic import Field, ValidationError

from empire_core.enums import Kingdom, MapItemType
from empire_core.protocol.base import BasePayload, enum_or_none
from empire_core.protocol.js import js_int

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
        MapItemType.METROPOL,
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


# Rows whose structure levels sit at fields 5 to 9. InteractiveMapobjectVO.parseAreaInfo
# (bundle line 3631) reads them through int() and floors keep, wall and gate at 1;
# CapitalMapobjectVO (18731) and MetropolMapobjectVO (21611) take them as sent.
# Kings towers, monuments, laboratories, villages and isles parse their own rows
# and leave the inherited levels at 0.
_FLOORED_LEVEL_TYPES = frozenset(
    {MapItemType.CASTLE, MapItemType.OUTPOST, MapItemType.KINGDOM_CASTLE, MapItemType.FACTION_CAMP}
)


_RAW_LEVEL_TYPES = frozenset({MapItemType.CAPITAL, MapItemType.METROPOL})


# The level of an upgradable landmark: MonumentMapobjectVO reads it at field 6,
# LaboratoryMapobjectVO at field 5.
_LANDMARK_LEVEL_FIELDS: dict[MapItemType, int] = {MapItemType.MONUMENT: 6, MapItemType.LABORATORY: 5}


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

    Client: ``WorldmapObjectFactory.parseWorldMapArea`` (bundle line 5343)
    """

    item_type: int = 0
    x: int = 0
    y: int = 0
    owner_id: int = -1
    raw_data: list[Any] = Field(
        default_factory=list,
        description="The whole row; past [type, x, y] its layout depends on the area type",
    )

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
    def camp_kingdom_id(self) -> Kingdom | None:
        """The kingdom an NPC camp sits in, as the camp row reports it; None for a kingdom id Kingdom lacks."""
        value = self._dungeon_field(_DUNGEON_KINGDOM_FIELD)
        return None if value is None else enum_or_none(Kingdom, value)

    def _level_field(self, index: int, minimum: int = 0) -> int:
        """A structure level, 0 for a row that carries none."""
        if len(self.raw_data) <= index:
            return 0
        value = self.raw_data[index]
        if self.item_type in _FLOORED_LEVEL_TYPES:
            return max(js_int(value), minimum)
        if self.item_type in _RAW_LEVEL_TYPES and isinstance(value, int) and not isinstance(value, bool):
            return value
        return 0

    @property
    def landmark_level(self) -> int | None:
        """A monument's or laboratory's level, or None for other types."""
        index = _LANDMARK_LEVEL_FIELDS.get(cast(MapItemType, self.item_type))
        if index is None or len(self.raw_data) <= index:
            return None
        value = self.raw_data[index]
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @property
    def keep_level(self) -> int:
        """The defender's keep level; floored at 1 except on a capital or metropolis, 0 for a landmark."""
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
            MapItemType.KINGDOM_CASTLE,
            MapItemType.METROPOL,
        )

    @property
    def capturer_id(self) -> int:
        if self.item_type == MapItemType.OUTPOST:
            return self.raw_data[15] if len(self.raw_data) > 15 else -1
        elif self.item_type in (MapItemType.CAPITAL, MapItemType.METROPOL):
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


def parse_area_rows(value: Any) -> tuple[list[MapAreaItem], int]:
    """
    Map rows as :class:`MapAreaItem`, with how many rows could not be read.

    A row shorter than ``[type, x, y, id]`` is dropped without counting, and a
    row whose fields have the wrong types is counted and skipped, so one bad
    row costs only itself.

    Client: ``CastleWorldmapData.parseAreaInfos`` (bundle line 18993) hands
    each row to ``WorldmapObjectFactory.parseWorldMapArea`` (bundle line 5343).
    """
    if not isinstance(value, list):
        return [], 0
    items: list[MapAreaItem] = []
    skipped = 0
    for row in value:
        if isinstance(row, MapAreaItem):
            items.append(row)
            continue
        if not (isinstance(row, list) and len(row) >= 4):
            continue
        try:
            items.append(MapAreaItem.from_list(row))
        except (ValidationError, TypeError):
            skipped += 1
    return items, skipped


__all__ = [
    "MapAreaItem",
    "parse_area_rows",
]
