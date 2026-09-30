"""Game enumerations.

Every public enum lives in this package, one module per area. The modules
import nothing but :mod:`enum`, so any module can import them without a cycle.
"""

from .alliance import AllianceRank, BookmarkType, DiplomacyStatus, HelpType, OnlineState
from .army import ProductionListId, SlotType
from .castle import BuildingState, ExpansionType, MarketScope, ResourceCartType
from .combat import AttackType, AutoSkipCooldownType, CombatEffectType, Flank, LootPriority
from .commanders import EquipmentSlot, EquipmentType, Rareness, SCEItem, WearerType
from .map import Kingdom, MapItemType, PeaceModeStatus
from .messages import MessageType
from .movements import MovementType
from .ranking import RankingType
from .spy import SpyLogResult, SpyLogType, SpyOutcome, SpyStep, SpyType

__all__ = [
    # Map / kingdom
    "Kingdom",
    "MapItemType",
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
    "SpyLogResult",
    "SpyOutcome",
    "SpyStep",
    # Army
    "ProductionListId",
    "SlotType",
    # Castle
    "BuildingState",
    "ExpansionType",
    "MarketScope",
    "ResourceCartType",
    # Commanders / equipment
    "EquipmentSlot",
    "WearerType",
    "EquipmentType",
    "Rareness",
    # Alliance
    "AllianceRank",
    "BookmarkType",
    "DiplomacyStatus",
    "OnlineState",
    "HelpType",
    # Messages
    "MessageType",
    # Ranking
    "RankingType",
    # Inventory
    "SCEItem",
]
