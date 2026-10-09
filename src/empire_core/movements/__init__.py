"""Army movements."""

from typing import TYPE_CHECKING

from empire_core.enums import AttackAdvisorType, AutoSkipCooldownType, MapItemType, MovementType, SpyType
from empire_core.utils.lazy import lazy_exports

from .models import (
    CancelMovementRequest,
    CancelMovementResponse,
    GetMovementsRequest,
    GetMovementsResponse,
    MovementArea,
    MovementArmy,
    MovementMarket,
    MovementOwner,
    MovementRecord,
    MovementSpy,
    MovementUnitInfo,
    MovementWrapper,
)
from .service import MovementsService
from .tracked import Movement, MovementResources

if TYPE_CHECKING:
    from empire_core.gamedata import Horse, Title, Tool, Unit

__all__ = [
    "CancelMovementRequest",
    "CancelMovementResponse",
    "GetMovementsRequest",
    "GetMovementsResponse",
    "MovementArea",
    "MovementArmy",
    "MovementMarket",
    "MovementOwner",
    "MovementRecord",
    "MovementSpy",
    "MovementUnitInfo",
    "MovementWrapper",
    "Movement",
    "MovementResources",
    "MovementType",
    "AttackAdvisorType",
    "MovementsService",
    "AutoSkipCooldownType",
    "MapItemType",
    "SpyType",
    "Horse",
    "Title",
    "Tool",
    "Unit",
]


if not TYPE_CHECKING:
    __getattr__ = lazy_exports(__name__, "empire_core.gamedata.ids", ("Horse", "Title", "Tool", "Unit"))
