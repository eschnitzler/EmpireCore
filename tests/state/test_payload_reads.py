"""State reads pushes through their models: no ``.get(`` or ``[...]`` on a payload is left in ``state/``."""

import ast
from pathlib import Path
from typing import NamedTuple

import empire_core.state

STATE = Path(empire_core.state.__file__).parent

# Models, whose validators are where the wire is read
MODELS = {"login_data.py"}

_PAYLOAD_TYPES = {"Any", "dict", "dict[str, Any]"}

# A copy of a payload is still the payload
_COPIES = {"dict", "list", "tuple"}


class PayloadRead(NamedTuple):
    line: int
    function: str
    key: str | None


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
    """A handler's untyped parameters, and every name bound from them."""
    names = {
        arg.arg
        for arg in (*function.args.args, *function.args.kwonlyargs)
        if arg.arg != "self" and (arg.annotation is None or ast.unparse(arg.annotation) in _PAYLOAD_TYPES)
    }
    bindings = _bindings(function)
    while True:
        found = set().union(*(_names(target) for target, value in bindings if _roots(value) & names)) - names
        if not found:
            return names
        names |= found


def payload_reads(path: Path) -> list[PayloadRead]:
    """Each ``.get(`` or subscript read on a payload in ``path``."""
    reads = set()
    for function in ast.walk(ast.parse(path.read_text())):
        if not isinstance(function, ast.FunctionDef):
            continue
        names = _payload_names(function)
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
                read, key = bool(_roots(node.func.value) & names), node.args[0] if node.args else None
            elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
                read, key = bool(_roots(node.value) & names), node.slice
            else:
                continue
            if read:
                name = key.value if isinstance(key, ast.Constant) and isinstance(key.value, str) else None
                reads.add(PayloadRead(node.lineno, function.name, name))
    return sorted(reads)


def payload_gets(path: Path) -> list[int]:
    """The lines of ``path`` that read a payload."""
    return sorted({read.line for read in payload_reads(path)})


def test_state_reads_no_payload():
    found = {
        path.name: lines
        for path in sorted(STATE.glob("*.py"))
        if path.name not in MODELS and (lines := payload_gets(path))
    }
    assert found == {}, "read these payloads through their response models"


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
    assert payload_gets(handler) == [2, 3, 4, 6, 8]
