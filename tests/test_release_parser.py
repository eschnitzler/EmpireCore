"""The release commit parser keeps a BREAKING CHANGE footer whole."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_parser():
    spec = importlib.util.spec_from_file_location(
        "release_commit_parser", ROOT / "scripts" / "release_commit_parser.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.ConventionalParser()


PARSER = _load_parser()


def _breaking(message: str) -> tuple[str, ...]:
    result = PARSER.parse_message(message)
    assert result is not None
    return result.breaking_descriptions


class TestBreakingFooter:
    def test_a_bulleted_footer_keeps_every_bullet(self):
        message = "feat(events)!: rename\n\nBody.\n\nBREAKING CHANGE: names change:\n- A -> B\n- C -> D\n"
        assert _breaking(message) == ("names change:\n- A -> B\n- C -> D",)

    def test_a_wrapped_prose_footer_reads_as_one_line(self):
        message = "fix(x)!: change\n\nBREAKING CHANGE: the field is now an int\nor None.\n"
        assert _breaking(message) == ("the field is now an int or None.",)

    def test_a_commit_without_one_has_none(self):
        assert _breaking("fix(x): change\n\nBody.\n") == ()
