"""Automation modules for EmpireCore."""

from .quest_automation import QuestMixin
from .battle_reports import BattleReportMixin
from .alliance_tools import AllianceMixin, ChatMixin
from .map_scanner import MapScanner
from .resource_manager import ResourceManager
from .building_queue import BuildingManager
from .unit_production import UnitManager

__all__ = [
    "QuestMixin",
    "BattleReportMixin",
    "AllianceMixin",
    "ChatMixin",
    "MapScanner",
    "ResourceManager",
    "BuildingManager",
    "UnitManager",
]