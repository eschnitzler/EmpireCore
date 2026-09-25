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
from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator

from .base import BasePayload, BaseRequest, BaseResponse, Position, ResourceAmount

logger = logging.getLogger(__name__)

# =============================================================================
# Location Types
# =============================================================================

LOCATION_TYPES = {
    0: "Empty",
    1: "Castle",
    2: "Dungeon",
    3: "Capital",
    4: "Outpost",
    7: "Treasure Dungeon",
    12: "Castle",  # Colored kingdom castle (KID 1-4)
    15: "Camp",
    22: "Metro",
    26: "Monument",
    28: "Laboratory",
}


def get_location_type_name(type_id: int) -> str:
    """Get the human-readable name for a location type."""
    return LOCATION_TYPES.get(type_id, f"Unknown ({type_id})")


# =============================================================================
# Player Castle (gcl parsed)
# =============================================================================


class PlayerCastle(BasePayload):
    """
    A castle/location from the gdi response's gcl.C[].AI[] arrays.

    AI array format (confirmed from packet examples):
    [type, x, y, location_id, owner_id, lvl1, lvl2, lvl3, lvl4, lvl5,
     name, ?, ?, ?, capturer_id_capital, capturer_id_outpost, kingdom, ...]

    Index reference:
    - 0:  castle_type (1=Castle, 3=Capital, 4=Outpost, 12=?, 15=Camp, 22=Metro)
    - 1:  x
    - 2:  y
    - 3:  location_id (area_id)
    - 4:  owner_id
    - 10: name
    - 14: capturer_id (Capital/Metro)
    - 15: capturer_id (Outpost)
    - 16: kingdom (KID)
    """

    kingdom: int = 0
    location_id: int = 0
    x: int = 0
    y: int = 0
    castle_type: int = 0
    owner_id: int = 0
    name: str = ""
    capturer_id: int = -1

    @property
    def castle_type_name(self) -> str:
        """Human-readable castle type."""
        return get_location_type_name(self.castle_type)

    @property
    def is_being_captured(self) -> bool:
        """Check if this location is currently being captured."""
        return self.capturer_id != -1

    @classmethod
    def from_list(cls, data: list, kingdom: int = 0) -> "PlayerCastle":
        """Parse from a gcl.C[].AI[] array entry."""
        if not data or len(data) < 4:
            return cls(kingdom=kingdom)

        castle_type = data[0] if len(data) > 0 else 0
        x = data[1] if len(data) > 1 else 0
        y = data[2] if len(data) > 2 else 0
        location_id = data[3] if len(data) > 3 else 0
        owner_id = data[4] if len(data) > 4 else 0
        name = data[10] if len(data) > 10 else ""

        # Capturer ID position depends on type
        type_name = get_location_type_name(castle_type)
        if type_name == "Outpost":
            capturer_id = data[15] if len(data) > 15 else -1
        elif type_name in ("Capital", "Metro"):
            capturer_id = data[14] if len(data) > 14 else -1
        else:
            capturer_id = -1

        # Kingdom can also be read from index 16 if present (overrides passed-in kingdom)
        if len(data) > 16 and isinstance(data[16], int):
            kingdom = data[16]

        return cls(
            kingdom=kingdom,
            location_id=location_id,
            x=x,
            y=y,
            castle_type=castle_type,
            owner_id=owner_id,
            name=name,
            capturer_id=capturer_id,
        )


# =============================================================================
# GCL - Get Castles List
# =============================================================================


def _kingdom_entries(section: Any) -> list[tuple[int, dict[str, Any]]]:
    """(kingdom id, entry) pairs from a ``C: [{KID, AI: [...]}]`` section."""
    pairs: list[tuple[int, dict[str, Any]]] = []
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
    """One of the player's locations: a gcl entry plus its positional row.

    An ``AI[n]`` alias is the row index the client's
    InteractiveMapobjectVO.parseAreaInfo reads; the other aliases are the
    entry keys around the row.
    """

    castle_id: int = Field(alias="AI[3]", default=0)
    castle_name: str = Field(alias="AI[10]", default="")
    x: int = Field(alias="AI[1]", default=0)
    y: int = Field(alias="AI[2]", default=0)
    kingdom_id: int = Field(alias="KID", default=0)
    castle_type: int = Field(alias="AI[0]", default=0)  # 1=castle, 3=capital, 4=outpost, 12=kingdom castle, 22=metro
    owner_id: int = Field(alias="AI[4]", default=0)
    occupier_id: int = Field(alias="AI[14|15]", default=-1)  # 14 for a capital or metro, 15 for an outpost
    keep_level: int = Field(alias="AI[5]", default=0)
    wall_level: int = Field(alias="AI[6]", default=0)
    gate_level: int = Field(alias="AI[7]", default=0)
    tower_level: int = Field(alias="AI[8]", default=0)
    moat_level: int = Field(alias="AI[9]", default=0)
    open_gate_seconds: int = Field(alias="OGT", default=0)
    open_gate_counter: int = Field(alias="OGC", default=0)
    abandon_outpost_seconds: int = Field(alias="AOT", default=-1)
    cancel_abandon_seconds: int = Field(alias="CAT", default=-1)
    no_abandon_seconds: int = Field(alias="TA", default=-1)

    @property
    def position(self) -> Position:
        """Get castle position as Position object."""
        return Position(X=self.x, Y=self.y, KID=self.kingdom_id)

    @classmethod
    def from_entry(cls, entry: dict[str, Any], kingdom: int = 0) -> CastleInfo:
        """Parse a ``gcl.C[].AI[]`` entry; its ``AI`` row shares the gdi layout."""
        row = entry["AI"]
        parsed = PlayerCastle.from_list(row, kingdom)
        fields: dict[str, Any] = {
            "castle_id": parsed.location_id,
            "castle_name": parsed.name,
            "x": parsed.x,
            "y": parsed.y,
            "kingdom_id": kingdom,
            "castle_type": parsed.castle_type,
            "owner_id": parsed.owner_id,
            "occupier_id": parsed.capturer_id,
            "keep_level": row[5],
            "wall_level": row[6],
            "gate_level": row[7],
            "tower_level": row[8],
            "moat_level": row[9],
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
        castles = []
        for kid, entry in _kingdom_entries(data.pop("C")):
            row = entry.get("AI")
            if isinstance(row, list) and len(row) == 1 and isinstance(row[0], list):
                # A row wrapped in one extra list, which the old gdi parser unwrapped; the client does not
                row = row[0]
                entry = {**entry, "AI": row}
            if not (isinstance(row, list) and len(row) > 10):
                logger.debug(f"Skipping malformed gcl row: {entry!r}")
                continue
            castles.append(CastleInfo.from_entry(entry, kid))
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
    Select/jump to a castle (makes it the active castle).

    Command: jca (acknowledged by the server as 'jaa')
    Payload: {"CID": castle_id, "KID": kingdom_id}
    """

    command = "jca"
    response_command = "jaa"

    castle_id: int = Field(alias="CID")
    kingdom_id: int = Field(alias="KID", default=0)


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
    Payload: {"CID": castle_id, "N": "new_name", "AT": castle_type, "KID": kingdom_id, "P": 1}
    Client: C2SRenameCastleVO

    ``P`` is 0 when naming a newly acquired castle and 1 for a normal rename.
    """

    command = "arc"

    castle_id: int = Field(alias="CID")
    castle_name: str = Field(alias="N")
    castle_type: int = Field(alias="AT")
    kingdom_id: int = Field(alias="KID", default=0)
    is_rename: int = Field(alias="P", default=1)


class RenameCastleResponse(BaseResponse):
    """
    Response to castle rename.

    Command: arc
    Payload: {"CID": castle_id, "KID": kingdom_id, "P": 0 or 1}
    Client: ARCCommand.executeCommand
    """

    command = "arc"

    castle_id: int = Field(alias="CID")
    kingdom_id: int = Field(alias="KID", default=0)
    is_rename: int = Field(alias="P", default=1)


# =============================================================================
# RST - Relocate Castle
# =============================================================================


class RelocateCastleRequest(BaseRequest):
    """
    Relocate a castle to new coordinates.

    Command: rst
    Payload: {"CID": castle_id, "X": x, "Y": y, "KID": kingdom_id}
    """

    command = "rst"

    castle_id: int = Field(alias="CID")
    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    kingdom_id: int = Field(alias="KID", default=0)


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

    castle_id: int = Field(alias="CID")


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

    castle_id: int = Field(alias="CID")


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
    "LOCATION_TYPES",
    "PlayerCastle",
    "get_location_type_name",
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
