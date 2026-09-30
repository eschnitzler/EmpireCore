"""Griffe extensions for the API reference."""

import re

import griffe

_HEADER = re.compile(r"^(\s*)(Example|Examples|Usage):{1,2}\s*$")


def fence_examples(text: str) -> str:
    """Put the plain code under an ``Example:`` or ``Usage:`` header in a python code fence."""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = _HEADER.match(line)
        out.append(line)
        i += 1
        if not match:
            continue
        indent = len(match.group(1))
        body = []
        while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
            body.append(lines[i])
            i += 1
        trailing = []
        while body and not body[-1].strip():
            trailing.append(body.pop())
        code = [b for b in body if b.strip()]
        if not code or any("```" in b or ">>>" in b for b in code):
            out.extend(body + trailing)
            continue
        pad = " " * min(len(b) - len(b.lstrip()) for b in code)
        out.extend([f"{pad}```python", *body, f"{pad}```", *trailing])
    return "\n".join(out)


class FenceExamples(griffe.Extension):
    def on_instance(self, *, obj: griffe.Object, **kwargs: object) -> None:
        if obj.docstring is not None:
            obj.docstring.value = fence_examples(obj.docstring.value)
