"""
Pacing of map area reads (``gaa``) per account.

The server bans an account for 12 hours (``IS_BANNED``) once it has read about
810,000 map tiles within a window of roughly 26 to 50 seconds, whatever the
request size and whatever other commands go with it. The game client has no
such limit of its own: it reads only the part of the map on screen, so it
never comes near. Measured on server build 6.1174.6 (2026-10-12), on fresh
accounts in one kingdom:

=========  ===========  ========  =============
Side       Requests/s   Requests  Outcome
=========  ===========  ========  =============
90         ~16          105       banned
90         ~4           105       banned
60         ~16          228       banned
60         ~16          150       not banned
30         ~22          150       not banned
90         ~2           150       not banned
90         ~1.45        400       not banned
=========  ===========  ========  =============

The pacer spaces requests by their tile count, with no burst allowance: with
the window not known exactly, any burst could be the one that crosses it.
"""

import math
import threading
import time
from collections.abc import Callable

from empire_core.utils.cancel import sleep_unless_cancelled


class MapAreaPacer:
    """
    Spaces one account's map area reads so they stay under the server's tile budget.

    Each read waits until the one before it has had ``tiles / tiles_per_second``
    seconds to itself. Threads sharing a client share its pacer, so several
    scans on one account are paced together.
    """

    def __init__(self, tiles_per_second: Callable[[], float]) -> None:
        self._tiles_per_second = tiles_per_second
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self, tiles: int, cancel: threading.Event | None = None) -> bool:
        """Wait for the turn of a read of ``tiles`` tiles; whether ``cancel`` was set first."""
        rate = self._tiles_per_second()
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + (0.0 if math.isinf(rate) else tiles / rate)
        if start > now:
            return sleep_unless_cancelled(start - now, cancel)
        return cancel is not None and cancel.is_set()


__all__ = ["MapAreaPacer"]
