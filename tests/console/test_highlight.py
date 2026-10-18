from prompt_toolkit.document import Document

from empire_core.console.highlight import BANNER_MARK, OutputLexer


def styles(text):
    get_line = OutputLexer().lex_document(Document(text))
    return [" ".join(style for style, *_ in get_line(i)) for i in range(len(text.splitlines()))]


def test_echoed_input_gets_a_prompt_and_python_colours():
    [line] = styles(">>> client.castle.get_all()")
    assert line.startswith("class:output.prompt") and "pygments" in line


def test_results_are_python_coloured():
    [line] = styles("[1, 'a']")
    assert "pygments" in line


def test_a_traceback_is_red_to_its_last_line():
    text = 'Traceback (most recent call last):\n  File "<console>", line 1\n    1 / 0\nZeroDivisionError: x\n[1]'
    *trace, after = styles(text)
    assert all(line == "class:output.error" for line in trace)
    assert "pygments" in after


def test_a_syntax_error_without_a_header_is_red():
    text = '  File "<console>", line 1\n    1 +* 2\n       ^\nSyntaxError: invalid syntax'
    assert set(styles(text)) == {"class:output.error"}


def test_status_log_and_banner_lines():
    ok, fail, warning, banner = styles(f"✓ 0.21 s\n✗ 0.02 s\nWARNING x: y\n{BANNER_MARK}hello")
    assert ok == "class:output.ok" and fail == "class:output.fail"
    assert warning == "class:output.warning" and banner == "class:output.banner"
