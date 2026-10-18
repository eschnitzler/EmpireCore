import contextlib
import threading

from empire_core.console.runner import CodeRunner, PaneWriter


def run(source, namespace=None):
    out: list[str] = []
    runner = CodeRunner(namespace if namespace is not None else {}, out.append)
    writer = PaneWriter(out.append)
    with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
        assert runner.run(source)
        runner.join(5)
    return "".join(out)


def test_expression_is_echoed():
    assert run("1 + 1") == "2\n"


def test_statements_then_expression():
    assert run("a = 2\nb = 3\na * b") == "6\n"


def test_print_is_captured():
    assert run("print('hi')") == "hi\n"


def test_exception_shows_traceback_without_runner_frames():
    output = run("1 / 0")
    assert "ZeroDivisionError" in output and "runner.py" not in output


def test_system_exit_is_reported_not_raised():
    assert "SystemExit" in run("raise SystemExit(3)")
    assert "KeyboardInterrupt" in run("raise KeyboardInterrupt")


def test_on_done_reports_time_and_success():
    outcomes: list[tuple[float, bool]] = []
    runner = CodeRunner({}, lambda _: None, on_done=lambda elapsed, ok: outcomes.append((elapsed, ok)))
    runner.run("x = 1")
    runner.join(5)
    runner.run("1 / 0")
    runner.join(5)
    assert [ok for _, ok in outcomes] == [True, False]
    assert all(0 <= elapsed < 1 for elapsed, _ in outcomes)


def test_results_go_to_show_as_values_and_land_in_underscore():
    shown: list[object] = []
    namespace: dict = {}
    runner = CodeRunner(namespace, lambda _text: None, show=shown.append)
    runner.run("[1, 2]")
    runner.join(5)
    runner.run("None")
    runner.join(5)
    assert shown == [[1, 2]] and namespace["_"] == [1, 2]


def test_namespace_persists():
    namespace: dict = {}
    run("x = 5", namespace)
    assert run("x", namespace) == "5\n"


def test_busy_runner_refuses():
    gate = threading.Event()
    runner = CodeRunner({"gate": gate}, lambda _: None)
    assert runner.run("gate.wait(5)")
    assert runner.busy and not runner.run("1")
    gate.set()
    runner.join(5)
    assert not runner.busy


def test_is_complete():
    assert CodeRunner.is_complete("1 + 1")
    assert not CodeRunner.is_complete("for i in range(3):")
    assert not CodeRunner.is_complete("for i in range(3):\n    print(i)")
    assert CodeRunner.is_complete("for i in range(3):\n    print(i)\n")
    assert CodeRunner.is_complete("for i in range(3):\n    print(i)\n    ")
    assert CodeRunner.is_complete("1 +* 2")


def test_writer_is_thread_safe():
    out: list[str] = []
    writer = PaneWriter(out.append)
    threads = [threading.Thread(target=lambda: [writer.write("x") for _ in range(500)]) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert "".join(out) == "x" * 2000


def test_interrupt_frees_the_runner_and_stops_a_python_loop():
    outcomes: list[bool] = []

    def done(_elapsed, ok):
        outcomes.append(ok)

    runner = CodeRunner({}, lambda _text: None, on_done=done)
    runner.run("while True:\n    pass")
    worker = runner._thread
    assert runner.busy and runner.interrupt()
    assert not runner.busy
    assert worker is not None
    worker.join(2)
    assert not worker.is_alive() and outcomes == []


def test_a_new_input_runs_right_after_an_interrupt():
    out: list[str] = []
    gate = threading.Event()
    runner = CodeRunner({"gate": gate}, out.append)
    runner.run("gate.wait(5)")
    runner.interrupt()
    assert runner.run("21 * 2")
    runner.join(5)
    gate.set()
    assert "42\n" in out


def test_interrupt_when_idle_does_nothing():
    assert CodeRunner({}, lambda _text: None).interrupt() is False
