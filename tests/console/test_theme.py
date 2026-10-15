from empire_core.console.theme import STYLE


def colour(style_class):
    return STYLE.get_attrs_for_style_str(f"class:{style_class}").color


def test_sent_and_received_arrows_are_green_and_red():
    sent, received = colour("frame.sent"), colour("frame.received")
    assert sent and received and sent != received


def test_selection_keeps_the_arrow_colour():
    assert STYLE.get_attrs_for_style_str("class:frame.selected class:frame.sent").color == colour("frame.sent")
