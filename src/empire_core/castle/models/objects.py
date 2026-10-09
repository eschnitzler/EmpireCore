"""A castle's buildings and its construction queue.

Commands:
- scl: Show the construction list
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from empire_core.enums import BuildingState
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, read_or_none, readable_list
from empire_core.protocol.js import ClientInt, ClientNumber, js_int, js_number, js_number_or_none, js_truthy

from .details import _ProductionAreaSection

if TYPE_CHECKING:
    from empire_core.gamedata import ConstructionItem

logger = logging.getLogger(__name__)

# The row index the upgrade target sits at, past the wod id.
_UPGRADE_TARGET_INDEX = 16
_FIRST_BUILDING_INDEX = 5

_B = TypeVar("_B", bound=BaseModel)


def block_or_none(model: type[_B], value: Any) -> _B | None:
    """A reply's block read as ``model``, or None when it is not an object or cannot be read."""
    if isinstance(value, model):
        return value
    if not isinstance(value, dict):
        return None
    return read_or_none(model.model_validate, value, warn=logger, what=f"a {model.__name__} block")


# ConstructionConst (dll line 18983)
FREE_SLOT = -1
LOCKED_SLOT = -2


def _building_state(value: Any) -> BuildingState:
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            return BuildingState(value)
        except ValueError:
            pass
    return BuildingState.INITIAL


class BuildingRow(BasePayload):
    """
    One placed object in a castle: a building, wall, gate, tower, ground or
    fixed object, read by field position.

    - 0 wod id, 1 object id, 2 x, 3 y, 4 rotation (1 for a building inside a
      district); each through ``int()``
    - 5 seconds of the running construction done, 6 state, 7 hit points, 8 the
      construction boost at the start, times 100, 9 efficiency, 10 damage type
      (0 when absent)
    - 11 onwards: values the building's type reads, such as a unit-producing
      building's production speed
    - 14 the district the building sits in, 15 its slot there
    - 16 the upgrade target's wod id, -1 when absent

    A row may come wrapped as ``{"O": [...]}``. Where the client reads an
    absent 1 to 4, 14 or 15 as 0, so does this. Fields 5 to 10 are read only
    by the building classes (``ABasicBuildingVO``), which the client picks by
    the wod id's group and name; this reads them whenever the row reaches
    index 5 and leaves them None otherwise, which is not verified to match
    the client's class for every wod id.

    Client: ``IsoHelperData.createIsoObjectVOByServer`` (bundle line 63049),
    ``AVisualVO.parseServerObject`` (bundle line 17801),
    ``AIsoObjectVO.parseServerObject`` (bundle line 11265),
    ``ABasicBuildingVO.parseServerObject`` (bundle lines 17866-17868, index 5 is ``_constructionCompletionInSec``),
    ``AUnitProductionBuildingVO.parseServerObject`` (bundle line 36254)
    """

    wod_id: int = Field(description="The building type's wod id")
    object_id: int = Field(default=0, description="The object's id in its castle, which building commands name")
    x: int = Field(default=0, description="Castle grid x")
    y: int = Field(default=0, description="Castle grid y")
    rotation: int = Field(default=0, description="Rotation")
    construction_completed_seconds: int | None = Field(
        default=None, description="Seconds of the running construction done when the row was sent"
    )
    state: BuildingState | None = Field(default=None, description="What the building is doing")
    hit_points: int | None = Field(default=None, description="Hit points, 100 when undamaged")
    construction_boost_at_start: float | None = Field(
        default=None, description="The construction speed boost when the construction started, as a factor"
    )
    efficiency: int | None = Field(default=None, description="Efficiency in percent")
    damage_type: int | None = Field(default=None, description="Damage type, 0 for none")
    district_id: int = Field(default=0, description="Object id of the district the building sits in, 0 for none")
    district_slot_id: int = Field(default=0, description="The building's slot in its district")
    upgrade_target_wod_id: int = Field(default=-1, description="Wod id the building is upgrading to, -1 for none")

    @property
    def is_in_district(self) -> bool:
        """Whether the building sits in a district."""
        return self.district_id > 0

    @classmethod
    def from_list(cls, data: Any) -> BuildingRow:
        """
        Read a building row, bare or wrapped as ``{"O": [...]}``.

        Raises:
            ValueError: It is not a row.
        """
        row = data.get("O") if isinstance(data, dict) else data
        if not isinstance(row, list) or not row:
            raise ValueError(f"Not a building row: {data!r:.200}")

        def at(index: int) -> Any:
            return row[index] if len(row) > index else None

        district_id = js_int(at(14))
        values: dict[str, Any] = {
            "wod_id": js_int(row[0]),
            "object_id": js_int(at(1)),
            "x": js_int(at(2)),
            "y": js_int(at(3)),
            "rotation": 1 if district_id > 0 else js_int(at(4)),
            "district_id": district_id,
            "district_slot_id": js_int(at(15)),
            "upgrade_target_wod_id": js_int(row[_UPGRADE_TARGET_INDEX]) if len(row) > _UPGRADE_TARGET_INDEX else -1,
        }
        if len(row) > _FIRST_BUILDING_INDEX:
            values.update(
                construction_completed_seconds=js_int(at(5)),
                state=_building_state(at(6)),
                hit_points=js_int(at(7)),
                construction_boost_at_start=js_number(at(8)) / 100,
                efficiency=js_int(at(9)),
                damage_type=js_int(row[10]) if len(row) > 10 else 0,
            )
        return cls(**values)


def building_or_none(value: Any) -> BuildingRow | None:
    """A reply's building row, or None when it has none or it cannot be read."""
    if value is None or isinstance(value, BuildingRow):
        return value
    try:
        return BuildingRow.from_list(value)
    except (ValueError, ValidationError):
        logger.debug(f"Unreadable building row {value!r:.200}")
        return None


def building_rows(value: Any) -> list[BuildingRow]:
    """
    Each readable row of a list of building rows.

    The client throws on a null or malformed entry; here one costs only itself.
    """
    if not isinstance(value, list):
        return []
    rows = [building_or_none(entry) for entry in value]
    return [row for row in rows if row is not None]


class ConstructionSlot(BasePayload):
    """
    One construction slot of a castle.

    Client: ``ConstructionSlotVO`` (bundle lines 131242-131250), filled by
    ``AreaDataConstructionList.parseList`` (bundle line 131170)
    """

    model_config = ConfigDict(frozen=True)

    position: int = Field(description="The slot's place in the list, from 0")
    object_id: int = Field(
        description="Object id of the building under construction there; FREE_SLOT (-1) or LOCKED_SLOT (-2)"
    )
    is_waiting: bool = Field(
        default=False, description="A waiting slot: its position is at or past the castle's construction slots"
    )

    @property
    def is_free(self) -> bool:
        """Whether nothing is being built there (``ConstructionConst.SLOTSTATEUNLOCKED``)."""
        return self.object_id == FREE_SLOT

    @property
    def is_locked(self) -> bool:
        """Whether the slot is still locked (``ConstructionConst.SLOTSTATELOCKED``)."""
        return self.object_id == LOCKED_SLOT


class ConstructionList(BasePayload):
    """
    A castle's construction slots, the ``scl`` block.

    Client: ``AreaDataConstructionList.parseSCL`` / ``parseList`` (bundle
    lines 131173, 131166), which read each ``OIDL`` entry through ``int()``
    into a ``ConstructionSlotVO`` at its position
    """

    slots: tuple[ConstructionSlot, ...] = Field(alias="OIDL", default=(), description="The slots, in order")
    slot_count: int | float = Field(alias="SSC", default=1, description="Number of construction slots")

    @model_validator(mode="before")
    @classmethod
    def _slots(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # e.SSC ? e.SSC : 1, kept as a number
        sent_count = data.get("SSC", data.get("slot_count"))
        count = js_number_or_none(sent_count) if js_truthy(sent_count) else None
        count = 1 if count is None else count
        ids = data.get("OIDL", data.get("slots"))
        if not isinstance(ids, list | tuple):
            ids = []
        slots = [
            entry
            if isinstance(entry, ConstructionSlot | dict)
            else {"position": position, "object_id": js_int(entry), "is_waiting": position >= count}
            for position, entry in enumerate(ids)
        ]
        rest = {key: value for key, value in data.items() if key not in ("OIDL", "slots", "SSC", "slot_count")}
        return {**rest, "OIDL": slots, "SSC": count}

    @property
    def free_slots(self) -> int:
        """Number of free slots."""
        return sum(1 for slot in self.slots if slot.is_free)

    @property
    def building_object_ids(self) -> list[int]:
        """Object ids of the buildings under construction."""
        return [slot.object_id for slot in self.slots if not (slot.is_free or slot.is_locked)]


class FieldEfficiency(_ProductionAreaSection):
    """Resource field efficiency per resource (``RA<key>``)."""

    wood: ClientInt = Field(alias="RAW", default=0)
    stone: ClientInt = Field(alias="RAS", default=0)
    food: ClientInt = Field(alias="RAF", default=0)
    coal: ClientInt = Field(alias="RAC", default=0)
    oil: ClientInt = Field(alias="RAO", default=0)
    glass: ClientInt = Field(alias="RAG", default=0)
    iron: ClientInt = Field(alias="RAI", default=0)
    aquamarine: ClientInt = Field(alias="RAA", default=0)
    honey: ClientInt = Field(alias="RAHONEY", default=0)
    mead: ClientInt = Field(alias="RAMEAD", default=0)
    beef: ClientInt = Field(alias="RABEEF", default=0)


_BUILDING_GROUPS = ("BD", "D", "G", "T", "BG", "FP")


class PlacedConstructionItem(BasePayload):
    """
    A construction item on a building: one ``CIL`` entry.

    Client: ``ABasicBuildingVO.parseConstructionItems`` (bundle lines 18005-18010), which puts the item at
    its slot type's first index plus ``int(S)`` and gives a temporary item the ``RS`` seconds left
    """

    construction_item_id: EnumOrInt["ConstructionItem"] = Field(alias="CID", description="The construction item")
    slot: ClientInt = Field(alias="S", default=0, description="Its slot among the slots of its item's slot type")
    remaining_seconds: ClientNumber = Field(
        alias="RS", default=0, description="Seconds a temporary item has left; 0 for a permanent one"
    )


class BuildingConstructionItems(BasePayload):
    """
    The construction items on one building: one ``CI`` entry.

    Client: ``ABasicBuildingVO.parseConstructionItems`` (bundle lines 18000-18006), which takes the entry
    whose ``OID`` is the building's
    """

    object_id: ClientInt = Field(alias="OID", description="The building's object id")
    items: tuple[PlacedConstructionItem, ...] = Field(alias="CIL", default=(), description="Its construction items")

    @field_validator("items", mode="before")
    @classmethod
    def _readable(cls, value: Any) -> Any:
        return readable_list(PlacedConstructionItem, value, accept=lambda entry: isinstance(entry, dict))


class CastleBuildings(BasePayload):
    """
    A castle's buildings, the ``gca`` block.

    The block's ``A`` (the castle's map row) and ``O`` (its owner) are kept as sent.

    Client: ``AreaDataUpdater.parseGCA`` (bundle line 131497),
    ``IsoDataObjectGroupInnerBuilding.parseGCA`` (bundle line 80810),
    ``IsoDataObjectGroupDefence.parseGCA`` (bundle line 80220),
    ``IsoDataObjectGroupGround.parseGCA`` (bundle line 80771),
    ``IsoDataObjectGroupFixedPosition.parseGCA`` (bundle line 80743),
    ``AreaDataStorageItem.parseGCA`` (bundle line 131381), ``AreaDataUpdater.parseConstructionItems``
    (bundle line 131524)
    """

    buildings: list[BuildingRow] = Field(alias="BD", default_factory=list, description="Buildings inside the walls")
    walls: list[BuildingRow] = Field(alias="D", default_factory=list, description="The wall and the moat")
    gates: list[BuildingRow] = Field(alias="G", default_factory=list, description="The gate")
    towers: list[BuildingRow] = Field(alias="T", default_factory=list, description="The towers")
    grounds: list[BuildingRow] = Field(alias="BG", default_factory=list, description="Ground tiles and expansions")
    fixed_positions: list[BuildingRow] = Field(
        alias="FP", default_factory=list, description="Objects at fixed positions"
    )
    construction_list: ConstructionList | None = Field(
        alias="scl", default=None, description="The construction slots; None when the block has none"
    )
    construction_items: tuple[BuildingConstructionItems, ...] = Field(
        alias="CI", default=(), description="The construction items on each building that has any"
    )
    field_efficiency: FieldEfficiency = Field(
        default_factory=FieldEfficiency, description="Resource field efficiency per resource"
    )

    @field_validator(*("buildings", "walls", "gates", "towers", "grounds", "fixed_positions"), mode="before")
    @classmethod
    def _rows(cls, value: Any) -> list[BuildingRow]:
        return building_rows(value)

    @field_validator("construction_list", mode="before")
    @classmethod
    def _construction_list(cls, value: Any) -> ConstructionList | None:
        return block_or_none(ConstructionList, value)

    @field_validator("construction_items", mode="before")
    @classmethod
    def _construction_items(cls, value: Any) -> Any:
        return readable_list(BuildingConstructionItems, value, accept=lambda entry: isinstance(entry, dict))

    @model_validator(mode="before")
    @classmethod
    def _efficiency_sees_the_block(cls, data: Any) -> Any:
        if isinstance(data, dict) and "field_efficiency" not in data:
            data = {**data, "field_efficiency": data}
        return data

    def all_objects(self) -> list[BuildingRow]:
        """Every object in the castle, buildings first."""
        return [*self.buildings, *self.walls, *self.gates, *self.towers, *self.grounds, *self.fixed_positions]

    def find(self, object_id: int) -> BuildingRow | None:
        """The object with this id, or None."""
        return next((row for row in self.all_objects() if row.object_id == object_id), None)


# =============================================================================
# SCL - Show Construction List
# =============================================================================


class ShowConstructionListRequest(BaseRequest):
    """
    Get the joined castle's construction slots.

    Command: scl
    Payload: {}

    Client: ``C2SShowConstructionListVO`` (bundle line 63754)
    """

    command = "scl"


class ShowConstructionListResponse(ConstructionList, BaseResponse):
    """
    The joined castle's construction slots.

    Command: scl
    Payload: {"OIDL": [object_id, ...], "SSC": slot_count}

    Client: ``SCLCommand.executeCommand`` (bundle line 123374)
    """

    command = "scl"


__all__ = [
    "FREE_SLOT",
    "LOCKED_SLOT",
    "BuildingRow",
    "BuildingConstructionItems",
    "CastleBuildings",
    "PlacedConstructionItem",
    "ConstructionList",
    "FieldEfficiency",
    "ShowConstructionListRequest",
    "ShowConstructionListResponse",
    "building_or_none",
    "building_rows",
]
