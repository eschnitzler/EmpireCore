"""Griffe extensions: the source's reST-flavoured docstrings as Markdown, and callback declarations as methods."""

import re

import griffe

_EXAMPLE_HEADER = re.compile(r"^(\s*)(Example|Examples|Usage):{1,2}\s*$")
_ROLE = re.compile(r":(?:py:)?(?:meth|class|attr|func|mod|exc|data|obj):`(~?)([^`<]*?)(?:\s*<([^>]+)>)?`")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")
_UNDERLINE = re.compile(r"^\s*([-=~^])\1{2,}\s*$")
_TABLE_RULE = re.compile(r"^\s*=+(?:\s+=+)+\s*$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _role(match: re.Match[str]) -> str:
    short, text, target = match.groups()
    text = (text or target or "").strip()
    if short:
        text = text.rsplit(".", 1)[-1]
    return f"`{text}`"


def _take_block(lines: list[str], i: int, indent: int) -> tuple[list[str], int]:
    body = []
    while i < len(lines) and (not lines[i].strip() or _indent(lines[i]) > indent):
        body.append(lines[i])
        i += 1
    return body, i


def _fenced(body: list[str], language: str) -> list[str]:
    trailing = []
    while body and not body[-1].strip():
        trailing.append(body.pop())
    code = [b for b in body if b.strip()]
    if not code or any("```" in b or ">>>" in b for b in code):
        return body + trailing
    pad = " " * min(_indent(b) for b in code)
    return [f"{pad}```{language}", *body, f"{pad}```", *trailing]


def _literal(body: list[str], indent: int) -> list[str]:
    code = [b for b in body if b.strip()]
    if not code:
        return body
    cut = min(_indent(b) for b in code) - indent
    while body and not body[0].strip():
        body = body[1:]
    trailing = []
    while body and not body[-1].strip():
        trailing.append(body.pop())
    pad = " " * indent
    return ["", f"{pad}```python", *[b[cut:] if b.strip() else "" for b in body], f"{pad}```", *trailing]


def markdownify(text: str) -> str:
    """Rewrite reST roles, literal blocks, headings, tables and tight lists as Markdown."""
    lines = text.splitlines()
    out: list[str] = []
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            i += 1
            continue
        if in_fence:
            out.append(line)
            i += 1
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if _TABLE_RULE.match(line):
            table = [line]
            i += 1
            rules = 1
            while i < len(lines) and rules < 3:
                table.append(lines[i])
                rules += bool(_TABLE_RULE.match(lines[i]))
                i += 1
            pad = " " * _indent(line)
            out.extend(["", f"{pad}```text", *table, f"{pad}```", ""])
            continue
        if line.strip() and _UNDERLINE.match(nxt) and len(nxt.strip()) >= len(line.strip()) - 1:
            out.extend(["", f"{' ' * _indent(line)}**{_ROLE.sub(_role, line.strip())}**", ""])
            i += 2
            continue
        header = _EXAMPLE_HEADER.match(line)
        if header or (line.rstrip().endswith("::") and not line.strip().startswith(":")):
            body, i = _take_block(lines, i + 1, _indent(line))
            if header:
                out.append(line)
                out.extend(_fenced(body, "python"))
                continue
            stripped = line.rstrip()[:-2].rstrip()
            out.append(_ROLE.sub(_role, stripped + ":") if stripped else "")
            out.extend(_literal(body, _indent(line)))
            continue
        line = _ROLE.sub(_role, line)
        previous = out[-1] if out else ""
        if (
            _LIST_ITEM.match(line)
            and previous.strip()
            and not _LIST_ITEM.match(previous)
            and _indent(previous) <= _indent(line)
        ):
            out.append("")
        out.append(line)
        i += 1
    return "\n".join(out)


class MarkdownDocstrings(griffe.Extension):
    def on_instance(self, *, obj: griffe.Object, **kwargs: object) -> None:
        if obj.docstring is not None:
            obj.docstring.value = markdownify(obj.docstring.value)


class CallbackDeclarations(griffe.Extension):
    """Show each ``on_x = Event[A, B]()`` (or ``EventOf[C]()``) as the method it is, with its ``.remove``."""

    def on_class_members(self, *, cls: griffe.Class, **kwargs: object) -> None:
        for name, member in list(cls.members.items()):
            value = getattr(member, "value", None)
            if not (isinstance(value, griffe.ExprCall) and isinstance(value.function, griffe.ExprSubscript)):
                continue
            declaration = str(value.function.left).rsplit(".", 1)[-1]
            arguments = value.function.slice
            if declaration == "Event":
                elements = arguments.elements if isinstance(arguments, griffe.ExprTuple) else [arguments]
                callback = griffe.ExprSubscript(
                    "Callable", griffe.ExprTuple([griffe.ExprList(list(elements)), "object"], implicit=True)
                )
            elif declaration == "EventOf":
                callback = arguments
            else:
                continue
            docstring = member.docstring.value if member.docstring is not None else ""
            positional = griffe.ParameterKind.positional_or_keyword
            cls.set_member(
                name,
                griffe.Function(
                    name,
                    lineno=member.lineno,
                    endlineno=member.endlineno,
                    parameters=griffe.Parameters(
                        griffe.Parameter("self", kind=positional),
                        griffe.Parameter("callback", annotation=callback, kind=positional),
                    ),
                    returns="None",
                    docstring=griffe.Docstring(
                        f"{docstring}\n\nUnregister a callback with `{name}.remove(callback)`.".lstrip(),
                        parent=member.parent,
                    ),
                ),
            )
