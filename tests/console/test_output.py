from empire_core.console.output import OutputLog

WIDE_LIST = list(range(1000, 1010))


def test_results_reflow_to_the_width():
    log = OutputLog()
    log.show(WIDE_LIST)
    narrow, changed = log.render(30)
    assert changed and len(narrow.splitlines()) > 1 and all(len(line) <= 30 for line in narrow.splitlines())
    wide, changed = log.render(100)
    assert changed and wide == repr(WIDE_LIST) + "\n"


def test_text_is_kept_as_written():
    log = OutputLog()
    log.write("printed " * 20 + "\n")
    assert log.render(20)[0] == log.render(200)[0] == "printed " * 20 + "\n"


def test_nothing_new_at_the_same_width_is_no_change():
    log = OutputLog()
    log.write("a\n")
    log.render(50)
    assert log.render(50) == ("a\n", False)
    log.write("b\n")
    assert log.render(50) == ("a\nb\n", True)


def test_old_entries_go_past_the_limit():
    log = OutputLog(limit=len("second\nthird\n"))
    for word in ("first\n", "second\n", "third\n"):
        log.write(word)
    text, _ = log.render(50)
    assert text == "second\nthird\n"


def test_clear_forgets_everything():
    log = OutputLog()
    log.write("a\n")
    log.show(1)
    log.clear()
    assert log.render(50) == ("", True)
