"""The army: units, production, the hospital and spy-report armies."""

from typing import TYPE_CHECKING

from empire_core.enums import Kingdom, ProductionListId, SlotType, SpyArmySection
from empire_core.utils.lazy import lazy_exports

from .models import (
    BUY_UNIT_PACKAGE_SK,
    AddedUnit,
    AttackWave,
    CancelHealRequest,
    CancelHealResponse,
    CancelProductionRequest,
    CancelProductionResponse,
    CurrentProductionSlot,
    DismissManyWoundedRequest,
    DismissUnitsRequest,
    DismissUnitsResponse,
    DismissWoundedRequest,
    DismissWoundedResponse,
    DoubleProductionSlotRequest,
    DoubleProductionSlotResponse,
    GetProductionListRequest,
    GetProductionListResponse,
    GetUnitsRequest,
    GetUnitsResponse,
    HealAllRequest,
    HealAllResponse,
    HealUnitsRequest,
    HealUnitsResponse,
    HospitalSlot,
    ProduceUnitsRequest,
    ProduceUnitsResponse,
    ProductionList,
    ProductionSlot,
    SkipHealRequest,
    SkipHealResponse,
    UnitInventory,
    WaveFlank,
    WoundedUnits,
)
from .service import ArmyService
from .spy_army import SpyArmy, SpyArmyBlock, SpyStacks

if TYPE_CHECKING:
    from empire_core.gamedata import Tool, Unit

__all__ = [
    "AttackWave",
    "WaveFlank",
    "HealUnitsRequest",
    "HealUnitsResponse",
    "CancelHealRequest",
    "CancelHealResponse",
    "SkipHealRequest",
    "SkipHealResponse",
    "DismissWoundedRequest",
    "DismissManyWoundedRequest",
    "WoundedUnits",
    "DismissWoundedResponse",
    "HealAllRequest",
    "HealAllResponse",
    "ProductionList",
    "ProductionSlot",
    "CurrentProductionSlot",
    "HospitalSlot",
    "ProduceUnitsRequest",
    "ProduceUnitsResponse",
    "AddedUnit",
    "GetProductionListRequest",
    "GetProductionListResponse",
    "DoubleProductionSlotRequest",
    "DoubleProductionSlotResponse",
    "CancelProductionRequest",
    "CancelProductionResponse",
    "BUY_UNIT_PACKAGE_SK",
    "UnitInventory",
    "GetUnitsRequest",
    "GetUnitsResponse",
    "DismissUnitsRequest",
    "DismissUnitsResponse",
    "ProductionListId",
    "SlotType",
    "ArmyService",
    "SpyArmy",
    "SpyArmySection",
    "SpyArmyBlock",
    "SpyStacks",
    "Kingdom",
    "Tool",
    "Unit",
]


if not TYPE_CHECKING:
    __getattr__ = lazy_exports(__name__, "empire_core.gamedata.ids", ("Tool", "Unit"))
