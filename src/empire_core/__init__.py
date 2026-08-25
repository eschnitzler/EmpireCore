"""
EmpireCore - Python library for Goodgame Empire automation.

Everything re-exported here is public API and covered by the deprecation
policy. Names reached through submodules (``empire_core.protocol.*``,
``empire_core.state.manager``, ``empire_core.network.*``, ...) that are *not*
re-exported here are internal: they can move or change shape in any release.
Import from the package root instead of deep-importing::

    from empire_core import EmpireClient, Kingdom, MapItemType, ScanResult
"""

from importlib.metadata import PackageNotFoundError, version

from empire_core.accounts import Account, accounts
from empire_core.client.client import EmpireClient
from empire_core.client.map_scanner import ScanResult
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
from empire_core.pool import AccountPool, PoolExhaustedError
from empire_core.protocol.errors import GGEError
from empire_core.protocol.models.alliance import AllianceInfo, AllianceMember
from empire_core.protocol.models.castle import CastleInfo
from empire_core.protocol.models.chat import decode_chat_text, encode_chat_text
from empire_core.protocol.models.commanders import (
    Castellan,
    Commander,
    Equipment,
    EquipmentSlot,
)
from empire_core.protocol.models.map import Kingdom, MapAreaItem, MapItemType, MapObject
from empire_core.protocol.models.messages import SpyCastleInfo
from empire_core.protocol.models.ranking import RankingEntry
from empire_core.protocol.packet import Packet
from empire_core.services.spy import SpyResult, SpyService
from empire_core.state.models import Alliance, Building, Castle, Player, Resources
from empire_core.state.world_models import Movement, MovementResources
from empire_core.utils.enums import KingdomType, MapObjectType, MovementType
from empire_core.utils.events import GameEvent
from empire_core.utils.troops import get_troop_ids, troop_data_available

try:
    __version__ = version(__package__ or "empire-core")
except PackageNotFoundError:  # pragma: no cover - exercised in tests via monkeypatch
    # Imported from a source checkout / vendored tree with no installed
    # distribution metadata (e.g. PYTHONPATH=src). Import must still succeed.
    __version__ = "0.0.0.dev0"

__all__ = [
    "EmpireClient",
    "EmpireConfig",
    "AccountPool",
    "Account",
    "accounts",
    # Exceptions
    "EmpireError",
    "NetworkError",
    "ConnectionClosedError",
    "LoginError",
    "LoginCooldownError",
    "PacketError",
    "EmpireTimeoutError",
    "CommandError",
    "GGEError",
    "PoolExhaustedError",
    # State models (live game state for the logged-in account)
    "Player",
    "Castle",
    "Resources",
    "Building",
    "Alliance",
    "Movement",
    "MovementResources",
    # Protocol models (parsed server responses)
    "Packet",
    "CastleInfo",
    "AllianceInfo",
    "AllianceMember",
    "RankingEntry",
    "MapAreaItem",
    "MapObject",
    "SpyCastleInfo",
    "Commander",
    "Castellan",
    "Equipment",
    # Services / results
    "ScanResult",
    "SpyService",
    "SpyResult",
    # Enums
    "Kingdom",
    "EquipmentSlot",
    "MapItemType",
    "MovementType",
    "MapObjectType",
    "KingdomType",
    "GameEvent",
    # Helpers
    "decode_chat_text",
    "encode_chat_text",
    "troop_data_available",
    "get_troop_ids",
]
