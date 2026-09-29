"""The player's castle list.

Commands:
- gcl: Get castles list
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import Field, ValidationError, model_validator

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


_INTERACTIVE_ROW = _RowLayout(
    object_id=3, owner=4, owner_through_int=True, name=10, kingdom=16, occupier=15, levels="floored"
)


_CAPITAL_ROW = _RowLayout(object_id=3, owner=4, owner_through_int=True, name=10, kingdom=16, occupier=14, levels="raw")


# The area types a castle list can hold, each with its client parser's layout.
_ROW_LAYOUTS: dict[Any, _RowLayout] = {
    MapItemType.CASTLE: _INTERACTIVE_ROW,
    MapItemType.OUTPOST: _INTERACTIVE_ROW,
    MapItemType.KINGDOM_CASTLE: _INTERACTIVE_ROW,
    MapItemType.FACTION_CAMP: _INTERACTIVE_ROW,
    MapItemType.CAPITAL: _CAPITAL_ROW,
    MapItemType.METROPOL: _CAPITAL_ROW,
    MapItemType.KINGS_TOWER: _RowLayout(object_id=3, owner=4, owner_through_int=True, name=7, kingdom=5),
    MapItemType.MONUMENT: _RowLayout(
        object_id=3, owner=4, owner_through_int=False, name=9, kingdom=7, landmark_level=6
    ),
    MapItemType.LABORATORY: _RowLayout(
        object_id=3, owner=4, owner_through_int=False, name=8, kingdom=6, landmark_level=5
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
      gate at least 1, name 10, occupier 15, kingdom 16.
    - Capitals and metropolises: as above, but the levels as sent and the
      occupier at 14.
    - Kings towers: object id 3, owner 4, kingdom 5, name 7.
    - Monuments: object id 3, owner 4, level 6, kingdom 7, name 9.
    - Laboratories: object id 3, owner 4, level 5, kingdom 6, name 8.
    - Faction capitals: owner 3, and no object id, name or kingdom.

    The client stores the row's kingdom as sent; one that is not a Kingdom
    reads as the kingdom the row is listed under.

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
    capturer_id: int = Field(default=-1, description="Player id of the occupier, -1 when there is none")
    keep_level: int | None = Field(default=None, description="Keep level; None for a type with none")
    wall_level: int | None = Field(default=None, description="Wall level; None for a type with none")
    gate_level: int | None = Field(default=None, description="Gate level; None for a type with none")
    tower_level: int | None = Field(default=None, description="Tower level; None for a type with none")
    moat_level: int | None = Field(default=None, description="Moat level; None for a type with none")
    landmark_level: int | None = Field(
        default=None, description="A monument's or laboratory's level; None for any other type"
    )

    @property
    def is_being_captured(self) -> bool:
        """Whether someone occupies this castle; the client's ``isOccupied`` is an occupier id above -1."""
        return self.capturer_id > -1

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
        if layout.occupier is not None:
            occupier = data[layout.occupier] if len(data) > layout.occupier else -1
            values["capturer_id"] = js_int(occupier) if layout.levels == "floored" else occupier
        if layout.levels == "floored":
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
    Get list of player's castles.

    Command: gcl
    Payload: {} (the game client sends {"PID": own_player_id})
    """

    command = "gcl"


class CastleInfo(BasePayload):
    """
    One of the player's locations: a castle list entry and its map row.

    Entry: {"AI": [row], "OGT": .., "OGC": .., "AOT": .., "CAT": .., "TA": ..}

    The row is read by its area type's layout (see :class:`PlayerCastle`); an
    ``AI[n]`` alias names the field a castle's row keeps the value in. The
    other aliases are the entry's keys, and ``KID`` is the kingdom block the
    entry is listed under. A faction capital's row carries no object id, so
    it has no CastleInfo.

    Client: ``CastleListVO.parseCastleList`` (bundle line 13698), which reads
    the row with ``WorldmapObjectFactory.parseWorldMapArea`` and the entry's
    ``OGT``, ``OGC``, ``AOT``, ``CAT`` and ``TA`` through ``int()``
    """

    castle_id: int = Field(alias="AI[3]", default=0, description="The castle's object id")
    castle_name: str = Field(alias="AI[10]", default="", description="The castle's name")
    x: int = Field(alias="AI[1]", default=0, description="Map x")
    y: int = Field(alias="AI[2]", default=0, description="Map y")
    kingdom_id: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The kingdom it is listed under")
    castle_type: MapItemType = Field(alias="AI[0]", default=MapItemType.EMPTY, description="The castle's area type")
    owner_id: int = Field(alias="AI[4]", default=0, description="Player id of the owner")
    occupier_id: int = Field(
        alias="AI[14|15]",
        default=-1,
        description="Player id of the occupier, -1 when there is none",
    )
    keep_level: int | None = Field(alias="AI[5]", default=None, description="Keep level; None for a type with none")
    wall_level: int | None = Field(alias="AI[6]", default=None, description="Wall level; None for a type with none")
    gate_level: int | None = Field(alias="AI[7]", default=None, description="Gate level; None for a type with none")
    tower_level: int | None = Field(alias="AI[8]", default=None, description="Tower level; None for a type with none")
    moat_level: int | None = Field(alias="AI[9]", default=None, description="Moat level; None for a type with none")
    landmark_level: int | None = Field(
        default=None, description="A monument's or laboratory's level; None for any other type"
    )
    open_gate_seconds: int = Field(alias="OGT", default=0, description="Seconds the gate stays open")
    open_gate_counter: int = Field(alias="OGC", default=0, description="How often the gate has been opened")
    abandon_outpost_seconds: int = Field(
        alias="AOT", default=-1, description="Seconds until the outpost is abandoned, -1 when it is not"
    )
    cancel_abandon_seconds: int = Field(
        alias="CAT", default=-1, description="Seconds left to cancel abandoning the outpost"
    )
    no_abandon_seconds: int = Field(
        alias="TA", default=-1, description="Seconds before the outpost may be abandoned again"
    )

    @property
    def is_occupied(self) -> bool:
        """Whether someone occupies it; the client's ``isOccupied`` is an occupier id above -1."""
        return self.occupier_id > -1

    @property
    def position(self) -> Position:
        """Get castle position as Position object."""
        return Position(X=self.x, Y=self.y, KID=self.kingdom_id)

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
            "kingdom_id": kingdom,
            "castle_type": parsed.castle_type,
            "owner_id": parsed.owner_id,
            "occupier_id": parsed.capturer_id,
            "keep_level": parsed.keep_level,
            "wall_level": parsed.wall_level,
            "gate_level": parsed.gate_level,
            "tower_level": parsed.tower_level,
            "moat_level": parsed.moat_level,
            "landmark_level": parsed.landmark_level,
        }
        fields.update({key: entry[key] for key in ("OGT", "OGC", "AOT", "CAT", "TA") if key in entry})
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

    player_id: int = Field(alias="PID", default=0)
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
