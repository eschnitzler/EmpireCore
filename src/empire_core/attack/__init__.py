"""Attacks: sending, pre-calculation, presets and dungeon cooldowns."""

from typing import TYPE_CHECKING

from empire_core.enums import AttackType, AutoSkipCooldownType, Flank, Kingdom, LootPriority, MapItemType
from empire_core.utils.lazy import lazy_exports

from .models import (
    PRESET_NAME_MAX_LENGTH,
    AttackCounterResponse,
    AttackInfoResponse,
    AttackPreset,
    AttackTargetArea,
    CreateAttackRequest,
    CreateAttackResponse,
    GetAttackInfoRequest,
    GetAttackInfoResponse,
    GetBossDungeonAttackInfoRequest,
    GetBossDungeonAttackInfoResponse,
    GetCapitalConquerInfoRequest,
    GetCapitalConquerInfoResponse,
    GetDungeonAttackInfoRequest,
    GetDungeonAttackInfoResponse,
    GetIslandAttackInfoRequest,
    GetIslandAttackInfoResponse,
    GetLandmarkAttackInfoRequest,
    GetLandmarkAttackInfoResponse,
    GetMetropolConquerInfoRequest,
    GetMetropolConquerInfoResponse,
    GetOutpostConquerInfoRequest,
    GetOutpostConquerInfoResponse,
    GetPresetsRequest,
    GetPresetsResponse,
    GetVillageAttackInfoRequest,
    GetVillageAttackInfoResponse,
    MinuteSkipDungeonRequest,
    MinuteSkipDungeonResponse,
    PresetArmy,
    RenamePresetRequest,
    RenamePresetResponse,
    SavePresetRequest,
    SavePresetResponse,
    SkipDungeonCooldownRequest,
    SkipDungeonCooldownResponse,
)
from .service import AttackService

if TYPE_CHECKING:
    from empire_core.gamedata import Currency, CurrencyId, LegendSkill, Tool

__all__ = [
    "MinuteSkipDungeonRequest",
    "MinuteSkipDungeonResponse",
    "SkipDungeonCooldownRequest",
    "SkipDungeonCooldownResponse",
    "AttackTargetArea",
    "AttackInfoResponse",
    "GetAttackInfoRequest",
    "GetAttackInfoResponse",
    "GetPresetsRequest",
    "GetPresetsResponse",
    "AttackPreset",
    "PresetArmy",
    "SavePresetRequest",
    "SavePresetResponse",
    "RenamePresetRequest",
    "RenamePresetResponse",
    "PRESET_NAME_MAX_LENGTH",
    "CreateAttackRequest",
    "CreateAttackResponse",
    "GetDungeonAttackInfoRequest",
    "GetDungeonAttackInfoResponse",
    "GetBossDungeonAttackInfoRequest",
    "GetBossDungeonAttackInfoResponse",
    "GetLandmarkAttackInfoRequest",
    "GetLandmarkAttackInfoResponse",
    "GetVillageAttackInfoRequest",
    "GetVillageAttackInfoResponse",
    "GetIslandAttackInfoRequest",
    "GetIslandAttackInfoResponse",
    "GetOutpostConquerInfoRequest",
    "GetOutpostConquerInfoResponse",
    "GetCapitalConquerInfoRequest",
    "GetCapitalConquerInfoResponse",
    "GetMetropolConquerInfoRequest",
    "GetMetropolConquerInfoResponse",
    "AttackType",
    "LootPriority",
    "AutoSkipCooldownType",
    "AttackService",
    "AttackCounterResponse",
    "Flank",
    "Kingdom",
    "MapItemType",
    "Currency",
    "CurrencyId",
    "LegendSkill",
    "Tool",
]


if not TYPE_CHECKING:
    __getattr__ = lazy_exports(__name__, "empire_core.gamedata.ids", ("Currency", "CurrencyId", "LegendSkill", "Tool"))
