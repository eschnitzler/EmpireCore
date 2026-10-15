"""A rounded panel whose border and title light up while it has focus."""

from collections.abc import Callable

from prompt_toolkit.filters import Filter
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.layout import AnyContainer, Container, HSplit, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import AnyDimension


class Panel:
    """``body`` in a rounded border with a title; ``title`` is called on every render."""

    def __init__(
        self,
        body: AnyContainer,
        title: Callable[[], StyleAndTextTuples],
        focused: Filter,
        *,
        height: AnyDimension = None,
    ) -> None:
        def border() -> str:
            return "class:panel.border.focused" if focused() else "class:panel.border"

        def heading() -> StyleAndTextTuples:
            name = "class:panel.title.focused" if focused() else "class:panel.title"
            return [(border(), "─ "), *[(style or name, text) for style, text, *_ in title()], (border(), " ")]

        def edge(char: str) -> Window:
            return Window(width=1, height=1, char=char, style=border)

        self.container = HSplit(
            [
                VSplit(
                    [
                        edge("╭"),
                        Window(FormattedTextControl(heading), height=1, dont_extend_width=True),
                        Window(height=1, char="─", style=border),
                        edge("╮"),
                    ]
                ),
                VSplit([Window(width=1, char="│", style=border), body, Window(width=1, char="│", style=border)]),
                VSplit([edge("╰"), Window(height=1, char="─", style=border), edge("╯")]),
            ],
            height=height,
        )

    def __pt_container__(self) -> Container:
        return self.container
