"""Game enumerations.

Every public enum lives in this package, one module per area. The modules
import nothing but :mod:`enum`, so any module can import them without a cycle.
"""

from .alliance import DiplomacyStatus, HelpType, OnlineState
from .army import ProductionListId, SlotType
from .combat import AttackType, AutoSkipCooldownType, CombatEffectType, Flank, LootPriority
from .commanders import EquipmentSlot, EquipmentType, Rareness, SCEItem, WearerType
from .map import Kingdom, MapItemType
from .movements import MovementType
from .ranking import RankingType
from .spy import SpyType

__all__ = [
    # Map / kingdom
    "Kingdom",
    "MapItemType",
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
    # Army
    "ProductionListId",
    "SlotType",
    # Commanders / equipment
    "EquipmentSlot",
    "WearerType",
    "EquipmentType",
    "Rareness",
    # Alliance
    "DiplomacyStatus",
    "OnlineState",
    "HelpType",
    # Ranking
    "RankingType",
    # Inventory
    "SCEItem",
]
