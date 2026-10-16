from empire_core.console.help import COLUMNS, help_column, help_size


def text(fragments):
    return "".join(fragment[1] for fragment in fragments)


def test_every_section_and_key_is_shown():
    shown = " ".join(text(help_column(column)) for column in COLUMNS)
    for column in COLUMNS:
        for title, entries in column:
            assert title in shown
            for key, what in entries:
                assert key in shown and what in shown


def test_code_and_panes_sit_left_frames_and_commands_right():
    left, right = (text(help_column(column)) for column in COLUMNS)
    assert "Code" in left and "Panes" in left and "Frames" in right and "Commands" in right


def test_the_overlay_is_wide_enough_and_shorter_than_one_column_list():
    width, height = help_size()
    longest = max(len(text(help_column(column)).splitlines()) for column in COLUMNS)
    assert height == longest
    everything = sum(len(entries) + 2 for column in COLUMNS for _, entries in column)
    assert height < everything
    assert all(len(line) <= width for column in COLUMNS for line in text(help_column(column)).splitlines())


def test_help_uses_only_help_styles():
    styles = {fragment[0] for column in COLUMNS for fragment in help_column(column)}
    assert styles <= {"class:help.heading", "class:help.key", "class:help.text", ""}
