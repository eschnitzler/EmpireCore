"""What the output pane shows: text as it was written, and results kept as values that re-flow to its width."""

import threading
from collections import deque
from dataclasses import dataclass
from typing import Any

from empire_core.console.pretty import pretty

OUTPUT_CHARS = 200_000


@dataclass(frozen=True)
class Result:
    value: Any


class OutputLog:
    """Thread-safe: written to from any thread, rendered on the render thread.

    The oldest entries go once the rendered text passes ``limit`` characters.
    """

    def __init__(self, limit: int = OUTPUT_CHARS) -> None:
        self.limit = limit
        self._entries: deque[tuple[str | Result, str]] = deque()
        self._pending: list[str | Result] = []
        self._width = 0
        self._size = 0
        self._joined = ""
        self._cleared = False
        self._lock = threading.Lock()

    def write(self, text: str) -> None:
        with self._lock:
            self._pending.append(text)

    def show(self, value: Any) -> None:
        with self._lock:
            self._pending.append(Result(value))

    def clear(self) -> None:
        with self._lock:
            self._pending.clear()
            self._cleared = True

    def render(self, width: int) -> tuple[str, bool]:
        """The whole text at ``width``, and whether it changed since the last call."""
        with self._lock:
            pending, self._pending = self._pending, []
            cleared, self._cleared = self._cleared, False
        if cleared:
            self._entries.clear()
            self._size = 0
        changed = cleared or bool(pending) or width != self._width
        if not changed:
            return self._joined, False
        if width != self._width:
            self._width = width
            self._entries = deque((entry, self._text(entry)) for entry, _ in self._entries)
            self._size = sum(len(text) for _, text in self._entries)
        for entry in pending:
            text = self._text(entry)
            self._entries.append((entry, text))
            self._size += len(text)
        while self._size > self.limit and self._entries:
            self._size -= len(self._entries.popleft()[1])
        self._joined = "".join(text for _, text in self._entries)
        return self._joined, True

    def _text(self, entry: str | Result) -> str:
        return pretty(entry.value, width=self._width) + "\n" if isinstance(entry, Result) else entry
