"""
Extract the game client's command tables into ``tests/data/client_commands.json``.

    uv run python scripts/extract_client_commands.py --download              # the live client
    uv run python scripts/extract_client_commands.py --bundle Game.bundle.a4a25ae6d735e29092f6.js \\
        --dll ggs.dll.145565eddbcbe244aab0.js
    uv run python scripts/extract_client_commands.py --download --check      # exit 1 if the tables changed

The client names every command it sends ``C2S_<NAME>`` and every reply or push
it handles ``S2C_<NAME>``, as static fields of its constant classes
(``ClientConstSF`` in the bundle; ``ConstantsSmartFox``, ``CoreEventsConstants``,
``BasicSmartfoxConstants`` and ``BasicSmartfoxClient`` in the dll). The snapshot
maps each command id to the constants that hold it, so a renamed constant shows
in a diff as well as a dropped id. The release is the hash in each file's name.

``--check`` exits 1 when the snapshot would change. Both modes also list every
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
from pathlib import Path
from typing import Any

SCRIPT = "scripts/extract_client_commands.py"
BASE_URL = "https://empire-html5.goodgamestudios.com/default"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "tests" / "data" / "client_commands.json"
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
}
_COMMAND_KEYWORDS = ("cmd_id", "command")
# Constants whose keys or members are server command ids.
_COMMAND_TABLES = {"_DISPATCH", "_SECTION_PUSHES"}
_COMMAND_NAMES = {"cmd", "cmd_id", "command"}
_XT_COMMAND = re.compile(r"^%xt%\{[^}]*\}%([A-Za-z]+)%")

_ASSIGNMENT = re.compile(r"([A-Za-z_$][\w$]*)\.((?:C2S|S2C)_[A-Z0-9_]+)=\"([^\"]*)\"")
# A minified holder: var f=function(){return function ConstantsSmartFox(){}}()
_HOLDER = re.compile(r"\b([A-Za-z_$][\w$]*)=function\(\)\{return function ([A-Za-z_$][\w$]*)\(")
_BUNDLE_NAME = re.compile(r"Game\.bundle\.([0-9a-f]+)\.js")
_DLL_NAME = re.compile(r"ggs\.dll\.([0-9a-f]+)\.js")


def extract(source: str) -> dict[str, dict[str, list[str]]]:
    """Every ``C2S_``/``S2C_`` constant in ``source``, as ``{"client"|"server": {id: ["Holder.NAME", ...]}}``."""
    holders: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for match in _HOLDER.finditer(source):
        holders[match.group(1)].append((match.start(), match.group(2)))

    def holder_name(var: str, position: int) -> str:
        names = [name for start, name in holders.get(var, []) if start < position]
        return names[-1] if names else var

    tables: dict[str, dict[str, set[str]]] = {"client": defaultdict(set), "server": defaultdict(set)}
    for match in _ASSIGNMENT.finditer(source):
        var, constant, command = match.groups()
        side = "client" if constant.startswith("C2S_") else "server"
        tables[side][command].add(f"{holder_name(var, match.start())}.{constant}")
    return {
        side: {command: sorted(names) for command, names in sorted(table.items())} for side, table in tables.items()
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
    }


@functools.lru_cache(maxsize=1)
def library_commands() -> dict[str, dict[str, list[str]]]:
    """
    The commands the library registers, as ``{"client"|"server"|"either": {id: [where, ...]}}``.

    Requests (``command``) are client commands; replies (``response_command``, and
    every registered response model) are server commands; ``GGECommand`` values
    are either; plain strings the code uses are those :func:`raw_commands` finds.
    """
    import empire_core.protocol.models  # noqa: F401  imports every area's models
    from empire_core.protocol.base import BaseRequest, BaseResponse, GGECommand

    found: dict[str, dict[str, set[str]]] = {
        "client": defaultdict(set),
        "server": defaultdict(set),
        "either": defaultdict(set),
    }

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
    the command of an ``%xt%`` f-string.
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


def changes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """What differs between two snapshots, one line each."""
    lines = [
        f"{key}: {old.get(key)} -> {new[key]}" for key in ("bundle_release", "dll_release") if old.get(key) != new[key]
    ]
    for side in ("client", "server"):
        before, after = old.get(side, {}), new[side]
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
    parser.add_argument("--bundle", type=Path, help="a Game.bundle.<hash>.js (split or not)")
    parser.add_argument("--dll", type=Path, help="a ggs.dll.<hash>.js (split or not)")
    parser.add_argument("--bundle-release", help="the bundle's release hash, when its file name lacks it")
    parser.add_argument("--dll-release", help="the dll's release hash, when its file name lacks it")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="snapshot file to write")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if the snapshot would change")
    args = parser.parse_args(argv)

    if args.download:
        bundle, dll, bundle_release, dll_release = download()
    elif args.bundle and args.dll:
        bundle, dll = args.bundle.read_text(encoding="utf-8"), args.dll.read_text(encoding="utf-8")
        bundle_release = _release(args.bundle, _BUNDLE_NAME, args.bundle_release)
        dll_release = _release(args.dll, _DLL_NAME, args.dll_release)
    else:
        parser.error("pass --download, or both --bundle and --dll")

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
    if args.check:
        return 1 if diff else 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(new), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
