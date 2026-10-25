"""Types the public API promises, asserted for mypy and for pyright (CI runs basedpyright on this package).

Each ``assert_type`` is checked statically by both checkers; at runtime it only returns its argument.
"""

from collections.abc import Callable

from typing_extensions import assert_type, get_overloads

from empire_core import Movement
from empire_core.events import (
    EVENT_CLASSES,
    AlienInvasionEvent,
    GachaEvent,
    SamuraiInvasionEvent,
    SpecialEvent,
    TravelingKnightsEvent,
)
from empire_core.gamedata.ids.events import Event
from empire_core.state import GameState


def test_get_event_is_typed_by_the_event(state: GameState) -> None:
    assert_type(state.get_event(Event.SAMURAI_INVASION), SamuraiInvasionEvent | None)
    assert_type(state.get_event(Event.BLOODCROW_INVASION), AlienInvasionEvent | None)
    assert_type(state.get_event(Event.CARNIVAL_OF_MASKS), GachaEvent | None)
    assert_type(state.get_event(Event.TRAVELING_KNIGHTS_67), TravelingKnightsEvent | None)
    assert_type(state.get_event(Event.TECHNICUS), SpecialEvent | None)
    assert_type(state.get_event(103), SpecialEvent | None)


def test_every_event_class_has_its_overload() -> None:
    typed: dict[Event, type] = {}
    for overload in get_overloads(GameState.get_event):
        hints = overload.__annotations__
        members = getattr(hints["event"], "__args__", ())
        if all(isinstance(member, Event) for member in members):
            returned = next(arg for arg in hints["return"].__args__ if arg is not type(None))
            typed.update(dict.fromkeys(members, returned))
    assert typed == EVENT_CLASSES


def test_an_event_decorates_and_keeps_the_callback_type(state: GameState) -> None:
    @state.on_incoming_attack
    def on_attack(movement: Movement) -> None: ...

    assert_type(on_attack, Callable[[Movement], object])
    assert state.on_incoming_attack.calls() == [on_attack]
