"""
EmpireCore - Python library for Goodgame Empire automation.
"""

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.state.models import Player, Castle, Resources, Building, Alliance
from empire_core.state.world_models import Movement, MapObject, MovementResources
from empire_core.state.unit_models import Army, UnitStats, UNIT_IDS
from empire_core.state.quest_models import Quest, DailyQuest
from empire_core.state.report_models import BattleReport, ReportManager
# Mixins (formerly Automation classes)
from empire_core.automation.quest_automation import QuestMixin
from empire_core.automation.battle_reports import BattleReportMixin
from empire_core.automation.alliance_tools import AllianceMixin, ChatMixin
# Automation Bots
from empire_core.automation.map_scanner import MapScanner
from empire_core.automation.resource_manager import ResourceManager
from empire_core.automation.building_queue import BuildingManager
from empire_core.automation.unit_production import UnitManager
from empire_core.utils.calculations import (
    calculate_distance,
    calculate_travel_time,
    calculate_resource_production,
    format_time,
    is_within_range,
)
from empire_core.utils.helpers import (
    CastleHelper,
    MovementHelper,
    ResourceHelper,
    PlayerHelper,
)
from empire_core.utils.enums import MovementType, MapObjectType, KingdomType
from empire_core.events import (
    Event,
    PacketEvent,
    EventManager,
    MovementEvent,
    MovementStartedEvent,
    MovementUpdatedEvent,
    MovementArrivedEvent,
    MovementCancelledEvent,
    IncomingAttackEvent,
    ReturnArrivalEvent,
    AttackSentEvent,
    ScoutSentEvent,
    TransportSentEvent,
)

__version__ = "0.1.0"

__all__ = [
    "EmpireClient",
    "EmpireConfig",
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
    # Mixins
    "QuestMixin",
    "BattleReportMixin",
    "AllianceMixin",
    "ChatMixin",
    # Automation Bots
    "MapScanner",
    "ResourceManager",
    "BuildingManager",
    "UnitManager",
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