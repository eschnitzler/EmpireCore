"""Completion for the input: Python from jedi on the console's live objects, and the ``:`` commands."""

from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any

import jedi
from jedi.api.classes import Completion as JediCompletion
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document


class NamespaceCompleter(Completer):
    """Completes Python against the objects in ``namespace``, as they are at the moment.

    The jedi results of the last completion are kept, so :meth:`docs` can read the docstring of
    the one the menu highlights.
    """

    def __init__(self, namespace: dict[str, Any]) -> None:
        self.namespace = namespace
        self._last: dict[str, JediCompletion] = {}
        self._docs: dict[str, str] = {}

    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterator[Completion]:
        row, column = document.cursor_position_row + 1, document.cursor_position_col
        try:
            # jedi runs live objects' __getattr__ and races the worker thread; a failure means no menu.
            found = jedi.Interpreter(document.text, [self.namespace]).complete(row, column)
        except Exception:
            return
        self._last = {completion.name: completion for completion in found}
        self._docs = {}
        for completion in found:
            typed = completion.get_completion_prefix_length()
            yield Completion(completion.name, start_position=-typed, display_meta=completion.type)

    def docs(self, name: str) -> str:
        """The docstring of ``name`` among the last completions; empty when it has none."""
        if name not in self._docs:
            completion = self._last.get(name)
            try:
                self._docs[name] = completion.docstring() if completion is not None else ""
            except Exception:
                self._docs[name] = ""
        return self._docs[name]


class CommandCompleter(Completer):
    """Completes ``:`` commands by name, and their argument where the command lists the choices.

    ``commands`` gives each command's description; ``arguments`` maps a command to its choices.
    """

    def __init__(
        self, commands: Callable[[], Mapping[str, str]], arguments: Mapping[str, Callable[[], Iterable[str]]]
    ) -> None:
        self.commands = commands
        self.arguments = arguments

    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterator[Completion]:
        text = document.text_before_cursor.lstrip()[1:]
        name, _, argument = text.partition(" ")
        if not _:
            for command, description in sorted(self.commands().items()):
                if command.startswith(name):
                    yield Completion(command, start_position=-len(name), display_meta=description)
            return
        choices = self.arguments.get(name)
        word = argument.rsplit(" ", 1)[-1]
        for choice in sorted(set(choices())) if choices else ():
            if choice.startswith(word):
                yield Completion(choice, start_position=-len(word))


class ConsoleCompleter(Completer):
    """The input's completer: ``:`` commands when the line starts with ``:``, Python otherwise."""

    def __init__(self, python: Completer, commands: Completer) -> None:
        self.python = python
        self.commands = commands

    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterator[Completion]:
        chosen = self.commands if document.text.lstrip().startswith(":") else self.python
        yield from chosen.get_completions(document, complete_event)


def signature_at(namespace: dict[str, Any], text: str, row: int, column: int) -> str:
    """The signature of the call the cursor is in, as ``name(params)``; empty outside a call."""
    signatures = jedi.Interpreter(text, [namespace]).get_signatures(row + 1, column)
    return signatures[0].to_string() if signatures else ""
