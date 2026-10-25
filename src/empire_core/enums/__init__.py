"""Game enumerations.

Every public enum is exported here. The hand-written ones live in this package, one
module per area; those modules import nothing but :mod:`enum`, so any module can
import them without a cycle. The generated game-data id enums (``Unit``, ``Tool``,
``Research``, ...) live in :mod:`empire_core.gamedata` and load on first use here too.
"""

from typing import TYPE_CHECKING

from empire_core.utils.lazy import lazy_exports

from .alliance import (
    AllianceBuffType,
    AllianceChronicleAction,
    AllianceRank,
    BookmarkType,
    DiplomacyStatus,
    ForumRankGroup,
    HelpType,
    OnlineState,
)
from .army import ProductionListId, RecruitmentMode, SlotType
from .castle import (
    BuildingState,
    ConstructionItemMode,
    ExpansionType,
    KingdomTransferType,
    MarketScope,
    Resource,
    ResourceCartType,
    TaxStatus,
    Weekday,
)
from .collectables import BoosterId, CollectableKind, RewardGrantType
from .combat import (
    AttackAdvisorType,
    AttackType,
    AutoSkipCooldownType,
    BattleLogFlank,
    CombatEffectType,
    Flank,
    LootPriority,
    TargetRead,
)
from .commanders import EquipmentSlot, EquipmentType, Rareness, WearerType
from .errors import GGEError
from .events import PerformanceStatistic, RaidBossCardStatus
from .gamedata import (
    BuildingGroundType,
    BuildingGroup,
    CastleEffect,
    EffectTemplate,
    PlayerRelation,
    QuestConditionType,
    RelicEffectType,
    TitleDisplayType,
    ToolCategory,
    ToolSide,
    UnitRole,
)
from .login import VersionCheckStatus
from .map import (
    FactionProtectionStatus,
    Kingdom,
    KingdomDirection,
    MapItemType,
    NPCOwner,
    PeaceModeDuration,
    PeaceModeStatus,
    TreasureMapProgress,
)
from .messages import BattleLogAttackType, LogResult, MessageType
from .movements import MovementType
from .player import MercenaryMissionRarity, MercenaryMissionState, MysteryBoxKey, PremiumAccountType, TitleSystem
from .ranking import RankingType
from .rewards import LoginBonusSpecial
from .spy import SpyArmySection, SpyLogType, SpyOutcome, SpyStep, SpyType

if TYPE_CHECKING:
    from empire_core.gamedata.ids import (
        Achievement,
        AllianceCrestColor,
        AllianceCrestLayout,
        Building,
        ConstructionItem,
        Currency,
        CurrencyId,
        DailyQuestId,
        DifficultyType,
        Effect,
        EffectType,
        EquipmentGroup,
        Event,
        Gem,
        GemColor,
        General,
        GeneralAbility,
        GeneralRarity,
        GeneralsHubCharacter,
        GeneralSkill,
        GlobalEffect,
        Horse,
        LegendSkill,
        LootBox,
        LootBoxType,
        MainQuest,
        QuestId,
        RaidBoss,
        Research,
        SceatSkill,
        Title,
        Tool,
        Unit,
    )

__all__ = [
    "ConstructionItemMode",
    "RaidBossCardStatus",
    "PerformanceStatistic",
    # Map / kingdom
    "Kingdom",
    "KingdomDirection",
    "MapItemType",
    "NPCOwner",
    "PeaceModeStatus",
    "PeaceModeDuration",
    "FactionProtectionStatus",
    "TreasureMapProgress",
    # Movement
    "MovementType",
    # Attack / combat
    "AttackType",
    "LootPriority",
    "AutoSkipCooldownType",
    "AttackAdvisorType",
    "Flank",
    "BattleLogFlank",
    "CombatEffectType",
    "TargetRead",
    # Errors and the login
    "GGEError",
    "VersionCheckStatus",
    # Spy
    "SpyType",
    "SpyLogType",
    "SpyOutcome",
    "SpyStep",
    "SpyArmySection",
    # Army
    "ProductionListId",
    "RecruitmentMode",
    "SlotType",
    # Castle
    "BuildingState",
    "ExpansionType",
    "MarketScope",
    "Resource",
    "ResourceCartType",
    "TaxStatus",
    "Weekday",
    "KingdomTransferType",
    # Collectables
    "BoosterId",
    "CollectableKind",
    "RewardGrantType",
    # Commanders / equipment
    "EquipmentSlot",
    "WearerType",
    "EquipmentType",
    "Rareness",
    # Alliance
    "AllianceBuffType",
    "AllianceChronicleAction",
    "AllianceRank",
    "ForumRankGroup",
    "BookmarkType",
    "DiplomacyStatus",
    "OnlineState",
    "HelpType",
    # Messages
    "MessageType",
    "LogResult",
    "BattleLogAttackType",
    # Player
    "TitleSystem",
    "MysteryBoxKey",
    "PremiumAccountType",
    "MercenaryMissionRarity",
    "MercenaryMissionState",
    # Ranking
    "RankingType",
    # Rewards
    "LoginBonusSpecial",
    # Game data
    "BuildingGroundType",
    "CastleEffect",
    "BuildingGroup",
    "PlayerRelation",
    "QuestConditionType",
    "RelicEffectType",
    "TitleDisplayType",
    "ToolCategory",
    "ToolSide",
    "UnitRole",
    "EffectTemplate",
    # Game-data ids, generated
    "Achievement",
    "AllianceCrestColor",
    "AllianceCrestLayout",
    "Building",
    "ConstructionItem",
    "Currency",
    "CurrencyId",
    "DailyQuestId",
    "DifficultyType",
    "Effect",
    "EffectType",
    "EquipmentGroup",
    "Event",
    "Gem",
    "GemColor",
    "General",
    "GeneralAbility",
    "GeneralRarity",
    "GeneralSkill",
    "GeneralsHubCharacter",
    "GlobalEffect",
    "Horse",
    "LegendSkill",
    "LootBox",
    "LootBoxType",
    "MainQuest",
    "QuestId",
    "RaidBoss",
    "Research",
    "SceatSkill",
    "Title",
    "Tool",
    "Unit",
]

if not TYPE_CHECKING:
    __getattr__ = lazy_exports(__name__, "empire_core.gamedata.ids", __all__[__all__.index("Achievement") :])
