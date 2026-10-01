"""Harness shared by the service tests: a scripted connection and a stub client."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, cast

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.enums import Kingdom
from empire_core.exceptions import EmpireTimeoutError
from empire_core.network.connection import ResponseWaiter
from empire_core.protocol.models import AttackWave, WaveFlank
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
    return json.loads(raw)


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
        self.sent: list[str] = []
        self.requested: list[str] = []
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

    def request(self, data: str, cmd_id: str, timeout: float = 5.0, accepts: Any = None) -> Packet:
        self.requested.append(cmd_id)
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
    def __init__(self, alliance_id: int = 0, level: int = 0):
        self.alliance_id = alliance_id
        self.level = level
        self.legendary_level = 0


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

    def update_from_packet(self, cmd_id: str, payload: object) -> None:
        self.updates.append((cmd_id, payload))

    def get_local_player(self) -> StubPlayer | None:
        return self.local_player

    def get_castles(self) -> list[Castle]:
        return list(self.castles)

    def get_all_movements(self) -> list:
        self.events.append("get_all_movements")
        return list(self.movements)

    def reset(self) -> None:
        self.events.append("reset")


def make_client(
    script: dict[str, Any] | None = None,
    state: StubState | None = None,
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
    stub = state or StubState()
    if castles is not None:
        stub.castles = gcl_castles(*castles)
    client.state = stub  # type: ignore[assignment]
    client.game_data = None
    client.is_logged_in = True
    client._handlers = {}
    client._handlers_lock = threading.Lock()
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
    return AttackWave(
        L=WaveFlank(U=units or [], T=tools or []),
        M=WaveFlank(U=middle_units or []),
        R=WaveFlank(),
    )
