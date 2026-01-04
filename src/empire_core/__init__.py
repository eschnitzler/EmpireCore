"""
EmpireCore - Python library for Goodgame Empire automation.
"""

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.state.models import Alliance, Building, Castle, Player, Resources
from empire_core.state.world_models import MapObject, Movement, MovementResources
from empire_core.state.unit_models import UNIT_IDS, Army, UnitStats
from empire_core.utils.enums import KingdomType, MapObjectType, MovementType

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
    # Enums
    "MovementType",
    "MapObjectType",
    "KingdomType",
    # Constants
    "UNIT_IDS",
]
