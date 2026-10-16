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
from collections.abc import Callable, Iterable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Any, NamedTuple

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import CompleteEvent, ThreadedCompleter
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
from prompt_toolkit.layout.dimension import AnyDimension, Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.lexers import DynamicLexer, PygmentsLexer
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.search import start_search
from prompt_toolkit.styles import DynamicStyle
from prompt_toolkit.widgets import SearchToolbar, TextArea
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
from empire_core.console.completion import CommandCompleter, ConsoleCompleter, NamespaceCompleter, signature_at
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
from empire_core.console.output import OutputLog
from empire_core.console.runner import CodeRunner, PaneWriter
from empire_core.console.settings import Settings, load_settings, save_settings, settings_path
from empire_core.console.theme import THEMES, ThemeName
from empire_core.console.widgets import Panel, ScrollbarControl, TextPane, osc52, selected_text, text_scrollbar
from empire_core.exceptions import EmpireError
from empire_core.network.connection import FrameDirection

HISTORY = Path.home() / ".empire_console_history"
PAGE = 20
NOTICE_SECONDS = 2.5
DOCS_ROWS = 8
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
TEXT_KEYS = [
    ("↑↓ PgUp PgDn", "scroll"),
    ("/ n N", "search"),
    ("Home End", "top / bottom"),
    ("Ctrl-arrows", "panes"),
    ("F1", "help"),
]
# Panes by where they sit, for Ctrl-arrows, and in F2's cycle order.
GRID = (("output", "frames"), ("input", "detail"))
CYCLE = ("input", "frames", "detail", "output")


class Command(NamedTuple):
    """A ``:`` command: what it runs with its arguments, and what completion says about it."""

    run: Callable[[list[str]], object]
    summary: str


@dataclass
class PaneSizes:
    """Where the borders sit: the code column's share of the width, the input's lines and the frame list's
    share of the height."""

    column: float = 0.5
    input_rows: int = 5
    frames: float = 0.55


class Console:
    """A REPL on ``client`` beside every frame its connection sends and receives."""

    def __init__(self, client: EmpireClient, *, history: Path | None = None, settings: Settings | None = None) -> None:
        settings = settings or Settings()
        self.client = client
        self.frames = FrameLog()
        self.frames.set_filter(settings.filter)
        self.namespace: dict[str, Any] = {"client": client, "empire_core": importlib.import_module("empire_core")}
        self.namespace["exit"] = self.namespace["quit"] = self.quit
        self.selected: Row | None = None
        self.raw = settings.raw
        self.show_help = False
        self.zoomed = False
        self.theme: ThemeName = settings.theme
        self.sizes = PaneSizes(settings.column, settings.input_rows, settings.frames)
        self.dragging: str | None = None
        self.commands: dict[str, Command] = {
            "filter": Command(self._filter, "only these commands"),
            "grep": Command(lambda args: self._search(" ".join(args)), "frames containing text"),
            "pause": Command(lambda _args: self.frames.toggle_pause(), "freeze the frame list"),
            "theme": Command(self._theme, "dark, light, or toggle"),
            "clear": Command(self._clear, "forget every frame"),
            "raw": Command(lambda _args: self.toggle_raw(), "parsed or raw detail"),
            "save": Command(self._save, "shown frames as JSON lines"),
            "help": Command(lambda _args: self.toggle_help(), "keys and commands"),
            "quit": Command(lambda _args: self.quit(), "close the client and exit"),
            "login": Command(lambda _args: self.login(), "log in again after a drop"),
            "run": Command(self._run_file, "run a Python file here"),
        }
        self.output_log = OutputLog()
        self._cursor_row = 0
        self._top = 0
        self.logging_in = False
        self.disconnected = False
        self.completer = NamespaceCompleter(self.namespace)
        arguments: dict[str, Callable[[], Iterable[str]]] = {
            "theme": lambda: THEMES,
            "filter": self.frames.commands,
            "run": lambda: (path.name for path in Path().glob("*.py")),
        }
        self.completer_for_input = ConsoleCompleter(
            self.completer,
            CommandCompleter(lambda: {name: command.summary for name, command in self.commands.items()}, arguments),
        )
        self.search_toolbar = SearchToolbar(ignore_case=True)
        self._signature_cache: tuple[tuple[str, int, int], str] | None = None
        self._shown: tuple[Row | None, bool, int] = (None, False, 0)
        self._detail = Detail("")
        self._notice = ("", 0.0)
        self.writer = PaneWriter(self._queue_output)
        self.runner = CodeRunner(
            self.namespace,
            self._queue_output,
            on_done=self._finished,
            show=self._show_result,
        )

        python, json_lexer = PygmentsLexer(PythonLexer), PygmentsLexer(JsonLexer)
        self.output = TextPane(
            lexer=OutputLexer(), wrap_lines=True, on_copy=self.copy, search=self.search_toolbar.control
        )
        self.input = TextArea(
            multiline=True,
            focus_on_click=True,
            lexer=python,
            completer=ThreadedCompleter(self.completer_for_input),
            complete_while_typing=True,
            history=FileHistory(str(history or HISTORY)),
            get_line_prefix=lambda line, _wrap: [("class:output.prompt", "... " if line else ">>> ")],
        )
        self.detail = TextPane(
            lexer=DynamicLexer(lambda: python if self._detail.model else json_lexer),
            wrap_lines=False,
            on_copy=self.copy,
            search=self.search_toolbar.control,
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
        # Session callbacks run on the receive thread; they only set state and queue output.
        client.on_disconnect(self._dropped)
        client.on_session_retry(self._retrying)
        client.on_session_restored(self._restored)
        client.on_session_lost(self._lost)
        self._queue_output(f"{BANNER_MARK}empire-console · {self.who} · client and empire_core are ready · F1 help\n")

    def settings(self) -> Settings:
        """What to remember of this console for the next run."""
        return Settings(
            theme=self.theme,
            zone=self.client.config.default_zone,
            column=self.sizes.column,
            input_rows=self.sizes.input_rows,
            frames=self.sizes.frames,
            filter=sorted(self.frames.filter),
            raw=self.raw,
        )

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
                HSplit(
                    [
                        ConditionalContainer(self._docs_window(), Condition(lambda: self.docs_place() == "detail")),
                        ConditionalContainer(
                            self._scrolled(self.detail, "detail"), Condition(lambda: self.docs_place() != "detail")
                        ),
                    ]
                ),
                self._detail_title,
                has_focus(self.detail),
                grips={"left": column, "top": frame_rows},
            ),
        }
        docs_on_top = Panel(
            self._docs_window(height=lambda: Dimension.exact(min(self.docs_text().count("\n") + 1, DOCS_ROWS))),
            self._docs_title,
            to_filter(False),
        )
        code = HSplit(
            [
                ConditionalContainer(docs_on_top, Condition(lambda: self.docs_place() == "top")),
                self.panels["output"],
                self.panels["input"],
            ],
            width=lambda: Dimension() if self.zoomed else Dimension.exact(self._code_width()),
        )
        frames = HSplit([self.panels["frames"], self.panels["detail"]])
        banner = Window(FormattedTextControl(self.banner), height=1, style="class:banner")
        body = HSplit(
            style="class:app",
            children=[
                ConditionalContainer(banner, Condition(lambda: self.disconnected)),
                VSplit(
                    [
                        ConditionalContainer(code, Condition(lambda: not (self.zoomed and right_side()))),
                        ConditionalContainer(frames, Condition(lambda: not (self.zoomed and not right_side()))),
                    ]
                ),
                self.search_toolbar,
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

        @keys.add("/", filter=in_text)
        def _(event: KeyPressEvent) -> None:
            start_search()

        @keys.add("n", filter=in_text)
        def _(event: KeyPressEvent) -> None:
            event.current_buffer.apply_search(event.app.current_search_state, include_current_position=False)

        @keys.add("N", filter=in_text)
        def _(event: KeyPressEvent) -> None:
            event.current_buffer.apply_search(~event.app.current_search_state, include_current_position=False)

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
            if self.runner.interrupt():
                self._queue_output("✗ interrupted\n")
            else:
                self.input.buffer.reset()

        for key in ("c-c", "y"):
            keys.add(key, filter=in_text)(lambda event: self._copy_pane(event.current_buffer))

        @keys.add("c", filter=in_frames)
        def _(event: KeyPressEvent) -> None:
            self._copy_pane(self.detail.buffer)

        @keys.add("c-l")
        def _(event: KeyPressEvent) -> None:
            self.output_log.clear()

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

        @keys.add("p", filter=in_frames)
        def _(event: KeyPressEvent) -> None:
            self.jump_to_partner()

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
            command.run(args)

    def showing_docs(self) -> bool:
        return bool(self.docs_text())

    def docs_place(self) -> str | None:
        """Where the docs go, clear of the completion menu, which opens upward from the input.

        Beside it, in the Detail pane's place, or atop the code column when that side is zoomed.
        """
        if not self.showing_docs():
            return None
        return "top" if self.zoomed else "detail"

    def _docs_window(self, height: AnyDimension = None) -> Window:
        return Window(FormattedTextControl(lambda: [("class:docs", self.docs_text())]), wrap_lines=True, height=height)

    def docs_text(self) -> str:
        """The docstring of the completion the menu highlights; empty when there is none."""
        state = self.input.buffer.complete_state
        current = state.current_completion if state is not None else None
        if current is None or self.input.text.lstrip().startswith(":"):
            return ""
        return self.completer.docs(current.text).strip()

    def _docs_title(self) -> StyleAndTextTuples:
        state = self.input.buffer.complete_state
        current = state.current_completion if state is not None else None
        return [("", "Docs"), ("class:panel.chip", f" · {current.text}" if current is not None else "")]

    def start(self, *, login: bool) -> None:
        """Begin the background work of a fresh console: warm up completion and, with ``login``, log in."""
        threading.Thread(target=self._warm_up, name="console-warm-up", daemon=True).start()
        if login:
            self.login()

    def login(self) -> None:
        """Log in on a background thread, as at start-up and with ``:login`` after a drop."""
        if self.logging_in:
            self._queue_output("✗ already logging in\n")
        elif not self.client.username or not (self.client.password or self.client.login_token):
            self._queue_output("✗ no account to log in with; start the console with --username\n")
        else:
            self.logging_in = True
            threading.Thread(target=self._login, name="console-login", daemon=True).start()

    def banner(self) -> StyleAndTextTuples:
        return [("class:banner", f" ✗ Disconnected from {self.client.config.default_zone} · :login to reconnect ")]

    def _dropped(self) -> None:
        self.disconnected = True
        self._queue_output("✗ the session dropped · :login to reconnect\n")

    def _retrying(self, attempt: int, wait: float, error: Exception) -> None:
        self._queue_output(f"… login attempt {attempt} failed ({error}); retrying in {wait:.0f} s\n")

    def _restored(self) -> None:
        self.disconnected = False
        self._queue_output("✓ session restored\n")

    def _lost(self, error: Exception) -> None:
        self.disconnected = True
        self._queue_output(f"✗ session lost: {error} · :login to reconnect\n")

    def _warm_up(self) -> None:
        # jedi's first completion takes a few hundred ms; pay it before anyone presses Tab.
        list(self.completer.get_completions(Document("client."), CompleteEvent()))

    def _login(self) -> None:
        started = time.monotonic()
        try:
            # A drop is usually another login of the account, which starts the server's login
            # cooldown; retrying waits it out, each wait reported through on_session_retry.
            self.client.login(retry=True)
        except Exception as e:
            self._queue_output(f"✗ {type(e).__name__}: {e}\n")
        else:
            self.disconnected = False
            self._queue_output(f"✓ logged in as {self.who} in {duration_label(time.monotonic() - started)}\n")
        finally:
            self.logging_in = False
            self.application.invalidate()

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

    def partner(self, row: Row) -> Row | None:
        """The request a reply answers, or the reply to a request, if it is still in view."""
        if row.pair is None:
            return None
        return next((other for other in self.frames.visible() if other.pair == row.pair and other is not row), None)

    def jump_to_partner(self) -> None:
        partner = self.partner(self.selected) if self.selected is not None else None
        if partner is not None:
            self.selected = partner
            self._sync_detail()

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
        content, changed = self.output_log.render(self.pane_widths()[0])
        if changed:
            old = self.output.buffer
            if old.cursor_position >= len(old.text):
                cursor = len(content)
            else:
                # Re-flowed text moves; keep the line the reader was on.
                document = Document(content)
                row = min(old.document.cursor_position_row, document.line_count - 1)
                cursor = document.translate_row_col_to_index(row, 0)
            self.output.buffer.set_document(Document(content, cursor), bypass_readonly=True)
        self._sync_detail()

    def close(self) -> None:
        self.client.connection.remove_frame_listener(self.frames.add)
        self.client.on_disconnect.remove(self._dropped)
        self.client.on_session_retry.remove(self._retrying)
        self.client.on_session_restored.remove(self._restored)
        self.client.on_session_lost.remove(self._lost)

    def list_height(self) -> int:
        """The frame list's rows on screen: its panel less the borders and the column header."""
        return max(self._frames_height() - 3, 1)

    def render_frame_list(self) -> StyleAndTextTuples:
        """The rows that fit, scrolled only as far as keeps the selection in view."""
        rows = self.frames.visible()
        height = self.list_height()
        current = self._row_index(rows)
        if self.selected is None:
            self._top = len(rows) - height
        elif current < self._top:
            self._top = current
        elif current >= self._top + height:
            self._top = current - height + 1
        top = self._top = max(0, min(self._top, len(rows) - height))
        # The cursor must point into these rows, even if frames arrive before it is asked for.
        self._cursor_row = max(current - top, 0)
        lines: StyleAndTextTuples = []
        partner = self.partner(self.selected) if self.selected is not None else None
        for row in rows[top : top + height]:
            chosen = row is self.selected
            highlight = "class:frame.selected " if chosen else ""
            handler = self._mouse_handler(row)
            marker = "▌" if chosen else "┆" if row is partner else " "
            lines.append((highlight + "class:frame.marker", marker, handler))
            lines.extend((highlight + style, text, handler) for style, text, *_ in row.cells)
            lines.append(("", "\n"))
        return lines[:-1]

    def toolbar(self) -> StyleAndTextTuples:
        online = self.client.connection.connected
        if self.logging_in:
            spin = SPINNER[int(time.monotonic() * 8) % len(SPINNER)]
            parts: StyleAndTextTuples = [("class:toolbar.busy", f" {spin} logging in {self.who} ")]
        elif online:
            parts = [("class:toolbar.online", f" ● {self.who} ")]
        else:
            parts = [("class:toolbar.offline", f" ○ {self.who} offline ")]
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
            parts += [("class:toolbar.key", " Ctrl-C"), ("class:toolbar", " stop ")]
        return parts

    def detail_title_text(self) -> str:
        return "".join(fragment[1] for fragment in self._detail_title())

    def _theme(self, args: list[str]) -> None:
        """Switch to the named theme, or to the other one when none is named."""
        name = args[0] if args else next(theme for theme in THEMES if theme != self.theme)
        for theme in THEMES:
            if theme == name:
                self.theme = theme
                return
        self._queue_output(f"✗ unknown theme {name}; {' or '.join(THEMES)}\n")

    def _run_file(self, args: list[str]) -> None:
        """Run a file in the console's namespace, as typed code runs: it sees client, and keeps what it defines."""
        if not args:
            self._queue_output("✗ :run needs a file, as in :run script.py\n")
            return
        path = Path(" ".join(args)).expanduser()
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as e:
            self._queue_output(f"✗ could not read {path}: {e.strerror or e}\n")
            return
        self._queue_output(f"▶ {path}\n")
        if not self.runner.run(source, filename=str(path), echo=False):
            self._queue_output("✗ still running the last input\n")

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

    def pane_widths(self) -> tuple[int, int]:
        """The text widths of Output and Detail, from the layout: borders and a scrollbar take three."""
        columns = self.application.output.get_size().columns
        code = columns if self.zoomed else self._code_width()
        frames = columns if self.zoomed else columns - code
        return max(code - 3, 20), max(frames - 3, 20)

    def _show_result(self, value: object) -> None:
        self.output_log.show(value)
        self.application.invalidate()

    def _queue_output(self, text: str) -> None:
        self.output_log.write(text)
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
        width = self.pane_widths()[1]
        if self._shown == (row, self.raw, width) or (row is None and self._shown[0] is None):
            return
        self._shown = (row, self.raw, width)
        self._detail = frame_detail(row.frame, parsed=not self.raw, width=width) if row is not None else Detail("")
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
        if self.docs_place() == "detail":
            return self._docs_title()
        row = self._shown[0]
        if row is None:
            return [("", "Detail")]
        mode = "parsed" if self._detail.model else "raw"
        following = "" if self.selected is not None else " · following"
        title: StyleAndTextTuples = [("", detail_title(row)), ("class:panel.chip.model", f" · {mode}")]
        partner = self.partner(row)
        if partner is not None:
            link = "request" if partner.frame.direction is FrameDirection.SENT else "reply"
            took = f" in {duration_label(partner.latency)}" if partner.latency is not None else ""
            title.append(("class:panel.chip.filter", f" · {link}{took}, p"))
        return [*title, ("class:panel.chip", following)]


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
    parser.add_argument("--zone", help="the world to play on, such as EmpireEx_3; the last one, else US1")
    parser.add_argument("--list-zones", action="store_true", help="list the worlds and exit")
    parser.add_argument("--no-login", action="store_true", help="start without connecting")
    parser.add_argument("--keep-session", action="store_true", help="log in again by itself after a drop")
    parser.add_argument("--log-level", default="WARNING", help="library log level shown in the output pane")
    parser.add_argument("--theme", choices=sorted(THEMES), help="dark or light; the last one, else dark")
    args = parser.parse_args(argv)
    path = settings_path()
    settings = load_settings(path)
    if args.theme:
        settings = settings.model_copy(update={"theme": args.theme})

    try:
        if args.list_zones:
            print_zones()
            return 0
        config = zone_config(args.zone or settings.zone)
    except (EmpireError, ValueError) as e:
        print(f"empire-console: {e}", file=sys.stderr)
        return 2

    username, password = (args.username, None) if args.no_login else credentials(args.username)
    client = EmpireClient(username=username, password=password, config=config, keep_session=args.keep_session)
    console = Console(client, settings=settings)

    handler = logging.StreamHandler(console.writer)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(args.log_level.upper())
    try:
        with redirect_stdout(console.writer), redirect_stderr(console.writer):
            console.application.run(pre_run=lambda: console.start(login=not args.no_login))
    finally:
        root.removeHandler(handler)
        console.close()
        client.close()
    try:
        save_settings(console.settings(), path)
    except OSError as e:
        print(f"empire-console: could not save settings to {path}: {e}", file=sys.stderr)
    return 0
