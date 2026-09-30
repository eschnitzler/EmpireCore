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
from empire_core.alliance.models.info import AllianceInfo, AllianceMember
from empire_core.army.models.units import AttackWave, WaveFlank
from empire_core.castle.models.castles import CastleInfo
from empire_core.client.client import EmpireClient
from empire_core.commanders.models.equipment import Equipment
from empire_core.commanders.models.roster import Castellan, Commander
from empire_core.config import EmpireConfig
from empire_core.enums import AttackType, EquipmentSlot, Kingdom, LootPriority, MapItemType, MovementType, SpyType
from empire_core.exceptions import (
    AmbiguousLookupError,
    AttackInProgressError,
    CommandError,
    ConnectionClosedError,
    EmpireError,
    EmpireTimeoutError,
    GameDataNotLoadedError,
    LoginCooldownError,
    LoginError,
    NetworkError,
    PacketError,
    ReceiveThreadError,
)
from empire_core.gamedata import GameData, ToolStats, UnitStats
from empire_core.map.models.areas import MapObject
from empire_core.map.models.items import MapAreaItem
from empire_core.map.scanner import ScanResult
from empire_core.messages.models import SpyCastleInfo
from empire_core.movements.tracked import Movement, MovementResources
from empire_core.pool import AccountPool, PoolExhaustedError
from empire_core.protocol.errors import GGEError
from empire_core.protocol.packet import Packet
from empire_core.protocol.text import decode_json_text, encode_json_text
from empire_core.ranking.models import RankingEntry
from empire_core.spy.service import SpyResult, SpyService
from empire_core.state.models import Alliance, Building, Castle, Player, Resources
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
    "AttackInProgressError",
    "GameDataNotLoadedError",
    "AmbiguousLookupError",
    "GGEError",
    "PoolExhaustedError",
    "ReceiveThreadError",
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
    "AttackWave",
    "WaveFlank",
    # Services / results
    "ScanResult",
    "GameData",
    "UnitStats",
    "ToolStats",
    "SpyService",
    "SpyResult",
    # Enums
    "Kingdom",
    "AttackType",
    "LootPriority",
    "SpyType",
    "EquipmentSlot",
    "MapItemType",
    "MovementType",
    "GameEvent",
    # Helpers
    "decode_json_text",
    "encode_json_text",
    "troop_data_available",
    "get_troop_ids",
]
