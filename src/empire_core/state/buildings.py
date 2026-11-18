"""The joined castle's placed objects, by object id: whole from jaa, gca and ebe, row by row from the pushes and
replies that carry one, and removed by sob, sbd and etc."""

import time
from collections.abc import Callable, Iterable
from typing import Any, NamedTuple

from pydantic import BaseModel

from empire_core.castle.models.buildings import (
    BuildResponse,
    CollectExtensionGiftResponse,
    DestroyBuildingResponse,
    FastCompleteResponse,
    MoveBuildingResponse,
    RepairAllResponse,
    RepairBuildingResponse,
    SellBuildingResponse,
    UpgradeBuildingResponse,
    UpgradeWallResponse,
)
from empire_core.castle.models.districts import MoveToDistrictResponse, RemoveFromDistrictResponse
from empire_core.castle.models.objects import BuildingRow, CarriedCastleBuildings, CastleBuildings
from empire_core.castle.models.storage import PlaceStoredDecorationResponse, StoreBuildingResponse
from empire_core.castle.models.updates import BuildingChanged, BuildingEfficiencyChanged, DamagedBuildings
from empire_core.enums import GGEError
from empire_core.state.base import StateBase, read_section
from empire_core.state.models import PlacedBuilding

_SUCCESS = frozenset({GGEError.ALL_OK})
# EMOCommand, MDECommand and RDECommand also read a failed move's reply: the building where it stayed
_MOVED_OR_NOT = frozenset({GGEError.ALL_OK, GGEError.MOVE_FAILED})


class _Carrier(NamedTuple):
    model: type[BaseModel]
    rows: Callable[[Any], Iterable[BuildingRow | None]] = lambda _: ()
    removed: Callable[[Any], int | None] = lambda _: None
    applied_on: frozenset[GGEError] = _SUCCESS


def _one(reply: Any) -> tuple[BuildingRow | None]:
    return (reply.building,)


def _object_id(reply: Any) -> int:
    return reply.object_id


# Client: AreaDataUpdater (split.js lines 658985-659186), whose parsers hand each row to
# IsoUpdaterData.updateObjectInfo or updateMultipleObjectInfos and each removal to removeObjectByObjectId
_CARRIERS: dict[str, _Carrier] = {
    # GCACommand, parseEBE: parseGCA; a jaa's castle is applied with the join it starts
    "gca": _Carrier(CarriedCastleBuildings),
    "ebe": _Carrier(CarriedCastleBuildings),
    # parseGCB, parseGDB, parseIRA: B; parseEUP: O
    "gcb": _Carrier(BuildingEfficiencyChanged, lambda push: push.buildings),
    "gdb": _Carrier(DamagedBuildings, lambda push: push.buildings),
    "ira": _Carrier(RepairAllResponse, lambda reply: reply.buildings),
    "eup": _Carrier(UpgradeBuildingResponse, lambda reply: reply.buildings),
    # parseEGO, parseEDO: the payload's O; parseFCO, parseRBU: O; parseEBU, parseNewIsoObject: NO; parseEMO: MO
    "ego": _Carrier(BuildingChanged, _one),
    "edo": _Carrier(DestroyBuildingResponse, _one),
    "fco": _Carrier(FastCompleteResponse, _one),
    "rbu": _Carrier(RepairBuildingResponse, _one),
    "ebu": _Carrier(BuildResponse, _one),
    "pio": _Carrier(PlaceStoredDecorationResponse, _one),
    "emo": _Carrier(MoveBuildingResponse, _one, applied_on=_MOVED_OR_NOT),
    "mde": _Carrier(MoveToDistrictResponse, _one, applied_on=_MOVED_OR_NOT),
    "rde": _Carrier(RemoveFromDistrictResponse, _one, applied_on=_MOVED_OR_NOT),
    # parseEUD re-lays the defence group's positions from the castle's shape first, which changes no row; then N
    "eud": _Carrier(UpgradeWallResponse, _one),
    # parseSOB, parseSBD, parseETC: OID
    "sob": _Carrier(StoreBuildingResponse, removed=_object_id),
    "sbd": _Carrier(SellBuildingResponse, removed=_object_id),
    "etc": _Carrier(CollectExtensionGiftResponse, removed=_object_id),
}

BUILDING_CARRIERS = frozenset(_CARRIERS)


class BuildingsState(StateBase):
    def _apply_building_carrier(self, cmd_id: str, data: Any, error_code: int) -> None:
        """Apply what a push or reply carries to the joined castle's placed objects.

        A whole castle replaces them while an area is joined; a row replaces or adds the object of its id, as the
        client does for an id of 0 or more; a removal drops the id. Rows and removals wait for a whole castle.

        Client: ``IsoUpdaterData.updateObjectInfo``, ``updateMultipleObjectInfos``, ``removeObjectByObjectId``
        (split.js lines 654563, 654550, 654621), ``IsoUpdaterData.parseGCA`` (split.js line 654737);
        ``IsoCommandPackageObjectUpdateInfo.createCommandList`` (split.js line 655236) skips a negative id
        """
        carrier = _CARRIERS[cmd_id]
        if GGEError.from_code(error_code) not in carrier.applied_on:
            return
        reply = read_section(carrier.model, data, f"the joined castle's objects in a {cmd_id}")
        if reply is None:
            return
        if isinstance(reply, BuildingChanged) and reply.area_booster is not None:
            self._apply_area_booster(reply.area_booster)
        if isinstance(reply, CarriedCastleBuildings):
            if reply.buildings is not None and self.joined_area is not None:
                self._replace_buildings(reply.buildings)
            return
        if self.buildings is None:
            return
        held = dict(self.buildings)
        now = time.time()
        for row in carrier.rows(reply):
            if row is not None and row.object_id >= 0:
                held[row.object_id] = PlacedBuilding(row=row, received_at=now)
        if (object_id := carrier.removed(reply)) is not None:
            held.pop(object_id, None)
        self.buildings = held

    def _replace_buildings(self, castle: CastleBuildings | None) -> None:
        """Start the joined castle's objects over from a whole castle; None when it has no readable block.

        Client: ``IsoUpdaterData.parseGCA`` (split.js line 654737) destroys every group before parsing the block
        """
        now = time.time()
        self.buildings = (
            None
            if castle is None
            else {row.object_id: PlacedBuilding(row=row, received_at=now) for row in castle.all_objects()}
        )

    def get_buildings(self) -> dict[int, PlacedBuilding] | None:
        """The joined castle's placed objects by object id, each as the last packet that carried its row sent it;
        None before a join, after a map read and after a join whose reply had no buildings."""
        with self._lock:
            return None if self.buildings is None else dict(self.buildings)
