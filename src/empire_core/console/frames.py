"""The frames the console has seen, and how one reads as a line or as detail."""

import json
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from empire_core.network.connection import Frame, FrameDirection

PREVIEW_CHARS = 70


@dataclass(frozen=True)
class Row:
    """A frame with its list line, formatted once when it arrives."""

    frame: Frame
    line: str


class FrameLog:
    """A bounded, thread-safe record of frames, with a command filter and a pausable view."""

    def __init__(self, capacity: int = 5000) -> None:
        self.on_change: Callable[[], None] | None = None
        self.filter: frozenset[str] = frozenset()
        self._rows: deque[Row] = deque(maxlen=capacity)
        self._frozen: list[Row] | None = None
        self._visible: list[Row] | None = None
        self._lock = threading.Lock()

    @property
    def paused(self) -> bool:
        return self._frozen is not None

    def add(self, frame: Frame) -> None:
        row = Row(frame, frame_line(frame))
        with self._lock:
            self._rows.append(row)
            if self._frozen is None:
                self._visible = None
        self._changed()

    def visible(self) -> list[Row]:
        with self._lock:
            if self._visible is None:
                rows = list(self._rows) if self._frozen is None else self._frozen
                self._visible = [r for r in rows if not self.filter or r.frame.command in self.filter]
            return self._visible

    def set_filter(self, commands: Iterable[str]) -> None:
        with self._lock:
            self.filter = frozenset(commands)
            self._visible = None
        self._changed()

    def toggle_pause(self) -> bool:
        with self._lock:
            self._frozen = list(self._rows) if self._frozen is None else None
            self._visible = None
        self._changed()
        return self.paused

    def clear(self) -> None:
        with self._lock:
            self._rows.clear()
            if self._frozen is not None:
                self._frozen = []
            self._visible = None
        self._changed()

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()


def frame_line(frame: Frame) -> str:
    arrow = "↑" if frame.direction is FrameDirection.SENT else "↓"
    stamp = time.strftime("%H:%M:%S", time.localtime(frame.at))
    status = f"err {frame.error_code}" if frame.error_code else ""
    preview = " ".join(_payload(frame.text)[: PREVIEW_CHARS * 2].split())[:PREVIEW_CHARS]
    return f"{stamp} {arrow} {frame.command or '?':<12} {status:<9} {_size(len(frame.text)):>8}  {preview}"


def frame_detail(frame: Frame) -> str:
    try:
        return json.dumps(json.loads(_payload(frame.text)), indent=2)
    except ValueError:
        return frame.text


def _payload(text: str) -> str:
    """An XT frame's JSON part: from its first ``{`` or ``[`` to before the closing ``%``."""
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not text.startswith("%xt%") or not starts:
        return text
    return text[min(starts) : len(text.rstrip("%"))]


def _size(chars: int) -> str:
    return f"{chars} B" if chars < 1024 else f"{chars / 1024:.1f} KB"
