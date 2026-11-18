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

# A copy of a payload is still the payload
_COPIES = {"dict", "list", "tuple"}


def _roots(node: ast.expr) -> set[str]:
    """The names an expression such as ``data["A"].get("B")`` can start from."""
    if isinstance(node, ast.IfExp):
        return _roots(node.body) | _roots(node.orelse)
    if isinstance(node, ast.BoolOp):
        return set().union(*(_roots(value) for value in node.values))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _COPIES and node.args:
        return _roots(node.args[0])
    if isinstance(node, ast.Call):
        return _roots(node.func)
    if isinstance(node, (ast.Subscript, ast.Attribute)):
        return _roots(node.value)
    return {node.id} if isinstance(node, ast.Name) else set()


def _names(target: ast.expr) -> set[str]:
    """The names an assignment or loop target binds."""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Starred):
        return _names(target.value)
    if isinstance(target, (ast.Tuple, ast.List)):
        return set().union(*(_names(element) for element in target.elts))
    return set()


def _bindings(function: ast.FunctionDef) -> list[tuple[ast.expr, ast.expr]]:
    """Each target in ``function``, with the value or the iterable it is bound from."""
    bound: list[tuple[ast.expr, ast.expr]] = []
    for node in ast.walk(function):
        if isinstance(node, ast.Assign):
            bound += [(target, node.value) for target in node.targets]
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
            bound.append((node.target, node.value))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            bound.append((node.target, node.iter))
    return bound


def _payload_names(function: ast.FunctionDef) -> set[str]:
    """A handler's untyped parameters, and the names bound from them in any number of steps."""
    names = {
        arg.arg
        for arg in (*function.args.args, *function.args.kwonlyargs)
        if arg.arg != "self" and (arg.annotation is None or ast.unparse(arg.annotation) in _PAYLOAD_TYPES)
    }
    bindings = _bindings(function)
    while found := {name for target, value in bindings if _roots(value) & names for name in _names(target)} - names:
        names |= found
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
            and _roots(node.func.value) & names
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


def test_the_guard_follows_loops_comprehensions_and_copies(tmp_path):
    handler = tmp_path / "handler.py"
    handler.write_text(
        "def _handle_x(self, data: Any, cache: Cache) -> None:\n"
        "    for entry in data['M'] if isinstance(data['M'], list) else []:\n"
        "        entry.get('M')\n"
        "    [row.get('B') for row in data['R']]\n"
        "    copy: dict[str, Any] = dict(data)\n"
        "    copy.get('C')\n"
        "    for key, value in copy.items():\n"
        "        value.get('D')\n"
        "    model = read(Model, data)\n"
        "    model.get('E')\n"
        "    cache.get('F')\n"
    )
    assert payload_gets(handler) == [3, 4, 6, 8]
