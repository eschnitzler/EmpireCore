"""
Extract the game client's command tables into ``tests/data/client_commands.json``.

    uv run python scripts/extract_client_commands.py --download              # the live client
    uv run python scripts/extract_client_commands.py --bundle Game.bundle.a4a25ae6d735e29092f6.js \\
        --dll ggs.dll.145565eddbcbe244aab0.js
    uv run python scripts/extract_client_commands.py --download --check      # exit 1 if the command tables changed

The client names every command it sends ``C2S_<NAME>`` and every reply or push
it handles ``S2C_<NAME>``, as static fields of its constant classes
(``ClientConstSF`` in the bundle; ``ConstantsSmartFox``, ``CoreEventsConstants``,
``BasicSmartfoxConstants`` and ``BasicSmartfoxClient`` in the dll). The snapshot
maps each command id to the constants that hold it, so a renamed constant shows
in a diff as well as a dropped id. The release is the hash in each file's name.

Two kinds of message the constant tables alone miss are added as well: the
SmartFox system messages ``BasicSmartfoxClient.handleSystemMessage`` switches
on (``apiOK``, ``joinOK``, ``roundTripRes``), as server messages, and every
constant the client passes to ``sendMessage``, as a client command, since the
keepalive is sent under ``S2C_PING``.

The ``requests`` and ``handlers`` tables record how the client uses each id
(see :func:`usage`): the request classes it constructs and the constants it sends
directly, and the handler classes it registers, marked `` (ack)`` when they never
read the payload. ``--coverage`` sorts every id into done, ack-only, remaining,
excluded or dead (:func:`classify`), with the exclusions, issue owners and the
commands covered without a model taken from ``tests/data/client_coverage.json``;
alone it reports on the committed snapshot, offline, and
``tests/protocol/test_client_coverage.py`` keeps the rules file current.

    uv run python scripts/extract_client_commands.py --coverage

``--check`` exits 1 when a table would change; a new release alone
only prints its hashes. Both modes also list every
command the library registers that the fresh tables lack;
``tests/protocol/test_client_commands.py`` fails on those against the committed
snapshot, offline.
"""

from __future__ import annotations

import argparse
import ast
import functools
import json
import re
import sys
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPT = "scripts/extract_client_commands.py"
BASE_URL = "https://empire-html5.goodgamestudios.com/default"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "tests" / "data" / "client_commands.json"
COVERAGE_RULES = Path(__file__).resolve().parents[1] / "tests" / "data" / "client_coverage.json"
SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "empire_core"

# Methods taking a command id, with the argument it is in and the direction of that command.
_COMMAND_ARGUMENTS = {
    "on_response": (0, "server"),
    "_register_handler": (0, "server"),
    "_unregister_handler": (0, "server"),
    "subscribe": (0, "server"),
    "unsubscribe": (0, "server"),
    "create_waiter": (0, "server"),
    "cancel_waiter": (0, "server"),
    "wait_for_result": (0, "server"),
    "request": (1, "server"),
    "build_xt": (1, "client"),
    "build_command": (1, "client"),
}
_COMMAND_KEYWORDS = ("cmd_id", "command")
# Constants whose keys or members are server command ids.
_COMMAND_TABLES = {"_DISPATCH", "_SECTION_PUSHES"}
_COMMAND_NAMES = {"cmd", "cmd_id", "command"}
_XT_COMMAND = re.compile(r"^%xt%\{[^}]*\}%([A-Za-z]+)%")

_ASSIGNMENT = re.compile(r"([A-Za-z_$][\w$]*)\.((?:C2S|S2C)_[A-Z0-9_]+)=\"([^\"]*)\"")
# A minified holder: var f=function(){return function ConstantsSmartFox(){}}()
_HOLDER = re.compile(r"\b([A-Za-z_$][\w$]*)=function\(\)\{return function ([A-Za-z_$][\w$]*)\(")
# BasicSmartfoxClient.handleSystemMessage=function(e){...switch(n){case"apiOK":...default:
_SYSTEM_HANDLER = re.compile(r"\.handleSystemMessage=function\(.*?\bdefault:", re.S)
_SYSTEM_CASE = re.compile(r"case\"([A-Za-z]+)\":")
# t.sendMessage(BasicSmartfoxClient.S2C_PING,[""])
_SENT = re.compile(r"\.sendMessage\(([A-Za-z_$][\w$]*)\.(S2C_[A-Z0-9_]+)\b")
# A command constant as code reads it: a.ClientConstSF.C2S_JOIN_CASTLE, f.S2C_PING
_REFERENCE = r"(?:[\w$]+\.)*?([\w$]+)\.((?:C2S|S2C)_[A-Z0-9_]+)\b"
# C2SJoinCastleVO.prototype.getCmdId=function(){return a.ClientConstSF.C2S_JOIN_CASTLE}
_REQUEST_CLASS = re.compile(r"([\w$]+)\.prototype\.getCmdId=function\(\)\{return " + _REFERENCE)
# u.BasicModel.smartfoxClient.sendMessage(s.BasicSmartfoxConstants.C2S_LOGIN,[...])
_DIRECT_SEND = re.compile(r"\.(?:sendMessage|sendServerMessageAndWait)\(" + _REFERENCE)
# i.set(s.ClientConstSF.S2C_PREMIUM_FLAG_INFO,new jl.GPFCommand)
_REGISTRATION = re.compile(r"\.set\(" + _REFERENCE + r",new (?:[\w$]+\.)*([\w$]+)\)")
_CONSTRUCTION = re.compile(r"\bnew (?:[\w$]+\.)*([\w$]+)")
_CLASS = re.compile(r"\.__extends\(([\w$]+),")
# ...},GPFCommand}(l.CastleCommand) closes the class's module function, passing its parent
_PARENT = r"\b{}\}}\((?:[\w$]+(?:\([^()]*\))?\.)*([\w$]+)\)"
_METHOD = re.compile(r"([\w$]+)\.prototype\.(executeCommand|exec)=function\(([\w$,]*)\)\{")
_ERROR_DIALOG = r"\.showErrorDialog\([\w$]+,{}\)"
# The snapshot's tables: the constants on each side, then what the client sends and handles
_TABLES = ("client", "server", "requests", "handlers")
_BUNDLE_NAME = re.compile(r"Game\.bundle\.([0-9a-f]+)\.js")
_DLL_NAME = re.compile(r"ggs\.dll\.([0-9a-f]+)\.js")


def _holder_names(source: str) -> Callable[[str, int], str]:
    """The constant class a (possibly minified) variable names at a position in ``source``."""
    holders: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for match in _HOLDER.finditer(source):
        holders[match.group(1)].append((match.start(), match.group(2)))

    def holder_name(var: str, position: int) -> str:
        names = [name for start, name in holders.get(var, []) if start < position]
        return names[-1] if names else var

    return holder_name


def extract(source: str) -> dict[str, dict[str, list[str]]]:
    """Every ``C2S_``/``S2C_`` constant in ``source``, as ``{"client"|"server": {id: ["Holder.NAME", ...]}}``."""
    holder_name = _holder_names(source)
    tables: dict[str, dict[str, set[str]]] = {"client": defaultdict(set), "server": defaultdict(set)}
    values: dict[tuple[str, str], str] = {}
    for match in _ASSIGNMENT.finditer(source):
        var, constant, command = match.groups()
        side = "client" if constant.startswith("C2S_") else "server"
        tables[side][command].add(f"{holder_name(var, match.start())}.{constant}")
        values[(var, constant)] = command
    for match in _SENT.finditer(source):
        var, constant = match.groups()
        if (var, constant) in values:
            tables["client"][values[(var, constant)]].add(f"{holder_name(var, match.start())}.{constant} (sent)")
    for handler in _SYSTEM_HANDLER.finditer(source):
        for case in _SYSTEM_CASE.finditer(handler.group(0)):
            tables["server"][case.group(1)].add("BasicSmartfoxClient.handleSystemMessage")
    return {
        side: {command: sorted(names) for command, names in sorted(table.items())} for side, table in tables.items()
    }


@dataclass
class _ClientClass:
    parent: str | None = None
    methods: dict[str, tuple[list[str], str]] = field(default_factory=dict)


def _block(source: str, start: int) -> str:
    """The body of the ``{`` block at ``start``, skipping braces inside string literals."""
    depth, quote, index = 0, "", start
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = ""
        elif char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1 : index]
        index += 1
    raise ValueError(f"unclosed block at {start}")


def _classes(source: str) -> dict[str, _ClientClass]:
    """Each ``__extends`` class in ``source`` with its parent and its ``executeCommand``/``exec`` methods."""
    classes: dict[str, _ClientClass] = defaultdict(_ClientClass)
    for match in _CLASS.finditer(source):
        name = match.group(1)
        end = re.compile(_PARENT.format(re.escape(name))).search(source, match.end())
        classes[name].parent = end.group(1) if end else None
    for match in _METHOD.finditer(source):
        name, method, params = match.groups()
        classes[name].methods[method] = (params.split(",") if params else [], _block(source, match.end() - 1))
    return classes


def _payload_used(body: str, names: set[str]) -> bool:
    """Whether ``body`` uses any of ``names`` other than to show the server's error dialog."""
    for name in names:
        body = re.sub(_ERROR_DIALOG.format(re.escape(name)), "", body)
    return any(re.search(rf"(?<![\w$.]){re.escape(name)}(?![\w$])", body) for name in names)


def _reads_payload(
    name: str, classes: dict[str, _ClientClass], method: str = "executeCommand", start: str | None = None
) -> bool:
    """
    Whether the handler class ``name`` reads its reply's payload, following inherited and super calls.

    ``executeCommand(code, params)`` gets the payload as ``params``; ``CastleCommand`` hands
    ``[code, params]`` to ``exec``, which is looked up from ``name`` again. ``start`` is the
    class to look ``method`` up from, for a super call. Anything not followed counts as read.
    """
    owner: str | None = start or name
    while owner is not None and method not in classes.get(owner, _ClientClass()).methods:
        owner = classes.get(owner, _ClientClass()).parent
    if owner is None:
        return True
    params, body = classes[owner].methods[method]
    parent = classes[owner].parent
    if method == "executeCommand":
        if len(params) < 2:
            return "arguments" in body
        payload = {params[1]}
        if re.search(r"\bthis\.exec\(", body):
            return _reads_payload(name, classes, "exec")
    else:
        if not params:
            return "arguments" in body
        row = re.escape(params[0])
        body = re.sub(rf"(?<![\w$.]){row}\[1\]", "__payload__", body)
        payload = {"__payload__", *re.findall(r"([\w$]+)=__payload__\b", body)}
        body = re.sub(r"[\w$]+=__payload__\b", "", body)
        if re.search(rf"(?<![\w$.]){row}(?!\[0\])(?![\w$])", body):
            return True
    super_call = re.compile(rf"[\w$]+\.prototype\.{method}\.call\(this,{','.join(map(re.escape, params))}\)")
    if super_call.search(body):
        body = super_call.sub("", body)
        if parent is None or _reads_payload(name, classes, method, parent):
            return True
    return _payload_used(body, payload)


def usage(sources: Sequence[str]) -> dict[str, dict[str, list[str]]]:
    """
    Which commands the client sends and handles, as ``{"requests"|"handlers": {id: [...]}}``.

    A request is a ``getCmdId`` class the client constructs, or a constant it passes straight to
    ``sendMessage``/``sendServerMessageAndWait`` (``"Holder.NAME (sent)"``). A handler is a class
    the client registers under a constant with ``commandDict.set``, marked `` (ack)`` when it
    never reads the reply's payload, and the SmartFox system messages. Registrations key the
    handler, not its ``cmdId`` getter: ``GPFCommand`` is registered under ``gpf`` but returns ``gdi``.
    """
    values: dict[tuple[str, str], str] = {}
    by_constant: dict[str, set[str]] = defaultdict(set)
    named = [(source, _holder_names(source)) for source in sources]
    for source, holder_name in named:
        for match in _ASSIGNMENT.finditer(source):
            var, constant, value = match.groups()
            values[(holder_name(var, match.start()), constant)] = value
            by_constant[constant].add(value)

    def resolve(holder: str, constant: str) -> str:
        found = values.get((holder, constant))
        if found is None and len(by_constant[constant]) == 1:
            found = next(iter(by_constant[constant]))
        if found is None:
            raise ValueError(f"cannot resolve {holder}.{constant}")
        return found

    classes: dict[str, _ClientClass] = {}
    constructed: set[str] = set()
    requests: dict[str, set[str]] = defaultdict(set)
    handlers: dict[str, set[str]] = defaultdict(set)
    request_classes: list[tuple[str, str]] = []
    for source, holder_name in named:
        for name, found in _classes(source).items():
            classes.setdefault(name, found)
        constructed.update(_CONSTRUCTION.findall(source))
        for match in _REQUEST_CLASS.finditer(source):
            name, holder, constant = match.groups()
            request_classes.append((name, resolve(holder_name(holder, match.start()), constant)))
        for match in _DIRECT_SEND.finditer(source):
            holder, constant = match.groups()
            holder = holder_name(holder, match.start())
            requests[resolve(holder, constant)].add(f"{holder}.{constant} (sent)")
        for match in _REGISTRATION.finditer(source):
            holder, constant, name = match.groups()
            handlers[resolve(holder_name(holder, match.start()), constant)].add(name)
        for handler in _SYSTEM_HANDLER.finditer(source):
            for case in _SYSTEM_CASE.finditer(handler.group(0)):
                handlers[case.group(1)].add("BasicSmartfoxClient.handleSystemMessage")
    for name, sent in request_classes:
        if name in constructed:
            requests[sent].add(name)
    marked = {
        command: {name if _reads_payload(name, classes) else f"{name} (ack)" for name in names}
        for command, names in handlers.items()
    }
    return {
        "requests": {command: sorted(names) for command, names in sorted(requests.items())},
        "handlers": {command: sorted(names) for command, names in sorted(marked.items())},
    }


def snapshot(bundle: str, dll: str, bundle_release: str, dll_release: str) -> dict[str, Any]:
    """The committed file's content for these client sources."""
    merged: dict[str, dict[str, set[str]]] = {"client": defaultdict(set), "server": defaultdict(set)}
    for source in (bundle, dll):
        for side, table in extract(source).items():
            for command, names in table.items():
                merged[side][command].update(names)
    return {
        "generated_by": SCRIPT,
        "bundle_release": bundle_release,
        "dll_release": dll_release,
        **{
            side: {command: sorted(names) for command, names in sorted(table.items())} for side, table in merged.items()
        },
        **usage((bundle, dll)),
    }


@functools.lru_cache(maxsize=1)
def library_models() -> dict[str, dict[str, list[str]]]:
    """
    The commands the library has models for, as ``{"client"|"server": {id: [model, ...]}}``.

    Requests (``command``) are client commands; replies (``response_command``, and
    every response model, registered or not) are server commands.
    """
    import empire_core.protocol.models  # noqa: F401  imports every area's models
    from empire_core.protocol.base import BaseRequest, BaseResponse

    found: dict[str, dict[str, set[str]]] = {"client": defaultdict(set), "server": defaultdict(set)}

    def subclasses(cls: type) -> list[type]:
        found = [sub for direct in cls.__subclasses__() for sub in (direct, *subclasses(direct))]
        return [sub for sub in found if sub.__module__.startswith("empire_core.")]

    for request in subclasses(BaseRequest):
        command = request.__dict__.get("command")
        if isinstance(command, str):
            found["client"][command].add(request.__qualname__)
        response_command = request.__dict__.get("response_command")
        if isinstance(response_command, str):
            found["server"][response_command].add(f"{request.__qualname__}.response_command")
    for response in subclasses(BaseResponse):
        command = response.__dict__.get("command")
        if isinstance(command, str):
            found["server"][command].add(response.__qualname__)
    return {side: {command: sorted(names) for command, names in sorted(table.items())} for side, table in found.items()}


@functools.lru_cache(maxsize=1)
def library_commands() -> dict[str, dict[str, list[str]]]:
    """
    The commands the library registers, as ``{"client"|"server"|"either": {id: [where, ...]}}``.

    The :func:`library_models`, ``GGECommand`` values (either side), and the plain
    strings :func:`raw_commands` finds.
    """
    from empire_core.protocol.base import GGECommand

    found: dict[str, dict[str, set[str]]] = {
        side: defaultdict(set, {command: set(names) for command, names in table.items()})
        for side, table in library_models().items()
    }
    found["either"] = defaultdict(set)
    for name, value in vars(GGECommand).items():
        if name.isupper() and isinstance(value, str):
            found["either"][value].add(f"GGECommand.{name}")
    for side, command, where in raw_commands():
        found[side][command].add(where)
    return {side: {command: sorted(names) for command, names in sorted(table.items())} for side, table in found.items()}


def _text(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _call_command(node: ast.Call) -> tuple[str, str] | None:
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
    if name not in _COMMAND_ARGUMENTS:
        return None
    index, side = _COMMAND_ARGUMENTS[name]
    value = node.args[index] if len(node.args) > index else None
    if value is None:
        value = next((k.value for k in node.keywords if k.arg in _COMMAND_KEYWORDS), None)
    command = _text(value)
    return (side, command) if command is not None else None


def raw_commands(root: Path = SOURCE_ROOT) -> list[tuple[str, str, str]]:
    """
    Command ids the library's code uses as plain strings, as ``(side, command, "file:line")``.

    Read from the source: the command argument of the methods in
    ``_COMMAND_ARGUMENTS``, the keys and members of the ``_COMMAND_TABLES``
    constants, strings compared with a ``cmd``/``cmd_id``/``command`` name, and
    the command of an ``%xt%`` f-string or a ``build_command`` call.
    """
    found: list[tuple[str, str, str]] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root.parent).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            where = f"{rel}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, ast.Call):
                hit = _call_command(node)
                if hit is not None:
                    found.append((*hit, where))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if node.value is not None and any(isinstance(t, ast.Name) and t.id in _COMMAND_TABLES for t in targets):
                    value = node.value
                    if isinstance(value, ast.Call) and value.args:
                        value = value.args[0]
                    items = value.keys if isinstance(value, ast.Dict) else getattr(value, "elts", [])
                    found += [("server", text, where) for text in map(_text, items) if text is not None]
            elif isinstance(node, ast.Compare):
                operands = [node.left, *node.comparators]
                if any(isinstance(o, ast.Name) and o.id in _COMMAND_NAMES for o in operands):
                    found += [("server", text, where) for text in map(_text, operands) if text is not None]
            elif isinstance(node, ast.JoinedStr):
                match = _XT_COMMAND.match(ast.unparse(node)[2:-1])
                if match:
                    found.append(("client", match.group(1), where))
    return found


def missing_commands(tables: dict[str, Any]) -> list[tuple[str, str, list[str]]]:
    """Every library command the tables lack, as ``(side, command, where)``."""
    client, server = set(tables["client"]), set(tables["server"])
    known = {"client": client, "server": server, "either": client | server}
    return [
        (side, command, where)
        for side, table in library_commands().items()
        for command, where in table.items()
        if command not in known[side]
    ]


BUCKETS = ("done", "ack-only", "remaining", "excluded", "dead")


@dataclass(frozen=True)
class Coverage:
    """
    Where one client command stands.

    ``detail`` is what covers a command done without a model, the reason a command is
    excluded, or the owner of a remaining one; ``missing`` is what a remaining one lacks.
    """

    command: str
    bucket: str
    detail: str = ""
    missing: tuple[str, ...] = ()


def _covered_sides(entry: dict[str, Any]) -> set[str]:
    return {entry["raw"]} if "raw" in entry else {"server"}


def classify(
    tables: dict[str, Any], rules: dict[str, Any], models: dict[str, dict[str, list[str]]] | None = None
) -> list[Coverage]:
    """
    Every command of the snapshot ``tables`` in one of :data:`BUCKETS`.

    A command the client sends needs a request model, and one it handles needs a typed reply
    unless every handler ignores the payload (``ack-only``). A command it neither sends nor
    handles is ``dead``. ``rules`` (``client_coverage.json``) names what covers a command without
    a model, what is excluded on purpose, and which issue owns each remaining command.
    """
    models = library_models() if models is None else models
    excluded = {command: reason for reason, commands in rules["excluded"].items() for command in commands}
    owners = {command: f"#{issue}" for issue, commands in rules["owners"].items() for command in commands}
    owners.update(rules["unowned"])
    found = []
    for command in sorted(set(tables["client"]) | set(tables["server"])):
        handlers = tables["handlers"].get(command, [])
        sent = command in tables["requests"]
        if not sent and not handlers:
            found.append(Coverage(command, "dead"))
            continue
        cover = rules["covered_without_model"].get(command)
        covered = _covered_sides(cover) if cover else set()
        ack = all(handler.endswith(" (ack)") for handler in handlers)
        missing = tuple(
            part
            for part, side, needed in (("request", "client", sent), ("reply", "server", handlers and not ack))
            if needed and command not in models[side] and side not in covered
        )
        if missing:
            if command in excluded:
                found.append(Coverage(command, "excluded", excluded[command]))
            else:
                found.append(Coverage(command, "remaining", owners.get(command, ""), missing))
        elif handlers and ack and command not in models["server"] and "server" not in covered:
            found.append(Coverage(command, "ack-only"))
        else:
            found.append(Coverage(command, "done", cover["note"] if cover else ""))
    return found


def coverage_report(tables: dict[str, Any], coverage: list[Coverage]) -> str:
    """``classify``'s result as Markdown, the same for the same input."""
    buckets: dict[str, list[Coverage]] = {bucket: [] for bucket in BUCKETS}
    for row in coverage:
        buckets[row.bucket].append(row)
    lines = [
        f"# Client coverage: bundle {tables['bundle_release']}, dll {tables['dll_release']}",
        "",
        "| Bucket | Commands |",
        "|---|---|",
        *(f"| {bucket} | {len(rows)} |" for bucket, rows in buckets.items()),
        "",
        "## Remaining",
        "",
        "| Command | Missing | Owner |",
        "|---|---|---|",
        *(f"| `{row.command}` | {' and '.join(row.missing)} | {row.detail} |" for row in buckets["remaining"]),
    ]
    by_reason: dict[str, list[str]] = defaultdict(list)
    for row in buckets["excluded"]:
        by_reason[row.detail].append(f"`{row.command}`")
    lines += ["", "## Excluded", ""] + [f"- {reason}: {' '.join(commands)}" for reason, commands in by_reason.items()]
    for bucket in ("ack-only", "dead"):
        lines += ["", f"## {bucket.capitalize()}", "", " ".join(f"`{row.command}`" for row in buckets[bucket])]
    lines += ["", "## Done without a model", ""]
    lines += [f"- `{row.command}`: {row.detail}" for row in buckets["done"] if row.detail]
    return "\n".join(lines) + "\n"


def changes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """What differs between two snapshots, one line each."""
    lines = [
        f"{key}: {old.get(key)} -> {new[key]}" for key in ("bundle_release", "dll_release") if old.get(key) != new[key]
    ]
    for side in _TABLES:
        before, after = old.get(side, {}), new.get(side, {})
        lines += [
            f"{side} dropped {command} ({', '.join(before[command])})" for command in sorted(set(before) - set(after))
        ]
        lines += [
            f"{side} added {command} ({', '.join(after[command])})" for command in sorted(set(after) - set(before))
        ]
        lines += [
            f"{side} {command}: {', '.join(before[command])} -> {', '.join(after[command])}"
            for command in sorted(set(before) & set(after))
            if before[command] != after[command]
        ]
    return lines


def render(data: dict[str, Any]) -> str:
    """The snapshot as JSON with one command per line, so a diff shows one line per change."""
    parts = []
    for key, value in data.items():
        if isinstance(value, dict):
            rows = ",\n".join(f"    {json.dumps(command)}: {json.dumps(names)}" for command, names in value.items())
            parts.append(f"  {json.dumps(key)}: {{\n{rows}\n  }}")
        else:
            parts.append(f"  {json.dumps(key)}: {json.dumps(value)}")
    return "{\n" + ",\n".join(parts) + "\n}\n"


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "EmpireCore extract_client_commands"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def download() -> tuple[str, str, str, str]:
    """The live bundle and dll with their release hashes, found from ``index.html``."""
    index = _fetch(f"{BASE_URL}/index.html")
    bundle_match, dll_match = _BUNDLE_NAME.search(index), _DLL_NAME.search(index)
    if bundle_match is None or dll_match is None:
        raise SystemExit("index.html names no Game.bundle.<hash>.js or ggs.dll.<hash>.js")
    bundle = _fetch(f"{BASE_URL}/{bundle_match.group(0)}")
    dll = _fetch(f"{BASE_URL}/dll/{dll_match.group(0)}")
    return bundle, dll, bundle_match.group(1), dll_match.group(1)


def _release(path: Path, pattern: re.Pattern[str], given: str | None) -> str:
    if given:
        return given
    match = pattern.search(path.name)
    if match is None:
        raise SystemExit(f"{path.name} has no release hash in its name; pass it with --bundle-release/--dll-release")
    return match.group(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--download", action="store_true", help="read the live client named by index.html")
    parser.add_argument("--bundle", type=Path, help="a Game.bundle.<hash>.js, minified as served")
    parser.add_argument("--dll", type=Path, help="a ggs.dll.<hash>.js, minified as served")
    parser.add_argument("--bundle-release", help="the bundle's release hash, when its file name lacks it")
    parser.add_argument("--dll-release", help="the dll's release hash, when its file name lacks it")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="snapshot file to write")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if a command table would change")
    parser.add_argument(
        "--coverage", action="store_true", help="print the coverage report; alone, for the committed snapshot"
    )
    parser.add_argument("--rules", type=Path, default=COVERAGE_RULES, help="the coverage rules file")
    args = parser.parse_args(argv)

    def report(tables: dict[str, Any]) -> None:
        if args.coverage:
            rules = json.loads(args.rules.read_text(encoding="utf-8"))
            print(coverage_report(tables, classify(tables, rules)), end="")

    if args.coverage and not (args.download or args.bundle or args.dll):
        report(json.loads(args.out.read_text(encoding="utf-8")))
        return 0
    if args.download:
        bundle, dll, bundle_release, dll_release = download()
    elif args.bundle and args.dll:
        bundle, dll = args.bundle.read_text(encoding="utf-8"), args.dll.read_text(encoding="utf-8")
        bundle_release = _release(args.bundle, _BUNDLE_NAME, args.bundle_release)
        dll_release = _release(args.dll, _DLL_NAME, args.dll_release)
    else:
        parser.error("pass --download, or both --bundle and --dll, or --coverage alone")

    new = snapshot(bundle, dll, bundle_release, dll_release)
    if not new["client"] or not new["server"]:
        raise SystemExit("found no command constants; has the client's constant layout changed?")
    old = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    diff = changes(old, new)
    missing = missing_commands(new)
    for line in diff:
        print(line)
    for side, command, where in missing:
        print(f"library {side} command not in the client: {command} ({', '.join(where)})", file=sys.stderr)
    print(f"{len(new['client'])} client and {len(new['server'])} server commands")
    report(new)
    if args.check:
        return 1 if any(old.get(side) != new.get(side) for side in _TABLES) else 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(new), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
