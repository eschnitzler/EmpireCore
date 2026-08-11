"""Tests for the public API surface of ``empire_core``.

These guard the *boundary* of the library rather than any single behaviour:

- what ``empire_core.__all__`` promises and where those objects really live,
- that the enums describing a given server ID space are not silently forked,
- that ``__version__`` survives a metadata-less (vendored / PYTHONPATH) import,
- that public dataclasses/models are actually typed and expose pythonic names.

The names asserted below are the de-facto public surface: every one of them is
imported by an external consumer today, so a rename here is a breaking change.
"""

import importlib
import importlib.metadata
from dataclasses import fields
from typing import Any, get_type_hints

import pytest

import empire_core

# ---------------------------------------------------------------------------
# Top-level exports (findings 1 & 2)
# ---------------------------------------------------------------------------

# (exported name, module that owns the object)
# Every entry is deep-imported by the flagship consumer today.
_DE_FACTO_PUBLIC_SURFACE = [
    ("EmpireClient", "empire_core.client.client"),
    ("EmpireConfig", "empire_core.config"),
    ("AccountPool", "empire_core.pool"),
    ("Account", "empire_core.accounts"),
    ("accounts", "empire_core.accounts"),
    ("Kingdom", "empire_core.protocol.models.map"),
    ("MapItemType", "empire_core.protocol.models.map"),
    ("MapAreaItem", "empire_core.protocol.models.map"),
    ("ScanResult", "empire_core.client.map_scanner"),
    ("SpyService", "empire_core.services.spy"),
    ("SpyResult", "empire_core.services.spy"),
    ("Packet", "empire_core.protocol.packet"),
    ("GGEError", "empire_core.protocol.errors"),
    ("CastleInfo", "empire_core.protocol.models.castle"),
    ("AllianceMember", "empire_core.protocol.models.alliance"),
    ("RankingEntry", "empire_core.protocol.models.ranking"),
    ("decode_chat_text", "empire_core.protocol.models.chat"),
    ("encode_chat_text", "empire_core.protocol.models.chat"),
    # The documented-preferred pool API raises this, and count_troops' docs
    # tell callers to use these two — none may require a deep import.
    ("PoolExhaustedError", "empire_core.pool"),
    ("troop_data_available", "empire_core.utils.troops"),
    ("get_troop_ids", "empire_core.utils.troops"),
]


@pytest.mark.parametrize("name, module_path", _DE_FACTO_PUBLIC_SURFACE)
def test_de_facto_public_surface_is_exported_from_the_top_level(name: str, module_path: str) -> None:
    """Consumers must not have to deep-import internal modules for these."""
    assert name in empire_core.__all__, f"{name} missing from empire_core.__all__"
    module = importlib.import_module(module_path)
    assert getattr(empire_core, name) is getattr(module, name)


def test_previously_exported_names_are_still_available() -> None:
    """Nothing that was public before may disappear (backwards compatibility)."""
    for name in (
        "EmpireClient",
        "EmpireConfig",
        "AccountPool",
        "EmpireError",
        "NetworkError",
        "ConnectionClosedError",
        "LoginError",
        "LoginCooldownError",
        "PacketError",
        "EmpireTimeoutError",
        "CommandError",
        "Player",
        "Castle",
        "Resources",
        "Building",
        "Alliance",
        "Movement",
        "MovementResources",
        "MovementType",
        "MapObjectType",
        "KingdomType",
        "GameEvent",
    ):
        assert name in empire_core.__all__
        assert getattr(empire_core, name) is not None


def test_all_entries_resolve_and_are_unique() -> None:
    assert len(empire_core.__all__) == len(set(empire_core.__all__))
    for name in empire_core.__all__:
        assert hasattr(empire_core, name), f"__all__ advertises missing attribute {name}"


def test_top_level_movement_is_the_state_model_consumers_use() -> None:
    """`empire_core.Movement` must stay the state model with the GGE field names."""
    from empire_core.state.world_models import Movement as StateMovement

    assert empire_core.Movement is StateMovement


# ---------------------------------------------------------------------------
# Forked enums (finding 3)
# ---------------------------------------------------------------------------

# MapObjectType (movement target areas) and MapItemType (map-scan AI array)
# overlap heavily but disagree on these three IDs. Neither has been verified
# against live packets, so both are kept; this pins the known divergence so a
# future change to either table has to be deliberate.
_KNOWN_MAP_TYPE_CONFLICTS = {2, 7, 12}


def test_kingdom_type_is_an_alias_of_the_authoritative_kingdom_enum() -> None:
    """One kingdom ID space => one enum. KingdomType stays as a legacy alias."""
    from empire_core.protocol.models.map import Kingdom
    from empire_core.utils import enums

    assert enums.KingdomType is Kingdom
    assert empire_core.KingdomType is Kingdom
    # The old members must keep working, and the alias gains the member the
    # duplicate table was missing.
    assert enums.KingdomType.GREEN == 0
    assert enums.KingdomType.STORM == 4
    assert enums.KingdomType(10) is Kingdom.BERIMOND


def test_map_type_enums_only_disagree_on_the_documented_values() -> None:
    from empire_core.protocol.models.map import MapItemType
    from empire_core.utils.enums import MapObjectType

    shared = {m.value for m in MapObjectType} & {m.value for m in MapItemType}
    conflicts = {v for v in shared if MapObjectType(v).name != MapItemType(v).name}
    assert conflicts == _KNOWN_MAP_TYPE_CONFLICTS


def test_map_object_type_documents_its_id_space_and_the_conflicts() -> None:
    """The duplicate table must say what it describes and where it disagrees."""
    from empire_core.utils.enums import MapObjectType

    doc = MapObjectType.__doc__ or ""
    assert "MapItemType" in doc, "MapObjectType must point at the parallel enum"
    for value in sorted(_KNOWN_MAP_TYPE_CONFLICTS):
        assert str(value) in doc, f"conflicting ID {value} is not documented"


# ---------------------------------------------------------------------------
# __version__ without distribution metadata (finding 4)
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
# Exceptions (findings 5 & 9)
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
# SpyResult typing (finding 6)
# ---------------------------------------------------------------------------


def test_spy_result_payload_fields_are_typed() -> None:
    from empire_core.protocol.models.messages import SpyCastleInfo
    from empire_core.services.spy import SpyResult

    hints = get_type_hints(SpyResult)
    assert hints["spy_data"] == list[Any]
    assert hints["battle_data"] == dict[str, Any]
    assert hints["target"] == SpyCastleInfo | None

    bare_any = [name for name, hint in hints.items() if hint is Any]
    assert not bare_any, f"untyped SpyResult fields: {bare_any}"


def test_spy_result_payload_defaults_are_empty_not_none() -> None:
    from empire_core.services.spy import SpyResult

    result = SpyResult(success=False, reason="no_spies_available")
    assert result.spy_data == []
    assert result.battle_data == {}
    assert result.target is None
    # Mutable defaults must not be shared between instances.
    assert SpyResult(success=True).spy_data is not result.spy_data
    assert {f.name for f in fields(SpyResult)} >= {
        "success",
        "reason",
        "message_id",
        "spy_data",
        "battle_data",
        "target",
    }


# ---------------------------------------------------------------------------
# State models expose pythonic names (findings 7 & 8)
# ---------------------------------------------------------------------------

_SNAKE_CASE_ALIASES = {
    "Castle": [
        ("id", "OID"),
        ("name", "N"),
        ("x", "X"),
        ("y", "Y"),
        ("kingdom_id", "KID"),
        ("population", "P"),
        ("next_day_population", "NDP"),
        ("max_castellans", "MC"),
        ("has_barracks", "B"),
        ("has_workshop", "WS"),
        ("has_dwelling", "DW"),
        ("has_harbour", "H"),
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
    ],
    "Alliance": [
        ("id", "AID"),
        ("name", "N"),
        ("abbreviation", "SA"),
        ("rank", "R"),
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
    missing = [snake for snake, _ in _SNAKE_CASE_ALIASES[model_name] if not hasattr(model_cls, snake)]
    assert not missing, f"{model_name} has no pythonic alias for {missing}"

    instance = model_cls()
    for snake, wire in _SNAKE_CASE_ALIASES[model_name]:
        assert getattr(instance, snake) == getattr(instance, wire), f"{model_name}.{snake} != .{wire}"


def test_state_movement_documents_the_protocol_namesake() -> None:
    """Two public classes are named Movement; the collision must be documented."""
    from empire_core.protocol.models.map import Movement as ProtocolMovement
    from empire_core.state.world_models import Movement as StateMovement

    assert StateMovement is not ProtocolMovement
    doc = StateMovement.__doc__ or ""
    assert "protocol.models.map" in doc, "state Movement must warn about its protocol namesake"
