"""
Pacing of one account's attack sends (``cra``).

The server refuses an attack sent less than 4 seconds after the account's
previous one. The game client has no such limit of its own:
``CastleAttackData.sendAttack`` (bundle line 133852) sends the ``cra`` at
once, and no error id names the refusal, so the interval is server behavior
as observed, not a client constant.
"""

import threading
import time
from collections.abc import Callable

from empire_core.utils.cancel import sleep_unless_cancelled


class AttackSendPacer:
    """
    Spaces one account's attack sends at least ``interval`` seconds apart.

    Threads sharing a client share its pacer, so attacks sent from several
    threads on one account are paced together.
    """

    def __init__(self, interval: Callable[[], float]) -> None:
        self._interval = interval
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self, cancel: threading.Event | None = None) -> bool:
        """Wait for the next send's turn; whether ``cancel`` was set first."""
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + self._interval()
        if start > now:
            return sleep_unless_cancelled(start - now, cancel)
        return cancel is not None and cancel.is_set()


__all__ = ["AttackSendPacer"]
