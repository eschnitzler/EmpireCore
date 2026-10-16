"""Running typed code on a worker thread, with its output sent to a pane."""

import ast
import codeop
import io
import sys
import threading
import time
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

    The last statement of an input, when it is an expression and not None, goes to ``show`` and
    is kept as ``_``, as the Python REPL does; by default ``show`` writes its repr.
    ``on_done`` gets how long the input ran and whether it finished without an exception.
    """

    def __init__(
        self,
        namespace: dict[str, Any],
        write: Callable[[str], None],
        on_done: Callable[[float, bool], None] | None = None,
        show: Callable[[Any], None] | None = None,
    ) -> None:
        self.namespace = namespace
        self.started_at = 0.0
        self._write = write
        self._show = show or (lambda value: write(repr(value) + "\n"))
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
        self.started_at = time.monotonic()
        self._thread = threading.Thread(target=self._execute, args=(source,), name="console-runner", daemon=True)
        self._thread.start()
        return True

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _execute(self, source: str) -> None:
        ok = False
        try:
            tree = ast.parse(source, "<console>")
            last = tree.body[-1] if tree.body and isinstance(tree.body[-1], ast.Expr) else None
            body = ast.Module(tree.body[:-1] if last else tree.body, type_ignores=[])
            exec(compile(body, "<console>", "exec"), self.namespace)
            if last is not None:
                value = eval(compile(ast.Expression(last.value), "<console>", "eval"), self.namespace)
                if value is not None:
                    self.namespace["_"] = value
                    self._show(value)
            ok = True
        except BaseException as e:
            # The traceback starts at the user's code, not at this frame.
            tb = e.__traceback__.tb_next if e.__traceback__ is not None else None
            self._write("".join(traceback.format_exception(type(e), e, tb)))
        finally:
            sys.stdout.flush()
            if self._on_done is not None:
                self._on_done(time.monotonic() - self.started_at, ok)
