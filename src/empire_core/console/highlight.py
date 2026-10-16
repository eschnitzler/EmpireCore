"""Colours for the output pane: echoed input, results, tracebacks, log lines and run status."""

import re
from collections.abc import Callable
from enum import Enum
from functools import lru_cache

import pygments
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.styles.pygments import pygments_token_to_classname
from pygments.lexers.python import PythonLexer

BANNER_MARK = "◆ "
PROMPTS = (">>> ", "... ")

_LOG = re.compile(r"(DEBUG|INFO|WARNING|ERROR|CRITICAL) ")
_PYTHON = PythonLexer(stripnl=False, ensurenl=False)


class Kind(Enum):
    PYTHON = ""
    PROMPT = "class:output.prompt"
    ERROR = "class:output.error"
    WARNING = "class:output.warning"
    OK = "class:output.ok"
    FAIL = "class:output.fail"
    BANNER = "class:output.banner"
    DIM = "class:output.dim"


LOG_KINDS = {"DEBUG": Kind.DIM, "INFO": Kind.DIM, "WARNING": Kind.WARNING, "ERROR": Kind.ERROR, "CRITICAL": Kind.ERROR}


class OutputLexer(Lexer):
    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        lines = document.lines
        kinds = line_kinds(lines)

        def get_line(number: int) -> StyleAndTextTuples:
            if number >= len(lines):
                return []
            line, kind = lines[number], kinds[number]
            if kind is Kind.PROMPT:
                return [(kind.value, line[:4]), *python_fragments(line[4:])]
            if kind is Kind.PYTHON:
                return list(python_fragments(line))
            return [(kind.value, line)]

        return get_line


def line_kinds(lines: list[str]) -> list[Kind]:
    """Each line's kind; a traceback runs from its header (or first ``File`` line) to its unindented last line."""
    kinds: list[Kind] = []
    in_traceback = False
    for line in lines:
        if line.startswith("Traceback (most recent call last):") or line.startswith('  File "'):
            in_traceback = True
        if in_traceback:
            kinds.append(Kind.ERROR)
            in_traceback = line[:1].isspace() or line.startswith("Traceback")
        elif line.startswith(PROMPTS):
            kinds.append(Kind.PROMPT)
        elif line.startswith("✓ "):
            kinds.append(Kind.OK)
        elif line.startswith("✗ "):
            kinds.append(Kind.FAIL)
        elif line.startswith(BANNER_MARK):
            kinds.append(Kind.BANNER)
        elif match := _LOG.match(line):
            kinds.append(LOG_KINDS[match.group(1)])
        else:
            kinds.append(Kind.PYTHON)
    return kinds


@lru_cache(maxsize=4096)
def python_fragments(text: str) -> tuple[tuple[str, str], ...]:
    return tuple(("class:" + pygments_token_to_classname(token), value) for token, value in pygments.lex(text, _PYTHON))
