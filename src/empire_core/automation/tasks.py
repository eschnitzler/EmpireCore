"""
Asyncio Task Loop Helper
Inspired by discord.ext.tasks.

This module provides a simple way to run background tasks at a specific interval.
It is designed to be used as a decorator.

Usage:
    from empire_core.automation import tasks

    @tasks.loop(seconds=10)
    async def my_background_task():
        print("Doing something...")

    my_background_task.start()
"""

import asyncio
import datetime
import inspect
import logging
import traceback
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class Loop:
    """
    A background task loop.
    Created via the @tasks.loop decorator.
    """

    def __init__(
        self,
        coro: Callable[..., Awaitable[Any]],
        seconds: float,
        minutes: float,
        hours: float,
        count: Optional[int],
        reconnect: bool,
        loop: Optional[asyncio.AbstractEventLoop],
    ):
        self.coro = coro
        self.seconds = seconds
        self.minutes = minutes
        self.hours = hours
        self.count = count
        self.reconnect = reconnect
        self._loop = loop or asyncio.get_event_loop()

        self._task: Optional[asyncio.Task] = None
        self._injected_args: tuple = ()
        self._injected_kwargs: dict = {}
        self._stop_next_iteration = False
        self._current_loop = 0
        self._next_iteration: Optional[datetime.datetime] = None
        self._last_iteration: Optional[datetime.datetime] = None
        self._before_loop: Optional[Callable[..., Awaitable[Any]]] = None
        self._after_loop: Optional[Callable[..., Awaitable[Any]]] = None
        self._error_handler: Optional[Callable[[Exception], Awaitable[Any]]] = None

        # Calculate interval in seconds
        self._interval = seconds + (minutes * 60.0) + (hours * 3600.0)

        if self._interval < 0:
            raise ValueError("Interval cannot be negative")

    async def _runner(self, *args, **kwargs):
        """The main loop runner."""
        try:
            if self._before_loop:
                await self._before_loop(*args, **kwargs)
        except Exception as e:
            logger.error(f"Exception in before_loop for {self.coro.__name__}: {e}")
            if self._error_handler:
                await self._error_handler(e)
            return

        self._current_loop = 0
        self._stop_next_iteration = False

        # Main execution loop
        while True:
            if self._stop_next_iteration:
                break

            if self.count is not None and self._current_loop >= self.count:
                break

            self._last_iteration = datetime.datetime.now(datetime.timezone.utc)
            self._next_iteration = self._last_iteration + datetime.timedelta(seconds=self._interval)

            try:
                await self.coro(*args, **kwargs)
            except asyncio.CancelledError:
                self._stop_next_iteration = True
                raise
            except Exception as e:
                await self._handle_error(e)
                if not self.reconnect:
                    self._stop_next_iteration = True

            self._current_loop += 1

            if self._stop_next_iteration:
                break

            # Sleep until next iteration
            now = datetime.datetime.now(datetime.timezone.utc)
            if now < self._next_iteration:
                sleep_seconds = (self._next_iteration - now).total_seconds()
                await asyncio.sleep(sleep_seconds)

        try:
            if self._after_loop:
                await self._after_loop(*args, **kwargs)
        except Exception as e:
            logger.error(f"Exception in after_loop for {self.coro.__name__}: {e}")
            await self._handle_error(e)

    async def _handle_error(self, exception: Exception):
        """Internal error handling dispatch."""
        if self._error_handler:
            try:
                await self._error_handler(exception)
            except Exception as e:
                logger.error(f"Error in error handler for {self.coro.__name__}: {e}")
        else:
            logger.error(f"Unhandled exception in task {self.coro.__name__}: {exception}")
            traceback.print_exc()

    def start(self, *args, **kwargs):
        """
        Starts the background task.
        arguments passed here are passed to the coroutine.
        """
        if self._task is not None and not self._task.done():
            raise RuntimeError("Task is already running")

        self._injected_args = args
        self._injected_kwargs = kwargs
        self._task = self._loop.create_task(self._runner(*args, **kwargs))
        return self._task

    def stop(self):
        """Stops the background task cleanly after the current iteration."""
        self._stop_next_iteration = True

    def cancel(self):
        """Cancels the background task immediately."""
        if self._task:
            self._task.cancel()
        self._stop_next_iteration = True

    def restart(self, *args, **kwargs):
        """Restarts the task."""
        self.cancel()
        self.start(*args, **kwargs)

    def before_loop(self, coro):
        """Decorator to register a coroutine to run before the loop starts."""
        if not inspect.iscoroutinefunction(coro):
            raise TypeError("Expected coroutine function")
        self._before_loop = coro
        return coro

    def after_loop(self, coro):
        """Decorator to register a coroutine to run after the loop finishes."""
        if not inspect.iscoroutinefunction(coro):
            raise TypeError("Expected coroutine function")
        self._after_loop = coro
        return coro

    def error(self, coro):
        """Decorator to register a coroutine to handle errors in the loop."""
        if not inspect.iscoroutinefunction(coro):
            raise TypeError("Expected coroutine function")
        self._error_handler = coro
        return coro

    @property
    def is_running(self) -> bool:
        """Check if the task is currently running."""
        return self._task is not None and not self._task.done()

    @property
    def current_loop(self) -> int:
        """Get the current iteration count."""
        return self._current_loop


def loop(
    seconds: float = 0,
    minutes: float = 0,
    hours: float = 0,
    count: Optional[int] = None,
    reconnect: bool = True,
    loop: Optional[asyncio.AbstractEventLoop] = None,
):
    """
    Decorator to create a background task loop.

    Args:
        seconds: Duration in seconds between iterations.
        minutes: Duration in minutes.
        hours: Duration in hours.
        count: Optional number of loops to run before stopping.
        reconnect: If True, handles errors and continues. If False, stops on error.
        loop: Optional asyncio loop.
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Loop:
        return Loop(
            func,
            seconds=seconds,
            minutes=minutes,
            hours=hours,
            count=count,
            reconnect=reconnect,
            loop=loop,
        )

    return decorator
