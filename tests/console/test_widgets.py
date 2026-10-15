from prompt_toolkit.application import Application, create_app_session
from prompt_toolkit.application.current import set_app
from prompt_toolkit.data_structures import Point
from prompt_toolkit.document import Document
from prompt_toolkit.input import DummyInput
from prompt_toolkit.layout import Layout
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from prompt_toolkit.output import DummyOutput

from empire_core.console.widgets import BorderControl, ScrollbarControl, TextPane, osc52


def event(y, kind=MouseEventType.MOUSE_DOWN, button=MouseButton.LEFT):
    return MouseEvent(Point(0, y), kind, button, frozenset())


def bar(first, shown, total):
    jumps: list[int] = []
    control = ScrollbarControl(lambda: (first, shown, total), jumps.append)
    content = control.create_content(1, 10)
    thumb = [i for i in range(10) if "button" in content.get_line(i)[0][0]]
    return control, jumps, thumb


def test_thumb_shows_where_the_view_is():
    _, _, top = bar(0, 10, 100)
    _, _, bottom = bar(90, 10, 100)
    assert top == [0] and bottom == [9]


def test_no_thumb_when_everything_fits():
    _, _, thumb = bar(0, 10, 5)
    assert thumb == []


def test_click_and_drag_jump_proportionally():
    control, jumps, _ = bar(0, 10, 100)
    control.mouse_handler(event(9))
    control.mouse_handler(event(0, MouseEventType.MOUSE_MOVE))
    assert jumps == [90, 0]


def test_wheel_scrolls_by_steps():
    control, jumps, _ = bar(50, 10, 100)
    control.mouse_handler(event(5, MouseEventType.SCROLL_DOWN, MouseButton.NONE))
    control.mouse_handler(event(5, MouseEventType.SCROLL_UP, MouseButton.NONE))
    assert jumps == [53, 47]


def test_moving_without_a_button_does_nothing():
    control, jumps, _ = bar(0, 10, 100)
    assert control.mouse_handler(event(5, MouseEventType.MOUSE_MOVE, MouseButton.NONE)) is NotImplemented
    assert jumps == []


def test_border_draws_its_line_and_reports_a_press():
    presses: list[int] = []
    border = BorderControl("│", lambda: "class:panel.border", lambda: presses.append(1))
    content = border.create_content(1, 3)
    assert content.line_count == 3 and content.get_line(2)[0][1] == "│"
    assert border.mouse_handler(event(1)) is None and presses == [1]
    assert border.mouse_handler(event(1, MouseEventType.MOUSE_UP)) is NotImplemented


def selecting_pane(copied):
    pane = TextPane(lexer=None, wrap_lines=False, on_copy=copied.append)
    pane.buffer.set_document(Document("alpha beta gamma", 0), bypass_readonly=True)
    pane.buffer.start_selection()
    pane.buffer.cursor_position = 5
    return pane


def test_scrolling_drops_the_selection_instead_of_growing_it():
    pane = selecting_pane([])
    assert pane.control.mouse_handler(event(0, MouseEventType.SCROLL_DOWN, MouseButton.NONE)) is NotImplemented
    assert pane.buffer.selection_state is None


def test_releasing_the_mouse_copies_the_selection():
    copied: list[str] = []
    pane = selecting_pane(copied)
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        with set_app(Application(layout=Layout(pane))):
            pane.control.mouse_handler(event(0, MouseEventType.MOUSE_UP))
    assert copied == ["alpha"]


def test_osc52_carries_the_text_base64_encoded():
    assert osc52("hi") == "\x1b]52;c;aGk=\x07"
