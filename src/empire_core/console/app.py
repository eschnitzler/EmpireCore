"""The console's screen: code on the left, the socket on the right."""

import argparse
import importlib
import json
import logging
import os
import re
import sys
import threading
import time
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Any

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import ThreadedCompleter
from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition, has_focus, to_filter
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import (
    AnyContainer,
    ConditionalContainer,
    Float,
    FloatContainer,
    HSplit,
    Layout,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.lexers import DynamicLexer, PygmentsLexer
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.styles import DynamicStyle
from prompt_toolkit.widgets import TextArea
from pygments.lexers.data import JsonLexer
from pygments.lexers.python import PythonLexer

from empire_core.client.client import EmpireClient
from empire_core.config import (
    EMPIRE_GAME_ID,
    EMPIRE_NETWORK_ID,
    EmpireConfig,
    fetch_network_instances,
    instance_for_zone,
)
from empire_core.console.completion import NamespaceCompleter, signature_at
from empire_core.console.frames import (
    HEADER,
    Detail,
    FrameLog,
    Row,
    detail_title,
    duration_label,
    frame_detail,
    size_label,
)
from empire_core.console.help import COLUMNS, GUTTER, column_width, help_column, help_size
from empire_core.console.highlight import BANNER_MARK, OutputLexer
from empire_core.console.pretty import pretty
from empire_core.console.runner import CodeRunner, PaneWriter
from empire_core.console.theme import THEMES
from empire_core.console.widgets import Panel, ScrollbarControl, TextPane, osc52, selected_text, text_scrollbar
from empire_core.exceptions import EmpireError

HISTORY = Path.home() / ".empire_console_history"
RENDER_ROWS = 500
OUTPUT_CHARS = 200_000
PAGE = 20
NOTICE_SECONDS = 2.5
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
SGR_MOUSE = re.compile(r"\x1b\[<\d+;(?P<x>\d+);(?P<y>\d+)(?P<kind>[mM])")

CODE_KEYS = [("Enter", "run"), ("Tab", "complete"), ("Ctrl-arrows", "panes"), ("F1", "help"), ("Ctrl-D", "quit")]
FRAME_KEYS = [
    ("↑↓", "select"),
    ("End", "follow"),
    ("r", "raw"),
    ("F3", "zoom"),
    ("Ctrl-arrows", "panes"),
    ("F1", "help"),
]
TEXT_KEYS = [("↑↓ PgUp PgDn", "scroll"), ("Home End", "top / bottom"), ("Ctrl-arrows", "panes"), ("F1", "help")]
# Panes by where they sit, for Ctrl-arrows, and in F2's cycle order.
GRID = (("output", "frames"), ("input", "detail"))
CYCLE = ("input", "frames", "detail", "output")


@dataclass
class PaneSizes:
    """Where the borders sit: the code column's share of the width, the input's lines and the frame list's
    share of the height."""

    column: float = 0.5
    input_rows: int = 5
    frames: float = 0.55


class Console:
    """A REPL on ``client`` beside every frame its connection sends and receives."""

    def __init__(self, client: EmpireClient, *, history: Path | None = None, theme: str = "dark") -> None:
        self.client = client
        self.frames = FrameLog()
        self.namespace: dict[str, Any] = {"client": client, "empire_core": importlib.import_module("empire_core")}
        self.namespace["exit"] = self.namespace["quit"] = self.quit
        self.selected: Row | None = None
        self.raw = False
        self.show_help = False
        self.zoomed = False
        self.theme = theme
        self.sizes = PaneSizes()
        self.dragging: str | None = None
        self.commands: dict[str, Callable[[list[str]], object]] = {
            "filter": self._filter,
            "grep": lambda args: self._search(" ".join(args)),
            "pause": lambda _args: self.frames.toggle_pause(),
            "theme": self._theme,
            "clear": self._clear,
            "raw": lambda _args: self.toggle_raw(),
            "save": self._save,
            "help": lambda _args: self.toggle_help(),
            "quit": lambda _args: self.quit(),
        }
        self._pending: list[str] = []
        self._pending_lock = threading.Lock()
        self._cursor_row = 0
        self._signature_cache: tuple[tuple[str, int, int], str] | None = None
        self._shown: tuple[Row | None, bool] = (None, False)
        self._detail = Detail("")
        self._notice = ("", 0.0)
        self.writer = PaneWriter(self._queue_output)
        self.runner = CodeRunner(
            self.namespace,
            self._queue_output,
            on_done=self._finished,
            display=lambda value: pretty(value, width=self._output_width()),
        )

        python, json_lexer = PygmentsLexer(PythonLexer), PygmentsLexer(JsonLexer)
        self.output = TextPane(lexer=OutputLexer(), wrap_lines=True, on_copy=self.copy)
        self.input = TextArea(
            multiline=True,
            focus_on_click=True,
            lexer=python,
            completer=ThreadedCompleter(NamespaceCompleter(self.namespace)),
            complete_while_typing=True,
            history=FileHistory(str(history or HISTORY)),
            get_line_prefix=lambda line, _wrap: [("class:output.prompt", "... " if line else ">>> ")],
        )
        self.detail = TextPane(
            lexer=DynamicLexer(lambda: python if self._detail.model else json_lexer),
            wrap_lines=False,
            on_copy=self.copy,
        )
        self.frame_list = FormattedTextControl(self.render_frame_list, focusable=True, get_cursor_position=self._cursor)
        self.scrollbars = {
            "output": text_scrollbar(self.output),
            "frames": ScrollbarControl(self._list_position, self._list_scroll_to),
            "detail": text_scrollbar(self.detail),
        }
        self.application: Application[None] = Application(
            layout=Layout(self._layout(), focused_element=self.input),
            key_bindings=self._bindings(),
            style=DynamicStyle(lambda: THEMES[self.theme]),
            full_screen=True,
            mouse_support=True,
            min_redraw_interval=0.05,
            refresh_interval=0.5,
            before_render=lambda _app: self.flush(),
        )
        self.frames.on_change = self.application.invalidate
        client.connection.add_frame_listener(self.frames.add)
        self._queue_output(f"{BANNER_MARK}empire-console · {self.who} · client and empire_core are ready · F1 help\n")

    @property
    def who(self) -> str:
        """``user @ EmpireEx_21``: the account and the world it plays on."""
        return f"{self.client.username or 'no account'} @ {self.client.config.default_zone}"

    @property
    def output_text(self) -> str:
        return self.output.text

    def panes(self) -> dict[str, TextArea | TextPane | FormattedTextControl]:
        return {"output": self.output, "input": self.input, "frames": self.frame_list, "detail": self.detail}

    def _layout(self) -> FloatContainer:
        right_side = has_focus(self.frame_list) | has_focus(self.detail)
        column, code_rows, frame_rows = (
            lambda kind=kind: self.start_drag(kind) for kind in ("column", "code", "frames")
        )
        header = Window(FormattedTextControl([("class:frame.header", " " + HEADER)]), height=1)
        self.panels = {
            "output": Panel(
                self._scrolled(self.output, "output"),
                lambda: [("", "Output")],
                has_focus(self.output),
                grips={"right": column, "bottom": code_rows},
            ),
            "input": Panel(
                self.input,
                self._input_title,
                has_focus(self.input),
                height=lambda: Dimension.exact(self.sizes.input_rows + 2),
                grips={"right": column, "top": code_rows},
            ),
            "frames": Panel(
                HSplit([header, self._scrolled(Window(self.frame_list, wrap_lines=False), "frames")]),
                self._frames_title,
                has_focus(self.frame_list),
                height=lambda: Dimension.exact(self._frames_height()),
                grips={"left": column, "bottom": frame_rows},
            ),
            "detail": Panel(
                self._scrolled(self.detail, "detail"),
                self._detail_title,
                has_focus(self.detail),
                grips={"left": column, "top": frame_rows},
            ),
        }
        code = HSplit(
            [self.panels["output"], self.panels["input"]],
            width=lambda: Dimension() if self.zoomed else Dimension.exact(self._code_width()),
        )
        frames = HSplit([self.panels["frames"], self.panels["detail"]])
        body = HSplit(
            style="class:app",
            children=[
                VSplit(
                    [
                        ConditionalContainer(code, Condition(lambda: not (self.zoomed and right_side()))),
                        ConditionalContainer(frames, Condition(lambda: not (self.zoomed and not right_side()))),
                    ]
                ),
                Window(FormattedTextControl(self.toolbar), height=1, style="class:toolbar"),
            ],
        )
        left, right = COLUMNS
        help_body = HSplit(
            [
                Window(height=1),
                VSplit(
                    [
                        Window(width=2),
                        Window(FormattedTextControl(help_column(left)), width=column_width(left)),
                        Window(width=GUTTER),
                        Window(FormattedTextControl(help_column(right)), width=column_width(right)),
                        Window(width=2),
                    ],
                    height=help_size()[1],
                ),
                Window(height=1),
            ],
            style="class:help",
        )
        help_panel = Panel(
            help_body,
            lambda: [("", "Keys and commands"), ("class:panel.chip", " · Esc or F1 to close")],
            to_filter(True),
        )
        return FloatContainer(
            body,
            style="class:app",
            floats=[
                Float(xcursor=True, ycursor=True, content=CompletionsMenu(max_height=12, scroll_offset=1)),
                Float(content=ConditionalContainer(help_panel, Condition(lambda: self.show_help))),
            ],
        )

    def start_drag(self, kind: str) -> None:
        """Start resizing at a border: ``"column"``, ``"code"`` (output and input) or ``"frames"``."""
        self.dragging = kind

    def _drag_to(self, x: int, y: int) -> None:
        rows, columns = self.application.output.get_size()
        body = rows - 1
        resize = {
            "column": lambda: setattr(self.sizes, "column", min(max(x / columns, 0.2), 0.8)),
            "code": lambda: setattr(self.sizes, "input_rows", max(min(body - y - 2, body - 8), 1)),
            "frames": lambda: setattr(self.sizes, "frames", min(max((y + 1) / body, 0.15), 0.85)),
        }
        if self.dragging in resize:
            resize[self.dragging]()

    def _code_width(self) -> int:
        return max(round(self.application.output.get_size().columns * self.sizes.column), 20)

    def _frames_height(self) -> int:
        body = self.application.output.get_size().rows - 1
        return max(min(round(body * self.sizes.frames), body - 5), 5)

    def _scrolled(self, body: AnyContainer, pane: str) -> VSplit:
        return VSplit([body, Window(self.scrollbars[pane], width=1)])

    def _bindings(self) -> KeyBindings:
        keys = KeyBindings()
        in_input = has_focus(self.input)
        in_frames = has_focus(self.frame_list)
        in_text = has_focus(self.output) | has_focus(self.detail)
        helping = Condition(lambda: self.show_help)
        dragging = Condition(lambda: self.dragging is not None)
        # The menu opens while typing; Enter runs the input unless a completion is picked.
        picked = Condition(
            lambda: self.input.buffer.complete_state is not None
            and self.input.buffer.complete_state.current_completion is not None
        )

        # While a border is held, read the terminal's mouse reports directly: they carry screen
        # positions, where a control only learns positions inside itself.
        @keys.add(Keys.Vt100MouseEvent, filter=dragging, eager=True)
        def _(event: KeyPressEvent) -> None:
            report = SGR_MOUSE.match(event.data)
            if report is None:
                return
            if report["kind"] == "m":
                self.dragging = None
            else:
                self._drag_to(int(report["x"]) - 1, int(report["y"]) - 1)

        @keys.add("f1")
        def _(event: KeyPressEvent) -> None:
            self.toggle_help()

        @keys.add("escape", filter=helping)
        def _(event: KeyPressEvent) -> None:
            self.show_help = False

        # Terminals send Shift-F2 as F14.
        for key, step in (("f2", 1), ("f14", -1)):
            keys.add(key)(lambda _event, step=step: self._cycle_focus(step))

        for key, rows, columns in (("c-up", -1, 0), ("c-down", 1, 0), ("c-left", 0, -1), ("c-right", 0, 1)):
            keys.add(key)(lambda _event, rows=rows, columns=columns: self._move_focus(rows, columns))

        @keys.add("home", filter=in_text)
        def _(event: KeyPressEvent) -> None:
            event.current_buffer.cursor_position = 0

        @keys.add("end", filter=in_text)
        def _(event: KeyPressEvent) -> None:
            event.current_buffer.cursor_position = len(event.current_buffer.text)

        @keys.add("f4")
        def _(event: KeyPressEvent) -> None:
            self._theme([])

        @keys.add("f3")
        def _(event: KeyPressEvent) -> None:
            self.zoomed = not self.zoomed

        @keys.add("c-c", filter=in_input)
        def _(event: KeyPressEvent) -> None:
            self.input.buffer.reset()

        for key in ("c-c", "y"):
            keys.add(key, filter=in_text)(lambda event: self._copy_pane(event.current_buffer))

        @keys.add("c", filter=in_frames)
        def _(event: KeyPressEvent) -> None:
            self._copy_pane(self.detail.buffer)

        @keys.add("c-l")
        def _(event: KeyPressEvent) -> None:
            self.output.buffer.set_document(Document(""), bypass_readonly=True)

        @keys.add("c-d")
        def _(event: KeyPressEvent) -> None:
            event.app.exit()

        @keys.add("enter", filter=in_input & picked)
        def _(event: KeyPressEvent) -> None:
            self.input.buffer.complete_state = None

        @keys.add("enter", filter=in_input & ~picked)
        def _(event: KeyPressEvent) -> None:
            self.input.buffer.complete_state = None
            text = self.input.text
            if text.strip().startswith(":") or CodeRunner.is_complete(text):
                self._take_input()
            else:
                line = self.input.document.current_line
                indent = line[: len(line) - len(line.lstrip())] + ("    " if line.rstrip().endswith(":") else "")
                self.input.buffer.insert_text("\n" + indent)

        @keys.add("escape", "enter", filter=in_input)
        def _(event: KeyPressEvent) -> None:
            self._take_input()

        for key, step in (("up", -1), ("down", 1), ("pageup", -PAGE), ("pagedown", PAGE), ("home", -sys.maxsize)):
            keys.add(key, filter=in_frames)(lambda _event, step=step: self.select(step))

        @keys.add("end", filter=in_frames)
        def _(event: KeyPressEvent) -> None:
            self.selected = None
            self._sync_detail()

        @keys.add("r", filter=in_frames)
        def _(event: KeyPressEvent) -> None:
            self.toggle_raw()

        return keys

    def _take_input(self) -> None:
        text = self.input.text
        self.input.buffer.append_to_history()
        self.input.buffer.reset()
        self.submit(text)

    def submit(self, source: str) -> None:
        if not source.strip():
            return
        if source.strip().startswith(":"):
            self.execute_command(source.strip())
            return
        echo = "\n".join(("... " if i else ">>> ") + line for i, line in enumerate(source.rstrip().splitlines()))
        self._queue_output(echo + "\n")
        if not self.runner.run(source):
            self._queue_output("✗ still running the last input\n")

    def execute_command(self, line: str) -> None:
        name, *args = line[1:].split() or [""]
        command = self.commands.get(name)
        if command is None:
            self._queue_output(f"✗ unknown command :{name}, F1 lists them\n")
        else:
            command(args)

    def quit(self) -> None:
        """Exit the console; safe from any thread, so code can call ``exit()``."""
        loop = self.application.loop
        if loop is not None:
            loop.call_soon_threadsafe(self.application.exit)

    def copy(self, text: str) -> None:
        """Put ``text`` on the in-app clipboard and, through the terminal, the system one."""
        self.application.clipboard.set_text(text)
        self.application.output.write_raw(osc52(text))
        self.application.output.flush()
        self._notice = (f"copied {size_label(len(text.encode()))}", time.monotonic() + NOTICE_SECONDS)
        self.application.invalidate()

    def select(self, step: int) -> None:
        """Move the selection ``step`` frames from the selected one, or from the newest."""
        rows = self.frames.visible()
        if rows:
            current = self._row_index(rows)
            self.selected = rows[max(0, min(current + step, len(rows) - 1))]
            self._sync_detail()

    def toggle_raw(self) -> None:
        self.raw = not self.raw
        self._sync_detail()

    def toggle_help(self) -> None:
        self.show_help = not self.show_help

    def flush(self) -> None:
        """Bring the panes up to date with other threads; runs on the render thread."""
        with self._pending_lock:
            text, self._pending = "".join(self._pending), []
        if text:
            old = self.output.buffer
            following = old.cursor_position >= len(old.text)
            content = (old.text + text)[-OUTPUT_CHARS:]
            dropped = len(old.text) + len(text) - len(content)
            cursor = len(content) if following else max(old.cursor_position - dropped, 0)
            self.output.buffer.set_document(Document(content, cursor), bypass_readonly=True)
        self._sync_detail()

    def close(self) -> None:
        self.client.connection.remove_frame_listener(self.frames.add)

    def render_frame_list(self) -> StyleAndTextTuples:
        """The rows around the cursor only; the list may hold thousands."""
        rows = self.frames.visible()
        current = self._row_index(rows)
        top = max(0, min(current - RENDER_ROWS // 2, len(rows) - RENDER_ROWS))
        # The cursor must point into these rows, even if frames arrive before it is asked for.
        self._cursor_row = max(current - top, 0)
        lines: StyleAndTextTuples = []
        for row in rows[top : top + RENDER_ROWS]:
            chosen = row is self.selected
            highlight = "class:frame.selected " if chosen else ""
            handler = self._mouse_handler(row)
            lines.append((highlight + "class:frame.marker", "▌" if chosen else " ", handler))
            lines.extend((highlight + style, text, handler) for style, text, *_ in row.cells)
            lines.append(("", "\n"))
        return lines[:-1]

    def toolbar(self) -> StyleAndTextTuples:
        online = self.client.connection.connected
        status = f" ● {self.who} " if online else f" ○ {self.who} offline "
        parts: StyleAndTextTuples = [("class:toolbar.online" if online else "class:toolbar.offline", status)]
        layout = self.application.layout
        keys = CODE_KEYS
        if layout.has_focus(self.frame_list):
            keys = FRAME_KEYS
        elif layout.has_focus(self.output) or layout.has_focus(self.detail):
            keys = TEXT_KEYS
        for key, what in keys:
            parts += [("class:toolbar.key", f" {key}"), ("class:toolbar", f" {what} ")]
        notice, until = self._notice
        if notice and time.monotonic() < until:
            parts.append(("class:toolbar.online", f"  ✓ {notice} "))
        if self.runner.busy:
            elapsed = time.monotonic() - self.runner.started_at
            spin = SPINNER[int(elapsed * 4) % len(SPINNER)]
            parts.append(("class:toolbar.busy", f"  {spin} running {duration_label(elapsed)} "))
        return parts

    def detail_title_text(self) -> str:
        return "".join(fragment[1] for fragment in self._detail_title())

    def _theme(self, args: list[str]) -> None:
        """Switch to the named theme, or to the other one when none is named."""
        name = args[0] if args else next(theme for theme in THEMES if theme != self.theme)
        if name in THEMES:
            self.theme = name
        else:
            self._queue_output(f"✗ unknown theme {name}; {' or '.join(THEMES)}\n")

    def _filter(self, commands: list[str]) -> None:
        self.frames.set_filter(c for arg in commands for c in arg.split(",") if c)
        self.selected = None
        self._sync_detail()

    def _search(self, text: str) -> None:
        self.frames.set_search(text)
        self.selected = None
        self._sync_detail()

    def _clear(self, _args: list[str]) -> None:
        self.frames.clear()
        self.selected = None
        self._sync_detail()

    def _save(self, args: list[str]) -> None:
        path = Path(args[0] if args else time.strftime("frames-%Y%m%d-%H%M%S.jsonl")).expanduser()
        rows = self.frames.visible()
        records = (
            {
                "at": row.frame.at,
                "direction": row.frame.direction.value,
                "command": row.frame.command,
                "error_code": row.frame.error_code,
                "text": row.frame.text,
            }
            for row in rows
        )
        try:
            path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        except OSError as e:
            self._queue_output(f"✗ could not save: {e}\n")
        else:
            self._queue_output(f"✓ saved {len(rows)} frames to {path}\n")

    def _finished(self, elapsed: float, ok: bool) -> None:
        self._queue_output(f"{'✓' if ok else '✗'} {duration_label(elapsed)}\n")

    def _copy_pane(self, buffer: Buffer) -> None:
        """Copy the selection, or the whole pane when nothing is selected."""
        self.copy(selected_text(buffer) or buffer.text)

    def _focused_pane(self) -> str:
        layout = self.application.layout
        return next((name for name, pane in self.panes().items() if layout.has_focus(pane)), "input")

    def _cycle_focus(self, step: int) -> None:
        current = CYCLE.index(self._focused_pane())
        self.application.layout.focus(self.panes()[CYCLE[(current + step) % len(CYCLE)]])

    def _move_focus(self, rows: int, columns: int) -> None:
        focused = self._focused_pane()
        row, column = next((r, c) for r, line in enumerate(GRID) for c, name in enumerate(line) if name == focused)
        row = max(0, min(row + rows, len(GRID) - 1))
        column = max(0, min(column + columns, len(GRID[0]) - 1))
        self.application.layout.focus(self.panes()[GRID[row][column]])

    def _list_position(self) -> tuple[int, int, int]:
        rows = self.frames.visible()
        return self._row_index(rows), 1, len(rows)

    def _list_scroll_to(self, index: int) -> None:
        rows = self.frames.visible()
        if rows:
            self.selected = rows[max(0, min(index, len(rows) - 1))]
            self._sync_detail()

    def _output_width(self) -> int:
        info = self.output.window.render_info
        return info.window_width - 2 if info is not None else 88

    def _queue_output(self, text: str) -> None:
        with self._pending_lock:
            self._pending.append(text)
        self.application.invalidate()

    def _row_index(self, rows: list[Row]) -> int:
        """Where the selected row is in ``rows``; the newest row when none is selected or it is gone."""
        if self.selected is not None:
            for i in range(len(rows) - 1, -1, -1):
                if rows[i] is self.selected:
                    return i
            self.selected = None
        return len(rows) - 1

    def _cursor(self) -> Point:
        return Point(0, self._cursor_row)

    def _mouse_handler(self, row: Row) -> Callable[[MouseEvent], object]:
        def handle(event: MouseEvent) -> object:
            if event.event_type is MouseEventType.MOUSE_UP:
                self.selected = row
                self.application.layout.focus(self.frame_list)
                self._sync_detail()
            elif event.event_type is MouseEventType.SCROLL_UP:
                self.select(-3)
            elif event.event_type is MouseEventType.SCROLL_DOWN:
                self.select(3)
            else:
                return NotImplemented
            return None

        return handle

    def _sync_detail(self) -> None:
        """Show the selected frame, or the newest one while following, unless it is already shown."""
        rows = self.frames.visible()
        row = self.selected if self.selected is not None else (rows[-1] if rows else None)
        if self._shown[0] is row and self._shown[1] == self.raw:
            return
        self._shown = (row, self.raw)
        self._detail = frame_detail(row.frame, parsed=not self.raw) if row is not None else Detail("")
        self.detail.buffer.set_document(Document(self._detail.text, 0), bypass_readonly=True)

    def _input_title(self) -> StyleAndTextTuples:
        document = self.input.document
        key = (document.text, document.cursor_position_row, document.cursor_position_col)
        if self._signature_cache is None or self._signature_cache[0] != key:
            try:
                text = signature_at(self.namespace, *key)
            except Exception:
                text = ""
            self._signature_cache = (key, text)
        signature = self._signature_cache[1]
        return [("class:signature", signature)] if signature else [("", "Python")]

    def _frames_title(self) -> StyleAndTextTuples:
        title: StyleAndTextTuples = [("", "Frames"), ("class:panel.chip", f" · {len(self.frames.visible())}")]
        if self.frames.filter:
            title.append(("class:panel.chip.filter", f" · {','.join(sorted(self.frames.filter))}"))
        if self.frames.search:
            title.append(("class:panel.chip.filter", f" · /{self.frames.search}"))
        if self.frames.paused:
            title.append(("class:panel.chip.paused", " · paused"))
        else:
            title.append(("class:panel.chip.live", " · live"))
        return title

    def _detail_title(self) -> StyleAndTextTuples:
        row = self._shown[0]
        if row is None:
            return [("", "Detail")]
        mode = "parsed" if self._detail.model else "raw"
        following = "" if self.selected is not None else " · following"
        return [("", detail_title(row)), ("class:panel.chip.model", f" · {mode}"), ("class:panel.chip", following)]


def zone_config(zone: str | None) -> EmpireConfig:
    """US1 unless ``zone`` names another world, which the game's server list resolves."""
    return EmpireConfig() if zone is None else EmpireConfig.for_instance(instance_for_zone(zone))


def credentials(
    username: str | None,
    *,
    ask: Callable[[str], str] = input,
    ask_secret: Callable[[str], str] = getpass,
) -> tuple[str, str]:
    """The username and password, asking for whichever the flags and environment do not give."""
    username = username or ask("Username: ").strip()
    return username, os.getenv("GGE_PASSWORD") or ask_secret(f"Password for {username}: ")


def print_zones() -> None:
    default = EmpireConfig().default_zone
    for world in fetch_network_instances(EMPIRE_GAME_ID, EMPIRE_NETWORK_ID):
        # A world is named by its country or language key: generic_country_FR, generic_language_pt.
        country = world.instance_loca_id.rsplit("_", 1)[-1]
        print(f"{'*' if world.zone == default else ' '} {world.zone:<14} {country:<14} {world.server}")


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="empire-console", description="A Python REPL on a live client beside its socket frames."
    )
    parser.add_argument("--username", default=os.getenv("GGE_USERNAME"), help="defaults to $GGE_USERNAME, else asked")
    parser.add_argument("--zone", help="the world to play on, such as EmpireEx_3; US1 (EmpireEx_21) by default")
    parser.add_argument("--list-zones", action="store_true", help="list the worlds and exit")
    parser.add_argument("--no-login", action="store_true", help="start without connecting")
    parser.add_argument("--log-level", default="WARNING", help="library log level shown in the output pane")
    parser.add_argument("--theme", choices=sorted(THEMES), default="dark", help="dark (default) or light")
    args = parser.parse_args(argv)

    try:
        if args.list_zones:
            print_zones()
            return 0
        config = zone_config(args.zone)
    except (EmpireError, ValueError) as e:
        print(f"empire-console: {e}", file=sys.stderr)
        return 2

    username, password = (args.username, None) if args.no_login else credentials(args.username)
    client = EmpireClient(username=username, password=password, config=config)
    console = Console(client, theme=args.theme)
    if not args.no_login:
        print(f"Logging in as {username} on {config.default_zone}…")
        try:
            client.login()
        except EmpireError as e:
            print(f"{type(e).__name__}: {e}", file=sys.stderr)
            console.close()
            client.close()
            return 1

    handler = logging.StreamHandler(console.writer)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(args.log_level.upper())
    try:
        with redirect_stdout(console.writer), redirect_stderr(console.writer):
            console.application.run()
    finally:
        root.removeHandler(handler)
        console.close()
        client.close()
    return 0
