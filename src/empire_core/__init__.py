"""
EmpireCore - Python library for Goodgame Empire automation.
"""

# Accounts
from empire_core.accounts import Account, accounts
from empire_core.automation import tasks
from empire_core.automation.alliance_tools import AllianceService, ChatService
from empire_core.automation.battle_reports import BattleReportService
from empire_core.automation.building_queue import BuildingManager
from empire_core.automation.defense_manager import DefenseManager

# Automation Bots
from empire_core.automation.map_scanner import MapScanner
from empire_core.automation.quest_automation import QuestService
from empire_core.automation.resource_manager import ResourceManager
from empire_core.automation.unit_production import UnitManager
from empire_core.client.client import EmpireClient

# Services (formerly Mixins)
from empire_core.client.defense import DefenseService
from empire_core.config import EmpireConfig
from empire_core.events import (
    AttackSentEvent,
    Event,
    EventManager,
    IncomingAttackEvent,
    MovementArrivedEvent,
    MovementCancelledEvent,
    MovementEvent,
    MovementStartedEvent,
    MovementUpdatedEvent,
    PacketEvent,
    ReturnArrivalEvent,
    ScoutSentEvent,
    TransportSentEvent,
)
from empire_core.state.models import Alliance, Building, Castle, Player, Resources
from empire_core.state.quest_models import DailyQuest, Quest
from empire_core.state.report_models import BattleReport, ReportManager
from empire_core.state.unit_models import UNIT_IDS, Army, UnitStats
from empire_core.state.world_models import MapObject, Movement, MovementResources
from empire_core.utils.calculations import (
    calculate_distance,
    calculate_resource_production,
    calculate_travel_time,
    format_time,
    is_within_range,
)
from empire_core.utils.enums import KingdomType, MapObjectType, MovementType
from empire_core.utils.helpers import (
    CastleHelper,
    MovementHelper,
    PlayerHelper,
    ResourceHelper,
)

__version__ = "0.1.0"

__all__ = [
    "EmpireClient",
    "EmpireConfig",
    # Accounts
    "Account",
    "accounts",
    # Models
    "Player",
    "Castle",
    "Resources",
    "Building",
    "Alliance",
    "Movement",
    "MovementResources",
    "MapObject",
    "Army",
    "UnitStats",
    "Quest",
    "DailyQuest",
    "BattleReport",
    "ReportManager",
    # Services
    "DefenseService",
    "QuestService",
    "BattleReportService",
    "AllianceService",
    "ChatService",
    # Automation Bots
    "MapScanner",
    "ResourceManager",
    "BuildingManager",
    "UnitManager",
    "DefenseManager",
    "tasks",
    # Enums
    "MovementType",
    "MapObjectType",
    "KingdomType",
    # Constants
    "UNIT_IDS",
    # Utilities
    "calculate_distance",
    "calculate_travel_time",
    "calculate_resource_production",
    "format_time",
    "is_within_range",
    "CastleHelper",
    "MovementHelper",
    "ResourceHelper",
    "PlayerHelper",
    # Events
    "Event",
    "PacketEvent",
    "EventManager",
    "MovementEvent",
    "MovementStartedEvent",
    "MovementUpdatedEvent",
    "MovementArrivedEvent",
    "MovementCancelledEvent",
    "IncomingAttackEvent",
    "ReturnArrivalEvent",
    "AttackSentEvent",
    "ScoutSentEvent",
    "TransportSentEvent",
]
