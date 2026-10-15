import pytest

from empire_core.console.theme import DARK, LIGHT, THEMES, Palette, contrast


def attrs(theme, style_classes):
    return THEMES[theme].get_attrs_for_style_str(" ".join(f"class:{c}" for c in style_classes.split()))


@pytest.mark.parametrize("palette", [DARK, LIGHT], ids=["dark", "light"])
def test_text_is_easy_to_read(palette: Palette):
    assert contrast(palette.text, palette.background) >= 7
    assert contrast(palette.dim, palette.background) >= 3


@pytest.mark.parametrize("palette", [DARK, LIGHT], ids=["dark", "light"])
def test_accents_stand_out_from_the_background(palette: Palette):
    for accent in (palette.blue, palette.green, palette.red, palette.yellow, palette.purple, palette.cyan):
        assert contrast(accent, palette.background) >= 3, accent


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_the_app_paints_its_own_background(theme):
    palette = {"dark": DARK, "light": LIGHT}[theme]
    assert attrs(theme, "app").bgcolor == palette.background.lstrip("#")


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_sent_and_received_arrows_are_red_and_green(theme):
    sent, received = attrs(theme, "frame.sent").color, attrs(theme, "frame.received").color
    assert sent and received and sent != received


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_code_and_json_are_coloured(theme):
    keyword = attrs(theme, "pygments pygments.keyword").color
    string = attrs(theme, "pygments pygments.literal pygments.literal.string").color
    json_key = attrs(theme, "pygments pygments.name pygments.name.tag").color
    assert keyword and string and json_key and len({keyword, string, json_key}) == 3


def test_selection_keeps_the_arrow_colour():
    assert attrs("dark", "frame.selected frame.sent").color == attrs("dark", "frame.sent").color
