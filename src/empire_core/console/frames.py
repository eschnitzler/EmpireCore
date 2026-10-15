"""The frames the console has seen, and how one reads as a row or as detail."""

import json
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from prompt_toolkit.formatted_text import StyleAndTextTuples
from pydantic import ValidationError

from empire_core.console.pretty import pretty
from empire_core.network.connection import Frame, FrameDirection
from empire_core.protocol.base import get_response_model, parse_response

PREVIEW_CHARS = 70
HEADER = "time     ⇅ command      status       size     rtt  payload"


@dataclass(frozen=True)
class Row:
    """A frame as the list shows it, formatted once when it arrives.

    ``latency`` is the time since the request a reply answers: the last frame sent with its
    command that no reply has claimed yet. A push the console did not ask for has none.
    """

    frame: Frame
    size: int
    latency: float | None
    cells: StyleAndTextTuples

    @property
    def text(self) -> str:
        return "".join(cell[1] for cell in self.cells)


class FrameLog:
    """A bounded, thread-safe record of frames, with a command filter, a text search and a pausable view."""

    def __init__(self, capacity: int = 5000) -> None:
        self.on_change: Callable[[], None] | None = None
        self.filter: frozenset[str] = frozenset()
        self.search = ""
        self._rows: deque[Row] = deque(maxlen=capacity)
        self._frozen: list[Row] | None = None
        self._visible: list[Row] | None = None
        self._sent_at: dict[str, float] = {}
        self._lock = threading.Lock()

    @property
    def paused(self) -> bool:
        return self._frozen is not None

    def add(self, frame: Frame) -> None:
        with self._lock:
            row = self._row(frame)
            dropped = self._rows[0] if len(self._rows) == self._rows.maxlen else None
            self._rows.append(row)
            # Extend the cached view instead of rebuilding it: frames arrive far more often than views change.
            if self._frozen is None and self._visible is not None:
                kept = self._visible[1:] if self._visible and self._visible[0] is dropped else self._visible
                self._visible = [*kept, row] if self._shows(row) else kept
        self._changed()

    def visible(self) -> list[Row]:
        with self._lock:
            if self._visible is None:
                rows = list(self._rows) if self._frozen is None else self._frozen
                self._visible = [r for r in rows if self._shows(r)]
            return self._visible

    def set_filter(self, commands: Iterable[str]) -> None:
        with self._lock:
            self.filter = frozenset(commands)
            self._visible = None
        self._changed()

    def set_search(self, text: str) -> None:
        with self._lock:
            self.search = text
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
            self._sent_at.clear()
            if self._frozen is not None:
                self._frozen = []
            self._visible = None
        self._changed()

    def _row(self, frame: Frame) -> Row:
        latency = None
        if frame.command and frame.direction is FrameDirection.SENT:
            self._sent_at[frame.command] = frame.at
        elif frame.command and frame.command in self._sent_at:
            latency = frame.at - self._sent_at.pop(frame.command)
        size = len(frame.text.encode("utf-8", errors="replace"))
        return Row(frame, size, latency, _cells(frame, size, latency))

    def _shows(self, row: Row) -> bool:
        return (not self.filter or row.frame.command in self.filter) and self.search in row.frame.text

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()


@dataclass(frozen=True)
class Detail:
    """A frame's payload as the detail pane shows it; ``model`` names the model it was parsed into."""

    text: str
    model: str | None = None


def frame_detail(frame: Frame, *, parsed: bool = True) -> Detail:
    """A received frame parsed into its response model, as the client parses it; otherwise its raw payload."""
    try:
        payload = json.loads(_payload(frame.text))
    except ValueError:
        return Detail(frame.text)
    raw = json.dumps(payload, indent=2, ensure_ascii=False)
    if not parsed or frame.direction is FrameDirection.SENT or not frame.command or not isinstance(payload, dict):
        return Detail(raw)
    try:
        response = parse_response(frame.command, payload)
    except ValidationError as e:
        model = get_response_model(frame.command)
        name = model.__name__ if model else frame.command
        return Detail(f"# not parsed as {name}: {e.error_count()} validation error(s); raw payload below\n{raw}")
    return Detail(pretty(response), type(response).__name__) if response is not None else Detail(raw)


def detail_title(row: Row) -> str:
    """``↓ gcl · GetCastlesResponse · 156 B · 14:15:22 · 48 ms``, with ``err N`` on a refusal."""
    frame = row.frame
    received = frame.direction is FrameDirection.RECEIVED
    model = get_response_model(frame.command) if received and frame.command else None
    parts = [
        f"{'↓' if received else '↑'} {frame.command or '?'}",
        model.__name__ if model else "",
        size_label(row.size),
        time.strftime("%H:%M:%S", time.localtime(frame.at)),
        duration_label(row.latency),
        f"err {frame.error_code}" if frame.error_code else "",
    ]
    return " · ".join(part for part in parts if part)


def size_label(size: int) -> str:
    return f"{size} B" if size < 1024 else f"{size / 1024:.1f} KB"


def duration_label(latency: float | None) -> str:
    if latency is None:
        return ""
    return f"{latency * 1000:.0f} ms" if latency < 1 else f"{latency:.1f} s"


def _cells(frame: Frame, size: int, latency: float | None) -> StyleAndTextTuples:
    sent = frame.direction is FrameDirection.SENT
    status = f"✗ {frame.error_code}" if frame.error_code else ""
    preview = " ".join(_payload(frame.text)[: PREVIEW_CHARS * 2].split())[:PREVIEW_CHARS]
    return [
        ("class:frame.time", time.strftime("%H:%M:%S ", time.localtime(frame.at))),
        ("class:frame.sent" if sent else "class:frame.received", "↑ " if sent else "↓ "),
        ("class:frame.command", f"{frame.command or '?':<13}"),
        ("class:frame.error" if status else "", f"{status:<9}"),
        ("class:frame.size", f"{size_label(size):>8}"),
        ("class:frame.latency", f"{duration_label(latency):>8}  "),
        ("class:frame.preview", preview),
    ]


def _payload(text: str) -> str:
    """An XT frame's JSON part: from its first ``{`` or ``[`` to before the closing ``%``."""
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not text.startswith("%xt%") or not starts:
        return text
    return text[min(starts) : len(text.rstrip("%"))]
