"""
Cancelling long calls: spy missions and kingdom scans take a ``cancel`` event.

A call that takes ``cancel: threading.Event`` looks at it between requests,
never during one. A request in flight is left to end with its own reply or
timeout, so its waiter is never abandoned and its reply cannot be taken by the
next request for that command (see ``Connection.request``); cancelling is
noticed within one request's timeout. Setting the event is the whole API: one
event can cancel many calls, for example at shutdown.
"""

import threading
import time


def sleep_unless_cancelled(seconds: float, cancel: threading.Event | None) -> bool:
    """Sleep ``seconds``, waking as soon as ``cancel`` is set; whether it is set."""
    if cancel is None:
        time.sleep(seconds)
        return False
    return cancel.wait(seconds)


__all__ = ["sleep_unless_cancelled"]
