import threading
import time
from contextlib import redirect_stdout

from prompt_toolkit.application import create_app_session
from prompt_toolkit.buffer import CompletionState
from prompt_toolkit.completion import Completion
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.output import DummyOutput

from empire_core.client.client import EmpireClient
from empire_core.console.app import RENDER_ROWS, Console
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
        assert time.perf_counter() - start < 0.05
        assert len(lines) <= RENDER_ROWS


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


def test_f2_toggles_between_input_and_frames(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        pipe.send_text("\x1bOQ\x1bOQ\x1bOQ\x04")
        console.application.run()
        assert console.application.layout.has_focus(console.frame_list)
        pipe.send_text("\x1bOQ\x04")
        console.application.run()
        assert console.application.layout.has_focus(console.input)


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


def test_exit_in_code_quits_the_console(tmp_path):
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        console = make_console(tmp_path)
        fallback = threading.Timer(5, pipe.send_text, ["\x04"])
        fallback.start()
        start = time.perf_counter()
        console.application.run(pre_run=lambda: console.submit("exit()"))
        fallback.cancel()
        assert time.perf_counter() - start < 4
