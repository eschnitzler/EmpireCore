"""
Pacing of map area reads (``gaa``) per account.

The server bans an account for 12 hours (``IS_BANNED``) once it has read about
810,000 map tiles within a window of 29 to 31 seconds, whatever the request
size and whatever other commands go with it, so an account can read about
27,000 tiles a second for as long as it likes. The limit is per account:
several accounts on one address each have their own. The game client has no
such limit of its own: it reads only the part of the map on screen, so it
never comes near. Measured on server build 6.1174.6 (2026-10-12):

Bursts of map area reads, one fresh account each:

=========  ===========  ========  =============
Side       Requests/s   Requests  Outcome
=========  ===========  ========  =============
90         ~16          105       banned
90         ~4           105       banned
60         ~16          228       banned
60         ~16          150       not banned
30         ~22          150       not banned
90         ~2           150       not banned
=========  ===========  ========  =============

A full green kingdom scan through this pacer:

=============  ==============================  ==========================
Tiles/s        Accounts at once                Outcome
=============  ==============================  ==========================
28,000         1                               banned after 30.6 s
26,000         1                               not banned (90 s)
25,000         5                               not banned
24,000         1                               not banned (97 s)
11,700         5                               not banned (199 s)
=============  ==============================  ==========================

The pacer spaces requests by their tile count, with no burst allowance, so no
stretch of the window ever holds more than the rate allows.
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
