"""Game enumerations.

Every public enum lives in this package, one module per area. The modules
import nothing but :mod:`enum`, so any module can import them without a cycle.
"""

from .alliance import AllianceChronicleAction, AllianceRank, BookmarkType, DiplomacyStatus, HelpType, OnlineState
from .army import ProductionListId, SlotType
from .castle import BuildingState, ExpansionType, MarketScope, Resource, ResourceCartType
from .combat import AttackType, AutoSkipCooldownType, CombatEffectType, Flank, LootPriority
from .commanders import EquipmentSlot, EquipmentType, Rareness, SCEItem, WearerType
from .map import Kingdom, MapItemType, NPCOwner, PeaceModeStatus
from .messages import BattleLogAttackType, LogResult, MessageType
from .movements import MovementType
from .player import TitleSystem
from .ranking import RankingType
from .spy import SpyLogType, SpyOutcome, SpyStep, SpyType

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
    "Flank",
    "CombatEffectType",
    # Spy
    "SpyType",
    "SpyLogType",
    "SpyOutcome",
    "SpyStep",
    # Army
    "ProductionListId",
    "SlotType",
    # Castle
    "BuildingState",
    "ExpansionType",
    "MarketScope",
    "Resource",
    "ResourceCartType",
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
    # Ranking
    "RankingType",
    # Inventory
    "SCEItem",
]
