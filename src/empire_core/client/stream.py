"""
Every client callback as one asyncio stream, for code that runs on an event loop.

The library stays threaded; a stream of :meth:`EmpireClient.listen` subscribes to the
callbacks inside ``async with`` and hands each call to a loop.
The game client decides none of this: it is library threading.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from types import TracebackType
from typing import TYPE_CHECKING, Any, Generic

from typing_extensions import TypeVarTuple, Unpack

from empire_core.exceptions import EventStreamOverflowError
from empire_core.services.base import BaseService
from empire_core.utils.callbacks import CallbackOwner, declared

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

Args = TypeVarTuple("Args")


@dataclass(frozen=True)
class ClientEvent(Generic[Unpack[Args]]):
    """One callback call, as an :class:`EventStream` delivers it.

    ``name`` is the registration's name without ``on_``: ``"incoming_attack"`` for
    ``client.state.on_incoming_attack``, ``"chat_message"`` for ``client.alliance.on_chat_message``.
    ``args`` are what a callback registered there is called with: one model for most,
    ``(old, new)`` for ``"incoming_attack_updated"`` and ``"occupation_updated"``,
    ``(movement, captured)`` for ``"occupation_ended"``,
    ``(movement_id, movement)`` for the movement callbacks, ``(error,)`` for ``"session_lost"``,
    ``(attempt, wait, error)`` for ``"session_retry"``,
    none for ``"disconnect"`` and ``"session_restored"``. From a stream of one registration,
    ``args`` is typed as that registration's callback parameters.
    """

    name: str
    args: tuple[Unpack[Args]]


@dataclass(frozen=True)
class CallbackSource:
    """An event the client, its state or a service declares as ``on_<name>``."""

    name: str
    register: Callable[[Callable[..., Any]], object]
    unregister: Callable[[Callable[..., Any]], None]
    on_callback_thread: bool


def callback_sources(client: EmpireClient) -> dict[str, CallbackSource]:
    """Every event the client, its state and its services declare (``Event``), by name."""
    services = [owner for owner in vars(client).values() if isinstance(owner, BaseService)]
    owners: list[CallbackOwner] = [client, client.state, *services]
    return {
        callbacks.name: CallbackSource(callbacks.name, callbacks, callbacks.remove, owner is client.state)
        for owner in owners
        for callbacks in declared(owner)
    }


_END = object()


class EventStream(Generic[Unpack[Args]]):
    """The calls of some callback registrations, delivered on an event loop in packet order.

    Made by :meth:`EmpireClient.listen`. Iterate it with ``async for``; each item is a
    :class:`ClientEvent`. Every call reaches the loop through the state callback thread,
    the state's own callbacks as they run there and the others queued behind them from
    the receive thread, so the events come in the order their packets came, whatever
    registration they belong to.

    It listens for the length of one ``async with``: entering subscribes, leaving (or
    :meth:`close`) stops listening, and a stream not entered refuses to be iterated.
    :meth:`EmpireClient.close_streams` ends it after the events already on their way.
    Sessions do not: a session that drops is a ``"disconnect"`` event, and after
    :meth:`EmpireClient.close` the stream keeps listening, so it delivers the next
    login's events, as the callbacks do.
    """

    def __init__(
        self,
        client: EmpireClient,
        sources: list[CallbackSource],
        loop: asyncio.AbstractEventLoop,
        maxsize: int,
    ) -> None:
        self._client = client
        self._sources = sources
        self._entered = False
        self._loop = loop
        self._maxsize = maxsize
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize)
        self._ending = False
        self._overflowed = False
        self._subscribed: list[tuple[Callable[[Callable[..., Any]], None], Callable[..., Any]]] = []
        self._subscription_lock = threading.Lock()

    def _deliver(self, name: str, *args: Any) -> None:
        try:
            self._loop.call_soon_threadsafe(self._put, ClientEvent(name, args))
        except RuntimeError:
            self._unsubscribe()

    def _put(self, event: Any) -> None:
        if self._ending:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._overflowed = True
            self._unsubscribe()
            self._end()

    def _end(self) -> None:
        if not self._ending:
            self._ending = True
            if not self._queue.full():
                self._queue.put_nowait(_END)

    def _unsubscribe(self) -> None:
        with self._subscription_lock:
            subscribed, self._subscribed = self._subscribed, []
        for unregister, callback in subscribed:
            try:
                unregister(callback)
            except ValueError:
                pass
        self._client._forget_stream(self)

    def _finish(self) -> None:
        """Stop listening and end the stream after the events already queued for it."""
        self._unsubscribe()
        state = self._client.state
        with state._executor_lock:
            closed = state._callback_executor is None
        if closed:
            self._post(self._end)
        else:
            state._dispatch_callback(self._post, self._end)

    def _post(self, call: Callable[[], None]) -> None:
        try:
            self._loop.call_soon_threadsafe(call)
        except RuntimeError:
            pass

    def close(self) -> None:
        """Stop listening and end the stream after the events it already holds. Safe from any thread."""
        self._unsubscribe()
        self._post(self._end)

    def __aiter__(self) -> EventStream[Unpack[Args]]:
        return self

    async def __anext__(self) -> ClientEvent[Unpack[Args]]:
        if not self._entered:
            raise RuntimeError("an EventStream listens only inside async with; enter it first")
        if self._ending and self._queue.empty():
            raise self._ended()
        event = await self._queue.get()
        if event is _END:
            raise self._ended()
        return event

    def _ended(self) -> Exception:
        if self._overflowed:
            return EventStreamOverflowError(f"{self._maxsize} events waited unread; the stream stopped listening")
        return StopAsyncIteration()

    async def __aenter__(self) -> EventStream[Unpack[Args]]:
        if self._entered:
            raise RuntimeError("an EventStream is entered once; call client.listen() again")
        self._entered = True
        with self._subscription_lock:
            self._client._remember_stream(self)
            for source in self._sources:
                callback = partial(self._deliver, source.name)
                if not source.on_callback_thread:
                    callback = partial(self._client.state._dispatch_callback, callback)
                source.register(callback)
                self._subscribed.append((source.unregister, callback))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
