"""The console's themes: One Dark (the default) and One Light, each one palette for the UI and the code."""

from dataclasses import dataclass

from prompt_toolkit.styles import Style


@dataclass(frozen=True)
class Palette:
    background: str
    panel: str
    row: str
    selection: str
    text: str
    dim: str
    faint: str
    blue: str
    green: str
    yellow: str
    red: str
    purple: str
    cyan: str
    orange: str


DARK = Palette(
    background="#282c34",
    panel="#21252b",
    row="#2c313c",
    selection="#3e4451",
    text="#b6bdca",
    dim="#7f848e",
    faint="#5c6370",
    blue="#61afef",
    green="#98c379",
    yellow="#e5c07b",
    red="#e06c75",
    purple="#c678dd",
    cyan="#56b6c2",
    orange="#d19a66",
)

# One Light, with green, yellow, red and blue deepened to stay readable on white.
LIGHT = Palette(
    background="#fafafa",
    panel="#eaeaeb",
    row="#e5e5e6",
    selection="#d4d8e0",
    text="#383a42",
    dim="#696c77",
    faint="#a0a1a7",
    blue="#3a6fe0",
    green="#3f8a3e",
    yellow="#a26e00",
    red="#d2402f",
    purple="#a626a4",
    cyan="#0184bc",
    orange="#986801",
)


def style(p: Palette) -> Style:
    return Style.from_dict(
        {
            "app": f"bg:{p.background} {p.text}",
            "panel.border": p.faint,
            "panel.border.focused": p.blue,
            "panel.title": f"bold {p.text}",
            "panel.title.focused": f"bold {p.blue}",
            "panel.chip": p.dim,
            "panel.chip.live": p.green,
            "panel.chip.paused": f"bold {p.yellow}",
            "panel.chip.filter": p.cyan,
            "panel.chip.model": p.purple,
            "frame.header": f"bold {p.faint}",
            "frame.time": p.faint,
            "frame.sent": f"bold {p.red}",
            "frame.received": f"bold {p.green}",
            "frame.command": f"bold {p.yellow}",
            "frame.error": f"bold {p.red}",
            "frame.size": p.dim,
            "frame.latency": p.purple,
            "frame.preview": p.dim,
            "frame.selected": f"bg:{p.row}",
            "frame.marker": f"bold {p.blue}",
            "output.prompt": f"bold {p.blue}",
            "output.error": p.red,
            "output.warning": p.yellow,
            "output.ok": p.green,
            "output.fail": p.red,
            "output.banner": f"bold {p.purple}",
            "output.dim": p.faint,
            "signature": f"italic {p.dim}",
            "toolbar": p.faint,
            "toolbar.key": f"bold {p.blue}",
            "toolbar.online": f"bold {p.green}",
            "toolbar.offline": f"bold {p.red}",
            "toolbar.busy": f"bold {p.yellow}",
            "help": f"bg:{p.background} {p.text}",
            "help.key": f"bold {p.blue}",
            "help.text": p.text,
            "help.heading": f"bold underline {p.purple}",
            "completion-menu": f"bg:{p.row} {p.text}",
            "completion-menu.completion.current": f"bg:{p.blue} {p.background}",
            "completion-menu.meta.completion": f"bg:{p.row} {p.dim}",
            "completion-menu.meta.completion.current": f"bg:{p.blue} {p.background}",
            "selected": f"bg:{p.selection}",
            "banner": f"bg:{p.red} bold {p.background}",
            "scrollbar.background": f"bg:{p.row}",
            "scrollbar.button": f"bg:{p.faint}",
            "pygments.keyword": p.purple,
            "pygments.keyword.constant": p.orange,
            "pygments.name.builtin": p.cyan,
            "pygments.name.function": p.blue,
            "pygments.name.class": p.yellow,
            "pygments.name.exception": p.yellow,
            "pygments.name.decorator": p.blue,
            "pygments.name.tag": p.red,
            "pygments.literal.string": p.green,
            "pygments.literal.number": p.orange,
            "pygments.operator": p.cyan,
            "pygments.operator.word": p.purple,
            "pygments.punctuation": p.text,
            "pygments.comment": f"italic {p.faint}",
            "pygments.error": p.red,
        }
    )


THEMES = {"dark": style(DARK), "light": style(LIGHT)}


def contrast(foreground: str, background: str) -> float:
    """The WCAG contrast ratio of two ``#rrggbb`` colours, from 1 to 21."""

    def luminance(colour: str) -> float:
        channels = [int(colour.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)
