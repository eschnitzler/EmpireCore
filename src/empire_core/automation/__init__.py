"""Automation modules for EmpireCore."""

from .quest_automation import QuestService
from .battle_reports import BattleReportMixin
from .alliance_tools import AllianceMixin, ChatMixin
from .map_scanner import MapScanner
from .resource_manager import ResourceManager
from .building_queue import BuildingManager
from .unit_production import UnitManager
from .defense_manager import DefenseManager
from . import tasks

__all__ = [
    "QuestService",
    "BattleReportMixin",
    "AllianceMixin",
    "ChatMixin",
    "MapScanner",
    "ResourceManager",
    "BuildingManager",
    "UnitManager",
    "DefenseManager",
    "tasks",
]