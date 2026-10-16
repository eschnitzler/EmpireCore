"""What F1 shows: the console's keys and commands, in two columns of sections."""

from prompt_toolkit.formatted_text import StyleAndTextTuples

Section = tuple[str, tuple[tuple[str, str], ...]]

COLUMNS: tuple[tuple[Section, ...], ...] = (
    (
        (
            "Code",
            (
                ("Enter", "run once the statement is complete"),
                ("Esc Enter", "run whatever is typed"),
                ("Tab  ↑↓", "complete · history"),
                ("Ctrl-C", "stop running code, else clear"),
                ("Ctrl-L", "clear the output"),
                ("exit()", "close the client and exit"),
            ),
        ),
        (
            "Panes",
            (
                ("Ctrl-arrows", "move to the pane that way"),
                ("F2  Shift-F2", "next · previous pane"),
                ("click  wheel", "focus · scroll a pane"),
                ("drag a border", "resize panes"),
                ("drag over text", "select and copy it"),
                ("Ctrl-C  y", "copy selection or pane"),
                ("Home  End", "top · bottom of a pane"),
            ),
        ),
    ),
    (
        (
            "Frames",
            (
                ("↑↓ PgUp PgDn", "select a frame"),
                ("Home  End", "oldest · follow the newest"),
                ("r", "parsed model or raw payload"),
                ("c", "copy the shown detail"),
                ("F3", "zoom the focused side"),
                ("F4", "dark or light theme"),
            ),
        ),
        (
            "Commands",
            (
                (":filter gbd gam", "only these commands"),
                (":grep text", "frames containing text"),
                (":pause  :clear", "freeze · forget frames"),
                (":raw", "parsed or raw detail"),
                (":theme [name]", "dark, light, or toggle"),
                (":save [file]", "shown frames as JSON lines"),
                (":quit", "close the client and exit"),
            ),
        ),
    ),
)

KEY_WIDTH = max(len(key) for column in COLUMNS for _, entries in column for key, _ in entries) + 2
GUTTER = 4


def help_column(sections: tuple[Section, ...]) -> StyleAndTextTuples:
    fragments: StyleAndTextTuples = []
    for index, (title, entries) in enumerate(sections):
        if index:
            fragments.append(("", "\n"))
        fragments.append(("class:help.heading", f"{title}\n"))
        for key, what in entries:
            fragments += [("class:help.key", f"{key:<{KEY_WIDTH}}"), ("class:help.text", f"{what}\n")]
    return fragments[:-1] + [(fragments[-1][0], fragments[-1][1].rstrip("\n"))]


def column_width(sections: tuple[Section, ...]) -> int:
    return KEY_WIDTH + max(len(what) for _, entries in sections for _, what in entries)


def help_size() -> tuple[int, int]:
    """The width and height of the two columns side by side, without border or padding."""
    width = sum(column_width(column) for column in COLUMNS) + GUTTER
    height = max(len("".join(f[1] for f in help_column(column)).splitlines()) for column in COLUMNS)
    return width, height
