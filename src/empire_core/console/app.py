"""The console's screen: code on the left, the socket on the right."""

import argparse
import importlib
import json
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from getpass import getpass
from pathlib import Path
from typing import Any

from prompt_toolkit.application import Application
from prompt_toolkit.completion import ThreadedCompleter
from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition, has_focus, to_filter
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
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
from prompt_toolkit.widgets import TextArea
from pygments.lexers.data import JsonLexer
from pygments.lexers.python import PythonLexer

from empire_core.client.client import EmpireClient
from empire_core.console.completion import NamespaceCompleter, signature_at
from empire_core.console.frames import HEADER, Detail, FrameLog, Row, detail_title, duration_label, frame_detail
from empire_core.console.highlight import BANNER_MARK, OutputLexer
from empire_core.console.pretty import pretty
from empire_core.console.runner import CodeRunner, PaneWriter
from empire_core.console.theme import STYLE
from empire_core.console.widgets import Panel, ScrollbarControl, text_scrollbar
from empire_core.exceptions import EmpireError

HISTORY = Path.home() / ".empire_console_history"
RENDER_ROWS = 500
OUTPUT_CHARS = 200_000
PAGE = 20
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

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
HELP = [
    ("Code", ""),
    ("Enter", "run once the statement is complete"),
    ("Esc Enter", "run whatever is typed"),
    ("Tab / ↑↓", "complete / history"),
    ("Ctrl-C", "clear the input"),
    ("Ctrl-L", "clear the output"),
    ("Panes", ""),
    ("Ctrl-arrows", "move to the pane in that direction"),
    ("F2 / Shift-F2", "next / previous pane"),
    ("click, wheel", "focus a pane, scroll it or its scrollbar"),
    ("Home / End", "top / bottom of Output and Detail"),
    ("Frames", ""),
    ("↑↓ PgUp PgDn", "select a frame (or click it)"),
    ("Home / End", "oldest frame / follow the newest"),
    ("r", "parsed model or raw payload"),
    ("F3", "zoom the focused side"),
    ("Commands", ""),
    (":filter gbd gam", "only these commands; none for all"),
    (":grep text", "only frames containing text"),
    (":pause  :clear", "freeze the view / forget frames"),
    (":raw", "toggle parsed and raw detail"),
    (":save [file]", "write the shown frames as JSON lines"),
    (":quit", "close the client and exit, as does exit()"),
]


class Console:
    """A REPL on ``client`` beside every frame its connection sends and receives."""

    def __init__(self, client: EmpireClient, *, history: Path | None = None) -> None:
        self.client = client
        self.frames = FrameLog()
        self.namespace: dict[str, Any] = {"client": client, "empire_core": importlib.import_module("empire_core")}
        self.namespace["exit"] = self.namespace["quit"] = self.quit
        self.selected: Row | None = None
        self.raw = False
        self.show_help = False
        self.zoomed = False
        self.commands: dict[str, Callable[[list[str]], object]] = {
            "filter": self._filter,
            "grep": lambda args: self._search(" ".join(args)),
            "pause": lambda _args: self.frames.toggle_pause(),
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
        self.writer = PaneWriter(self._queue_output)
        self.runner = CodeRunner(
            self.namespace,
            self._queue_output,
            on_done=self._finished,
            display=lambda value: pretty(value, width=self._output_width()),
        )

        python, json_lexer = PygmentsLexer(PythonLexer), PygmentsLexer(JsonLexer)
        self.output = TextArea(read_only=True, wrap_lines=True, focus_on_click=True, lexer=OutputLexer())
        self.input = TextArea(
            multiline=True,
            focus_on_click=True,
            lexer=python,
            completer=ThreadedCompleter(NamespaceCompleter(self.namespace)),
            complete_while_typing=True,
            history=FileHistory(str(history or HISTORY)),
            get_line_prefix=lambda line, _wrap: [("class:output.prompt", "... " if line else ">>> ")],
            height=Dimension(min=1, max=10),
        )
        self.detail = TextArea(
            read_only=True,
            wrap_lines=False,
            focus_on_click=True,
            lexer=DynamicLexer(lambda: python if self._detail.model else json_lexer),
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
            style=STYLE,
            full_screen=True,
            mouse_support=True,
            min_redraw_interval=0.05,
            refresh_interval=0.5,
            before_render=lambda _app: self.flush(),
        )
        self.frames.on_change = self.application.invalidate
        client.connection.add_frame_listener(self.frames.add)
        who = client.username or "no account"
        self._queue_output(f"{BANNER_MARK}empire-console · {who} · client and empire_core are ready · F1 help\n")

    @property
    def output_text(self) -> str:
        return self.output.text

    def panes(self) -> dict[str, TextArea | FormattedTextControl]:
        return {"output": self.output, "input": self.input, "frames": self.frame_list, "detail": self.detail}

    def _layout(self) -> FloatContainer:
        right_side = has_focus(self.frame_list) | has_focus(self.detail)
        code = HSplit(
            [
                Panel(self._scrolled(self.output, "output"), lambda: [("", "Output")], has_focus(self.output)),
                Panel(self.input, self._input_title, has_focus(self.input)),
            ],
            width=Dimension(weight=1),
        )
        header = Window(FormattedTextControl([("class:frame.header", " " + HEADER)]), height=1)
        frame_list = self._scrolled(Window(self.frame_list, wrap_lines=False), "frames")
        frames = HSplit(
            [
                Panel(HSplit([header, frame_list]), self._frames_title, has_focus(self.frame_list)),
                Panel(self._scrolled(self.detail, "detail"), self._detail_title, has_focus(self.detail)),
            ],
            width=Dimension(weight=1),
        )
        body = HSplit(
            [
                VSplit(
                    [
                        ConditionalContainer(code, Condition(lambda: not (self.zoomed and right_side()))),
                        ConditionalContainer(frames, Condition(lambda: not (self.zoomed and not right_side()))),
                    ]
                ),
                Window(FormattedTextControl(self.toolbar), height=1, style="class:toolbar"),
            ]
        )
        width = max(len(key) for key, _ in HELP) + max(len(what) for _, what in HELP) + 4
        help_text = Window(FormattedTextControl(self._help), width=width, height=len(HELP), style="class:help")
        help_panel = Panel(help_text, lambda: [("", "Help · Esc to close")], to_filter(True))
        return FloatContainer(
            body,
            floats=[
                Float(xcursor=True, ycursor=True, content=CompletionsMenu(max_height=12, scroll_offset=1)),
                Float(content=ConditionalContainer(help_panel, Condition(lambda: self.show_help))),
            ],
        )

    def _scrolled(self, body: AnyContainer, pane: str) -> VSplit:
        return VSplit([body, Window(self.scrollbars[pane], width=1)])

    def _bindings(self) -> KeyBindings:
        keys = KeyBindings()
        in_input = has_focus(self.input)
        in_frames = has_focus(self.frame_list)
        in_text = has_focus(self.output) | has_focus(self.detail)
        helping = Condition(lambda: self.show_help)
        # The menu opens while typing; Enter runs the input unless a completion is picked.
        picked = Condition(
            lambda: self.input.buffer.complete_state is not None
            and self.input.buffer.complete_state.current_completion is not None
        )

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

        @keys.add("f3")
        def _(event: KeyPressEvent) -> None:
            self.zoomed = not self.zoomed

        @keys.add("c-c")
        def _(event: KeyPressEvent) -> None:
            self.input.buffer.reset()

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
            highlight = " class:frame.selected" if chosen else ""
            handler = self._mouse_handler(row)
            lines.append(("class:frame.marker" + highlight, "▌" if chosen else " ", handler))
            lines.extend((style + highlight, text, handler) for style, text, *_ in row.cells)
            lines.append(("", "\n"))
        return lines[:-1]

    def toolbar(self) -> StyleAndTextTuples:
        online = self.client.connection.connected
        who = self.client.username or "no account"
        status = f" ● {who} " if online else f" ○ {who} offline "
        parts: StyleAndTextTuples = [("class:toolbar.online" if online else "class:toolbar.offline", status)]
        layout = self.application.layout
        keys = CODE_KEYS
        if layout.has_focus(self.frame_list):
            keys = FRAME_KEYS
        elif layout.has_focus(self.output) or layout.has_focus(self.detail):
            keys = TEXT_KEYS
        for key, what in keys:
            parts += [("class:toolbar.key", f" {key}"), ("class:toolbar", f" {what} ")]
        if self.runner.busy:
            elapsed = time.monotonic() - self.runner.started_at
            spin = SPINNER[int(elapsed * 4) % len(SPINNER)]
            parts.append(("class:toolbar.busy", f"  {spin} running {duration_label(elapsed)} "))
        return parts

    def detail_title_text(self) -> str:
        return "".join(fragment[1] for fragment in self._detail_title())

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

    def _help(self) -> StyleAndTextTuples:
        width = max(len(key) for key, _ in HELP) + 2
        lines: StyleAndTextTuples = []
        for key, what in HELP:
            if what:
                lines += [("class:help.key", f" {key:<{width}}"), ("class:help", f"{what}\n")]
            else:
                lines.append(("class:help.heading", f" {key}\n"))
        return lines


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="empire-console", description="A Python REPL on a live client beside its socket frames."
    )
    parser.add_argument("--username", default=os.getenv("GGE_USERNAME"), help="defaults to $GGE_USERNAME")
    parser.add_argument("--no-login", action="store_true", help="start without connecting")
    parser.add_argument("--log-level", default="WARNING", help="library log level shown in the output pane")
    args = parser.parse_args(argv)

    password = None
    if not args.no_login:
        if not args.username:
            parser.error("give --username or set GGE_USERNAME, or pass --no-login")
        password = os.getenv("GGE_PASSWORD") or getpass(f"Password for {args.username}: ")

    client = EmpireClient(username=args.username, password=password)
    console = Console(client)
    if not args.no_login:
        print(f"Logging in as {args.username}…")
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
