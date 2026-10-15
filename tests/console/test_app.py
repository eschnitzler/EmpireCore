import json
import threading
import time
from contextlib import redirect_stdout

from prompt_toolkit.application import create_app_session
from prompt_toolkit.buffer import CompletionState
from prompt_toolkit.completion import Completion
from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from prompt_toolkit.output import DummyOutput

from empire_core.client.client import EmpireClient
from empire_core.console.app import RENDER_ROWS, Console
from empire_core.console.highlight import BANNER_MARK
from empire_core.network.connection import Frame, FrameDirection


def make_console(tmp_path):
    return Console(EmpireClient(username="u", password="p"), history=tmp_path / "history")


def test_submit_runs_code_into_the_output(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        with redirect_stdout(console.writer):
            console.submit("print(6 * 7)")
            console.runner.join(5)
        console.flush()
        assert "42" in console.output_text


def test_commands_drive_the_frame_log(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        console.execute_command(":filter gbd gam")
        assert console.frames.filter == {"gbd", "gam"}
        console.execute_command(":pause")
        assert console.frames.paused
        console.execute_command(":nope")
        console.flush()
        assert "unknown command" in console.output_text


def test_frames_from_the_connection_are_recorded(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        frame = Frame(FrameDirection.RECEIVED, "gam", 0, "%xt%gam%1%0%{}%", 0.0)
        for listener in console.client.connection._listeners.calls("frame"):
            listener(frame)
        assert [row.frame for row in console.frames.visible()] == [frame]


def test_frame_list_render_is_fast(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        big = Frame(FrameDirection.RECEIVED, "gbd", 0, '%xt%gbd%1%0%{"x":"' + "y" * 50_000 + '"}%', 0.0)
        for _ in range(5000):
            console.frames.add(big)
        start = time.perf_counter()
        lines = console.render_frame_list()
        assert time.perf_counter() - start < 0.25
        assert sum(fragment[0].startswith("class:frame.marker") for fragment in lines) == RENDER_ROWS


def test_cursor_stays_inside_the_rendered_rows_when_frames_arrive(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        for frame in frames_of("gam", 3):
            console.frames.add(frame)
        rendered = sum(fragment[0].startswith("class:frame.marker") for fragment in console.render_frame_list())
        console.frames.add(frames_of("gbd", 1)[0])
        assert console._cursor().y < rendered


def test_app_starts_and_quits(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        pipe.send_text("\x04")
        console.application.run()


def test_layout_shows_a_completion_menu(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        assert any(isinstance(c, CompletionsMenu) for c in console.application.layout.walk())


def test_enter_accepts_a_selected_completion(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        buffer = console.input.buffer
        buffer.text = "client.castle.get_all"
        buffer.complete_state = CompletionState(buffer.document, [Completion("get_all")], complete_index=0)
        pipe.send_text("\r\x04")
        console.application.run()
        assert buffer.text == "client.castle.get_all" and buffer.complete_state is None
        assert ">>>" not in console.output_text


F2, SHIFT_F2 = "\x1bOQ", "\x1b[1;2Q"
CTRL = {"up": "\x1b[1;5A", "down": "\x1b[1;5B", "right": "\x1b[1;5C", "left": "\x1b[1;5D"}


def focused_after(console, pipe, keys):
    pipe.send_text(keys + "\x04")
    console.application.run()
    layout = console.application.layout
    return next(name for name, pane in console.panes().items() if layout.has_focus(pane))


def test_f2_cycles_through_every_pane(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        assert [focused_after(console, pipe, F2) for _ in range(4)] == ["frames", "detail", "output", "input"]
        assert focused_after(console, pipe, SHIFT_F2) == "output"


def test_ctrl_arrows_move_between_panes_by_position(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        steps = ["up", "right", "down", "left", "left", "down"]
        assert [focused_after(console, pipe, CTRL[step]) for step in steps] == [
            "output",
            "frames",
            "detail",
            "input",
            "input",
            "input",
        ]


def test_clicking_a_text_pane_focuses_it(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        assert console.output.control.focus_on_click() and console.detail.control.focus_on_click()


def test_home_and_end_jump_in_a_text_pane(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        console.detail.buffer.set_document(Document("a\nb\nc", 2), bypass_readonly=True)
        console.application.layout.focus(console.detail)
        pipe.send_text("\x1b[H\x04")
        console.application.run()
        assert console.detail.buffer.cursor_position == 0
        pipe.send_text("\x1b[F\x04")
        console.application.run()
        assert console.detail.buffer.cursor_position == len("a\nb\nc")


def test_output_keeps_its_place_while_scrolled_back(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        console.flush()
        console.output.buffer.cursor_position = 0
        console.writer.write("more\n")
        console.flush()
        assert console.output.buffer.cursor_position == 0
        console.output.buffer.cursor_position = len(console.output.text)
        console.writer.write("again\n")
        console.flush()
        assert console.output.buffer.cursor_position == len(console.output.text)


def test_text_scrollbar_jumps_where_clicked(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        text = "\n".join(str(i) for i in range(100))
        console.detail.buffer.set_document(Document(text, 0), bypass_readonly=True)
        bar = console.scrollbars["detail"]
        bar.create_content(1, 10)
        bar.mouse_handler(MouseEvent(Point(0, 9), MouseEventType.MOUSE_DOWN, MouseButton.LEFT, frozenset()))
        assert console.detail.document.cursor_position_row > 80


def frames_of(command, count):
    return [Frame(FrameDirection.RECEIVED, command, 0, f'%xt%{command}%1%0%{{"N":{i}}}%', 0.0) for i in range(count)]


def test_selection_stays_on_its_frame_as_the_log_rolls(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        for frame in frames_of("gam", 5000):
            console.frames.add(frame)
        console.select(-1)
        selected = console.selected
        console.frames.add(frames_of("gbd", 1)[0])
        assert selected is not None and console.selected is selected


def test_filter_and_clear_drop_the_selection(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        for frame in frames_of("gam", 3):
            console.frames.add(frame)
        console.select(-1)
        console.execute_command(":filter gbd")
        assert console.selected is None and console.detail.text == ""
        console.execute_command(":filter")
        console.select(-1)
        console.execute_command(":clear")
        assert console.selected is None and console.detail.text == ""


MIGHT = '%xt%gmu%1%0%{"MP":1252,"TSBM":953,"HMP":4976}%'


def might(at=0.0):
    return Frame(FrameDirection.RECEIVED, "gmu", 0, MIGHT, at)


def test_banner_names_the_account_and_help(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        console.flush()
        first = console.output_text.splitlines()[0]
        assert BANNER_MARK in first and " u " in first + " " and "F1" in first


def test_runs_report_success_or_failure_with_their_time(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        with redirect_stdout(console.writer):
            console.submit("1 + 1")
            console.runner.join(5)
            console.submit("1 / 0")
            console.runner.join(5)
        console.flush()
        statuses = [line[0] for line in console.output_text.splitlines() if line[:2] in ("✓ ", "✗ ")]
        assert statuses == ["✓", "✗"]


def test_detail_follows_the_newest_frame_until_one_is_selected(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        console.frames.add(might())
        console.flush()
        assert console.detail.text.startswith("MightPointsResponse(")
        console.select(0)
        selected = console.detail.text
        console.frames.add(frames_of("gam", 1)[0])
        console.flush()
        assert console.detail.text == selected


def test_raw_toggle_shows_the_json_payload(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        console.frames.add(might())
        console.execute_command(":raw")
        console.flush()
        assert console.detail.text.startswith("{") and '"MP": 1252' in console.detail.text
        assert "raw" in console.detail_title_text()
        console.execute_command(":raw")
        console.flush()
        assert console.detail.text.startswith("MightPointsResponse(")


def test_grep_searches_frame_text(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        console.execute_command(":grep 4976")
        assert console.frames.search == "4976"
        console.execute_command(":grep")
        assert console.frames.search == ""


def test_save_writes_the_visible_frames_as_json_lines(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        for frame in frames_of("gam", 3):
            console.frames.add(frame)
        target = tmp_path / "frames.jsonl"
        console.execute_command(f":save {target}")
        records = [json.loads(line) for line in target.read_text().splitlines()]
        assert [r["command"] for r in records] == ["gam"] * 3 and records[0]["direction"] == "received"


def test_f1_shows_help_and_f3_zooms(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        pipe.send_text("\x1bOP\x1bOR\x04")
        console.application.run()
        assert console.show_help and console.zoomed


def test_clicking_a_row_selects_it(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        for frame in frames_of("gam", 3):
            console.frames.add(frame)
        first_row = [fragment for fragment in console.render_frame_list() if len(fragment) == 3][0]
        first_row[2](MouseEvent(Point(0, 0), MouseEventType.MOUSE_UP, MouseButton.LEFT, frozenset()))
        assert console.selected is console.frames.visible()[0]


def test_toolbar_shows_the_account_and_connection(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        text = "".join(fragment[1] for fragment in console.toolbar())
        assert "u" in text and "offline" in text


def test_exit_in_code_quits_the_console(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        fallback = threading.Timer(5, pipe.send_text, ["\x04"])
        fallback.start()
        start = time.perf_counter()
        console.application.run(pre_run=lambda: console.submit("exit()"))
        fallback.cancel()
        assert time.perf_counter() - start < 4


def drag(console, pipe, kind, x, y):
    """Press a border, then move and release with the terminal's own (1-based) SGR mouse reports."""
    console.start_drag(kind)
    pipe.send_text(f"\x1b[<32;{x + 1};{y + 1}M\x1b[<0;{x + 1};{y + 1}m\x04")
    console.application.run()


def test_panes_have_fixed_sizes_that_typing_does_not_change(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        before = console.panels["input"].container.preferred_height(80, 100).preferred
        console.input.buffer.text = "\n".join("x" for _ in range(20))
        assert console.panels["input"].container.preferred_height(80, 100).preferred == before


def test_dragging_borders_resizes_panes(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        rows, columns = console.application.output.get_size()
        drag(console, pipe, "column", 20, 5)
        assert console.sizes.column == 20 / columns and console.dragging is None
        drag(console, pipe, "code", 0, 30)
        assert console.sizes.input_rows == (rows - 1) - 30 - 2
        drag(console, pipe, "frames", 0, 19)
        assert round(console.sizes.frames * (rows - 1)) == 20


def test_drags_are_clamped(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        drag(console, pipe, "column", 0, 0)
        assert console.sizes.column >= 0.2
        drag(console, pipe, "code", 0, 0)
        assert console.sizes.input_rows >= 1


def test_copy_fills_the_clipboard_and_says_so(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        console.copy("hello")
        assert console.application.clipboard.get_data().text == "hello"
        assert "copied 5 B" in "".join(fragment[1] for fragment in console.toolbar())


def test_ctrl_c_in_a_text_pane_copies_its_selection(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        console.detail.buffer.set_document(Document("alpha beta", 0), bypass_readonly=True)
        console.detail.buffer.start_selection()
        console.detail.buffer.cursor_position = 5
        console.application.layout.focus(console.detail)
        pipe.send_text("\x03\x04")
        console.application.run()
        assert console.application.clipboard.get_data().text == "alpha"


def test_c_in_frames_copies_the_shown_detail(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        console.frames.add(might())
        console.flush()
        console.application.layout.focus(console.frame_list)
        pipe.send_text("c\x04")
        console.application.run()
        assert console.application.clipboard.get_data().text.startswith("MightPointsResponse(")


def test_dark_is_the_default_theme_and_theme_toggles(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        assert console.theme == "dark"
        console.execute_command(":theme")
        assert console.theme == "light"
        console.execute_command(":theme dark")
        assert console.theme == "dark"
        console.execute_command(":theme sepia")
        console.flush()
        assert console.theme == "dark" and "unknown theme" in console.output_text


def test_f4_toggles_the_theme(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        pipe.send_text("\x1bOS\x04")
        console.application.run()
        assert console.theme == "light"


def test_overlays_take_the_theme_background(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        assert "class:app" in console.application.layout.container.style
