from typing import Any, Dict, Optional

from pydantic import BaseModel

# ============================================================
# Constants
# ============================================================

# Map chunk size for gaa requests
MAP_CHUNK_SIZE = 12


# Server error codes
class ServerError:
    """Server error code constants."""

    LOGIN_COOLDOWN = 453
    INVALID_CREDENTIALS = 401
    SESSION_EXPIRED = 440


# Resource type IDs used in transport payloads
class ResourceType:
    """Resource type ID constants for protocol payloads."""

    WOOD = "1"
    STONE = "2"
    FOOD = "3"


# Troop action types
class TroopActionType:
    """Troop action type constants."""

    ATTACK = 1
    SUPPORT = 2
    TRANSPORT = 3
    SPY = 4


# Default login payload values
LOGIN_DEFAULTS: Dict[str, Any] = {
    "CONM": 1150008,
    "RTM": 24,
    "ID": 0,
    "PL": 1,
    "LT": None,
    "LANG": "en",
    "DID": "0",
    "AID": "1745592024940879420",
    "KID": "",
    "REF": "https://empire.goodgamestudios.com",
    "GCI": "",
    "SID": 9,
    "PLFID": 1,
}


# ============================================================
# Configuration
# ============================================================


class EmpireConfig(BaseModel):
    """
    Configuration for EmpireCore.
    Defaults can be overridden by passing arguments to EmpireClient
    or (in the future) loading from environment variables/files.
    """

    # Connection
    game_url: str = "wss://ep-live-us1-game.goodgamestudios.com/"
    default_zone: str = "EmpireEx_21"
    game_version: str = "166"

    # Timeouts
    connection_timeout: float = 10.0
    login_timeout: float = 15.0
    request_timeout: float = 5.0

    # User (Optional defaults)
    username: Optional[str] = None
    password: Optional[str] = None


# Global default instance
default_config = EmpireConfig()
