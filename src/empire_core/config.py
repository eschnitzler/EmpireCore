import os
import secrets
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_AID_ENV_VAR = "EMPIRE_AID"
# Width of the AID the browser client sends (matching the literal that used to be
# hard-coded here): epoch-milliseconds plus six random digits.
_AID_DIGITS = 19


def generate_aid() -> str:
    """Build a fresh AID (the client's install/device id) in the format the game uses.

    The browser client's value looks like epoch-milliseconds followed by six
    random digits, so a generated one is indistinguishable in shape from a real
    install.
    """
    prefix = str(int(time.time() * 1000))
    suffix_digits = max(_AID_DIGITS - len(prefix), 1)
    return f"{prefix}{secrets.randbelow(10**suffix_digits):0{suffix_digits}d}"


def resolve_aid() -> str:
    """Return the AID to send to the server.

    Reads ``$EMPIRE_AID`` if it is set to something non-blank, otherwise
    generates one. The server treats this as a stable per-install identifier, so
    a long-lived deployment should generate one once, store it, and pin it via
    ``EMPIRE_AID``; otherwise every process start looks like a brand new device.
    Persisting it here is deliberately not done: a library must not write files
    or touch ``os.environ`` as an import side effect.
    """
    pinned = os.environ.get(_AID_ENV_VAR, "").strip()
    return pinned or generate_aid()


#: This process's install id. Resolved once at import so the fingerprint is
#: stable for the whole session; read it to persist and pin the value.
AID: str = resolve_aid()


# Default login payload values
LOGIN_DEFAULTS: dict[str, Any] = {
    "CONM": 1150008,
    "RTM": 24,
    "ID": 0,
    "PL": 1,
    "LT": None,
    "LANG": "en",
    "DID": "0",
    # Install/tracking id. Per-process by default (see resolve_aid): a single
    # hard-coded literal would make every user of this library present the same
    # device fingerprint to the server - trivially correlatable, and mass-bannable.
    "AID": AID,
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

    Instances are mutable: build one and assign to it, or pass field values to
    the constructor. The one exception is the shared :data:`default_config`
    below, which is frozen.
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
    # repr=False: keeps the secret out of repr()/str(), which reach logs and the
    # traceback locals captured by error reporters.
    password: str | None = Field(default=None, repr=False)


class _FrozenEmpireConfig(EmpireConfig):
    """An :class:`EmpireConfig` that rejects attribute assignment.

    Only used for the process-wide :data:`default_config`. Freezing
    ``EmpireConfig`` itself would break the ordinary
    ``cfg = EmpireConfig(); cfg.username = ...`` pattern that consumers use.
    """

    model_config = ConfigDict(frozen=True)


#: Shared fallback used by ``EmpireClient(config=None)``. Every such client
#: aliases this single instance, so it must not be mutable: one
#: ``client.config.default_zone = ...`` would otherwise silently repoint the
#: zone, timeouts and credentials of every other default-constructed client in
#: the process. To start from these defaults and change something, copy first::
#:
#:     cfg = EmpireConfig(**default_config.model_dump())
#:     cfg.default_zone = "EmpireEx_1"
default_config = _FrozenEmpireConfig()
