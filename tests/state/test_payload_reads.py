"""State reads pushes through their models: no ``.get(`` or ``[...]`` on a payload is left in ``state/``."""

import ast
from pathlib import Path
from typing import NamedTuple

import empire_core.state

STATE = Path(empire_core.state.__file__).parent

# Still read from the payload, each being converted to its models (#519)
NOT_YET_TYPED = {
    "movements.py",
}

# The movement pipeline, typed on its own branch: these functions, and only the gam key of the membership reply
MOVEMENT_OWNED = {
    ("manager.py", "_handle_attack_sent", None),
    ("manager.py", "_handle_movement_sent", None),
    ("manager.py", "_handle_thm", None),
    ("manager.py", "_apply_sent_movement", None),
    ("alliance.py", "apply_membership_response", "gam"),
}

# Models, whose validators are where the wire is read
MODELS = {"login_data.py"}

_PAYLOAD_TYPES = {"Any", "dict", "dict[str, Any]"}


class PayloadRead(NamedTuple):
    line: int
    function: str
    key: str | None


def _root(node: ast.expr) -> str | None:
    """The name an expression such as ``data["A"].get("B")`` starts from."""
    while isinstance(node, (ast.Subscript, ast.Attribute, ast.Call)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else None


def _payload_names(function: ast.FunctionDef) -> set[str]:
    """A handler's untyped parameters, and the names bound from them."""
    names = {
        arg.arg
        for arg in (*function.args.args, *function.args.kwonlyargs)
        if arg.arg != "self" and (arg.annotation is None or ast.unparse(arg.annotation) in _PAYLOAD_TYPES)
    }
    for node in ast.walk(function):
        if isinstance(node, (ast.Assign, ast.NamedExpr)) and _root(node.value) in names:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names |= {target.id for target in targets if isinstance(target, ast.Name)}
    return names


def payload_reads(path: Path) -> list[PayloadRead]:
    """Each ``.get(`` or subscript read on a payload in ``path``."""
    reads = set()
    for function in ast.walk(ast.parse(path.read_text())):
        if not isinstance(function, ast.FunctionDef):
            continue
        names = _payload_names(function)
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
                read, key = _root(node.func.value) in names, node.args[0] if node.args else None
            elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
                read, key = _root(node.value) in names, node.slice
            else:
                continue
            if read:
                name = key.value if isinstance(key, ast.Constant) and isinstance(key.value, str) else None
                reads.add(PayloadRead(node.lineno, function.name, name))
    return sorted(reads)


def payload_gets(path: Path) -> list[int]:
    """The lines of ``path`` that read a payload."""
    return sorted({read.line for read in payload_reads(path)})


def _owned(path: Path, read: PayloadRead) -> bool:
    return (path.name, read.function, None) in MOVEMENT_OWNED or (path.name, read.function, read.key) in MOVEMENT_OWNED


def test_state_reads_no_payload():
    found = {
        path.name: lines
        for path in sorted(STATE.glob("*.py"))
        if path.name not in NOT_YET_TYPED | MODELS
        and (lines := [read.line for read in payload_reads(path) if not _owned(path, read)])
    }
    assert found == {}, "read these payloads through their response models"


def test_every_file_not_yet_typed_still_reads_a_payload():
    # A converted file leaves the list, so the guard covers it from then on
    done = sorted(name for name in NOT_YET_TYPED if not payload_gets(STATE / name))
    assert done == []


def test_every_movement_owned_function_still_reads_a_payload():
    # Once typed, an entry leaves MOVEMENT_OWNED, so the guard covers it from then on
    reads = {
        (name, read.function) for name in {owned[0] for owned in MOVEMENT_OWNED} for read in payload_reads(STATE / name)
    }
    assert sorted((name, function) for name, function, _ in MOVEMENT_OWNED if (name, function) not in reads) == []


def test_the_guard_finds_a_payload_read(tmp_path):
    handler = tmp_path / "handler.py"
    handler.write_text(
        "def _handle_x(self, data: Any) -> None:\n"
        "    block = data['A']\n"
        "    self.cache.get(1)\n"
        "    data['C'].get('D')\n"
        "    self.seen[data] = block.get('B')\n"
        "    return {key: data[key] for key in KEYS}\n"
    )
    assert payload_gets(handler) == [2, 4, 5, 6]
    assert PayloadRead(2, "_handle_x", "A") in payload_reads(handler)
