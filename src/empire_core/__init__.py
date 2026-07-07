"""
EmpireCore - Python library for Goodgame Empire automation.
"""

from importlib.metadata import version

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.exceptions import (
    CommandError,
    ConnectionClosedError,
    EmpireError,
    EmpireTimeoutError,
    LoginCooldownError,
    LoginError,
    NetworkError,
    PacketError,
)
from empire_core.pool import AccountPool
from empire_core.state.models import Alliance, Building, Castle, Player, Resources
from empire_core.state.world_models import Movement, MovementResources
from empire_core.utils.enums import KingdomType, MapObjectType, MovementType
from empire_core.utils.events import GameEvent

__version__ = version(__package__)

__all__ = [
    "EmpireClient",
    "EmpireConfig",
    "AccountPool",
    # Exceptions
    "EmpireError",
    "NetworkError",
    "ConnectionClosedError",
    "LoginError",
    "LoginCooldownError",
    "PacketError",
    "EmpireTimeoutError",
    "CommandError",
    # Models
    "Player",
    "Castle",
    "Resources",
    "Building",
    "Alliance",
    "Movement",
    "MovementResources",
    # Enums
    "MovementType",
    "MapObjectType",
    "KingdomType",
    "GameEvent",
]
