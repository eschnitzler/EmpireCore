"""Tests for the public API surface of ``empire_core``.

These guard the *boundary* of the library rather than any single behavior:

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
from empire_core.enums import Kingdom

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
    ("Kingdom", "empire_core.enums"),
    ("MapItemType", "empire_core.enums"),
    ("MapAreaItem", "empire_core.map.models.items"),
    ("ScanResult", "empire_core.client.map_scanner"),
    ("SpyService", "empire_core.spy.service"),
    ("SpyResult", "empire_core.spy.service"),
    ("Packet", "empire_core.protocol.packet"),
    ("GGEError", "empire_core.protocol.errors"),
    ("CastleInfo", "empire_core.castle.models.castles"),
    ("AllianceMember", "empire_core.alliance.models.info"),
    ("RankingEntry", "empire_core.ranking.models"),
    ("decode_json_text", "empire_core.protocol.text"),
    ("encode_json_text", "empire_core.protocol.text"),
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
        "AttackInProgressError",
        "Player",
        "Castle",
        "Resources",
        "Building",
        "Alliance",
        "Movement",
        "MovementResources",
        "MovementType",
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
    from empire_core.commanders.models.roster import Castellan
    from empire_core.messages.models import SpyCastleInfo
    from empire_core.spy.service import SpyResult

    hints = get_type_hints(SpyResult)
    assert hints["spy_data"] == list[list[list[int]]]
    assert hints["defending_castellan"] == Castellan | None
    assert hints["target"] == SpyCastleInfo | None

    bare_any = [name for name, hint in hints.items() if hint is Any]
    assert not bare_any, f"untyped SpyResult fields: {bare_any}"


def test_spy_result_payload_defaults_are_empty_not_none() -> None:
    from empire_core.spy.service import SpyResult

    result = SpyResult(success=False, reason="no_spies_available")
    assert result.spy_data == []
    assert result.defending_castellan is None
    assert result.target is None
    # Mutable defaults must not be shared between instances.
    assert SpyResult(success=True).spy_data is not result.spy_data
    assert {f.name for f in fields(SpyResult)} >= {
        "success",
        "reason",
        "message_id",
        "spy_data",
        "defending_castellan",
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
    from empire_core.state.world_models import Movement as StateMovement

    assert not hasattr(protocol_map, "Movement")
    doc = StateMovement.__doc__ or ""
    assert "MovementWrapper" in doc and "MovementRecord" in doc
