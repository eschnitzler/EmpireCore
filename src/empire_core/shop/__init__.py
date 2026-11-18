"""Event shops: buying event packages at their fixed price, and how often you bought each."""

from typing import TYPE_CHECKING

from empire_core.enums import Kingdom, PackageBuyType
from empire_core.utils.lazy import lazy_exports

from .models import (
    UNSUPPORTED_BUY_TYPES,
    BuyEventPackageRequest,
    BuyEventPackageResponse,
    GetPackageBuyCountsRequest,
    PackageBuyCount,
    PackageBuyCountsResponse,
)
from .service import ShopService

if TYPE_CHECKING:
    from empire_core.gamedata import Event

__all__ = [
    "UNSUPPORTED_BUY_TYPES",
    "BuyEventPackageRequest",
    "BuyEventPackageResponse",
    "GetPackageBuyCountsRequest",
    "PackageBuyCount",
    "PackageBuyCountsResponse",
    "Event",
    "Kingdom",
    "PackageBuyType",
    "ShopService",
]


if not TYPE_CHECKING:
    __getattr__ = lazy_exports(__name__, "empire_core.gamedata.ids", ("Event",))
