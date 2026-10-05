"""Server errors are matched by name: no error code or status is compared with, or built from, a bare number."""

import ast
from pathlib import Path

import empire_core

PACKAGE = Path(empire_core.__file__).parent
CODE_SUFFIXES = ("code", "status")
CODE_CONSTRUCTORS = {"GGEError", "from_code"}


def _name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _names_a_code(node: ast.expr) -> bool:
    name = _name(node)
    return name is not None and name.lower().endswith(CODE_SUFFIXES)


def _int_literal(node: ast.expr) -> int | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _int_literal(node.operand)
        return None if value is None else -value
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    return None


def _nonzero_ints(node: ast.expr) -> bool:
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return any(_nonzero_ints(element) for element in node.elts)
    return _int_literal(node) not in (None, 0)


def _int_patterns(pattern: ast.pattern) -> bool:
    if isinstance(pattern, ast.MatchValue):
        return _nonzero_ints(pattern.value)
    if isinstance(pattern, ast.MatchOr):
        return any(_int_patterns(p) for p in pattern.patterns)
    return False


def _bare_code_uses(source: str) -> list[int]:
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            on_code_attribute = any(isinstance(o, ast.Attribute) and o.attr == "code" for o in operands)
            with_a_number = any(_names_a_code(o) for o in operands) and any(_nonzero_ints(o) for o in operands)
            if on_code_attribute or with_a_number:
                lines.append(node.lineno)
        elif isinstance(node, ast.Call):
            if _name(node.func) in CODE_CONSTRUCTORS and any(_nonzero_ints(a) for a in node.args):
                lines.append(node.lineno)
        elif isinstance(node, ast.Match):
            if _names_a_code(node.subject) and any(_int_patterns(case.pattern) for case in node.cases):
                lines.append(node.lineno)
    return lines


def test_no_error_code_is_compared_with_a_bare_number():
    found = [
        f"{path.relative_to(PACKAGE)}:{line}"
        for path in sorted(PACKAGE.rglob("*.py"))
        for line in _bare_code_uses(path.read_text())
    ]
    assert found == [], "compare CommandError.error with a GGEError member instead: " + ", ".join(found)


def test_the_check_finds_bare_codes():
    assert _bare_code_uses("packet.error_code == 114") == [1]
    assert _bare_code_uses("e.code != 337") == [1]
    assert _bare_code_uses("vck.error_code in (1, 2)") == [1]
    assert _bare_code_uses("status == 1") == [1]
    assert _bare_code_uses("self.vck_status != 2") == [1]
    assert _bare_code_uses("error_code == -1") == [1]
    assert _bare_code_uses("e.code == GGEError.ALLI_NOT_FOUND") == [1]
    assert _bare_code_uses("GGEError(114)") == [1]
    assert _bare_code_uses("GGEError.from_code(114)") == [1]
    assert _bare_code_uses("match packet.error_code:\n    case 0:\n        pass\n    case 114:\n        pass") == [1]
    assert _bare_code_uses("match status:\n    case 1 | 2:\n        pass") == [1]


def test_the_check_lets_names_through():
    assert _bare_code_uses("packet.error_code == 0") == []
    assert _bare_code_uses("packet.error_code == GGEError.ALLI_NOT_FOUND") == []
    assert _bare_code_uses("e.error is GGEError.NO_CHANGE") == []
    assert _bare_code_uses("GGEError(packet.error_code)") == []
    assert _bare_code_uses("match packet.error_code:\n    case GGEError.NO_CHANGE:\n        pass") == []
    assert _bare_code_uses("level == 1") == []
