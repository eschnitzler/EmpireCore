"""The package layering, checked on the source with ast (nothing is imported).

Every import counts: module level, inside functions and under TYPE_CHECKING.

- An area may import only areas of a strictly lower rank (RANK), plus the plumbing.
- The plumbing imports no area, no combat and nothing above the areas. The one exception
  is ``services.base``, which may name the client and the state under TYPE_CHECKING.
- ``protocol.base`` imports nothing from empire_core.
- Only the client and the tests import the ``protocol.models`` aggregator. Nothing in the
  library imports the ``empire_core`` root.
- Every area has an ``__init__``, and the enums import only ``enum``.

A second test checks that ``import empire_core`` fills the whole response registry.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

import empire_core

PACKAGE = Path(empire_core.__file__).parent

# An area may import only areas of strictly lower rank. combat is not an area package,
# but it sits in the chain: attack uses it, and it uses map, commanders and army.
RANK = {
    "map": 0,
    "ranking": 0,
    "events": 1,
    "commanders": 1,
    "castle": 1,
    "army": 2,
    "movements": 3,
    "messages": 3,
    "defense": 4,
    "combat": 5,
    "player": 5,
    "attack": 6,
    "alliance": 6,
    "spy": 7,
}
PLUMBING = {"protocol", "enums", "gamedata", "exceptions", "config", "utils", "services"}
ABOVE = {"client", "state", "network", "accounts", "pool"}
AGGREGATOR = "empire_core.protocol.models"


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(PACKAGE.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports() -> list[tuple[str, str, bool, int]]:
    """(importer, imported module, under TYPE_CHECKING, line) for every empire_core import."""
    out = []
    for path in sorted(PACKAGE.rglob("*.py")):
        importer = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        type_only = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
                type_only |= {id(n) for n in ast.walk(node)}
        base = importer.split(".") if path.name == "__init__.py" else importer.split(".")[:-1]
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    parent = base[: len(base) - (node.level - 1)]
                    module = ".".join(parent + ([node.module] if node.module else []))
                else:
                    module = node.module or ""
                targets = [module]
                for alias in node.names:
                    if (PACKAGE.parent / (module + "." + alias.name).replace(".", "/")).with_suffix(".py").exists():
                        targets.append(module + "." + alias.name)
                for t in targets:
                    out.append((importer, t, id(node) in type_only, node.lineno))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    out.append((importer, alias.name, id(node) in type_only, node.lineno))
    return [i for i in out if i[1] == "empire_core" or i[1].startswith("empire_core.")]


IMPORTS = _imports()


def _top(module: str) -> str:
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else ""


def _unlayered_packages() -> list[str]:
    tops = {_top(_module_name(p)) for p in PACKAGE.rglob("*.py")} - {""}
    return [f"{t}: no layer" for t in sorted(tops - set(RANK) - PLUMBING - ABOVE)]


def _area_violations() -> list[str]:
    bad = []
    for importer, module, _, line in IMPORTS:
        src, dst = _top(importer), _top(module)
        if src not in RANK or src == dst:
            continue
        if dst in RANK and RANK[dst] >= RANK[src]:
            bad.append(f"{importer}:{line} -> {module} (rank {RANK[src]} -> {RANK[dst]})")
        elif dst in ABOVE or module == "empire_core":
            bad.append(f"{importer}:{line} -> {module} (above the areas)")
        elif src == "combat" and dst in RANK and dst not in ("map", "commanders", "army"):
            bad.append(f"{importer}:{line} -> {module} (combat uses only map, commanders and army)")
    return bad


def _plumbing_violations() -> list[str]:
    bad = []
    for importer, module, type_only, line in IMPORTS:
        if _top(importer) not in PLUMBING or importer == AGGREGATOR:
            continue
        dst = _top(module)
        if importer == "empire_core.services.base" and type_only and dst in ("client", "state"):
            continue
        if dst in RANK or dst in ABOVE or module == "empire_core":
            bad.append(f"{importer}:{line} -> {module} (plumbing imports an area or above)")
    bad += [f"empire_core.protocol.base:{line} -> {m}" for i, m, _, line in IMPORTS if i == "empire_core.protocol.base"]
    return bad


def _aggregator_and_root_violations() -> list[str]:
    bad = [
        f"{i}:{line} -> {m} (only the client imports the aggregator)"
        for i, m, _, line in IMPORTS
        if m == AGGREGATOR and not i.startswith("empire_core.client") and i != AGGREGATOR
    ]
    bad += [
        f"{i}:{line} -> empire_core (the root)"
        for i, m, _, line in IMPORTS
        if m == "empire_core" and i != "empire_core"
    ]
    return bad


def _init_and_enum_violations() -> list[str]:
    bad = []
    for area in sorted(a for a in RANK if a != "combat"):
        if not (PACKAGE / area / "__init__.py").exists():
            bad.append(f"empire_core.{area}: no __init__")
    for path in sorted((PACKAGE / "enums").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and [a.name for a in node.names] != ["enum"]:
                bad.append(f"enums/{path.name}:{node.lineno} (enums import only enum)")
            elif isinstance(node, ast.ImportFrom):
                ok = node.level == 1 if path.name == "__init__.py" else node.module in ("enum", "__future__")
                if not ok:
                    bad.append(f"enums/{path.name}:{node.lineno} (enums import only enum)")
    return bad


def test_package_layering() -> None:
    problems = (
        _unlayered_packages()
        + _area_violations()
        + _plumbing_violations()
        + _aggregator_and_root_violations()
        + _init_and_enum_violations()
    )
    assert not problems, "\n".join(problems)


_REGISTRY_SCRIPT = """
import importlib, json, pkgutil
import empire_core
from empire_core.protocol import base
first = dict(base._response_registry)
for info in pkgutil.walk_packages(empire_core.__path__, "empire_core."):
    importlib.import_module(info.name)
print(json.dumps({"first": sorted(first), "all": sorted(base._response_registry)}))
"""


def test_import_empire_core_fills_the_whole_response_registry() -> None:
    """No response model may register only when some module happens to be imported later."""
    result = subprocess.run([sys.executable, "-c", _REGISTRY_SCRIPT], capture_output=True, text=True, check=True)
    seen = json.loads(result.stdout)
    assert seen["first"] == seen["all"]
    assert len(seen["all"]) >= 80
