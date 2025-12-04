"""Automation modules for EmpireCore."""

from .quest_automation import QuestAutomation
from .battle_reports import BattleReportAutomation
from .alliance_tools import AllianceManager, ChatManager
from .map_scanner import MapScanner
from .resource_manager import ResourceManager
from .building_queue import BuildingManager
from .unit_production import UnitManager

__all__ = [
    "QuestAutomation",
    "BattleReportAutomation",
    "AllianceManager",
    "ChatManager",
    "MapScanner",
    "ResourceManager",
    "BuildingManager",
    "UnitManager",
]
