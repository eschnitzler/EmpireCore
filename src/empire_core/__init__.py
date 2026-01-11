"""
EmpireCore - Python library for Goodgame Empire automation.
"""

from importlib.metadata import version

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.pool import AccountPool
from empire_core.state.models import Alliance, Building, Castle, Player, Resources
from empire_core.state.unit_models import UNIT_IDS, Army, UnitStats
from empire_core.state.world_models import MapObject, Movement, MovementResources
from empire_core.utils.enums import KingdomType, MapObjectType, MovementType

__version__ = version(__package__)

__all__ = [
    "EmpireClient",
    "EmpireConfig",
    "AccountPool",
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
