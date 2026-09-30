"""Detailed castle info and the production area block.

Commands:
- dcl: Get detailed castle info
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator

from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse
from empire_core.protocol.js import js_int, js_number, js_truthy

from .castles import _kingdom_entries

# =============================================================================
# DCL - Get Detailed Castle Info
# =============================================================================


class GetDetailedCastleRequest(BaseRequest):
    """
    Get resources, units and production data for every castle the player owns.

    Command: dcl
    Payload: {}

    The client sends ``{"CD": 1}``, or ``{"CD": 0}`` from some dialogs; what
    ``CD`` selects is not traced. The server lists every castle for ``{}``.

    Client: ``C2SGetDetailedCastleListVO`` (bundle line 7922)
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


class _ProductionAreaSection(BasePayload):
    """A per-resource slice of a block; validated from the whole block."""

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
    """
    The block's ``SAFE_<key>`` amounts per resource.

    The server sends them, but the client never reads them, so what they
    measure is not confirmed.
    """

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

_INT_AREA_KEYS = (
    "population",
    "neutral_deco_points",
    "sickness",
    "riot",
    "guards",
    "build_speed_percent",
    "unit_capacity",
    "auxiliary_capacity",
    "morale",
    "food_consumption_reduction_percent",
    "mead_consumption_reduction_percent",
    "beef_consumption_reduction_percent",
)


class CastleProductionArea(BasePayload):
    """
    A castle's production area, the ``gpa`` block.

    The per-resource sections are aliased key by key and validated from the
    same block, so each wire key appears once in this module. The whole-number
    fields are read through ``int()``, as the client reads them.

    Client: ``AreaDataUpdater.parseGPA`` (bundle line 131506),
    ``AreaDataCommonInfo.parseGPA`` (bundle line 130993),
    ``AreaDataStorageItem.parseGPA`` (bundle line 131380),
    ``AreaDataMorality.parseGPA`` (bundle line 131272),
    ``DetailedCastleVO.parseGpaData`` (bundle line 140979)
    """

    population: int = Field(alias="P", default=0, description="Population")
    neutral_deco_points: int = Field(alias="NDP", default=0, description="Decoration points")
    sickness: int = Field(alias="S", default=0, description="Sickness")
    riot: int = Field(alias="R", default=0, description="Riot")
    guards: int = Field(alias="GRD", default=0, description="Guards, before research boosts")
    build_speed_percent: int = Field(alias="BDB", default=100, description="Construction speed in percent")
    metropolis_food_bonus: float = Field(alias="MP", default=0.0, description="A metropolis's food production bonus")
    unit_capacity: int = Field(alias="US", default=0, description="How many units the castle holds")
    auxiliary_capacity: int = Field(alias="AUS", default=0, description="How many auxiliaries the castle holds")
    morale: int = Field(alias="M", default=0, description="Morale")
    faction_buff: float = Field(
        alias="RFPPA",
        default=0.0,
        description="Faction strength balance, 0 to 1: below 0.5 boosts red faction morale, above 0.5 blue",
    )
    food_consumption_delta: float = Field(alias="DFC", default=0.0, description="Food consumption per hour, times 10")
    food_consumption_reduction_percent: int = Field(
        alias="FCR", default=100, description="Food consumption in percent of the base"
    )
    mead_consumption_delta: float = Field(
        alias="DMEADC", default=0.0, description="Mead consumption per hour, times 10"
    )
    mead_consumption_reduction_percent: int = Field(
        alias="MEADCR", default=100, description="Mead consumption in percent of the base"
    )
    beef_consumption_delta: float = Field(
        alias="DBEEFC", default=0.0, description="Beef consumption per hour, times 10"
    )
    beef_consumption_reduction_percent: int = Field(
        alias="BEEFCR", default=100, description="Beef consumption in percent of the base"
    )
    barracks_speed: float = Field(alias="RS1", default=0.0, description="Barracks production speed")
    workshop_speed: float = Field(alias="RS2", default=0.0, description="Siege workshop production speed")
    defense_workshop_speed: float = Field(alias="RS3", default=0.0, description="Defense workshop production speed")
    hospital_speed: float = Field(alias="RSH", default=0.0, description="Hospital healing speed")
    production: ResourceProduction = Field(default_factory=ResourceProduction, description="Production per hour")
    storage_capacity: StorageCapacity = Field(default_factory=StorageCapacity, description="Storage capacity")
    production_bonus_percent: ProductionBonus = Field(
        default_factory=ProductionBonus, description="Production bonus in percent, 100 for none"
    )
    safe_amount: SafeAmount = Field(default_factory=SafeAmount, description="The block's SAFE_<key> amounts")

    _whole_numbers = field_validator(*_INT_AREA_KEYS, mode="before")(js_int)

    @field_validator("faction_buff", mode="before")
    @classmethod
    def _number(cls, value: Any) -> float:
        return js_number(value)

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
    """
    One castle's entry in the detailed castle list.

    The client reads ``AID``, ``D``, the 11 resources (through ``int()``
    wherever it uses them), ``MC``, ``AC``, ``SHI``, ``gpa`` and the flags
    ``B``, ``WS``, ``DW`` and ``H`` (through ``Boolean()``); ``KID`` is the
    kingdom block the entry is listed under. The server also sends ``OGT``,
    ``AOT``, ``HI`` and ``TU``, which the client does not read from this reply:
    it reads hospital and travelling units from ``gui``.

    Client: ``CastleUserCastleListDetailed.parseData`` (bundle line 140906),
    ``DetailedCastleVO.parseData`` (bundle line 140973)
    """

    castle_id: int = Field(alias="AID", description="The castle's object id")
    kingdom_id: int = Field(alias="KID", default=0, description="The castle's kingdom")
    wood: int = Field(alias="W", default=0, description="Wood in stock")
    stone: int = Field(alias="S", default=0, description="Stone in stock")
    food: int = Field(alias="F", default=0, description="Food in stock")
    coal: int = Field(alias="C", default=0, description="Coal in stock")
    oil: int = Field(alias="O", default=0, description="Oil in stock")
    glass: int = Field(alias="G", default=0, description="Glass in stock")
    iron: int = Field(alias="I", default=0, description="Iron in stock")
    aquamarine: int = Field(alias="A", default=0, description="Aquamarine in stock")
    honey: int = Field(alias="HONEY", default=0, description="Honey in stock")
    mead: int = Field(alias="MEAD", default=0, description="Mead in stock")
    beef: int = Field(alias="BEEF", default=0, description="Beef in stock")
    defense_value: int = Field(alias="D", default=0, description="Defense value")
    has_barracks: bool = Field(alias="B", default=False, description="Whether the castle has barracks")
    has_siege_workshop: bool = Field(alias="WS", default=False, description="Whether it has a siege workshop")
    has_defense_workshop: bool = Field(alias="DW", default=False, description="Whether it has a defense workshop")
    has_hospital: bool = Field(alias="H", default=False, description="Whether it has a hospital")
    market_carriages: int = Field(alias="MC", default=0, description="The castle's market carriages")
    open_gate_seconds: int = Field(alias="OGT", default=0, description="Seconds the gate stays open")
    abandon_outpost_seconds: int = Field(
        alias="AOT", default=-1, description="Seconds until the outpost is abandoned, -1 when it is not"
    )
    raw_units: list[list[int]] = Field(
        alias="AC", default_factory=list, description="Stationed units as [wod id, count] pairs"
    )
    raw_stronghold_units: list[list[int]] = Field(
        alias="SHI", default_factory=list, description="Stronghold units as [wod id, count] pairs"
    )
    raw_hospital_units: list[list[int]] = Field(
        alias="HI", default_factory=list, description="Wounded units as [wod id, count] pairs"
    )
    raw_travelling_units: list[list[int]] = Field(
        alias="TU", default_factory=list, description="Travelling units as [wod id, count] pairs"
    )
    production_area: CastleProductionArea | None = Field(
        alias="gpa", default=None, description="The castle's production area; None when the entry has none"
    )

    _whole_numbers = field_validator("castle_id", "defense_value", "market_carriages", *_RESOURCE_KEYS, mode="before")(
        js_int
    )
    _flags = field_validator(
        "has_barracks", "has_siege_workshop", "has_defense_workshop", "has_hospital", mode="before"
    )(js_truthy)

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


__all__ = [
    "GetDetailedCastleRequest",
    "GetDetailedCastleResponse",
    "DetailedCastleInfo",
    "CastleProductionArea",
    "ResourceProduction",
    "StorageCapacity",
    "ProductionBonus",
    "SafeAmount",
]
