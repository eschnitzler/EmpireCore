import math
import os
import random
import sys
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_AID_ENV_VAR = "EMPIRE_AID"
_random = random.SystemRandom()


def _to_fixed(number: float) -> str:
    """``number.toFixed()`` for a number that is not negative."""
    return repr(number) if number >= 1e21 else str(math.floor(number + 0.5))


def generate_aid() -> str:
    """
    A fresh account (install) id, made as the client makes one for a new install.

    Epoch milliseconds followed by a random number below 999999, not padded.

    Client: ``AccountCookie`` (dll line 9088)
    """
    return str(int(time.time() * 1000)) + _to_fixed(999999 * _random.random())


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


def generate_session_id() -> str:
    """
    A session id as the client makes one per page load; the version check sends it.

    Client: ``BasicEnvironmentGlobals.sessionId`` (dll line 34455)
    """
    return _to_fixed(_random.random() * sys.float_info.max)


def build_number(version: str) -> str:
    """
    The build number of a client version: ``"1.169.11"`` is ``"1169011"``.

    The minor and patch parts are padded to three digits; a patch suffix after
    ``-`` is dropped.

    Client: ``CastleVersionInformation.buildNumberGame`` (bundle line 10446)
    """
    major, minor, patch = version.split(".")[:3]
    return major + minor.rjust(3, "0") + patch.split("-")[0].rjust(3, "0")


# Default login payload values; CONM and RTM are measured during the login.
LOGIN_DEFAULTS: dict[str, Any] = {
    "ID": 0,
    "PL": 1,
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
    game_version: str = Field(default="166", description="SmartFox API version the verChk handshake sends")
    client_version: str = Field(
        default="1.169.11", description="Game client version whose build number the login and version check send"
    )

    # Timeouts
    connection_timeout: float = 10.0
    login_timeout: float = 15.0
    request_timeout: float = 5.0

    # User (Optional defaults)
    username: str | None = None
    # repr=False: keeps the secret out of repr()/str(), which reach logs and the
    # traceback locals captured by error reporters.
    password: str | None = Field(default=None, repr=False)

    @property
    def build_number(self) -> str:
        """The build number of :attr:`client_version`."""
        return build_number(self.client_version)


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
