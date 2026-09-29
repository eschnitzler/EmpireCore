"""
Castle protocol models.

Commands:
- gcl: Get castles list
- dcl: Get detailed castle info
- jca: Jump to / select castle
- arc: Rename castle
- rst: Relocate castle
- grc: Get resources
- gpa: Get production rates
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ConfigDict, Field, ValidationError, field_serializer, field_validator, model_validator

from empire_core.utils.enums import Kingdom, MapItemType

from ..js import js_int
from ..text import encode_json_text
from .base import BasePayload, BaseRequest, BaseResponse, Position, ResourceAmount, enum_or_none

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


# =============================================================================
# DCL - Get Detailed Castle Info
# =============================================================================


class GetDetailedCastleRequest(BaseRequest):
    """
    Get resources, units and production data for every castle the player owns.

    Command: dcl
    Payload: {} (the game client sends {"CD": 0}; the server lists every castle either way)
    """

    command = "dcl"


# Server keys of ClientConstCollectable.GROUP_LIST_RESOURCES, by field name.
_RESOURCE_KEYS = {
    "wood": "W",
    "stone": "S",
    "food": "F",
    "coal": "C",
    "oil": "O",
    "glass": "G",
    "iron": "I",
    "aquamarine": "A",
    "honey": "HONEY",
    "mead": "MEAD",
    "beef": "BEEF",
}


def _truncate(value: Any) -> Any:
    """Amounts arrive as floats ("W": 7000.0) and tick fractionally."""
    return int(value) if isinstance(value, float) else value


class _ProductionAreaSection(BasePayload):
    """A per-resource slice of the ``gpa`` block; validated from the whole block."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class ResourceProduction(_ProductionAreaSection):
    """Hourly production per resource; the client reads ``D<key>`` / 10."""

    wood: float = Field(alias="DW", default=0.0)
    stone: float = Field(alias="DS", default=0.0)
    food: float = Field(alias="DF", default=0.0)
    coal: float = Field(alias="DC", default=0.0)
    oil: float = Field(alias="DO", default=0.0)
    glass: float = Field(alias="DG", default=0.0)
    iron: float = Field(alias="DI", default=0.0)
    aquamarine: float = Field(alias="DA", default=0.0)
    honey: float = Field(alias="DHONEY", default=0.0)
    mead: float = Field(alias="DMEAD", default=0.0)
    beef: float = Field(alias="DBEEF", default=0.0)

    @field_validator("*", mode="before")
    @classmethod
    def _per_hour(cls, value: Any) -> Any:
        return value / 10 if isinstance(value, (int, float)) and not isinstance(value, bool) else value


class StorageCapacity(_ProductionAreaSection):
    """Storage capacity per resource (``MR<key>``)."""

    wood: int = Field(alias="MRW", default=0)
    stone: int = Field(alias="MRS", default=0)
    food: int = Field(alias="MRF", default=0)
    coal: int = Field(alias="MRC", default=0)
    oil: int = Field(alias="MRO", default=0)
    glass: int = Field(alias="MRG", default=0)
    iron: int = Field(alias="MRI", default=0)
    aquamarine: int = Field(alias="MRA", default=0)
    honey: int = Field(alias="MRHONEY", default=0)
    mead: int = Field(alias="MRMEAD", default=0)
    beef: int = Field(alias="MRBEEF", default=0)


class ProductionBonus(_ProductionAreaSection):
    """Production bonus per resource in percent (``<key>M``); 100 means no bonus."""

    wood: float = Field(alias="WM", default=0.0)
    stone: float = Field(alias="SM", default=0.0)
    food: float = Field(alias="FM", default=0.0)
    coal: float = Field(alias="CM", default=0.0)
    oil: float = Field(alias="OM", default=0.0)
    glass: float = Field(alias="GM", default=0.0)
    iron: float = Field(alias="IM", default=0.0)
    aquamarine: float = Field(alias="AM", default=0.0)
    honey: float = Field(alias="HONEYM", default=0.0)
    mead: float = Field(alias="MEADM", default=0.0)
    beef: float = Field(alias="BEEFM", default=0.0)


class SafeAmount(_ProductionAreaSection):
    """Amount per resource safe from plunder (``SAFE_<key>``)."""

    wood: float = Field(alias="SAFE_W", default=0.0)
    stone: float = Field(alias="SAFE_S", default=0.0)
    food: float = Field(alias="SAFE_F", default=0.0)
    coal: float = Field(alias="SAFE_C", default=0.0)
    oil: float = Field(alias="SAFE_O", default=0.0)
    glass: float = Field(alias="SAFE_G", default=0.0)
    iron: float = Field(alias="SAFE_I", default=0.0)
    aquamarine: float = Field(alias="SAFE_A", default=0.0)
    honey: float = Field(alias="SAFE_HONEY", default=0.0)
    mead: float = Field(alias="SAFE_MEAD", default=0.0)
    beef: float = Field(alias="SAFE_BEEF", default=0.0)


_PRODUCTION_AREA_SECTIONS = ("production", "storage_capacity", "production_bonus_percent", "safe_amount")


class CastleProductionArea(BasePayload):
    """The ``gpa`` block of a dcl entry, as AreaDataCommonInfo, AreaDataStorageItem,
    AreaDataMorality and AreaDataUpdater read it.

    The per-resource sections are aliased key by key and validated from the
    same block, so each wire key appears once in this module.
    """

    population: int = Field(alias="P", default=0)
    neutral_deco_points: int = Field(alias="NDP", default=0)
    sickness: int = Field(alias="S", default=0)
    riot: int = Field(alias="R", default=0)
    guards: int = Field(alias="GRD", default=0)
    build_speed_percent: int = Field(alias="BDB", default=100)
    metropolis_food_bonus: float = Field(alias="MP", default=0.0)
    unit_capacity: int = Field(alias="US", default=0)
    auxiliary_capacity: int = Field(alias="AUS", default=0)
    morale: int = Field(alias="M", default=0)
    food_consumption_delta: float = Field(alias="DFC", default=0.0)
    food_consumption_reduction_percent: int = Field(alias="FCR", default=100)
    mead_consumption_delta: float = Field(alias="DMEADC", default=0.0)
    mead_consumption_reduction_percent: int = Field(alias="MEADCR", default=100)
    beef_consumption_delta: float = Field(alias="DBEEFC", default=0.0)
    beef_consumption_reduction_percent: int = Field(alias="BEEFCR", default=100)
    barracks_speed: float = Field(alias="RS1", default=0.0)
    workshop_speed: float = Field(alias="RS2", default=0.0)
    defense_workshop_speed: float = Field(alias="RS3", default=0.0)
    hospital_speed: float = Field(alias="RSH", default=0.0)
    production: ResourceProduction = Field(default_factory=ResourceProduction)
    storage_capacity: StorageCapacity = Field(default_factory=StorageCapacity)
    production_bonus_percent: ProductionBonus = Field(default_factory=ProductionBonus)
    safe_amount: SafeAmount = Field(default_factory=SafeAmount)

    @model_validator(mode="before")
    @classmethod
    def _sections_see_the_whole_block(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        block = dict(data)
        data = dict(data)
        for name in _PRODUCTION_AREA_SECTIONS:
            data.setdefault(name, block)
        return data

    @property
    def food_consumption_per_hour(self) -> float:
        """Hourly food consumption (``DFC`` / 10)."""
        return self.food_consumption_delta / 10


class DetailedCastleInfo(BasePayload):
    """Per-castle detail from a dcl entry, as the client's DetailedCastleVO reads it."""

    castle_id: int = Field(alias="AID")
    kingdom_id: int = Field(alias="KID", default=0)
    wood: int = Field(alias="W", default=0)
    stone: int = Field(alias="S", default=0)
    food: int = Field(alias="F", default=0)
    coal: int = Field(alias="C", default=0)
    oil: int = Field(alias="O", default=0)
    glass: int = Field(alias="G", default=0)
    iron: int = Field(alias="I", default=0)
    aquamarine: int = Field(alias="A", default=0)
    honey: int = Field(alias="HONEY", default=0)
    mead: int = Field(alias="MEAD", default=0)
    beef: int = Field(alias="BEEF", default=0)
    defense_value: int = Field(alias="D", default=0)
    has_barracks: bool = Field(alias="B", default=False)
    has_siege_workshop: bool = Field(alias="WS", default=False)
    has_defense_workshop: bool = Field(alias="DW", default=False)
    has_hospital: bool = Field(alias="H", default=False)
    market_carriages: int = Field(alias="MC", default=0)
    open_gate_seconds: int = Field(alias="OGT", default=0)
    abandon_outpost_seconds: int = Field(alias="AOT", default=-1)
    raw_units: list[list[int]] = Field(alias="AC", default_factory=list)
    raw_stronghold_units: list[list[int]] = Field(alias="SHI", default_factory=list)
    raw_hospital_units: list[list[int]] = Field(alias="HI", default_factory=list)
    raw_travelling_units: list[list[int]] = Field(alias="TU", default_factory=list)
    production_area: CastleProductionArea | None = Field(alias="gpa", default=None)

    _truncate_amounts = field_validator(*_RESOURCE_KEYS, mode="before")(_truncate)

    @staticmethod
    def _pairs(rows: list[list[int]]) -> dict[int, int]:
        return {row[0]: row[1] for row in rows if len(row) >= 2}

    @property
    def units(self) -> dict[int, int]:
        """Units stationed here as {unit_id: count}, from the ``AC`` pairs."""
        return self._pairs(self.raw_units)

    @property
    def stronghold_units(self) -> dict[int, int]:
        """Units in the safe house / stronghold (``SHI``)."""
        return self._pairs(self.raw_stronghold_units)

    @property
    def hospital_units(self) -> dict[int, int]:
        """Wounded units in the hospital (``HI``)."""
        return self._pairs(self.raw_hospital_units)

    @property
    def travelling_units(self) -> dict[int, int]:
        """Units currently travelling (``TU``)."""
        return self._pairs(self.raw_travelling_units)


class GetDetailedCastleResponse(BaseResponse):
    """
    Detail for every castle the player owns.

    Command: dcl
    Payload: {"PID": player_id, "C": [{"KID": kingdom, "AI": [{"AID": castle_id, "W": .., "AC": [..], "gpa": {..}}]}]}
    """

    command = "dcl"

    player_id: int = Field(alias="PID", default=0)
    castles: list[DetailedCastleInfo] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _flatten_kingdoms(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "C" not in data:
            return data
        data = dict(data)
        data["castles"] = [{**entry, "KID": kid} for kid, entry in _kingdom_entries(data.pop("C"))]
        return data

    def castle(self, castle_id: int) -> DetailedCastleInfo | None:
        """The listed castle with this id, or None."""
        return next((c for c in self.castles if c.castle_id == castle_id), None)


# =============================================================================
# JCA - Jump to Castle / Select Castle
# =============================================================================


class SelectCastleRequest(BaseRequest):
    """
    Join a castle, making it the session's active castle.

    Command: jca (answered as 'jaa')
    Payload: {"CID": castle_id, "KID": kingdom_id}

    Castle-scoped reads such as ``gui`` answer for the joined castle.

    Client: ``C2SJoinCastleVO`` (bundle line 5841); its ``MY_CASTLE`` is -1
    """

    command = "jca"
    response_command = "jaa"

    castle_id: int = Field(
        alias="CID",
        description=(
            "The castle to join, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    kingdom_id: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")


class SelectCastleResponse(BaseResponse):
    """
    Response to castle selection.

    Command: jaa
    """

    command = "jaa"


# =============================================================================
# ARC - Rename Castle
# =============================================================================


class RenameCastleRequest(BaseRequest):
    """
    Rename a castle.

    Command: arc
    Payload: {"CID": castle_id, "P": 0 or 1, "KID": kingdom_id, "AT": area_type, "N": name}

    The keys follow the client's order: the constructor initialises CID, P, KID
    and AT before it sets N, which it encodes as it encodes any text it sends.

    Client: ``C2SRenameCastleVO`` (bundle line 42424)
    """

    command = "arc"

    castle_id: int = Field(
        alias="CID", description="The castle to rename, a CastleInfo.castle_id from client.castle.get_all()"
    )
    is_rename: int = Field(
        alias="P", default=1, description="1 to rename, 0 to name a newly acquired castle such as a monument"
    )
    kingdom_id: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")
    castle_type: MapItemType = Field(alias="AT", description="The castle's area type")
    castle_name: str = Field(alias="N", description="The new name")

    @field_serializer("castle_name")
    def _encoded_name(self, value: str) -> str:
        return encode_json_text(value)


class RenameCastleResponse(BaseResponse):
    """
    Response to castle rename.

    Command: arc
    Payload: {"CID": castle_id, "KID": kingdom_id, "P": 0 or 1}

    Client: ``ARCCommand.executeCommand`` (bundle line 124966), which looks the
    castle up by CID and KID, and joins a kingdom castle's area again after a
    first naming (P 0)
    """

    command = "arc"

    castle_id: int = Field(alias="CID", description="The renamed castle")
    kingdom_id: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")
    is_rename: int = Field(alias="P", default=1, description="1 for a rename, 0 for a first naming")


# =============================================================================
# RST - Relocate Castle
# =============================================================================


class RelocateCastleRequest(BaseRequest):
    """
    Start a relocation to a new position.

    Command: rst
    Payload: {"PX": x, "PY": y}

    The client sends only the position: no castle id and no kingdom.

    Client: ``C2SStartRelocationVO`` (bundle line 109634), sent by
    ``CastleRelocateDialog.onClick`` (bundle line 109619)
    """

    command = "rst"

    x: int = Field(alias="PX", description="Map x of the new position")
    y: int = Field(alias="PY", description="Map y of the new position")


class RelocateCastleResponse(BaseResponse):
    """
    Response to castle relocation.

    Command: rst
    """

    command = "rst"


# =============================================================================
# GRC - Get Resources
# =============================================================================


class GetResourcesRequest(BaseRequest):
    """
    Get current resources for a castle.

    Command: grc
    Payload: {"CID": castle_id}
    """

    command = "grc"

    castle_id: int = Field(
        alias="CID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )


class GetResourcesResponse(BaseResponse):
    """
    Response containing castle resources.

    Command: grc
    """

    command = "grc"

    resources: ResourceAmount | None = Field(alias="R", default=None)
    storage_capacity: ResourceAmount | None = Field(alias="SC", default=None)


# =============================================================================
# GPA - Get Production
# =============================================================================


class GetProductionRequest(BaseRequest):
    """
    Get production rates for a castle.

    Command: gpa
    Payload: {"CID": castle_id}
    """

    command = "gpa"

    castle_id: int = Field(
        alias="CID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )


class ProductionRates(BaseResponse):
    """Production rates per hour."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    wood: float = Field(alias="W", default=0.0)
    stone: float = Field(alias="S", default=0.0)
    food: float = Field(alias="F", default=0.0)
    coins: float = Field(alias="C", default=0.0)


class GetProductionResponse(BaseResponse):
    """
    Response containing production rates.

    Command: gpa
    """

    command = "gpa"

    production: ProductionRates | None = Field(alias="P", default=None)
    consumption: ProductionRates | None = Field(alias="CO", default=None)


__all__ = [
    # GCL - Get Castles
    "GetCastlesRequest",
    "GetCastlesResponse",
    "PlayerCastle",
    "CastleInfo",
    # DCL - Detailed Castle
    "GetDetailedCastleRequest",
    "GetDetailedCastleResponse",
    "DetailedCastleInfo",
    "CastleProductionArea",
    "ResourceProduction",
    "StorageCapacity",
    "ProductionBonus",
    "SafeAmount",
    # JCA - Select Castle
    "SelectCastleRequest",
    "SelectCastleResponse",
    # ARC - Rename Castle
    "RenameCastleRequest",
    "RenameCastleResponse",
    # RST - Relocate Castle
    "RelocateCastleRequest",
    "RelocateCastleResponse",
    # GRC - Get Resources
    "GetResourcesRequest",
    "GetResourcesResponse",
    # GPA - Get Production
    "GetProductionRequest",
    "GetProductionResponse",
    "ProductionRates",
]
