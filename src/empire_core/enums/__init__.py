"""Game enumerations.

Every public enum lives in this package, one module per area. The modules
import nothing but :mod:`enum`, so any module can import them without a cycle.
"""

from .alliance import AllianceChronicleAction, AllianceRank, BookmarkType, DiplomacyStatus, HelpType, OnlineState
from .army import ProductionListId, SlotType
from .castle import BuildingState, ExpansionType, MarketScope, Resource, ResourceCartType, TaxStatus
from .collectables import BoosterId, CollectableKind, RewardGrantType
from .combat import (
    AttackAdvisorType,
    AttackType,
    AutoSkipCooldownType,
    BattleLogFlank,
    CombatEffectType,
    Flank,
    LootPriority,
)
from .commanders import EquipmentSlot, EquipmentType, Rareness, WearerType
from .gamedata import (
    BuildingGroundType,
    BuildingGroup,
    PlayerRelation,
    QuestConditionType,
    RelicEffectType,
    TitleDisplayType,
    ToolCategory,
    ToolSide,
    UnitRole,
)
from .map import Kingdom, MapItemType, NPCOwner, PeaceModeStatus
from .messages import BattleLogAttackType, LogResult, MessageType
from .movements import MovementType
from .player import PremiumAccountType, TitleSystem
from .ranking import RankingType
from .rewards import LoginBonusSpecial
from .spy import SpyArmySection, SpyLogType, SpyOutcome, SpyStep, SpyType

__all__ = [
    # Map / kingdom
    "Kingdom",
    "MapItemType",
    "NPCOwner",
    "PeaceModeStatus",
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
    # Spy
    "SpyType",
    "SpyLogType",
    "SpyOutcome",
    "SpyStep",
    "SpyArmySection",
    # Army
    "ProductionListId",
    "SlotType",
    # Castle
    "BuildingState",
    "ExpansionType",
    "MarketScope",
    "Resource",
    "ResourceCartType",
    "TaxStatus",
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
    "AllianceChronicleAction",
    "AllianceRank",
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
    "PremiumAccountType",
    # Ranking
    "RankingType",
    # Rewards
    "LoginBonusSpecial",
    # Game data
    "BuildingGroundType",
    "BuildingGroup",
    "PlayerRelation",
    "QuestConditionType",
    "RelicEffectType",
    "TitleDisplayType",
    "ToolCategory",
    "ToolSide",
    "UnitRole",
]
