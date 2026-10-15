"""Running typed code on a worker thread, with its output sent to a pane."""

import ast
import codeop
import io
import sys
import threading
import traceback
from collections.abc import Callable
from typing import Any


class PaneWriter(io.TextIOBase):
    """A text stream that hands every write to ``write``, from any thread."""

    def __init__(self, write: Callable[[str], None]) -> None:
        self._write = write
        self._lock = threading.Lock()

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        with self._lock:
            self._write(text)
        return len(text)


class CodeRunner:
    """Runs one input at a time on a worker thread, in a namespace that persists between inputs.

    The last statement of an input is echoed when it is an expression, as the Python REPL does.
    """

    def __init__(
        self, namespace: dict[str, Any], write: Callable[[str], None], on_done: Callable[[], None] | None = None
    ) -> None:
        self.namespace = namespace
        self._write = write
        self._on_done = on_done
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @staticmethod
    def is_complete(source: str) -> bool:
        """Whether Enter should run ``source``: a syntax error is complete, so it gets reported."""
        try:
            # An auto-indented empty last line ends a block, as a truly empty one does.
            return codeop.compile_command(source.rstrip(" \t"), "<console>", "single") is not None
        except (SyntaxError, ValueError, OverflowError):
            return True

    def run(self, source: str) -> bool:
        if self.busy:
            return False
        self._thread = threading.Thread(target=self._execute, args=(source,), name="console-runner", daemon=True)
        self._thread.start()
        return True

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _execute(self, source: str) -> None:
        try:
            tree = ast.parse(source, "<console>")
            last = tree.body[-1:] if tree.body and isinstance(tree.body[-1], ast.Expr) else []
            body = ast.Module(tree.body[: len(tree.body) - len(last)], type_ignores=[])
            exec(compile(body, "<console>", "exec"), self.namespace)
            if last:
                exec(compile(ast.Interactive(last), "<console>", "single"), self.namespace)
        except BaseException as e:
            # The traceback starts at the user's code, not at this frame.
            tb = e.__traceback__.tb_next if e.__traceback__ is not None else None
            self._write("".join(traceback.format_exception(type(e), e, tb)))
        finally:
            sys.stdout.flush()
            if self._on_done is not None:
                self._on_done()
