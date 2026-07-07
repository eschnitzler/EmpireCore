from typing import Any

from pydantic import BaseModel

# ============================================================
# Constants
# ============================================================


# Server error codes
class ServerError:
    """Server error code constants."""

    LOGIN_COOLDOWN = 453
    INVALID_CREDENTIALS = 401
    SESSION_EXPIRED = 440


# Default login payload values
LOGIN_DEFAULTS: dict[str, Any] = {
    "CONM": 1150008,
    "RTM": 24,
    "ID": 0,
    "PL": 1,
    "LT": None,
    "LANG": "en",
    "DID": "0",
    # Static install/tracking id captured from a browser session; every
    # library user presents this same fingerprint to the server.
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
    username: str | None = None
    password: str | None = None


# Global default instance
default_config = EmpireConfig()
