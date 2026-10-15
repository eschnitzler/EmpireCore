"""The console's colours: a One Dark palette over pygments' one-dark code style."""

from prompt_toolkit.styles import BaseStyle, Style, merge_styles, style_from_pygments_cls
from pygments.styles import get_style_by_name

BLUE, GREEN, YELLOW, RED, PURPLE, CYAN = "#61afef", "#98c379", "#e5c07b", "#e06c75", "#c678dd", "#56b6c2"
TEXT, DIM, FAINT, PANEL, SELECTED = "#abb2bf", "#7f848e", "#5c6370", "#21252b", "#2c313c"

UI = Style.from_dict(
    {
        "panel.border": FAINT,
        "panel.border.focused": BLUE,
        "panel.title": f"bold {TEXT}",
        "panel.title.focused": f"bold {BLUE}",
        "panel.chip": DIM,
        "panel.chip.live": GREEN,
        "panel.chip.paused": f"bold {YELLOW}",
        "panel.chip.filter": CYAN,
        "panel.chip.model": PURPLE,
        "frame.header": f"bold {FAINT}",
        "frame.time": FAINT,
        "frame.sent": f"bold {CYAN}",
        "frame.received": f"bold {GREEN}",
        "frame.command": f"bold {YELLOW}",
        "frame.error": f"bold {RED}",
        "frame.size": DIM,
        "frame.latency": PURPLE,
        "frame.preview": DIM,
        "frame.selected": f"bg:{SELECTED}",
        "frame.marker": f"bold {BLUE}",
        "output.prompt": f"bold {BLUE}",
        "output.error": RED,
        "output.warning": YELLOW,
        "output.ok": GREEN,
        "output.fail": RED,
        "output.banner": f"bold {PURPLE}",
        "output.dim": FAINT,
        "signature": f"italic {DIM}",
        "toolbar": f"bg:{PANEL} {DIM}",
        "toolbar.key": f"bg:{PANEL} bold {BLUE}",
        "toolbar.online": f"bg:{PANEL} bold {GREEN}",
        "toolbar.offline": f"bg:{PANEL} bold {RED}",
        "toolbar.busy": f"bg:{PANEL} bold {YELLOW}",
        "help": f"bg:{PANEL} {TEXT}",
        "help.key": f"bg:{PANEL} bold {BLUE}",
        "help.heading": f"bg:{PANEL} bold {PURPLE}",
        "completion-menu": f"bg:{SELECTED} {TEXT}",
        "completion-menu.completion.current": f"bg:{BLUE} #282c34",
        "completion-menu.meta.completion": f"bg:{SELECTED} {DIM}",
        "completion-menu.meta.completion.current": f"bg:{BLUE} #282c34",
        "scrollbar.background": f"bg:{SELECTED}",
        "scrollbar.button": f"bg:{FAINT}",
    }
)

STYLE: BaseStyle = merge_styles([style_from_pygments_cls(get_style_by_name("one-dark")), UI])
