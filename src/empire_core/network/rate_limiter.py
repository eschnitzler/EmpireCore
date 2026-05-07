"""
Thread-safe rate limiter for EmpireCore WebSocket requests.
"""

import logging
import threading
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class DualRateLimiter:
    """
    A strictly precise Sliding Window Log rate limiter.

    Maintains a global token limit for all requests, plus specific limits for restricted
    commands (e.g., 'gaa'). Calculates sleep time cleanly without blocking other threads
    from queueing their own unrestricted commands.
    """

    def __init__(self, global_limit: int, command_limits: dict[str, int]):
        self.global_limit = global_limit
        self.command_limits = command_limits

        self._lock = threading.Lock()
        self._global_window: deque[float] = deque()
        self._command_windows: dict[str, deque[float]] = defaultdict(deque)

    def acquire(self, command: str) -> None:
        """
        Block the calling thread until it is safe to send the given command.
        Uses a Sliding Window Log (rolling 1000ms window).
        """
        while True:
            now = time.monotonic()

            with self._lock:
                # 1. Clean up expired timestamps (older than 1.0 second)
                while self._global_window and now - self._global_window[0] >= 1.0:
                    self._global_window.popleft()

                cmd_window = self._command_windows[command]
                while cmd_window and now - cmd_window[0] >= 1.0:
                    cmd_window.popleft()

                wait_time = 0.0

                # 2. Check command-specific limit first
                cmd_limit = self.command_limits.get(command)
                if cmd_limit and len(cmd_window) >= cmd_limit:
                    cmd_wait = 1.0 - (now - cmd_window[0])
                    wait_time = max(wait_time, cmd_wait)

                # 3. Check global limit
                if len(self._global_window) >= self.global_limit:
                    global_wait = 1.0 - (now - self._global_window[0])
                    wait_time = max(wait_time, global_wait)

                # 4. If limits are respected, consume token and proceed
                if wait_time <= 0:
                    self._global_window.append(now)
                    if cmd_limit:
                        cmd_window.append(now)
                    return

            # 5. If limits exceeded, sleep outside the lock
            # Add a 1ms buffer to prevent aggressive busy-spinning
            time.sleep(wait_time + 0.001)
