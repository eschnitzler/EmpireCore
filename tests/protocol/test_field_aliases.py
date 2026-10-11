"""Each wire key is declared once, as ``validation_alias``, and every type checker builds models by field name.

pydantic's ``@dataclass_transform`` makes ``Field(alias="X")`` rename the ``__init__``
parameter for pyright and Pylance, which do not read ``populate_by_name``. A field names its
key with ``validation_alias`` alone; ``BaseModel`` copies it to ``serialization_alias``.
"""

import ast
import importlib
import pkgutil
from pathlib import Path

import pydantic

import empire_core

PACKAGE = Path(empire_core.__file__).parent


def _field_calls() -> list[tuple[str, int, dict[str, ast.expr]]]:
    calls = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "Field":
                keywords = {k.arg: k.value for k in node.keywords if k.arg}
                calls.append((str(path.relative_to(PACKAGE)), node.lineno, keywords))
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


def _literal(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def test_no_field_uses_a_bare_alias() -> None:
    bare = [f"{path}:{line}" for path, line, keywords in _field_calls() if "alias" in keywords]
    assert not bare, f"use validation_alias= instead of alias=: {bare}"


def test_no_field_repeats_its_wire_key() -> None:
    repeated = [
        f"{path}:{line}"
        for path, line, keywords in _field_calls()
        if _literal(keywords.get("validation_alias")) is not None
        and _literal(keywords.get("validation_alias")) == _literal(keywords.get("serialization_alias"))
    ]
    assert not repeated, f"drop serialization_alias, BaseModel copies validation_alias: {repeated}"


def test_every_wire_key_is_read_and_written_under_the_same_name() -> None:
    mismatched = [
        f"{model.__qualname__}.{name}"
        for model in _models()
        for name, field in model.model_fields.items()
        if isinstance(field.validation_alias, str) and field.validation_alias != field.serialization_alias
    ]
    assert not mismatched, f"validation_alias and serialization_alias differ, subclass BaseModel: {mismatched}"


def test_a_forward_referenced_field_keeps_its_wire_key_after_a_rebuild() -> None:
    from empire_core.messages.models.battle_logs import BattleLogShortResponse

    assert BattleLogShortResponse.model_fields["detail"].serialization_alias == "bld"


def test_the_checks_see_field_calls() -> None:
    assert any(_literal(keywords.get("validation_alias")) for _, _, keywords in _field_calls())


def test_every_model_builds_on_empire_model() -> None:
    from empire_core.protocol.base import EmpireModel

    direct = [
        f"{cls.__module__}.{cls.__qualname__}"
        for cls in _models()
        if cls is not EmpireModel and not issubclass(cls, EmpireModel) and "[" not in cls.__qualname__
    ]
    assert direct == [], "subclass empire_core.protocol.base.EmpireModel, not pydantic's"
