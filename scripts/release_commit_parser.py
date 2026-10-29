"""
The conventional commit parser, keeping a ``BREAKING CHANGE`` footer's bullet list.

python-semantic-release reads a footer with ``BREAKING[ -]CHANGE:\\s?(.*)``, which stops at the first line
break, and leaves a line break before each ``- `` bullet. So a footer that lists its changes as bullets lost
every bullet. This parser keeps the whole footer; ``templates/.components/changes.md.j2`` nests the bullets.
"""

from __future__ import annotations

import re

from semantic_release.commit_parser.conventional import ConventionalCommitParser

BREAKING_FOOTER = re.compile(r"BREAKING[ -]CHANGE:\s?(.*)", re.DOTALL)


class ConventionalParser(ConventionalCommitParser):
    def commit_body_components_separator(self, accumulator: dict[str, list[str]], text: str) -> dict[str, list[str]]:
        if (match := BREAKING_FOOTER.match(text)) and (description := match.group(1).strip()):
            accumulator["breaking_descriptions"].append(description)
            return accumulator
        return super().commit_body_components_separator(accumulator, text)
