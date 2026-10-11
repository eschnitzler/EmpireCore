"""Client configuration and the game's server list."""

import json
import math
import os
import random
import sys
import threading
import time
import xml.etree.ElementTree as ET
from typing import Any, ClassVar

import requests
from pydantic import ConfigDict, Field, model_validator

from empire_core.exceptions import NetworkError
from empire_core.protocol.base import EmpireModel
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


class NetworkInstance(EmpireModel):
    """
    One game server (world) of a network, as ``network.xml`` lists it.

    Client: ``NetworkXMLParser`` (dll line 20264)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

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


EMPIRE_GAME_ID = 12
"""Goodgame Empire's game id, as in its ``games-netconf`` and language file URLs."""

EMPIRE_NETWORK_ID = 1
"""The network of Goodgame Empire's international worlds (``EmpireEx_*``)."""

CDN_SUB_DOMAIN = "files-ak"
"""The CDN host the client loads files from: ``files-`` and the active CDN's abbreviation (Akamai, ``ak``).

Client: ``cdnSubDomain`` (dll line 34406), ``CDN.abbreviation`` (dll lines 10973-10978)
"""

FALLBACK_CDN_SUB_DOMAIN = "media"
"""The host the client falls back to when its CDN fails (``_useFallbackCDN``, dll line 34406)."""


def network_config_url(
    game_id: int,
    network_id: int,
    *,
    test_servers: bool = False,
    cdn_sub_domain: str = CDN_SUB_DOMAIN,
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
    hosts = (
        [url_parts.pop("cdn_sub_domain")]
        if "cdn_sub_domain" in url_parts
        else [CDN_SUB_DOMAIN, FALLBACK_CDN_SUB_DOMAIN]
    )
    errors = []
    for host in hosts:
        url = network_config_url(game_id, network_id, cdn_sub_domain=host, **url_parts)
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as e:
            errors.append(f"{url}: {e}")
            continue
        return parse_network_instances(response.text, include_test=include_test)
    raise NetworkError(f"Could not load network.xml: {'; '.join(errors)}")


_instances_lock = threading.Lock()
_instances: dict[tuple[int, int], list[NetworkInstance]] = {}


def instance_for_zone(
    zone: str, *, game_id: int = EMPIRE_GAME_ID, network_id: int = EMPIRE_NETWORK_ID
) -> NetworkInstance:
    """
    The server a world (zone) lives on, from the network's ``network.xml``, read once per process.

    Raises:
        NetworkError: The server list could not be downloaded
        ValueError: The network lists no world of that zone
    """
    with _instances_lock:
        listed = _instances.get((game_id, network_id))
        if listed is None:
            listed = _instances[(game_id, network_id)] = fetch_network_instances(game_id, network_id)
    for instance in listed:
        if instance.zone == zone:
            return instance
    raise ValueError(f"No world {zone!r} in network {network_id} (known: {', '.join(sorted(i.zone for i in listed))})")


# ============================================================
# Configuration
# ============================================================


class EmpireConfig(EmpireModel):
    """
    Configuration for EmpireCore.
    Defaults can be overridden by passing arguments to EmpireClient
    or (in the future) loading from environment variables/files.

    Instances are mutable: build one and assign to it, or pass field values to
    the constructor. The one exception is the shared :data:`default_config`
    below, which is frozen. An assignment is validated as the constructor
    validates, and a value the field does not take raises ``ValidationError``.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(validate_assignment=True)

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

    # Login retries: library policy, the game client logs in again only when the player clicks
    # its reconnect dialog (CastleConnectionLostCommand.execute, onReconnect, bundle lines 120253, 120256)
    relogin_first_delay: float = Field(
        default=5.0,
        gt=0,
        description="Seconds from a drop to the first keep_session re-login, and from a failed "
        "login(retry=True) attempt to the next; above 0 and at most relogin_max_delay",
    )
    relogin_max_delay: float = Field(
        default=300.0,
        gt=0,
        description="The longest wait between two login attempts in seconds; each failure doubles it. "
        "At least relogin_first_delay: raise this one first when raising both on an existing config",
    )

    # User (Optional defaults)
    username: str | None = None
    # repr=False: keeps the secret out of repr()/str(), which reach logs and the
    # traceback locals captured by error reporters.
    password: str | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def relogin_delays_in_order(self) -> "EmpireConfig":
        """Refuse a first re-login delay longer than the cap on the delays."""
        if self.relogin_first_delay > self.relogin_max_delay:
            raise ValueError(
                f"relogin_first_delay ({self.relogin_first_delay}) is over relogin_max_delay ({self.relogin_max_delay})"
            )
        return self

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

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


#: Shared fallback used by ``EmpireClient(config=None)``. Every such client
#: aliases this single instance, so it must not be mutable: one
#: ``client.config.default_zone = ...`` would otherwise silently repoint the
#: zone, timeouts and credentials of every other default-constructed client in
#: the process. To start from these defaults and change something, copy first::
#:
#:     cfg = EmpireConfig(**default_config.model_dump())
#:     cfg.default_zone = "EmpireEx_1"
default_config = _FrozenEmpireConfig()

__all__ = [
    "EmpireConfig",
    "NetworkInstance",
    "CDN_SUB_DOMAIN",
    "EMPIRE_GAME_ID",
    "EMPIRE_NETWORK_ID",
    "FALLBACK_CDN_SUB_DOMAIN",
    "fetch_network_instances",
    "instance_for_zone",
    "network_config_url",
    "parse_network_instances",
]
