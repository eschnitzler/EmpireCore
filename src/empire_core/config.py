"""Client configuration and the game's server list."""

import json
import math
import os
import random
import sys
import time
import xml.etree.ElementTree as ET
from typing import Any

import requests
from pydantic import BaseModel, ConfigDict, Field

from empire_core.exceptions import NetworkError
from empire_core.protocol.js import js_number

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
# Server list (network.xml)
# ============================================================


class NetworkInstance(BaseModel):
    """
    One game server (world) of a network, as ``network.xml`` lists it.

    Client: ``NetworkXMLParser`` (dll line 20264)
    """

    model_config = ConfigDict(frozen=True)

    instance_id: int = Field(description="The instance's id")
    server: str = Field(description="Host name of the game server")
    port: int = Field(description="Port of the game server")
    zone: str = Field(description="Zone the login and every command name")
    zone_id: int = Field(description="The zone's id")
    instance_number: int = Field(description="Number of the world within its network")
    is_international: bool = Field(description="The world is open to every country")
    is_favorite: bool = Field(description="The world is marked as a favourite")
    default_country: str = Field(description="Code of the world's default country")
    instance_loca_id: str = Field(description="Localization key of the world's name")
    countries: list[str] = Field(description="Codes of the countries the world is for")

    @property
    def game_url(self) -> str:
        """The WebSocket URL of this server; the client always connects on port 443."""
        return f"wss://{self.server}:443"


def network_config_url(
    game_id: int,
    network_id: int,
    *,
    test_servers: bool = False,
    cdn_sub_domain: str = "content",
    domain: str = "goodgamestudios.com",
) -> str:
    """
    The URL of a network's ``network.xml``.

    ``https://{cdn_sub_domain}.{domain}/games-netconf/{game_id}/{network_id}.xml``,
    or with ``test_servers`` (the client's ``forceToShowTestServers``)
    ``https://files.{domain}/games-netconf-test/{game_id}/{network_id}.xml``.
    The ids come from the page the game is embedded in, not from the client;
    the host defaults are the client's.

    Client: ``LiveEnvironment.initPatterns`` (dll line 3894-3900); ``cdnSubDomain``
    and ``domain`` from ``BasicEnvironmentGlobals`` (dll line 34178, 34223)
    """
    if test_servers:
        return f"https://files.{domain}/games-netconf-test/{game_id}/{network_id}.xml"
    return f"https://{cdn_sub_domain}.{domain}/games-netconf/{game_id}/{network_id}.xml"


def _first(node: ET.Element, tag: str) -> ET.Element | None:
    return next((child for child in node.iter(tag) if child is not node), None)


def _text(node: ET.Element, tag: str) -> str:
    found = _first(node, tag)
    return (found.text or "") if found is not None else ""


def _number(node: ET.Element, tag: str) -> int:
    found = _first(node, tag)
    return int(js_number(found.text or "")) if found is not None else 0


def _countries(text: str) -> list[str]:
    if not text or text == "null" or len(text) < 6:
        return []
    try:
        codes = json.loads(text)
    except ValueError:
        return []
    return [code for code in codes if isinstance(code, str)] if isinstance(codes, list) else []


def _instance(node: ET.Element) -> NetworkInstance:
    return NetworkInstance(
        instance_id=int(js_number(node.get("value", ""))) if node.get("value") is not None else 0,
        server=_text(node, "server"),
        port=_number(node, "port"),
        zone=_text(node, "zone"),
        zone_id=_number(node, "zoneId"),
        instance_number=_number(node, "instanceName"),
        is_international=_text(node, "isInternational") == "1",
        is_favorite=_text(node, "isFavorite") == "1",
        default_country=_text(node, "defaultcountry"),
        instance_loca_id=_text(node, "instanceLocaId"),
        countries=_countries(_text(node, "countries")),
    )


def parse_network_instances(xml_text: str, include_test: bool = False) -> list[NetworkInstance]:
    """
    The servers a ``network.xml`` lists under ``instances``, and under ``test-instances`` too with ``include_test``.

    Country codes are kept as the file gives them (the client also drops the
    ones it has no country for), and a countries list that is not JSON reads
    as none, where the client would fail the whole file.

    Raises:
        ValueError: The text is not XML, or declares a DTD

    Client: ``NetworkXMLParser.parseInstances`` and ``parseTestInstances`` (dll line 20254),
    ``NetworkInstancesController.loadNetworkInstances`` (dll line 20233)
    """
    lowered = xml_text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("network.xml must not declare a DTD")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"network.xml is not XML: {e}") from e
    tags = ["instances", "test-instances"] if include_test else ["instances"]
    instances: list[NetworkInstance] = []
    for tag in tags:
        section = next(root.iter(tag), None)
        if section is not None:
            instances.extend(_instance(child) for child in section)
    return instances


def fetch_network_instances(
    game_id: int, network_id: int, include_test: bool = False, timeout: float = 10.0, **url_parts: Any
) -> list[NetworkInstance]:
    """
    Download a network's ``network.xml`` and read its servers.

    ``url_parts`` go to :func:`network_config_url` (``test_servers``,
    ``cdn_sub_domain``, ``domain``).

    Raises:
        NetworkError: The file could not be downloaded
        ValueError: The file is not XML
    """
    url = network_config_url(game_id, network_id, **url_parts)
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as e:
        raise NetworkError(f"Could not load {url}: {e}") from e
    return parse_network_instances(response.text, include_test=include_test)


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

    @classmethod
    def for_instance(cls, instance: NetworkInstance, **fields: Any) -> "EmpireConfig":
        """A config for one server of ``network.xml``: its URL and zone, and ``fields`` for the rest."""
        return cls(game_url=instance.game_url, default_zone=instance.zone, **fields)


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
