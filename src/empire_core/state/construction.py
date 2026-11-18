"""The joined castle's construction slots (scl), from the replies and pushes that carry them."""

from typing import Any

from empire_core.castle.models.buildings import (
    BuildResponse,
    BuyExtensionResponse,
    DestroyBuildingResponse,
    RepairBuildingResponse,
    TimeSkipBuildingResponse,
    UpgradeBuildingResponse,
)
from empire_core.castle.models.objects import ConstructionList, ShowConstructionListResponse
from empire_core.castle.models.updates import BuildingChanged
from empire_core.state.base import StateBase, read_section

# Replies and pushes whose scl AreaDataUpdater.parseSCL (split.js line 659010) applies, on success only:
# EBUCommand, EUPCommand, EDOCommand, RBUCommand, EBECommand, EGOCommand through parseEBU, parseEUP, parseEDO,
# parseRBU, parseEBE, parseEGO (split.js lines 659101, 659134, 659109, 659068, 659095, 659116), MSBCommand and
# SCLCommand (split.js lines 638086, 629997). The jaa and gca blocks are applied by their own handlers.
_CARRIERS: dict[
    str,
    type[
        BuildResponse
        | UpgradeBuildingResponse
        | DestroyBuildingResponse
        | RepairBuildingResponse
        | TimeSkipBuildingResponse
        | BuyExtensionResponse
        | BuildingChanged
        | ShowConstructionListResponse
    ],
] = {
    "ebu": BuildResponse,
    "eup": UpgradeBuildingResponse,
    "edo": DestroyBuildingResponse,
    "rbu": RepairBuildingResponse,
    "msb": TimeSkipBuildingResponse,
    "ebe": BuyExtensionResponse,
    "ego": BuildingChanged,
    "scl": ShowConstructionListResponse,
}

CONSTRUCTION_LIST_REPLIES = frozenset(_CARRIERS)


class ConstructionState(StateBase):
    """
    The joined castle's construction slots.

    A join's reply replaces them, and a map read or a lost session drops them. The client keeps them on its
    active area until the next join; the library drops them deliberately when the session leaves the castle.
    """

    def _apply_carried_construction_list(self, command: str, data: Any) -> None:
        """Keep the construction slots a successful carrier reply or push sent; one without any leaves them.

        Client: ``AreaDataUpdater.parseSCL`` (split.js line 659010), ``AreaDataConstructionList.parseSCL``
        (split.js line 657793); ``parseEBE`` (split.js line 659095) applies its ``gca`` block's slots, then its own
        """
        if not isinstance(data, dict) or "raw" in data or self.joined_area is None:
            return
        reply = read_section(_CARRIERS[command], data, "a reply's construction slots")
        carried: ConstructionList | None
        match reply:
            case None:
                return
            case ShowConstructionListResponse():
                carried = ConstructionList(slots=reply.slots, slot_count=reply.slot_count)
            case BuyExtensionResponse(construction_list=None, castle_buildings=buildings) if buildings is not None:
                carried = buildings.construction_list
            case _:
                carried = reply.construction_list
        if carried is not None:
            self.construction_list = carried

    def get_construction_list(self) -> ConstructionList | None:
        """The joined castle's construction slots; None before a join, after a map read, or when the join sent
        none."""
        with self._lock:
            return None if self.construction_list is None else self.construction_list.model_copy(deep=True)
