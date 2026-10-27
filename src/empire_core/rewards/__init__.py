"""Free rewards: login and startup bonuses, lost and found, the activity chest, weekly honour, patch notes, ..."""

from typing import TYPE_CHECKING

from empire_core.enums import LoginBonusSpecial
from empire_core.utils.lazy import lazy_exports

from .models import (
    LOGIN_BONUS_REQUIRED_XP,
    ActivityChestInfo,
    CollectLoginBonusRequest,
    CollectLoginBonusResponse,
    CollectLostAndFoundRequest,
    CollectLostAndFoundResponse,
    CollectPatchNoteRewardsRequest,
    CollectPatchNoteRewardsResponse,
    CollectStartupBonusRequest,
    CollectStartupBonusResponse,
    GetLoginBonusRequest,
    GetLoginBonusResponse,
    GetLostAndFoundRequest,
    GetLostAndFoundResponse,
    GetPatchNoteRewardsRequest,
    GetPatchNoteRewardsResponse,
    GetStartupBonusRequest,
    GetStartupBonusResponse,
    GetWeeklyHonorRequest,
    GetWeeklyHonorResponse,
    GoodgamesGiftRequest,
    GoodgamesGiftResponse,
    LoginBonus,
    LoginBonusDay,
    LostAndFoundItem,
    OpenActivityChestRequest,
    OpenActivityChestResponse,
    PendingRewardsInfo,
    RedeemVoucherRequest,
    RedeemVoucherResponse,
    RedeemWeeklyHonorRequest,
    RedeemWeeklyHonorResponse,
)
from .service import RewardsService

if TYPE_CHECKING:
    from empire_core.gamedata import Tool, Unit

__all__ = [
    "GoodgamesGiftRequest",
    "GoodgamesGiftResponse",
    "RedeemVoucherRequest",
    "RedeemVoucherResponse",
    "LOGIN_BONUS_REQUIRED_XP",
    "LoginBonusSpecial",
    "ActivityChestInfo",
    "CollectLoginBonusRequest",
    "CollectLoginBonusResponse",
    "CollectLostAndFoundRequest",
    "CollectLostAndFoundResponse",
    "CollectPatchNoteRewardsRequest",
    "CollectPatchNoteRewardsResponse",
    "CollectStartupBonusRequest",
    "CollectStartupBonusResponse",
    "GetLoginBonusRequest",
    "GetLoginBonusResponse",
    "GetLostAndFoundRequest",
    "GetLostAndFoundResponse",
    "GetPatchNoteRewardsRequest",
    "GetPatchNoteRewardsResponse",
    "GetStartupBonusRequest",
    "GetStartupBonusResponse",
    "GetWeeklyHonorRequest",
    "GetWeeklyHonorResponse",
    "LoginBonus",
    "LoginBonusDay",
    "LostAndFoundItem",
    "OpenActivityChestRequest",
    "OpenActivityChestResponse",
    "PendingRewardsInfo",
    "RedeemWeeklyHonorRequest",
    "RedeemWeeklyHonorResponse",
    "RewardsService",
    "Tool",
    "Unit",
]


if not TYPE_CHECKING:
    __getattr__ = lazy_exports(__name__, "empire_core.gamedata.ids", ("Tool", "Unit"))
