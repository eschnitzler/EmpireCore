"""The console's screen: code on the left, the socket on the right."""

import argparse
import importlib
import logging
import os
import sys
import threading
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from getpass import getpass
from pathlib import Path
from typing import Any

from prompt_toolkit.application import Application
from prompt_toolkit.completion import ThreadedCompleter
from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition, has_focus
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.layout import Float, FloatContainer, HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea
from pygments.lexers.python import PythonLexer

from empire_core.client.client import EmpireClient
from empire_core.console.completion import NamespaceCompleter, signature_at
from empire_core.console.frames import FrameLog, Row, frame_detail
from empire_core.console.runner import CodeRunner, PaneWriter
from empire_core.exceptions import EmpireError

HISTORY = Path.home() / ".empire_console_history"
RENDER_ROWS = 500
OUTPUT_CHARS = 200_000
KEYS = " F2 focus · Enter run · Esc Enter force run · Ctrl-C clear · Ctrl-D quit · :filter cmd… · :pause · :clear "

STYLE = Style.from_dict(
    {
        "sent": "ansicyan",
        "received": "ansigreen",
        "error": "ansired",
        "selected": "reverse",
        "title": "bold",
        "toolbar": "reverse",
    }
)


class Console:
    """A REPL on ``client`` beside every frame its connection sends and receives."""

    def __init__(self, client: EmpireClient, *, history: Path | None = None) -> None:
        self.client = client
        self.frames = FrameLog()
        self.namespace: dict[str, Any] = {"client": client, "empire_core": importlib.import_module("empire_core")}
        self._pending: list[str] = []
        self._pending_lock = threading.Lock()
        self.selected: Row | None = None
        self.commands: dict[str, Callable[[list[str]], object]] = {
            "filter": self._filter,
            "pause": lambda _args: self.frames.toggle_pause(),
            "clear": self._clear,
            "quit": lambda _args: self.quit(),
        }
        self.namespace["exit"] = self.namespace["quit"] = self.quit
        self._render_top = 0
        self._signature_cache: tuple[tuple[str, int, int], str] | None = None
        self.writer = PaneWriter(self._queue_output)
        self.runner = CodeRunner(self.namespace, self._queue_output, on_done=self._refresh)

        self.output = TextArea(read_only=True, wrap_lines=True, scrollbar=True)
        self.input = TextArea(
            prompt=">>> ",
            multiline=True,
            lexer=PygmentsLexer(PythonLexer),
            completer=ThreadedCompleter(NamespaceCompleter(self.namespace)),
            complete_while_typing=True,
            history=FileHistory(str(history or HISTORY)),
            height=Dimension(min=1, max=10),
        )
        self.detail = TextArea(read_only=True, wrap_lines=True, scrollbar=True)
        self.frame_list = FormattedTextControl(self.render_frame_list, focusable=True, get_cursor_position=self._cursor)
        self.application: Application[None] = Application(
            layout=Layout(self._layout(), focused_element=self.input),
            key_bindings=self._bindings(),
            style=STYLE,
            full_screen=True,
            mouse_support=True,
            min_redraw_interval=0.05,
            before_render=lambda _app: self.flush(),
        )
        self.frames.on_change = self._refresh
        client.connection.add_frame_listener(self.frames.add)

    @property
    def output_text(self) -> str:
        return self.output.text

    def _layout(self) -> FloatContainer:
        signature = Window(FormattedTextControl(self._signature), height=1, style="class:title")
        title = Window(FormattedTextControl(self._frames_title), height=1, style="class:title")
        toolbar = Window(FormattedTextControl(self._toolbar), height=1, style="class:toolbar")
        left = HSplit([self.output, signature, self.input], width=Dimension(weight=1))
        frame_list = Window(self.frame_list, wrap_lines=False)
        right = HSplit([title, frame_list, Window(height=1, char="─"), self.detail], width=Dimension(weight=1))
        body = HSplit([VSplit([left, Window(width=1, char="│"), right]), toolbar])
        menu = Float(xcursor=True, ycursor=True, content=CompletionsMenu(max_height=12, scroll_offset=1))
        return FloatContainer(body, floats=[menu])

    def _bindings(self) -> KeyBindings:
        keys = KeyBindings()
        in_input = has_focus(self.input)
        in_frames = has_focus(self.frame_list)
        # The menu opens while typing; Enter runs the input unless a completion is picked.
        picked = Condition(
            lambda: self.input.buffer.complete_state is not None
            and self.input.buffer.complete_state.current_completion is not None
        )

        @keys.add("f2")
        def _(event: KeyPressEvent) -> None:
            event.app.layout.focus(self.frame_list if event.app.layout.has_focus(self.input) else self.input)

        @keys.add("c-c")
        def _(event: KeyPressEvent) -> None:
            self.input.buffer.reset()

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

        @keys.add("up", filter=in_frames)
        def _(event: KeyPressEvent) -> None:
            self.select(-1)

        @keys.add("down", filter=in_frames)
        def _(event: KeyPressEvent) -> None:
            self.select(1)

        @keys.add("end", filter=in_frames)
        def _(event: KeyPressEvent) -> None:
            self.selected = None
            self._show_detail(None)

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
            self._queue_output("still running the last input\n")

    def execute_command(self, line: str) -> None:
        name, *args = line[1:].split() or [""]
        command = self.commands.get(name)
        if command is None:
            self._queue_output(f"unknown command :{name}\n")
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
            self._show_detail(self.selected)

    def _filter(self, commands: list[str]) -> None:
        self.frames.set_filter(commands)
        self.selected = None
        self._show_detail(None)

    def _clear(self, _args: list[str]) -> None:
        self.frames.clear()
        self.selected = None
        self._show_detail(None)

    def flush(self) -> None:
        """Move output written from other threads into the pane; runs on the render thread."""
        with self._pending_lock:
            text, self._pending = "".join(self._pending), []
        if text:
            content = (self.output.text + text)[-OUTPUT_CHARS:]
            self.output.buffer.set_document(Document(content, len(content)), bypass_readonly=True)

    def close(self) -> None:
        self.client.connection.remove_frame_listener(self.frames.add)

    def render_frame_list(self) -> StyleAndTextTuples:
        """The rows around the cursor only; the list may hold thousands."""
        rows = self.frames.visible()
        current = self._row_index(rows)
        self._render_top = max(0, min(current - RENDER_ROWS // 2, len(rows) - RENDER_ROWS))
        lines: StyleAndTextTuples = []
        for row in rows[self._render_top : self._render_top + RENDER_ROWS]:
            style = "class:error" if row.frame.error_code else f"class:{row.frame.direction.value}"
            if row is self.selected:
                style += " class:selected"
            lines.append((style, row.line + "\n"))
        return lines

    def _queue_output(self, text: str) -> None:
        with self._pending_lock:
            self._pending.append(text)
        self._refresh()

    def _refresh(self) -> None:
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
        return Point(0, max(self._row_index(self.frames.visible()) - self._render_top, 0))

    def _show_detail(self, row: Row | None) -> None:
        text = frame_detail(row.frame) if row is not None else ""
        self.detail.buffer.set_document(Document(text, 0), bypass_readonly=True)

    def _frames_title(self) -> StyleAndTextTuples:
        shown = ",".join(sorted(self.frames.filter)) or "all"
        state = "paused" if self.frames.paused else "live"
        return [("", f" frames  [{shown}]  [{state}]  {len(self.frames.visible())}")]

    def _signature(self) -> StyleAndTextTuples:
        document = self.input.document
        key = (document.text, document.cursor_position_row, document.cursor_position_col)
        if self._signature_cache is None or self._signature_cache[0] != key:
            try:
                text = signature_at(self.namespace, *key)
            except Exception:
                text = ""
            self._signature_cache = (key, text)
        return [("", self._signature_cache[1])]

    def _toolbar(self) -> StyleAndTextTuples:
        return [("", KEYS + ("· running… " if self.runner.busy else ""))]


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
