"""Castle defense."""

from typing import TYPE_CHECKING

from empire_core.enums import Kingdom
from empire_core.utils.lazy import lazy_exports

from .models import (
    ChangeKeepDefenseRequest,
    ChangeMoatDefenseRequest,
    ChangeWallDefenseRequest,
    GetDefenseRequest,
    GetDefenseResponse,
    GetSupportDefenseRequest,
    GetSupportDefenseResponse,
    KeepDefense,
    MoatDefense,
    WallDefense,
    WallSection,
    WallSectionSetup,
)
from .service import DefenseService

if TYPE_CHECKING:
    from empire_core.gamedata import Tool, Unit

__all__ = [
    "GetDefenseRequest",
    "GetDefenseResponse",
    "WallSection",
    "WallSectionSetup",
    "WallDefense",
    "KeepDefense",
    "MoatDefense",
    "ChangeKeepDefenseRequest",
    "ChangeWallDefenseRequest",
    "ChangeMoatDefenseRequest",
    "GetSupportDefenseRequest",
    "GetSupportDefenseResponse",
    "DefenseService",
    "Kingdom",
    "Tool",
    "Unit",
]


if not TYPE_CHECKING:
    __getattr__ = lazy_exports(__name__, "empire_core.gamedata.ids", ("Tool", "Unit"))
