"""Harness shared by the service tests: a scripted connection and a stub client."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, cast

from empire_core.client.client import EmpireClient
from empire_core.client.session import Session
from empire_core.commanders.models.roster import CommanderRoster
from empire_core.config import EmpireConfig
from empire_core.enums import Kingdom
from empire_core.events.models import SpecialEvent
from empire_core.exceptions import EmpireTimeoutError, StateNotLoadedError
from empire_core.gamedata import GameData, Horse
from empire_core.map.models.world import MapSize, ServerInfoResponse
from empire_core.network.connection import ResponseWaiter
from empire_core.player import BoosterInfoResponse
from empire_core.player.models.account import BoostedGlobalEffectsResponse
from empire_core.protocol.models import AttackWave
from empire_core.protocol.packet import Packet
from empire_core.state.manager import GameState
from empire_core.state.models import Castle, Player


def placed(slots: list[list[int]]) -> list[list[int]]:
    """A wave container's filled slots; fill_wave pads the rest with [-1, 0]."""
    return [slot for slot in slots if slot[0] != -1]


# =============================================================================
# Harness
# =============================================================================


def xt_packet(command: str, payload: Any = None, error_code: int = 0) -> Packet:
    """Build a response packet the way the wire delivers it."""
    body = "{}" if payload is None else json.dumps(payload)
    return Packet.from_bytes(f"%xt%{command}%1%{error_code}%{body}%".encode())


def request_payload(data: str) -> dict[str, Any]:
    """Recover the JSON payload from a built request packet.

    Split with maxsplit so a '%' inside the payload (encoded chat text uses
    '%5C' for a backslash) cannot truncate it.
    """
    raw = data.split("%", 5)[5]
    if raw.endswith("%"):
        raw = raw[:-1]
    # a frame with no parameter at all (sendEmptyCommandVO) reads as an empty payload
    return json.loads(raw) if raw else {}


# Live capture of an adi reply for a robber baron camp.
LIVE_ADI: dict[str, Any] = {
    "KID": 0,
    "HAWL": 1,
    "SCID": 2003,
    "gaa": {"AI": [2, 620, 231, -1, 0, -1, 0]},
    "gui": {
        "I": [[10, 10], [614, 2], [611, 1], [651, 300], [649, 300], [648, 300]],
        "SHI": [],
        "HI": [[9, 20]],
        "TU": [],
    },
    "gli": {
        "B": [{"ID": 1, "WID": 1, "VIS": 0, "LICID": 2003, "N": "", "GID": -1, "W": 2, "D": 9, "SPR": 1, "EQ": []}],
        "C": [
            {
                "ID": 0,
                "WID": 2,
                "VIS": 0,
                "N": "",
                "GID": -1,
                "W": 1,
                "D": 0,
                "SPR": 1,
                "EQ": [[6515211559, 6, 2, 10, 0, [[242, [25.0]]], 802, 22, 0, -1, -1, 1]],
            },
            {"ID": 2, "WID": 2, "VIS": 1, "N": "", "GID": -1, "W": 0, "D": 0, "SPR": 0, "EQ": []},
        ],
    },
    "AE": [],
}


class ScriptedConnection:
    """Scripted stand-in for Connection.

    ``script`` maps a command id to a Packet to return, an Exception to raise,
    or a list of either consumed one per call. Unscripted command ids get an
    empty successful packet, so an ``execute()`` call needs no scripting to
    succeed.

    ``pushes`` maps a command id to packets the server pushes right after
    answering it; they reach subscribers, as ``Connection._route_packet``
    hands every packet to them.
    """

    def __init__(self, script: dict[str, Any] | None = None, pushes: dict[str, list[Packet]] | None = None):
        self.script = script or {}
        self.room_id = -1
        self.pushes = pushes or {}
        self.subscribers: dict[str, list[Any]] = {}
        self.disconnect_listeners: list[Any] = []
        self.connected = True
        self.close_error: BaseException | None = None
        self.sent: list[str] = []
        self.requested: list[str] = []
        self.request_frames: list[str] = []
        self.request_payloads: list[tuple[str, dict[str, Any]]] = []
        self.waiters_created: list[str] = []
        self.waiters_canceled: list[str] = []
        self.waited_for: list[str] = []
        self.accepts: list[Any] = []
        self.locked: list[str] = []
        self.events: list[str] = []
        self.on_packet: Any = None
        self.on_disconnect = None

    def _resolve(self, cmd_id: str) -> Packet:
        result = self.script.get(cmd_id, xt_packet(cmd_id))
        if isinstance(result, list):
            result = result.pop(0) if result else xt_packet(cmd_id)
        if isinstance(result, Exception):
            raise result
        return result

    def send(self, data: str) -> None:
        self.sent.append(data)

    def send_and_drop_reply(self, data: str, cmd_id: str, window: float = 5.0) -> None:
        self.sent.append(data)

    def request(self, data: str, cmd_id: str, timeout: float = 5.0, accepts: Any = None) -> Packet:
        self.requested.append(cmd_id)
        self.request_frames.append(data)
        self.accepts.append(accepts)
        self.request_payloads.append((cmd_id, request_payload(data)))
        self.events.append(f"request:{cmd_id}")
        result = self._resolve(cmd_id)
        for pushed in self.pushes.pop(cmd_id, []):
            for callback in list(self.subscribers.get(pushed.command_id or "", [])):
                callback(pushed)
        if accepts is not None and result.error_code == 0 and not accepts(result):
            # Connection leaves a reply the check refuses to other waiters, so this one runs out
            raise EmpireTimeoutError(f"No {cmd_id} reply accepted")
        if self.on_packet is not None:
            # Connection feeds the state before it wakes the waiter
            self.on_packet(result)
        return result

    def create_waiter(self, cmd_id: str) -> ResponseWaiter:
        self.waiters_created.append(cmd_id)
        self.events.append(f"create_waiter:{cmd_id}")
        return ResponseWaiter()

    def cancel_waiter(self, cmd_id: str, waiter: ResponseWaiter) -> None:
        self.waiters_canceled.append(cmd_id)
        self.events.append(f"cancel_waiter:{cmd_id}")

    def wait_for_result(self, cmd_id: str, waiter: ResponseWaiter, timeout: float = 5.0) -> Packet:
        self.waited_for.append(cmd_id)
        self.events.append(f"wait_for_result:{cmd_id}")
        return self._resolve(cmd_id)

    def subscribe(self, cmd_id: str, callback: Any) -> None:
        self.subscribers.setdefault(cmd_id, []).append(callback)
        self.events.append(f"subscribe:{cmd_id}")

    def unsubscribe(self, cmd_id: str, callback: Any) -> None:
        if callback in self.subscribers.get(cmd_id, []):
            self.subscribers[cmd_id].remove(callback)
        self.events.append(f"unsubscribe:{cmd_id}")

    @contextmanager
    def command_lock(self, cmd_id: str, timeout: float = 5.0) -> Iterator[None]:
        self.locked.append(cmd_id)
        self.events.append(f"lock:{cmd_id}")
        yield
        self.events.append(f"unlock:{cmd_id}")

    def disconnect(self) -> None:
        self.connected = False

    generation = 0

    def run_if_current(self, generation: int, action: Any) -> bool:
        if generation != self.generation:
            return False
        action()
        return True

    def add_disconnect_listener(self, callback: Any) -> None:
        self.disconnect_listeners.append(callback)

    def remove_disconnect_listener(self, callback: Any) -> None:
        if callback in self.disconnect_listeners:
            self.disconnect_listeners.remove(callback)


class StubPlayer:
    def __init__(self, alliance_id: int = 0, level: int = 0, xp: int = 0):
        self.id = 0
        self.alliance_id = alliance_id
        self.level = level
        self.xp = xp
        self.legendary_level = 0
        self.model_fields_set = {"alliance_id", "level", "xp", "legendary_level"}


def stub_player(alliance_id: int = 0, level: int = 0) -> Player:
    """
    A stand-in for the real player record.

    Only the attributes the services read are set, so it is cast rather than
    constructed - a full Player needs a payload no test here cares about.
    """
    return cast(Player, StubPlayer(alliance_id=alliance_id, level=level))


OwnCastle = tuple[int, Kingdom] | tuple[int, Kingdom, int, int]


def gcl_castles(*castles: OwnCastle, owner_id: int = 1001) -> list[Castle]:
    """
    The castles a login gcl lists, as GameState reads them.

    Each castle is ``(castle_id, kingdom)`` or ``(castle_id, kingdom, x, y)``.
    """
    sections: dict[int, list[dict[str, Any]]] = {}
    for castle in castles:
        castle_id, kingdom = castle[0], castle[1]
        x, y = (castle[2], castle[3]) if len(castle) == 4 else (10, 20)
        row = [1, x, y, castle_id, owner_id, 1, 1, 1, 0, 0, f"Castle {castle_id}"]
        sections.setdefault(int(kingdom), []).append({"AI": row})
    gcl = {"C": [{"KID": kid, "AI": rows} for kid, rows in sections.items()]}
    state = GameState()
    try:
        state.update_from_packet("gbd", {"gpi": {"PID": owner_id}, "gcl": gcl})
        return state.get_castles()
    finally:
        state.shutdown()


LOGIN_SECTIONS: dict[str, Any] = {
    "gpi": {"PID": 1001, "PN": "me"},
    "rei": {"ARID": -1, "ARRT": 0, "BR": []},
    "boi": {"BO": [], "PA": 0, "PT": -1},
    "gmu": {"MP": 0, "TSBM": 0, "HMP": 0},
    "ufa": {"CF": 0, "HF": 0, "NHT": -1},
    "uar": {"FTM": {"CTXT": -1}, "BTM": {"CTXT": -1}, "ITM": {"TID": -1}, "PFX": "FAME", "SFX": "FAME"},
    "vli": {"AVP": 0, "RA": [], "FA": []},
    "gms": {"MS": 0, "BS": 0},
    "gli": {"C": [], "B": []},
    "nrf": {"NR": 0},
    "dql": {"PQL": 1},
}
"""The sections every login gbd brings, with nothing in them."""

SERVER_INFO: dict[str, Any] = {"XML_EP": "787.03", "minNameSize": 3, "sectorCountX": 99, "sectorCountY": 99}
"""The server info a connection opens with: a map of 99 by 99 sectors."""


def logged_in_state(**sections: Any) -> GameState:
    """A GameState fed the server info and a login gbd: :data:`LOGIN_SECTIONS` with ``sections`` replacing theirs."""
    state = GameState()
    state.update_from_packet("nfo", SERVER_INFO)
    state.update_from_packet("gbd", {**LOGIN_SECTIONS, **sections})
    return state


class StubState:
    """Only the members the services actually touch."""

    def __init__(
        self,
        local_player: StubPlayer | None = None,
        movements: list | None = None,
        castles: list[Castle] | None = None,
    ):
        self.local_player = local_player
        self.movements = movements if movements is not None else []
        self.castles = castles if castles is not None else []
        self.events: list[str] = []
        self.updates: list[tuple[str, object]] = []
        self.special_events: dict[int, SpecialEvent] = {}
        self.boosted_global_effects: BoostedGlobalEffectsResponse | None = None
        self.boosts: Any = BoosterInfoResponse.model_validate(LOGIN_SECTIONS["boi"])
        self.commanders: CommanderRoster | None = None

    def update_from_packet(self, cmd_id: str, payload: object, error_code: int = 0) -> None:
        self.updates.append((cmd_id, payload))

    def get_local_player(self) -> StubPlayer:
        if self.local_player is None:
            raise StateNotLoadedError("The local player not loaded: log in first")
        return self.local_player

    def get_castles(self) -> list[Castle]:
        return list(self.castles)

    def get_map_size(self, kingdom: Kingdom) -> MapSize:
        return ServerInfoResponse.model_validate(SERVER_INFO).map_size(kingdom)

    def get_commanders(self) -> CommanderRoster:
        if self.commanders is None:
            raise StateNotLoadedError("Commanders not loaded: log in first")
        return self.commanders

    def get_boosts(self) -> Any:
        if self.boosts is None:
            raise StateNotLoadedError("Boosters not loaded: log in first")
        return self.boosts

    def get_event(self, event: int) -> SpecialEvent | None:
        return self.special_events.get(int(event))

    def get_boosted_global_effects(self) -> BoostedGlobalEffectsResponse | None:
        return self.boosted_global_effects

    def get_last_packet_time(self, cmd_id: str) -> None:
        return None

    def get_all_movements(self) -> list:
        self.events.append("get_all_movements")
        return list(self.movements)

    def reset(self) -> None:
        self.events.append("reset")


COIN_HORSE = Horse.HORSE_STABLE1
"""A horse paid in coins, as items 786.03 has it."""
RUBY_HORSE = Horse.WARHORSE_STABLE1
"""A horse paid in rubies, as items 786.03 has it."""


def with_horses(client: EmpireClient) -> EmpireClient:
    """Give ``client`` game data with :data:`COIN_HORSE` and :data:`RUBY_HORSE`."""
    rows = [
        {"wodID": str(int(COIN_HORSE)), "costFactorC1": "1", "costFactorC2": "0.0"},
        {"wodID": str(int(RUBY_HORSE)), "costFactorC1": "0", "costFactorC2": "1.0"},
    ]
    client.game_data = GameData.parse("test", {"horses": rows})
    return client


PREBUILT_CASTLE_ITEMS: dict[str, Any] = {
    "prebuiltcastles": [
        {"preBuiltCastleID": "1", "comment1": "FactionKingdom", "comment2": "CheapCamp", "spaceIDs": "10",
         "minLevel": 15, "costWood": "900", "costStone": "900"},
        {"preBuiltCastleID": "3", "comment1": "FactionKingdom", "comment2": "C2Camp", "spaceIDs": "10",
         "minLevel": 15, "costC2": "49000"},
        {"preBuiltCastleID": "4", "comment1": "IceKingdom", "comment2": "CheapCamp", "spaceIDs": "2", "minLevel": 25,
         "costWood": "7000", "costStone": "7000", "costFood": "5000", "costC1": "5000", "costC2": "10000"},
        {"preBuiltCastleID": "6", "comment1": "IceKingdom", "comment2": "C2Camp", "spaceIDs": "2", "minLevel": 18,
         "costC2": "29000", "shownDiscount": "50"},
        {"preBuiltCastleID": "8", "comment1": "DessertKingdom", "comment2": "ResourceCamp", "spaceIDs": "1",
         "minLevel": 40, "costWood": "39000", "costStone": "39000", "costC2": "50000"},
        {"preBuiltCastleID": "11", "comment1": "VulcanoKingdom", "comment2": "ResourceCamp", "spaceIDs": "3",
         "minLevel": 50, "costWood": "79000", "costC2": "80000"},
        {"preBuiltCastleID": "16", "comment1": "Storm Island", "comment2": "CheapCamp", "spaceIDs": "4",
         "minLevel": 35, "costWood": "10000", "costC1": "5000"},
        {"preBuiltCastleID": "18", "comment1": "Storm Island", "comment2": "C2Camp", "spaceIDs": "4",
         "minLevel": 35, "costC2": "59000"},
        {"preBuiltCastleID": "22", "comment1": "Underworld", "comment2": "CheapCamp", "spaceIDs": "23",
         "minLevel": 30, "costWood": "10000", "costC2": "10000"},
        {"preBuiltCastleID": "24", "comment1": "Underworld", "comment2": "C2Camp", "spaceIDs": "23", "minLevel": 30,
         "costC2": "29000"},
        {"preBuiltCastleID": "28", "comment1": "Bladecoast", "comment2": "CheapCamp", "spaceIDs": "22,27,28",
         "minLevel": 30, "costWood": "10000"},
        {"preBuiltCastleID": "31", "comment1": "temp Server", "comment2": "PreCampLevel11", "spaceIDs": "0",
         "costWood": "0", "costC1": "0"},
        {"preBuiltCastleID": "32", "comment1": "temp Server", "comment2": "PreCampLevel11C2", "spaceIDs": "0",
         "costC2": "20000"},
        {"preBuiltCastleID": "35", "comment1": "ABG", "comment2": "PreCampLevel11C2", "spaceIDs": "0", "minLevel": 15,
         "costC2": "19999"},
        {"preBuiltCastleID": "40", "comment1": "Temp Server", "comment2": "Castle Transportation", "spaceIDs": "0",
         "minLevel": 6, "isMainCastleCopy": "1"},
    ],
    "tempServerPreBuiltCastles": [
        {"preBuiltCastleID": "31", "startPlayerLevel": "11", "startResourceID": "1"},
        {"preBuiltCastleID": "32", "startPlayerLevel": "11", "startResourceID": "2", "costC2": "19999"},
        {"preBuiltCastleID": "40", "startPlayerLevel": "70", "startPlayerLegendLevel": "800", "startResourceID": "6",
         "costCastlePassageToken": "1", "castlePassageTokenPackageID": "2358"},
    ],
    "allianceBattleGroundPreBuiltCastles": [
        {"preBuiltCastleID": "35", "startPlayerLevel": "15", "startResourceID": "3", "costC2": "19999"},
    ],
    "islandPreBuiltCastles": [
        {"preBuiltCastleID": "16", "startPlayerLevel": "35", "startResourceID": "7"},
        {"preBuiltCastleID": "18", "startPlayerLevel": "35", "startResourceID": "9", "costC2": "59000"},
    ],
    "currencies": [{"currencyID": "8", "Name": "CastlePassageToken"}],
}  # fmt: skip
"""Prebuilt castle rows as items 788.02 has them, trimmed to the columns the tests read."""


def with_prebuilt_castles(client: EmpireClient) -> EmpireClient:
    """Give ``client`` game data with :data:`PREBUILT_CASTLE_ITEMS`."""
    client.game_data = GameData.parse("test", PREBUILT_CASTLE_ITEMS)
    return client


def make_client(
    script: dict[str, Any] | None = None,
    state: StubState | GameState | None = None,
    pushes: dict[str, list[Packet]] | None = None,
    castles: Sequence[OwnCastle] | None = None,
) -> EmpireClient:
    """
    Build a client with every service attached, but no socket.

    ``castles`` are the player's castles, read from a gcl as at login (see :func:`gcl_castles`).
    """
    client = EmpireClient.__new__(EmpireClient)
    client.config = EmpireConfig()
    client.username = "tester"
    client.password = "secret"
    client.connection = ScriptedConnection(script, pushes)  # type: ignore[assignment]
    stub = state or StubState(StubPlayer())
    if castles is not None:
        stub.castles = gcl_castles(*castles)  # type: ignore[assignment]
    client.state = stub  # type: ignore[assignment]
    client.game_data = None
    client.is_logged_in = True
    client._handlers = {}
    client._handlers_lock = threading.Lock()
    client._streams = set()
    client._streams_lock = threading.Lock()
    client.keep_session = False
    client._session = Session(client)
    client._registry = EmpireClient._new_registry()
    client._attach_services()
    return client


def conn(client: EmpireClient) -> ScriptedConnection:
    return client.connection  # type: ignore[return-value]


GOLDEN_GCL: dict[str, Any] = {
    "PID": 1001,
    "C": [
        {
            "KID": 0,
            "AI": [
                {
                    "AI": [
                        1,
                        512,
                        256,
                        2001,
                        1001,
                        2,
                        2,
                        2,
                        1,
                        0,
                        "Main Castle",
                        0,
                        0,
                        -1,
                        -1,
                        -1,
                        0,
                        0,
                        [],
                        0,
                    ],
                    "AOT": -1,
                    "TA": -1,
                },
                {
                    "AI": [
                        4,
                        510,
                        257,
                        2002,
                        1001,
                        1,
                        1,
                        1,
                        0,
                        0,
                        "Outpost North",
                        0,
                        0,
                        -1,
                        1,
                        -1,
                        0,
                        0,
                        [],
                        0,
                    ],
                    "TA": 0,
                },
            ],
        }
    ],
}


# =============================================================================
# AttackService
# =============================================================================


def wave(units=None, tools=None, middle_units=None):
    """A wave from wire-shaped [wod_id, amount] pairs."""
    return AttackWave.model_validate({"L": {"U": units or [], "T": tools or []}, "M": {"U": middle_units or []}})
