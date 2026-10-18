"""Completion and call signatures from jedi, on the console's live objects."""

from collections.abc import Iterator
from typing import Any

import jedi
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document


class NamespaceCompleter(Completer):
    """Completes Python against the objects in ``namespace``, as they are at the moment."""

    def __init__(self, namespace: dict[str, Any]) -> None:
        self.namespace = namespace

    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterator[Completion]:
        row, column = document.cursor_position_row + 1, document.cursor_position_col
        try:
            # jedi runs live objects' __getattr__ and races the worker thread; a failure means no menu.
            found = jedi.Interpreter(document.text, [self.namespace]).complete(row, column)
        except Exception:  # noqa: BLE001 - see above
            return
        for completion in found:
            typed = completion.get_completion_prefix_length()
            yield Completion(completion.name, start_position=-typed, display_meta=completion.type)


def signature_at(namespace: dict[str, Any], text: str, row: int, column: int) -> str:
    """The signature of the call the cursor is in, as ``name(params)``; empty outside a call."""
    signatures = jedi.Interpreter(text, [namespace]).get_signatures(row + 1, column)
    return signatures[0].to_string() if signatures else ""
