"""
The callback registry: each owner declares its events once, and keeps every subscription in one store.

An owner (the client, its state, a service) declares an event as a class attribute::

    on_chat_message = Callbacks[Callable[[AllianceChatMessageResponse], None]]()
    remove_chat_message_callback = Remover(on_chat_message)

``owner.on_chat_message(callback)`` registers, ``owner.remove_chat_message_callback(callback)``
unregisters, and the owner fires the event through ``owner.on_chat_message.calls()``, a
snapshot taken under the store's lock. The store is the owner's ``_registry``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar, cast, overload

C = TypeVar("C", bound=Callable[..., Any])


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
class BoundCallbacks(Generic[C]):
    """One owner's event: call it to register a callback."""

    name: str
    registry: Registry

    def __call__(self, callback: C) -> None:
        self.registry.add(self.name, callback)

    def remove(self, callback: C) -> None:
        self.registry.remove(self.name, callback)

    def calls(self) -> list[C]:
        """The callbacks registered now, in the order registered."""
        return cast(list[C], self.registry.calls(self.name))


class Callbacks(Generic[C]):
    """An event declared as ``on_<name>``: registration on an instance, the declaration on the class."""

    name: str

    def __set_name__(self, owner: type, attribute: str) -> None:
        if not attribute.startswith("on_"):
            raise TypeError(f"{owner.__name__}.{attribute}: an event is declared as on_<name>")
        self.name = attribute.removeprefix("on_")

    @overload
    def __get__(self, owner: None, owner_type: type) -> Callbacks[C]: ...

    @overload
    def __get__(self, owner: CallbackOwner, owner_type: type) -> BoundCallbacks[C]: ...

    def __get__(self, owner: CallbackOwner | None, owner_type: type) -> Callbacks[C] | BoundCallbacks[C]:
        return self if owner is None else self.of(owner)

    def of(self, owner: CallbackOwner) -> BoundCallbacks[C]:
        return BoundCallbacks(self.name, owner._registry)


class Remover(Generic[C]):
    """The ``remove_<name>_callback`` of an ``on_<name>``: unregisters on an instance."""

    def __init__(self, callbacks: Callbacks[C]) -> None:
        self.callbacks = callbacks

    def __set_name__(self, owner: type, attribute: str) -> None:
        if attribute != f"remove_{self.callbacks.name}_callback":
            raise TypeError(
                f"{owner.__name__}.{attribute}: the remover of on_{self.callbacks.name} is named "
                f"remove_{self.callbacks.name}_callback"
            )

    @overload
    def __get__(self, owner: None, owner_type: type) -> Remover[C]: ...

    @overload
    def __get__(self, owner: CallbackOwner, owner_type: type) -> Callable[[C], None]: ...

    def __get__(self, owner: CallbackOwner | None, owner_type: type) -> Remover[C] | Callable[[C], None]:
        return self if owner is None else self.callbacks.of(owner).remove


def declared(owner: CallbackOwner) -> Iterator[BoundCallbacks[Any]]:
    """Every event ``owner``'s class and its bases declare, bound to ``owner``."""
    for cls in type(owner).__mro__:
        for value in vars(cls).values():
            if isinstance(value, Callbacks):
                yield value.of(owner)
