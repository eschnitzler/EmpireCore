"""State reads pushes through their models: no ``.get(`` on a payload is left in ``state/``."""

import ast
from pathlib import Path

import empire_core.state

STATE = Path(empire_core.state.__file__).parent

# Still read from the payload, each being converted to its models (#519)
NOT_YET_TYPED = {
    "manager.py",
    "movements.py",
}

# Models, whose validators are where the wire is read
MODELS = {"login_data.py"}

_PAYLOAD_TYPES = {"Any", "dict", "dict[str, Any]"}


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


def payload_gets(path: Path) -> list[int]:
    """The lines of ``path`` that call ``.get(`` on a payload."""
    lines = []
    for function in ast.walk(ast.parse(path.read_text())):
        if not isinstance(function, ast.FunctionDef):
            continue
        names = _payload_names(function)
        lines += [
            node.lineno
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and _root(node.func.value) in names
        ]
    return sorted(lines)


def test_state_reads_no_payload_with_get():
    found = {
        path.name: lines
        for path in sorted(STATE.glob("*.py"))
        if path.name not in NOT_YET_TYPED | MODELS and (lines := payload_gets(path))
    }
    assert found == {}, "read these payloads through their response models"


def test_every_file_not_yet_typed_still_reads_a_payload():
    # A converted file leaves the list, so the guard covers it from then on
    done = sorted(name for name in NOT_YET_TYPED if not payload_gets(STATE / name))
    assert done == []


def test_the_guard_finds_a_payload_read(tmp_path):
    handler = tmp_path / "handler.py"
    handler.write_text(
        "def _handle_x(self, data: Any) -> None:\n"
        "    block = data['A']\n"
        "    self.cache.get(1)\n"
        "    data['C'].get('D')\n"
        "    return block.get('B')\n"
    )
    assert payload_gets(handler) == [4, 5]
