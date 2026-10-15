"""A rounded panel whose border lights up with focus, and a scrollbar the mouse can use."""

from collections.abc import Callable

from prompt_toolkit.filters import Filter
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.layout import AnyContainer, Container, HSplit, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl, UIContent, UIControl
from prompt_toolkit.layout.dimension import AnyDimension
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from prompt_toolkit.widgets import TextArea

WHEEL_STEP = 3


class ScrollbarControl(UIControl):
    """A one-column scrollbar: click or drag the track to jump there, use the wheel to step.

    ``position`` returns ``(first, shown, total)`` in lines; ``scroll_to`` gets the first line to show.
    """

    def __init__(self, position: Callable[[], tuple[int, int, int]], scroll_to: Callable[[int], None]) -> None:
        self.position = position
        self.scroll_to = scroll_to
        self._height = 1

    def create_content(self, width: int, height: int) -> UIContent:
        self._height = max(height, 1)
        first, shown, total = self.position()
        thumb = range(0)
        if total > shown:
            size = max(1, round(height * shown / total))
            top = round((height - size) * first / (total - shown))
            thumb = range(top, top + size)
        lines: list[StyleAndTextTuples] = [
            [("class:scrollbar.button" if row in thumb else "class:scrollbar.background", " ")] for row in range(height)
        ]
        return UIContent(get_line=lambda row: lines[row], line_count=height)

    def mouse_handler(self, mouse_event: MouseEvent) -> object:
        first, shown, total = self.position()
        kind = mouse_event.event_type
        dragging = kind is MouseEventType.MOUSE_MOVE and mouse_event.button is not MouseButton.NONE
        if kind is MouseEventType.MOUSE_DOWN or dragging:
            fraction = mouse_event.position.y / max(self._height - 1, 1)
            self.scroll_to(round(fraction * max(total - shown, 0)))
        elif kind is MouseEventType.SCROLL_DOWN:
            self.scroll_to(first + WHEEL_STEP)
        elif kind is MouseEventType.SCROLL_UP:
            self.scroll_to(first - WHEEL_STEP)
        else:
            return NotImplemented
        return None


def text_scrollbar(area: TextArea) -> ScrollbarControl:
    """A scrollbar for a read-only text area; scrolling moves its cursor, which the view follows."""

    def position() -> tuple[int, int, int]:
        info = area.window.render_info
        lines = area.document.line_count
        if info is None:
            return 0, 1, lines
        return info.vertical_scroll, info.window_height, max(info.content_height, lines)

    def scroll_to(line: int) -> None:
        document = area.document
        line = max(0, min(line, document.line_count - 1))
        area.window.vertical_scroll = line
        area.buffer.cursor_position = document.translate_row_col_to_index(line, 0)

    return ScrollbarControl(position, scroll_to)


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
