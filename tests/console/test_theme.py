from empire_core.console.theme import STYLE


def background(style_class):
    return STYLE.get_attrs_for_style_str(f"class:{style_class}").bgcolor


def test_direction_badges_have_distinct_solid_backgrounds():
    sent, received = background("frame.sent"), background("frame.received")
    assert sent and received and sent != received


def test_selection_does_not_paint_over_a_badge():
    assert STYLE.get_attrs_for_style_str("class:frame.selected class:frame.sent").bgcolor == background("frame.sent")
