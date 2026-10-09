"""The player's castle list.

Commands:
- gcl: Get castles list
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import Field, ValidationError, field_validator, model_validator

from empire_core.enums import Kingdom, MapItemType
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, Position, enum_or_none
from empire_core.protocol.js import js_int

logger = logging.getLogger(__name__)


# =============================================================================
# Player Castle (gcl parsed)
# =============================================================================


@dataclass(frozen=True)
class _RowLayout:
    """Where one area type's castle-list row keeps each value; None where it has none."""

    object_id: int | None
    owner: int
    owner_through_int: bool
    name: int | None
    kingdom: int | None
    occupier: int | None = None
    levels: str | None = None
    landmark_level: int | None = None
    cooldowns: bool = False
    spy: int | None = None
    outpost_type: int | None = None
    skin: int | None = None
    protection: bool = False
    monument_type: int | None = None


_INTERACTIVE_ROW = _RowLayout(
    object_id=3,
    owner=4,
    owner_through_int=True,
    name=10,
    kingdom=16,
    occupier=15,
    levels="floored",
    cooldowns=True,
    spy=13,
    outpost_type=14,
    skin=17,
    protection=True,
)


_CAPITAL_ROW = _RowLayout(
    object_id=3,
    owner=4,
    owner_through_int=True,
    name=10,
    kingdom=16,
    occupier=14,
    levels="raw",
    cooldowns=True,
    spy=13,
    skin=15,
    protection=True,
)


# The area types a castle list can hold, each with its client parser's layout.
_ROW_LAYOUTS: dict[Any, _RowLayout] = {
    MapItemType.CASTLE: _INTERACTIVE_ROW,
    MapItemType.OUTPOST: _INTERACTIVE_ROW,
    MapItemType.KINGDOM_CASTLE: _INTERACTIVE_ROW,
    MapItemType.FACTION_CAMP: _INTERACTIVE_ROW,
    MapItemType.CAPITAL: _CAPITAL_ROW,
    MapItemType.METROPOL: _CAPITAL_ROW,
    MapItemType.KINGS_TOWER: _RowLayout(object_id=3, owner=4, owner_through_int=True, name=7, kingdom=5, spy=6),
    MapItemType.MONUMENT: _RowLayout(
        object_id=3, owner=4, owner_through_int=False, name=9, kingdom=7, landmark_level=6, spy=8, monument_type=5
    ),
    MapItemType.LABORATORY: _RowLayout(
        object_id=3, owner=4, owner_through_int=False, name=8, kingdom=6, landmark_level=5, spy=7
    ),
    MapItemType.FACTION_CAPITAL: _RowLayout(object_id=None, owner=3, owner_through_int=False, name=None, kingdom=None),
}


class PlayerCastle(BasePayload):
    """
    One row of a castle list's ``AI`` entries, read by field position as its
    area type's client parser reads it.

    - Castles, outposts, kingdom castles and faction camps
      (``InteractiveMapobjectVO.parseAreaInfo``): object id 3, owner 4, keep,
      wall, gate, tower and moat 5 to 9 through ``int()`` with keep, wall and
      gate at least 1, name 10, attack cooldown 11, sabotage cooldown 12,
      seconds since the last spy 13, outpost type 14, occupier 15, kingdom 16,
      equipment skin 17 and temporary sabotage protection 19 (on when it is 1);
      11 to 19 through ``int()``, so one the row lacks reads as 0.
    - Capitals and metropolises: as above, but the levels as sent, 13 as sent,
      the occupier at 14 and the skin at 15, both as sent, and no outpost type.
    - Kings towers: object id 3, owner 4, kingdom 5, seconds since the last spy 6, name 7.
    - Monuments: object id 3, owner 4, monument type 5, level 6, kingdom 7,
      seconds since the last spy 8, name 9.
    - Laboratories: object id 3, owner 4, level 5, kingdom 6, seconds since
      the last spy 7, name 8.
    - Faction capitals: owner 3, and no object id, name or kingdom.

    The client stores the row's kingdom as sent; one that is not a Kingdom
    reads as the kingdom the row is listed under. An occupier the row lacks
    reads as -1 here, where the client's ``int()`` would read 0: a
    deliberate leniency, so a short row does not look occupied.

    Client: ``WorldmapObjectFactory.parseWorldMapArea`` (bundle line 5343),
    ``InteractiveMapobjectVO.parseAreaInfo`` (bundle line 3631),
    ``CastleMapobjectVO.parseAreaInfo`` (bundle line 18910),
    ``FactionCampMapobjectVO.parseAreaInfo`` (bundle line 21526),
    ``CapitalMapobjectVO.parseAreaInfo`` (bundle line 18729),
    ``MetropolMapobjectVO.parseAreaInfo`` (bundle line 21609),
    ``KingstowerMapobjectVO.parseAreaInfo`` (bundle line 19055),
    ``MonumentMapobjectVO.parseAreaInfo`` (bundle line 21652),
    ``LaboratoryMapobjectVO.parseAreaInfo`` (bundle line 25900),
    ``FactionCapitalMapobjectVO.parseAreaInfo`` (bundle line 22764)
    """

    kingdom: Kingdom = Field(default=Kingdom.GREEN, description="The castle's kingdom")
    location_id: int | None = Field(default=None, description="The castle's object id; None for a type with none")
    x: int = Field(default=0, description="Map x")
    y: int = Field(default=0, description="Map y")
    castle_type: MapItemType = Field(default=MapItemType.EMPTY, description="The row's area type")
    owner_id: int = Field(default=0, description="Player id of the owner")
    name: str | None = Field(default=None, description="The castle's name; None for a type with none")
    occupier_id: int = Field(default=-1, description="Player id of the occupier, -1 when there is none")
    keep_level: int | None = Field(default=None, description="Keep level; None for a type with none")
    wall_level: int | None = Field(default=None, description="Wall level; None for a type with none")
    gate_level: int | None = Field(default=None, description="Gate level; None for a type with none")
    tower_level: int | None = Field(default=None, description="Tower level; None for a type with none")
    moat_level: int | None = Field(default=None, description="Moat level; None for a type with none")
    landmark_level: int | None = Field(
        default=None, description="A monument's or laboratory's level; None for any other type"
    )
    monument_type: int | None = Field(default=None, description="A monument's type; None for any other type")
    attack_cooldown_seconds: int | None = Field(
        default=None, description="Seconds until it can be attacked again; None for a type with none"
    )
    sabotage_cooldown_seconds: int | None = Field(
        default=None, description="Seconds until it can be sabotaged again; None for a type with none"
    )
    seconds_since_spy: int | None = Field(
        default=None, description="Seconds since it was last spied on; None for a type with none"
    )
    outpost_type: int | None = Field(default=None, description="The outpost type; None for a type with none")
    equipment_skin_id: int | None = Field(
        default=None, description="Unique id of the castle skin equipped; None for a type with none"
    )
    has_sabotage_protection: bool = Field(default=False, description="Whether a temporary sabotage protection is on")

    @property
    def is_occupied(self) -> bool:
        """Whether someone occupies this castle; the client's ``isOccupied`` is an occupier id above -1."""
        return self.occupier_id > -1

    @classmethod
    def from_list(cls, data: Any, kingdom: Kingdom = Kingdom.GREEN) -> "PlayerCastle":
        """
        Read a ``gcl.C[].AI[].AI`` row; ``kingdom`` is the block it is listed under.

        Raises:
            ValueError: The row is not a list, its area type is not one a
                castle list holds, or it is too short for its type's layout.
                ``ValidationError`` is one, for a field of the wrong type
        """
        if not isinstance(data, list) or not data:
            raise ValueError(f"Not a castle list row: {data!r}")
        area_type = data[0]
        layout = _ROW_LAYOUTS.get(area_type) if isinstance(area_type, int) and not isinstance(area_type, bool) else None
        if layout is None:
            raise ValueError(f"No castle list layout for area type {area_type!r}")
        if area_type == MapItemType.FACTION_CAMP and len(data) <= 3:
            raise ValueError("A faction camp row without its fields is not on the map")

        def field(index: int | None) -> Any:
            if index is None:
                return None
            if len(data) <= index:
                raise ValueError(f"Row too short for area type {area_type}: {data!r}")
            return data[index]

        def optional(index: int | None) -> Any:
            return data[index] if index is not None and len(data) > index else None

        through_int = layout.levels == "floored"
        row_kingdom = field(layout.kingdom) if layout.kingdom is not None and len(data) > layout.kingdom else None
        read_kingdom = (
            enum_or_none(Kingdom, row_kingdom)
            if isinstance(row_kingdom, int) and not isinstance(row_kingdom, bool)
            else None
        )
        owner = field(layout.owner)
        values: dict[str, Any] = {
            "kingdom": kingdom if read_kingdom is None else read_kingdom,
            "location_id": field(layout.object_id),
            "x": field(1),
            "y": field(2),
            "castle_type": area_type,
            "owner_id": js_int(owner) if layout.owner_through_int else owner,
            "name": field(layout.name),
            "landmark_level": field(layout.landmark_level),
        }
        if layout.monument_type is not None:
            values["monument_type"] = js_int(optional(layout.monument_type))
        if layout.occupier is not None:
            occupier = data[layout.occupier] if len(data) > layout.occupier else -1
            values["occupier_id"] = js_int(occupier) if through_int else occupier
        if layout.cooldowns:
            values["attack_cooldown_seconds"] = js_int(optional(11))
            values["sabotage_cooldown_seconds"] = js_int(optional(12))
        if layout.spy is not None:
            spy = optional(layout.spy)
            values["seconds_since_spy"] = js_int(spy) if through_int else spy
        if layout.outpost_type is not None:
            values["outpost_type"] = js_int(optional(layout.outpost_type))
        if layout.skin is not None:
            skin = optional(layout.skin)
            values["equipment_skin_id"] = js_int(skin) if through_int else skin
        if layout.protection:
            values["has_sabotage_protection"] = js_int(data[19] if len(data) > 19 else 0) == 1
        if through_int:
            keep, wall, gate, tower, moat = (js_int(field(i)) for i in range(5, 10))
            values.update(
                keep_level=max(keep, 1),
                wall_level=max(wall, 1),
                gate_level=max(gate, 1),
                tower_level=tower,
                moat_level=moat,
            )
        elif layout.levels == "raw":
            keep, wall, gate, tower, moat = (field(i) for i in range(5, 10))
            values.update(keep_level=keep, wall_level=wall, gate_level=gate, tower_level=tower, moat_level=moat)
        return cls(**values)


# =============================================================================
# GCL - Get Castles List
# =============================================================================


def _kingdom_entries(section: Any) -> list[tuple[Any, dict[str, Any]]]:
    """(kingdom id as sent, entry) pairs from a ``C: [{KID, AI: [...]}]`` section."""
    pairs: list[tuple[Any, dict[str, Any]]] = []
    if not isinstance(section, list):
        return pairs
    for kingdom in section:
        if not isinstance(kingdom, dict) or not isinstance(kingdom.get("AI"), list):
            continue
        kid = kingdom.get("KID", 0)
        pairs.extend((kid, entry) for entry in kingdom["AI"] if isinstance(entry, dict))
    return pairs


class GetCastlesRequest(BaseRequest):
    """
    Get a player's castle list.

    Command: gcl
    Payload: {"PID": player_id}

    The client always sends the logged-in player's id. Without one the
    payload is ``{}``, which the server answers with your castle list.

    Client: ``C2SGetCastleListVO`` (bundle line 60768); its
    ``MY_CASTLELIST`` is -1, but no caller sends it
    """

    command = "gcl"

    player_id: int | None = Field(
        validation_alias="PID", serialization_alias="PID", default=None, description="Your player id; None for none"
    )


_ENTRY_KEYS = ("OGT", "OGC", "AOT", "CAT", "TA")


class CastleInfo(BasePayload):
    """
    One of the player's locations: a castle list entry and its map row.

    Entry: {"AI": [row], "OGT": .., "OGC": .., "AOT": .., "CAT": .., "TA": ..}

    The row's values are read by its area type's layout, the field positions
    :class:`PlayerCastle` lists. ``OGT``, ``OGC``, ``AOT``, ``CAT`` and ``TA``
    are the entry's keys, read through ``int()`` (``OGT`` and ``OGC`` only when
    they are not 0), so one the entry lacks reads as 0. ``KID`` is the row's own
    kingdom when it carries one (``InteractiveMapobjectVO.parseAreaInfo``, bundle
    line 3637), else the block the entry is listed under. A faction capital's row carries no object
    id, so it has no CastleInfo.

    Client: ``CastleListVO.parseCastleList`` (bundle line 13698), which reads
    the row with ``WorldmapObjectFactory.parseWorldMapArea``
    """

    castle_id: int = Field(default=0, description="The castle's object id")
    castle_name: str = Field(default="", description="The castle's name")
    x: int = Field(default=0, description="Map x")
    y: int = Field(default=0, description="Map y")
    kingdom_id: Kingdom = Field(
        validation_alias="KID",
        serialization_alias="KID",
        default=Kingdom.GREEN,
        description="The castle's kingdom: the row's own, else the block it is listed under",
    )
    castle_type: MapItemType = Field(default=MapItemType.EMPTY, description="The castle's area type")
    owner_id: int = Field(default=0, description="Player id of the owner")
    occupier_id: int = Field(default=-1, description="Player id of the occupier, -1 when there is none")
    keep_level: int | None = Field(default=None, description="Keep level; None for a type with none")
    wall_level: int | None = Field(default=None, description="Wall level; None for a type with none")
    gate_level: int | None = Field(default=None, description="Gate level; None for a type with none")
    tower_level: int | None = Field(default=None, description="Tower level; None for a type with none")
    moat_level: int | None = Field(default=None, description="Moat level; None for a type with none")
    landmark_level: int | None = Field(
        default=None, description="A monument's or laboratory's level; None for any other type"
    )
    monument_type: int | None = Field(default=None, description="A monument's type; None for any other type")
    attack_cooldown_seconds: int | None = Field(
        default=None, description="Seconds until it can be attacked again; None for a type with none"
    )
    sabotage_cooldown_seconds: int | None = Field(
        default=None, description="Seconds until it can be sabotaged again; None for a type with none"
    )
    seconds_since_spy: int | None = Field(
        default=None, description="Seconds since it was last spied on; None for a type with none"
    )
    outpost_type: int | None = Field(default=None, description="The outpost type; None for a type with none")
    equipment_skin_id: int | None = Field(
        default=None, description="Unique id of the castle skin equipped; None for a type with none"
    )
    has_sabotage_protection: bool = Field(default=False, description="Whether a temporary sabotage protection is on")
    open_gate_seconds: int = Field(
        validation_alias="OGT", serialization_alias="OGT", default=0, description="Seconds the gate stays open"
    )
    open_gate_counter: int = Field(
        validation_alias="OGC", serialization_alias="OGC", default=0, description="How often the gate has been opened"
    )
    abandon_outpost_seconds: int = Field(
        validation_alias="AOT",
        serialization_alias="AOT",
        default=0,
        description="Seconds until the outpost is abandoned; not positive when it is not",
    )
    cancel_abandon_seconds: int = Field(
        validation_alias="CAT",
        serialization_alias="CAT",
        default=0,
        description="Seconds left to cancel abandoning the outpost",
    )
    no_abandon_seconds: int = Field(
        validation_alias="TA",
        serialization_alias="TA",
        default=0,
        description="Seconds before the outpost may be abandoned again",
    )

    _entry_ints = field_validator(
        *(
            "open_gate_seconds",
            "open_gate_counter",
            "abandon_outpost_seconds",
            "cancel_abandon_seconds",
            "no_abandon_seconds",
        ),
        mode="before",
    )(js_int)

    @property
    def is_occupied(self) -> bool:
        """Whether someone occupies it; the client's ``isOccupied`` is an occupier id above -1."""
        return self.occupier_id > -1

    @property
    def position(self) -> Position:
        """Get castle position as Position object."""
        return Position(x=self.x, y=self.y, kingdom=self.kingdom_id)

    @classmethod
    def from_entry(cls, entry: dict[str, Any], kingdom: Kingdom = Kingdom.GREEN) -> CastleInfo | None:
        """
        Parse a ``gcl.C[].AI[]`` entry; its ``AI`` row is read by its area type (see :class:`PlayerCastle`).

        None for a row the client reads but that names no castle: a faction
        capital, which has no object id, or a faction camp that is not on the map.
        """
        row = entry["AI"]
        if isinstance(row, list) and row and row[0] == MapItemType.FACTION_CAMP and len(row) <= 3:
            return None
        parsed = PlayerCastle.from_list(row, kingdom)
        if parsed.location_id is None:
            return None
        fields: dict[str, Any] = {
            "castle_id": parsed.location_id,
            "castle_name": parsed.name or "",
            "x": parsed.x,
            "y": parsed.y,
            "kingdom_id": parsed.kingdom,
            "castle_type": parsed.castle_type,
            "owner_id": parsed.owner_id,
            "occupier_id": parsed.occupier_id,
            "keep_level": parsed.keep_level,
            "wall_level": parsed.wall_level,
            "gate_level": parsed.gate_level,
            "tower_level": parsed.tower_level,
            "moat_level": parsed.moat_level,
            "landmark_level": parsed.landmark_level,
            "monument_type": parsed.monument_type,
            "attack_cooldown_seconds": parsed.attack_cooldown_seconds,
            "sabotage_cooldown_seconds": parsed.sabotage_cooldown_seconds,
            "seconds_since_spy": parsed.seconds_since_spy,
            "outpost_type": parsed.outpost_type,
            "equipment_skin_id": parsed.equipment_skin_id,
            "has_sabotage_protection": parsed.has_sabotage_protection,
        }
        fields.update({key: entry[key] for key in _ENTRY_KEYS if key in entry})
        return cls.model_validate(fields)


class GetCastlesResponse(BaseResponse):
    """
    The player's castle list.

    Command: gcl
    Payload: {"PID": player_id, "C": [{"KID": kingdom, "AI": [{"AI": [row...], "AOT": .., "TA": ..}, ...]}, ...]}

    Entries are flattened across kingdoms into ``castles``.

    Client: ``CastleListVO.parseCastleList`` (bundle line 13698), which gdi
    uses for its ``gcl`` block too.
    """

    command = "gcl"

    player_id: int = Field(validation_alias="PID", serialization_alias="PID", default=0)
    castles: list[CastleInfo] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _flatten_kingdoms(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "C" not in data:
            return data
        data = dict(data)
        section = data.pop("C")
        if isinstance(section, list):
            unreadable = [k for k in section if not (isinstance(k, dict) and isinstance(k.get("AI"), list))]
            if unreadable:
                logger.warning(
                    f"Skipped {len(unreadable)}/{len(section)} malformed gcl kingdom entries; "
                    "the castle list may be incomplete"
                )
        castles = []
        unparsed = 0
        for kid, entry in _kingdom_entries(section):
            try:
                castle = CastleInfo.from_entry(entry, kid)
            except (ValidationError, TypeError, ValueError, KeyError) as e:
                logger.debug(f"Skipping unreadable gcl row {entry!r}: {e}")
                unparsed += 1
                continue
            if castle is not None:
                castles.append(castle)
        if unparsed:
            logger.warning(f"Skipped {unparsed} gcl castle rows that could not be read")
        data["castles"] = castles
        return data


__all__ = [
    "GetCastlesRequest",
    "GetCastlesResponse",
    "PlayerCastle",
    "CastleInfo",
]
