"""Automation modules for EmpireCore."""

from .quest_automation import QuestService
from .battle_reports import BattleReportService
from .alliance_tools import AllianceService, ChatService
from .map_scanner import MapScanner
from .resource_manager import ResourceManager
from .building_queue import BuildingManager
from .unit_production import UnitManager
from .defense_manager import DefenseManager
from . import tasks

__all__ = [
    "QuestService",
    "BattleReportService",
    "AllianceService",
    "ChatService",
    "MapScanner",
    "ResourceManager",
    "BuildingManager",
    "UnitManager",
    "DefenseManager",
    "tasks",
]
