"""Army movements."""

from typing import TYPE_CHECKING

from empire_core.enums import (
    AttackAdvisorType,
    AutoSkipCooldownType,
    Kingdom,
    KingdomTransferType,
    MapItemType,
    MarketScope,
    MovementType,
    Resource,
    SpyType,
)
from empire_core.utils.lazy import lazy_exports

from .models import (
    CancelMovementRequest,
    CancelMovementResponse,
    CreateMarketMovementRequest,
    CreateMarketMovementResponse,
    GetMovementsRequest,
    GetMovementsResponse,
    GetTravelInfoRequest,
    GetTravelInfoResponse,
    KingdomGoodsTransferRequest,
    KingdomGoodsTransferResponse,
    KingdomUnitTransferRequest,
    KingdomUnitTransferResponse,
    MarketCastle,
    MarketInfoRequest,
    MarketInfoResponse,
    MinuteSkipKingdomTransferRequest,
    MinuteSkipKingdomTransferResponse,
    MovementArea,
    MovementArmy,
    MovementMarket,
    MovementOwner,
    MovementRecord,
    MovementSpy,
    MovementUnitInfo,
    MovementWrapper,
    SendSupportRequest,
    SendSupportResponse,
    SendTroopsRequest,
    SendTroopsResponse,
    TravelTargetArea,
    TravelUnits,
)
from .service import MovementsService
from .tracked import Movement, MovementResources

if TYPE_CHECKING:
    from empire_core.gamedata import Currency, Horse, Title, Tool, Unit

__all__ = [
    "Currency",
    "Kingdom",
    "KingdomTransferType",
    "MarketScope",
    "Resource",
    "KingdomGoodsTransferRequest",
    "KingdomGoodsTransferResponse",
    "KingdomUnitTransferRequest",
    "KingdomUnitTransferResponse",
    "MinuteSkipKingdomTransferRequest",
    "MinuteSkipKingdomTransferResponse",
    "GetTravelInfoRequest",
    "GetTravelInfoResponse",
    "TravelTargetArea",
    "TravelUnits",
    "SendSupportRequest",
    "SendSupportResponse",
    "SendTroopsRequest",
    "SendTroopsResponse",
    "CreateMarketMovementRequest",
    "CreateMarketMovementResponse",
    "MarketCastle",
    "MarketInfoRequest",
    "MarketInfoResponse",
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
    __getattr__ = lazy_exports(__name__, "empire_core.gamedata.ids", ("Currency", "Horse", "Title", "Tool", "Unit"))
