"""
EmpireCore - Python library for Goodgame Empire automation.
"""
from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.state.models import Player, Castle, Resources, Building, Alliance
from empire_core.state.world_models import Movement, MapObject
from empire_core.state.unit_models import Army, UnitStats, UNIT_IDS
from empire_core.state.quest_models import Quest, DailyQuest
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
    "MapObject",
    "Army",
    "UnitStats",
    "Quest",
    "DailyQuest",
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
]
