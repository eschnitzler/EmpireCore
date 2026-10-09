"""Wire keys are spelled so that every type checker builds models by field name.

pydantic's ``@dataclass_transform`` makes ``Field(alias="X")`` rename the ``__init__``
parameter for pyright and Pylance, which do not read ``populate_by_name``. A
``validation_alias`` plus a matching ``serialization_alias`` keeps the field name as the
parameter and the wire key on parse and dump.
"""

import ast
import importlib
import pkgutil
from pathlib import Path

import pydantic

import empire_core

PACKAGE = Path(empire_core.__file__).parent


def _field_calls() -> list[tuple[str, int, set[str]]]:
    calls = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "Field":
                calls.append((str(path.relative_to(PACKAGE)), node.lineno, {k.arg for k in node.keywords if k.arg}))
    return calls


def _models() -> list[type[pydantic.BaseModel]]:
    for module in pkgutil.walk_packages(empire_core.__path__, "empire_core."):
        importlib.import_module(module.name)
    seen: list[type[pydantic.BaseModel]] = []
    stack = list(pydantic.BaseModel.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if cls.__module__.startswith("empire_core.") and cls not in seen:
            seen.append(cls)
    return seen


def test_no_field_uses_a_bare_alias() -> None:
    bare = [f"{path}:{line}" for path, line, keywords in _field_calls() if "alias" in keywords]
    assert not bare, f"use validation_alias= and serialization_alias= instead of alias=: {bare}"


def test_every_wire_key_is_read_and_written_under_the_same_name() -> None:
    mismatched = [
        f"{model.__qualname__}.{name}"
        for model in _models()
        for name, field in model.model_fields.items()
        if isinstance(field.validation_alias, str) and field.validation_alias != field.serialization_alias
    ]
    assert not mismatched, f"validation_alias and serialization_alias differ: {mismatched}"


def test_the_ban_sees_field_calls() -> None:
    assert any("serialization_alias" in keywords for _, _, keywords in _field_calls())
