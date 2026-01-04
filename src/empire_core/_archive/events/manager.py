import asyncio
import inspect
import logging
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Type,
)

from empire_core.events.base import Event

logger = logging.getLogger(__name__)

EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


class EventManager:
    def __init__(self):
        # Map EventType -> List[Handler]
        self._listeners: Dict[Type[Event], List[EventHandler]] = {}

    def subscribe(self, event_type: Type[Event], handler: EventHandler):
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(handler)
        logger.debug(f"Registered handler {handler.__name__} for {event_type.__name__}")

    def listen(self, func: EventHandler):
        """
        Decorator to register an event handler.
        Infers the event type from the first argument's type hint.
        """
        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        if not params:
            raise ValueError(f"Handler {func.__name__} must have at least one argument (the event).")

        # Get type hint of first arg
        event_arg = params[0]
        if event_arg.annotation is inspect.Parameter.empty:
            raise ValueError(
                f"Handler {func.__name__} argument '{event_arg.name}' must have a type hint (e.g. 'event: AttackEvent')."
            )

        event_type = event_arg.annotation

        # Verify it's an Event subclass (or valid type)
        # We accept any type for flexibility, but ideally it's an Event
        self.subscribe(event_type, func)
        return func

    async def emit(self, event: Event):
        event_type = type(event)
        # Dispatch to specific listeners
        handlers = self._listeners.get(event_type, [])

        # Also dispatch to listeners of parent classes?
        # (e.g. PacketEvent listeners might want all PacketEvents)
        # For simplicity, currently exact match.
        # But to support 'Event' (all events), we can check mro.

        # Check MRO for polymorphism
        for cls in event_type.mro():
            if cls in self._listeners:
                if cls is not event_type:
                    handlers.extend(self._listeners[cls])

        # Dedup handlers?
        handlers = list(set(handlers))

        if not handlers:
            # logger.debug(f"No listeners for {event_type.__name__}")
            return

        # Run all listeners in parallel
        tasks: List[Coroutine] = []
        for func in handlers:
            tasks.append(func(event))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
