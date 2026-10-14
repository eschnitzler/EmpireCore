"""Every state read a user wants has a home on its game area's service, so nobody has to look in client.state."""

import ast
import inspect
from pathlib import Path

import empire_core
from empire_core.state.manager import GameState

PACKAGE = Path(empire_core.__file__).parent

# Readers that stay on client.state: freshness bookkeeping, and get_event, whose per-event
# overloads a service property cannot carry under every type checker
STATE_ONLY = {
    "get_castle_last_updated": "freshness of one castle's details",
    "get_castle_age": "freshness of one castle's details",
    "get_player_last_updated": "freshness of the player data",
    "get_events_last_updated": "freshness of the events",
    "get_last_packet_time": "freshness of one packet kind",
    "get_packet_times": "freshness of every packet kind",
    "get_event": "typed per event by overloads; client.events.running holds them all",
}


def _state_readers() -> set[str]:
    return {
        name for name, member in inspect.getmembers(GameState, inspect.isfunction) if name.startswith(("get_", "is_"))
    }


def _fronted() -> set[str]:
    """The readers a public service member hands out as they are: its body returns the state read."""
    fronted: set[str] = set()
    for path in PACKAGE.glob("*/service.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
                continue
            returned = node.body[-1]
            if (
                isinstance(returned, ast.Return)
                and isinstance(call := returned.value, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and ast.unparse(call.func.value) == "self.client.state"
            ):
                fronted.add(call.func.attr)
    return fronted


def test_every_state_reader_is_read_through_a_service() -> None:
    missing = sorted(_state_readers() - _fronted() - set(STATE_ONLY))
    assert not missing, f"read these through the service of their game area, or list them in STATE_ONLY: {missing}"


def test_the_state_only_readers_exist() -> None:
    assert not set(STATE_ONLY) - _state_readers()


def test_each_property_hands_out_what_state_holds() -> None:
    from empire_core.services.base import BaseService
    from tests.service_helpers import make_client

    client = make_client(state=GameState())
    services = {type(s).__name__: s for s in vars(client).values() if isinstance(s, BaseService)}
    for path in PACKAGE.glob("*/service.py"):
        for cls in [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef)]:
            for node in cls.body:
                if not (
                    isinstance(node, ast.FunctionDef) and any(ast.unparse(d) == "property" for d in node.decorator_list)
                ):
                    continue
                returned = node.body[-1]
                if not (isinstance(returned, ast.Return) and isinstance(call := returned.value, ast.Call)):
                    continue
                func = call.func
                if isinstance(func, ast.Attribute) and ast.unparse(func.value) == "self.client.state" and not call.args:
                    reader = getattr(client.state, func.attr)
                    assert getattr(services[cls.name], node.name) == reader(), f"{cls.name}.{node.name}"
