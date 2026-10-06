"""Tests for the public API surface of ``empire_core``.

The contract: a name is public when it is in ``empire_core.__all__`` or in the
``__all__`` of one of PUBLIC_MODULES, the first-level modules and packages such
as ``empire_core.map``. Every deeper path (``empire_core.map.models.items``,
``empire_core.spy.service``, ...) is private and may move in any release.

These tests check that contract, that the docs, examples and docstrings name
only public paths, that every type a public signature names is public, and the
shape of a few public types.
"""

import ast
import functools
import importlib
import importlib.metadata
import inspect
import pkgutil
import re
import sys
import textwrap
import types
from dataclasses import fields
from pathlib import Path
from typing import Annotated, Any, get_args, get_origin, get_type_hints

import pytest

import empire_core
from empire_core.enums import Kingdom
from empire_core.services import BaseService

REPO = Path(__file__).resolve().parent.parent

PUBLIC_MODULES = (
    "empire_core.accounts",
    "empire_core.alliance",
    "empire_core.army",
    "empire_core.attack",
    "empire_core.castle",
    "empire_core.combat",
    "empire_core.commanders",
    "empire_core.config",
    "empire_core.defense",
    "empire_core.enums",
    "empire_core.events",
    "empire_core.exceptions",
    "empire_core.gamedata",
    "empire_core.map",
    "empire_core.messages",
    "empire_core.movements",
    "empire_core.player",
    "empire_core.pool",
    "empire_core.protocol",
    "empire_core.quests",
    "empire_core.ranking",
    "empire_core.rewards",
    "empire_core.services",
    "empire_core.spy",
    "empire_core.state",
)
# What these hold that callers need is exported from the root or an area.
PRIVATE_MODULES = ("empire_core.client", "empire_core.network", "empire_core.utils")
PUBLIC_SUBMODULES: tuple[str, ...] = ()  # OWNER TO DECIDE: ("empire_core.protocol.models",) keeps that path public
PUBLIC_PATHS = ("empire_core", *PUBLIC_MODULES, *PUBLIC_SUBMODULES)

# The core names the root exports.
_ROOT_NAMES = (
    "EmpireClient",
    "EmpireConfig",
    "AccountPool",
    "PoolExhaustedError",
    "Account",
    "accounts",
    "EmpireError",
    "NetworkError",
    "ConnectionClosedError",
    "LoginError",
    "LoginCooldownError",
    "PacketError",
    "EmpireTimeoutError",
    "CommandError",
    "AttackInProgressError",
    "GGEError",
    "Packet",
    "Player",
    "Castle",
    "Resources",
    "Building",
    "Alliance",
    "Movement",
    "MovementResources",
    "MovementType",
    "GameEvent",
    "Kingdom",
    "MapItemType",
    "MapAreaItem",
    "ScanResult",
    "SpyService",
    "SpyResult",
    "CastleInfo",
    "AllianceMember",
    "RankingEntry",
    "decode_json_text",
    "encode_json_text",
    "troop_data_available",
    "get_troop_ids",
)


def _public_names(module_name: str) -> list[str]:
    return list(importlib.import_module(module_name).__all__)


def test_every_first_level_module_is_public_or_private() -> None:
    """A new first-level module needs a decision: public through its ``__all__``, or private."""
    found = {f"empire_core.{info.name}" for info in pkgutil.iter_modules(empire_core.__path__)}
    assert found == set(PUBLIC_MODULES) | set(PRIVATE_MODULES)


@pytest.mark.parametrize("module_name", ("empire_core", *PUBLIC_MODULES))
def test_public_module_all_is_unique_and_resolves(module_name: str) -> None:
    module = importlib.import_module(module_name)
    names = _public_names(module_name)
    assert len(names) == len(set(names)), f"{module_name}.__all__ repeats a name"
    missing = [name for name in names if not hasattr(module, name)]
    assert not missing, f"{module_name}.__all__ advertises missing names {missing}"


def test_root_exports_the_core_names() -> None:
    missing = [name for name in _ROOT_NAMES if name not in empire_core.__all__]
    assert not missing, f"missing from empire_core.__all__: {missing}"


def _owner(obj: object) -> str | None:
    module = getattr(obj, "__module__", None) if inspect.isclass(obj) or inspect.isfunction(obj) else None
    if not module or not module.startswith("empire_core."):
        return None
    return ".".join(module.split(".")[:2])


def test_root_names_are_exported_by_their_own_public_module() -> None:
    """``empire_core.MapAreaItem`` is also ``empire_core.map.MapAreaItem``, and so on."""
    unexported = []
    for name in empire_core.__all__:
        obj = getattr(empire_core, name)
        owner = _owner(obj)
        if owner in PUBLIC_MODULES and getattr(importlib.import_module(owner), name, None) is not obj:
            unexported.append(f"{name} (defined under {owner})")
        elif owner in PUBLIC_MODULES and name not in _public_names(owner):
            unexported.append(f"{name} (not in {owner}.__all__)")
    assert not unexported, unexported


@pytest.mark.parametrize("package", [m for m in PUBLIC_MODULES if hasattr(importlib.import_module(m), "__path__")])
def test_every_service_is_exported_from_its_package(package: str) -> None:
    """``client.<area>`` is typed by a service a caller can import from the area."""
    services = set()
    for info in pkgutil.walk_packages(importlib.import_module(package).__path__, f"{package}."):
        for name, obj in vars(importlib.import_module(info.name)).items():
            if inspect.isclass(obj) and issubclass(obj, BaseService) and obj.__module__ == info.name:
                services.add(name)
    missing = services - set(_public_names(package))
    assert not missing, f"{package}.__all__ lacks {sorted(missing)}"


def _unexported(path: str) -> str | None:
    """The first part of a dotted ``empire_core`` path past the public ones, or None when it is public."""
    module, *rest = path.split(".")
    for attr in rest:
        if f"{module}.{attr}" in PUBLIC_PATHS:
            module = f"{module}.{attr}"
        elif attr in _public_names(module):
            return None
        else:
            return f"{module}.{attr}"
    return None


def _code_problems(source: str) -> list[str]:
    """Imports of private paths or unexported names, and attribute paths through a private one."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        lines = [line.strip() for line in source.splitlines() if line.lstrip().startswith(("from ", "import "))]
        return [problem for line in lines if line != source.strip() for problem in _code_problems(line)]
    problems = []
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and not node.level and (node.module or "").split(".")[0] == "empire_core":
            module = node.module or ""
            if module not in PUBLIC_PATHS:
                problems.append(f"from {module} import ... (a private path)")
                continue
            for alias in node.names:
                if f"{module}.{alias.name}" in PUBLIC_PATHS:
                    bound[alias.asname or alias.name] = f"{module}.{alias.name}"
                elif alias.name != "*" and alias.name not in _public_names(module):
                    problems.append(f"{alias.name} is not in {module}.__all__")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] != "empire_core":
                    continue
                if alias.name not in PUBLIC_PATHS:
                    problems.append(f"import {alias.name} (a private path)")
                else:
                    bound[alias.asname or "empire_core"] = alias.name if alias.asname else "empire_core"
    inner: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or id(node) in inner:
            continue
        parts = []
        part: ast.expr = node
        while isinstance(part, ast.Attribute):
            inner.add(id(part))
            parts.append(part.attr)
            part = part.value
        if isinstance(part, ast.Name) and part.id in bound:
            path = ".".join([bound[part.id], *reversed(parts)])
            if private := _unexported(path):
                problems.append(f"{path} goes through {private}, which is not public")
    return problems


_FENCE = re.compile(
    r"^(?P<indent>[ \t]*)```(?P<lang>[\w-]*)[^\n]*\n(?P<body>.*?)^(?P=indent)```[ \t]*$", re.MULTILINE | re.DOTALL
)
_PROMPT = re.compile(r"^(>>>|\.\.\.) ?", re.MULTILINE)
# A path after "#", "[", "<", "~" or a role's backtick is a link anchor or a cross-reference, not import advice.
_DOTTED = re.compile(r"(?<![\w.#\[<~])(?<!:`)empire_core(?:\.\w+){2,}")
_NAMES_PRIVATE_PATHS = {"docs/reference/index.md": "it lists which paths are private"}


def _path_problems(text: str) -> list[str]:
    """Dotted ``empire_core`` paths in prose or code that go through a private module."""
    kept = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(":::"))
    return [
        f"{match.group()} goes through {private}, which is not public"
        for match in _DOTTED.finditer(kept)
        if (private := _unexported(match.group()))
    ]


def _documents() -> list[Path]:
    docs = [p for p in sorted((REPO / "docs").rglob("*.md")) if p.name != "changelog.md"]
    return [REPO / "README.md", *docs, *sorted((REPO / "examples").glob("*.py"))]


def _document_problems(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    where = path.relative_to(REPO).as_posix()
    if path.suffix == ".py":
        problems = _code_problems(text)
    else:
        problems = [
            problem
            for block in _FENCE.finditer(text)
            if block["lang"] in ("python", "py", "pycon")
            for problem in _code_problems(_PROMPT.sub("", textwrap.dedent(block["body"])))
        ]
    if where not in _NAMES_PRIVATE_PATHS and not where.startswith("docs/internals/"):
        problems += _path_problems(text)
    return [f"{where}: {problem}" for problem in problems]


def test_docs_and_examples_use_only_public_paths() -> None:
    """Imports and dotted paths in the README, the docs (bar the internals pages) and the examples are public."""
    problems = [problem for path in _documents() for problem in _document_problems(path)]
    assert not problems, "\n".join(problems)


_DOCSTRINGS_TO_FIX: dict[str, str] = {}


def test_docstrings_name_only_public_paths() -> None:
    """A docstring that tells the reader where something lives names a public path; cross-references are exempt."""
    problems = []
    for path in sorted((REPO / "src" / "empire_core").rglob("*.py")):
        where = path.relative_to(REPO).as_posix()
        if where in _DOCSTRINGS_TO_FIX:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                problems += [f"{where}: {problem}" for problem in _path_problems(ast.get_docstring(node) or "")]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    ("code", "problem"),
    [
        ("from empire_core.map import MapService, \\\n    ScanResult\n", None),
        ("from empire_core import (\n    EmpireClient,  # the client\n    Kingdom,\n)\n", None),
        ("from empire_core import EmpireClient; c = EmpireClient()\n", None),
        ("from empire_core.map import *\n", None),
        ("import empire_core.map as m\nm.MapService\n", None),
        ("import empire_core\nempire_core.map.MapService\n", None),
        ("from empire_core.map import NoSuchName\n", "NoSuchName is not in empire_core.map.__all__"),
        ("import empire_core.protocol.models as pm\n", "import empire_core.protocol.models (a private path)"),
        ("import os, empire_core.protocol.models\n", "import empire_core.protocol.models (a private path)"),
        ("import empire_core\nx = empire_core.protocol.models.Foo\n", "through empire_core.protocol.models"),
        ("import empire_core.map as m\nm.service.MapService\n", "through empire_core.map.service"),
        ("importlib.import_module('empire_core.protocol.models')\n", "through empire_core.protocol.models"),
        ("Use `from empire_core.events.titles import get_event_titles`.\n", "through empire_core.events.titles"),
        ("- from empire_core.protocol.models import X\n", "through empire_core.protocol.models"),
    ],
)
def test_the_docs_check_reads_every_import_form(code: str, problem: str | None) -> None:
    found = _code_problems(code) + _path_problems(code)
    if problem is None:
        assert not found
    else:
        assert any(problem in entry for entry in found), found


def test_the_docs_check_skips_reference_anchors() -> None:
    text = (
        "::: empire_core.gamedata.data\n"
        "[GameData][empire_core.gamedata.data.GameData]\n"
        "[load](../reference/gamedata.md#empire_core.gamedata.data.GameData.load)\n"
        ":meth:`GameData.load <empire_core.gamedata.data.GameData.load>`\n"
        ":class:`~empire_core.gamedata.data.GameData`\n"
        ":mod:`empire_core.gamedata.data`\n"
    )
    assert _path_problems(text) == []


def _exports() -> list[tuple[str, Any]]:
    """(name, object) for every name a public path exports."""
    return [
        (name, getattr(importlib.import_module(module), name))
        for module in PUBLIC_PATHS
        for name in _public_names(module)
    ]


@functools.cache
def _type_checking_names(module_name: str) -> dict[str, Any]:
    """What a module imports under ``if TYPE_CHECKING:``, imported now."""
    module = sys.modules[module_name]
    names: dict[str, Any] = {}
    for node in ast.parse(inspect.getsource(module)).body:
        if isinstance(node, ast.If) and ast.unparse(node.test) in ("TYPE_CHECKING", "typing.TYPE_CHECKING"):
            exec(
                compile(
                    ast.Module(body=node.body, type_ignores=[]), f"<type-checking imports of {module_name}>", "exec"
                ),
                dict(vars(module)),
                names,
            )
    return names


def _hints(obj: Any) -> dict[str, Any]:
    """The resolved hints, names imported only under TYPE_CHECKING included."""
    try:
        return get_type_hints(obj)
    except NameError:
        own = vars(sys.modules[obj.__module__])
        return get_type_hints(obj, localns={**_type_checking_names(obj.__module__), **own})


def _library_types(hint: Any) -> set[type]:
    if get_origin(hint) is Annotated:
        return _library_types(get_args(hint)[0])
    if get_origin(hint) is not None or isinstance(hint, types.UnionType):
        return {found for arg in get_args(hint) for found in _library_types(arg)}
    if inspect.isclass(hint) and hint.__module__.split(".")[0] == "empire_core":
        return {hint}
    return set()


def _signatures(obj: type | types.FunctionType) -> list[tuple[str, Any]]:
    """(where, object) for a public function, or for a public class and each public method it defines."""
    found: list[tuple[str, Any]] = [(f"{obj.__module__}.{obj.__qualname__}", obj)]
    for klass in getattr(obj, "__mro__", ()):
        if klass.__module__.split(".")[0] != "empire_core":
            continue
        for name, member in vars(klass).items():
            if name.startswith("_") and name != "__init__":
                continue
            member = member.fget if isinstance(member, property) else getattr(member, "__func__", member)
            if inspect.isfunction(member) and member.__module__.split(".")[0] == "empire_core":
                found.append((f"{klass.__module__}.{klass.__qualname__}.{name}", member))
    return found


_INTERNAL_TYPES = {
    "empire_core.client.stream.CallbackSource": "EventStream.__init__ takes it, but only the client builds streams",
    "empire_core.map.scanner._Client": "the structural type of a scanning client; callers pass EmpireClients",
}


def test_every_type_a_public_signature_names_is_public() -> None:
    """A type a public class, function or method takes or hands out can be imported from a public path."""
    public_ids = {id(obj) for _, obj in _exports()}
    problems = set()
    for root in {id(obj): obj for _, obj in _exports()}.values():
        if not (inspect.isclass(root) or inspect.isfunction(root)):
            continue
        for where, obj in _signatures(root):
            try:
                hints = _hints(obj)
            except NameError as e:
                problems.add(f"{where}: its hints name {e.name}, which cannot be resolved")
                continue
            for name, hint in hints.items():
                if inspect.isclass(obj) and name.startswith("_"):
                    continue
                for found in _library_types(hint):
                    path = f"{found.__module__}.{found.__qualname__}"
                    if id(found) not in public_ids and path not in _INTERNAL_TYPES:
                        problems.add(f"{where} ({name}): {path} is not public")
    assert not problems, "\n".join(sorted(problems))


def test_top_level_movement_is_the_state_model_consumers_use() -> None:
    """`empire_core.Movement` must stay the state model with the GGE field names."""
    from empire_core.movements.tracked import Movement as StateMovement

    assert empire_core.Movement is StateMovement


# ---------------------------------------------------------------------------
# Forked enums
# ---------------------------------------------------------------------------


def test_each_id_space_has_one_enum() -> None:
    """Kingdom and MapItemType are the only kingdom and area-type enums; the old duplicates are gone."""
    from empire_core import enums
    from empire_core.protocol import models

    assert models.Kingdom is enums.Kingdom and models.MapItemType is enums.MapItemType
    assert empire_core.MapItemType is enums.MapItemType
    for gone in ("KingdomType", "MapObjectType"):
        assert not hasattr(enums, gone)
        assert not hasattr(empire_core, gone)


def test_npc_camps_resolve_through_map_item_type() -> None:
    """A robber baron camp is AREA_TYPE_DUNGEON (2) in the client's own table."""
    from empire_core.enums import MapItemType

    assert MapItemType.DUNGEON == 2
    assert MapItemType(7) is MapItemType.TREASURE_DUNGEON
    assert MapItemType(12) is MapItemType.KINGDOM_CASTLE


def test_khan_camp_resolves_under_its_event_type() -> None:
    """The nomad khan camp is ALLIANCE_NOMAD_CAMP (35), not a type of its own."""
    from empire_core.enums import MapItemType

    assert MapItemType(35) is MapItemType.ALLIANCE_NOMAD_CAMP


def test_map_item_type_has_no_non_client_aliases() -> None:
    """WorldConst.AREA_TYPE_* (dll line 20003) names each id once."""
    from empire_core.enums import MapItemType

    for gone in ("ROBBER_BARON", "EXTERNAL_KINGDOM", "KHAN_CAMP", "KHAN_TENT"):
        assert gone not in MapItemType.__members__
    assert len(MapItemType.__members__) == len(MapItemType)


def test_ruins_are_castles_not_a_map_item_type() -> None:
    """A ruin is a CASTLE entry flagged isRuin; the client has no ruin type."""
    from empire_core.enums import MapItemType

    assert not hasattr(MapItemType, "RUIN")
    doc = MapItemType.__doc__ or ""
    assert "ruin" in doc.lower(), "the enum must say where ruins actually appear"


# ---------------------------------------------------------------------------
# __version__ without distribution metadata
# ---------------------------------------------------------------------------


def test_version_falls_back_when_distribution_metadata_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A vendored / PYTHONPATH import has no metadata and must still import."""

    def _missing(name: str, *args: Any, **kwargs: Any) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", _missing)
    try:
        reloaded = importlib.reload(empire_core)
        assert reloaded.__version__ == "0.0.0.dev0"
    finally:
        monkeypatch.undo()
        importlib.reload(empire_core)

    assert empire_core.__version__ != "0.0.0.dev0"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


def test_every_declared_exception_is_part_of_the_public_api() -> None:
    """No exception may exist that a caller can never catch (dead code)."""
    from empire_core import exceptions

    declared = {
        name
        for name, obj in vars(exceptions).items()
        if isinstance(obj, type) and issubclass(obj, exceptions.EmpireError)
    }
    missing = declared - set(empire_core.__all__)
    assert not missing, f"exceptions defined but not exported: {sorted(missing)}"


def test_command_error_exposes_the_resolved_gge_error() -> None:
    from empire_core.exceptions import CommandError
    from empire_core.protocol.errors import GGEError

    err = CommandError("cra", 55)
    assert err.code == 55
    assert err.error is GGEError.NOT_ENOUGH_RESOURCES
    assert "NOT_ENOUGH_RESOURCES" in str(err)


def test_command_error_does_not_mislabel_unknown_codes() -> None:
    """from_code() collapses unknown codes to GENERAL_ERROR; the raw code wins."""
    from empire_core.exceptions import CommandError

    err = CommandError("gaa", 999999)
    assert err.code == 999999
    assert err.error is None
    assert "GENERAL_ERROR" not in str(err)
    assert "999999" in str(err)


# ---------------------------------------------------------------------------
# SpyResult typing
# ---------------------------------------------------------------------------


def test_spy_result_fields_are_typed() -> None:
    from empire_core.enums import SpyOutcome, SpyStep
    from empire_core.exceptions import EmpireError
    from empire_core.messages.models import SpyReportResponse
    from empire_core.spy import SpyResult
    from empire_core.spy.models import SendSpyResponse

    hints = get_type_hints(SpyResult)
    assert hints["outcome"] == SpyOutcome
    assert hints["step"] == SpyStep | None
    assert hints["error"] == EmpireError | None
    assert hints["report"] == SpyReportResponse | None
    assert hints["mission"] == SendSpyResponse | None

    bare_any = [name for name, hint in hints.items() if hint is Any]
    assert not bare_any, f"untyped SpyResult fields: {bare_any}"


def test_spy_result_defaults_carry_no_report() -> None:
    from empire_core.enums import SpyOutcome
    from empire_core.spy import SpyResult

    result = SpyResult(SpyOutcome.NO_SPIES_AVAILABLE)
    assert (result.success, result.step, result.error, result.report, result.army) == (False, None, None, None, None)
    assert SpyResult(SpyOutcome.SUCCESS).success is True
    assert {f.name for f in fields(SpyResult)} == {"outcome", "step", "error", "message_id", "report", "mission"}


# ---------------------------------------------------------------------------
# State models expose pythonic names
# ---------------------------------------------------------------------------

_SNAKE_CASE_ALIASES = {
    "Castle": [
        ("id", "OID"),
        ("name", "N"),
        ("x", "X"),
        ("y", "Y"),
        ("kingdom_id", "KID"),
    ],
    "Player": [
        ("id", "PID"),
        ("name", "PN"),
        ("alliance_id", "AID"),
        ("level", "LVL"),
        ("xp", "XP"),
        ("legendary_level", "LL"),
        ("xp_for_current_level", "XPFCL"),
        ("xp_to_next_level", "XPTNL"),
        ("email", "E"),
        ("premium_flag", "PF"),
        ("vip_flag", "VF"),
        ("honor", "H"),
        ("ranking", "RP"),
    ],
    "Alliance": [
        ("id", "AID"),
        ("rank", "R"),
        ("current_fame", "ACF"),
    ],
    "Movement": [
        ("movement_id", "MID"),
        ("movement_type", "T"),
        ("progress_time", "PT"),
        ("total_time", "TT"),
        ("direction", "D"),
        ("target_id", "TID"),
        ("kingdom_id", "KID"),
        ("source_id", "SID"),
        ("owner_id", "OID"),
    ],
}


@pytest.mark.parametrize("model_name", sorted(_SNAKE_CASE_ALIASES))
def test_state_models_expose_snake_case_aliases_for_wire_fields(model_name: str) -> None:
    """Consumers must be able to avoid the raw two-letter GGE field names."""
    model_cls = getattr(empire_core, model_name)
    fields = model_cls.model_fields
    missing = [
        snake for snake, _ in _SNAKE_CASE_ALIASES[model_name] if snake not in fields and not hasattr(model_cls, snake)
    ]
    assert not missing, f"{model_name} has no pythonic alias for {missing}"

    instance = model_cls()
    for snake, wire in _SNAKE_CASE_ALIASES[model_name]:
        if snake in fields:
            assert fields[snake].alias == wire, f"{model_name}.{snake} is not aliased to {wire}"
            value = {str: "x", Kingdom: Kingdom.STORM}.get(fields[snake].annotation, 7)
            assert getattr(model_cls.model_validate({wire: value}), snake) == value
        else:
            assert getattr(instance, snake) == getattr(instance, wire), f"{model_name}.{snake} != .{wire}"


def test_state_movement_points_at_the_protocol_models() -> None:
    """The protocol layer no longer has a Movement of its own; the state one says where the raw models are."""
    from empire_core.map.models import items as protocol_map
    from empire_core.movements.tracked import Movement as StateMovement

    assert not hasattr(protocol_map, "Movement")
    doc = StateMovement.__doc__ or ""
    assert "MovementWrapper" in doc and "MovementRecord" in doc
