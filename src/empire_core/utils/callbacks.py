"""
The callback registry: each owner declares its events once, and keeps every subscription in one store.

An owner (the client, its state, a service) declares an event as a class attribute, typed by
the arguments its callbacks take::

    on_chat_message = Event[AllianceChatMessageResponse]()
    on_disconnect = Event[()]()

``owner.on_chat_message(callback)`` registers and returns the callback, so
``@owner.on_chat_message`` works as a decorator; ``owner.on_chat_message.remove(callback)``
unregisters, and the owner fires the event through ``owner.on_chat_message.calls()``, a
snapshot taken under the store's lock. The store is the owner's ``_registry``.

An event whose callbacks may take one of several signatures is declared by its callback
type instead: ``on_movement_arrived = EventOf[MovementEventCallback]()``.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar, cast, overload

from typing_extensions import TypeVarTuple, Unpack

C = TypeVar("C", bound=Callable[..., Any])
Args = TypeVarTuple("Args")


class Registry:
    """Every callback registered on one owner, by event name, guarded by one lock.

    ``unique``: registering a callback already registered is a no-op; otherwise it fires
    once per registration. ``missing_ok``: removing a callback not registered is a no-op;
    otherwise it raises ``ValueError``. Removing takes out the first registration.
    """

    def __init__(
        self, lock: AbstractContextManager[Any] | None = None, *, unique: bool = False, missing_ok: bool = False
    ) -> None:
        self._lock = lock if lock is not None else threading.Lock()
        self._unique = unique
        self._missing_ok = missing_ok
        self._callbacks: dict[str, list[Callable[..., Any]]] = {}

    def add(self, name: str, callback: Callable[..., Any]) -> None:
        with self._lock:
            callbacks = self._callbacks.setdefault(name, [])
            if not (self._unique and callback in callbacks):
                callbacks.append(callback)

    def remove(self, name: str, callback: Callable[..., Any]) -> None:
        with self._lock:
            callbacks = self._callbacks.get(name, [])
            if callback in callbacks:
                callbacks.remove(callback)
            elif not self._missing_ok:
                raise ValueError(f"callback {callback!r} is not registered for {name}")

    def calls(self, name: str) -> list[Callable[..., Any]]:
        with self._lock:
            return list(self._callbacks.get(name, ()))


class CallbackOwner(Protocol):
    """An owner of events: the client, its state or a service."""

    _registry: Registry


@dataclass(frozen=True)
class BoundEvent(Generic[C]):
    """One owner's event: call it to register a callback, ``remove`` it to unregister."""

    name: str
    registry: Registry

    def __call__(self, callback: C) -> C:
        """Register ``callback`` and return it, so the event also works as a decorator."""
        self.registry.add(self.name, callback)
        return callback

    def remove(self, callback: C) -> None:
        self.registry.remove(self.name, callback)

    def calls(self) -> list[C]:
        """The callbacks registered now, in the order registered."""
        return cast(list[C], self.registry.calls(self.name))


class EventOf(Generic[C]):
    """An event declared as ``on_<name>`` by its callback type: bound to an instance, the declaration on the class."""

    name: str

    def __set_name__(self, owner: type, attribute: str) -> None:
        if not attribute.startswith("on_"):
            raise TypeError(f"{owner.__name__}.{attribute}: an event is declared as on_<name>")
        self.name = attribute.removeprefix("on_")

    @overload
    def __get__(self, owner: None, owner_type: type) -> EventOf[C]: ...

    @overload
    def __get__(self, owner: CallbackOwner, owner_type: type) -> BoundEvent[C]: ...

    def __get__(self, owner: CallbackOwner | None, owner_type: type) -> EventOf[C] | BoundEvent[C]:
        return self if owner is None else self.of(owner)

    def of(self, owner: CallbackOwner) -> BoundEvent[C]:
        return BoundEvent(self.name, owner._registry)


class Event(EventOf[Callable[[Unpack[Args]], object]], Generic[Unpack[Args]]):
    """An event declared by the arguments its callbacks take: ``Event[Movement, bool]``, ``Event[()]``."""

    if sys.version_info < (3, 11):

        def __class_getitem__(cls, params: Any) -> Any:
            # Python 3.10's Generic refuses Event[()]
            return super().__class_getitem__(Unpack[tuple[()]] if params == () else params)  # type: ignore[misc]


def declared(owner: CallbackOwner) -> Iterator[BoundEvent[Any]]:
    """Every event ``owner``'s class and its bases declare, bound to ``owner``."""
    for cls in type(owner).__mro__:
        for value in vars(cls).values():
            if isinstance(value, EventOf):
                yield value.of(owner)
