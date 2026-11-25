"""Owner record alliance crest and Berimond blocks: frozen, and read into shared instances."""

import json
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from empire_core.alliance.models.info import AllianceMember
from empire_core.gamedata import AllianceCrestColor
from empire_core.map.models.areas import GetMapAreaResponse, MapObject
from empire_core.map.models.owners import AllianceCrest, AllianceEmblem, Interned, OwnerFaction
from empire_core.player.models.info import PlayerOwnerInfo

CREST = {"IS": 1, "SPT": 0, "S1": 19, "SC1": 36, "S2": 13, "SC2": 35, "BGT": 2, "BGC1": 6, "BGC2": 30}
ALLIANCE = {"ACCA": {"ACLI": 19, "ACCS": [1, 9, 18]}}
FACTION = {"FID": -1, "PMS": 0, "PMT": 0, "TID": 0}
BLOCKS: dict[str, tuple[type[BaseModel], str]] = {
    "alliance_emblem": (AllianceEmblem, "aee"),
    "faction": (OwnerFaction, "FN"),
}


def _record(owner_id: int, **blocks: Any) -> dict[str, Any]:
    return {"OID": owner_id, "N": f"Owner {owner_id}", "AID": 7, "E": CREST, "aee": ALLIANCE, "FN": FACTION, **blocks}


@pytest.fixture(autouse=True)
def _nothing_shared_yet() -> None:
    Interned.clear()


@pytest.mark.parametrize("model", [MapObject, AllianceMember, PlayerOwnerInfo])
@pytest.mark.parametrize("field", BLOCKS)
def test_equal_blocks_are_one_instance(model: type[BaseModel], field: str):
    first, second = model.model_validate(_record(1)), model.model_validate(_record(2))
    assert getattr(first, field) is not None
    assert getattr(first, field) is getattr(second, field)


@pytest.mark.parametrize("model", [MapObject, AllianceMember])
def test_player_crests_are_read_per_record(model: type[MapObject | AllianceMember]):
    first, second = model.model_validate(_record(1)), model.model_validate(_record(2))
    assert first.emblem == second.emblem
    assert first.emblem is not second.emblem


def test_a_record_read_from_json_text_shares_the_blocks():
    first = MapObject.model_validate(_record(1))
    second = MapObject.model_validate_json(json.dumps(_record(2)))
    assert first.alliance_emblem is second.alliance_emblem and first.faction is second.faction


def test_a_reply_shares_the_blocks_of_its_owners():
    response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "OI": [_record(n) for n in range(1, 4)]})
    assert len({id(owner.alliance_emblem) for owner in response.owners}) == 1
    assert len({id(owner.faction) for owner in response.owners}) == 1


def test_different_blocks_are_different_instances():
    first = MapObject.model_validate(_record(1))
    second = MapObject.model_validate(
        _record(2, aee={"ACCA": {"ACLI": 19, "ACCS": [1, 9, 17]}}, FN={**FACTION, "FID": 2})
    )
    assert first.alliance_emblem != second.alliance_emblem and first.faction != second.faction


def test_clearing_forgets_the_shared_instances():
    first = MapObject.model_validate(_record(1))
    Interned.clear()
    second = MapObject.model_validate(_record(2))
    assert first.faction == second.faction and first.faction is not second.faction


def test_a_full_cache_starts_over(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Interned, "MAXSIZE", 2)
    first = MapObject.model_validate(_record(1))
    for fid in (2, 3):
        MapObject.model_validate(_record(fid, FN={**FACTION, "FID": fid}))
    again = MapObject.model_validate(_record(4))
    assert again.faction == first.faction and again.faction is not first.faction


@pytest.mark.parametrize(
    ("field", "block"),
    [
        ("alliance_emblem", ALLIANCE),
        ("alliance_emblem", {"ACCA": {"ACLI": 19, "ACCS": []}}),
        ("alliance_emblem", {"ACCA": {"ACLI": 19}}),
        ("alliance_emblem", {"ACCA": {"ACLI": "19", "ACCS": ["1", 9]}}),
        ("alliance_emblem", {"ACCA": {"ACLI": 19, "ACCS": {"0": 1}}}),
        ("alliance_emblem", {"ACCA": {"ACLI": 19.0, "ACCS": [1.0]}}),
        ("alliance_emblem", {"ACCA": {"ACLI": True, "ACCS": [True]}}),
        ("alliance_emblem", {"ACCA": {"ACLI": 19, "ACCS": (1, 9)}}),
        ("alliance_emblem", {"ACCA": 5}),
        ("alliance_emblem", {"ACCA": []}),
        ("alliance_emblem", {"ACCA": None}),
        ("alliance_emblem", {**ALLIANCE, "XX": [1, {"Y": 2}]}),
        ("alliance_emblem", {}),
        ("faction", FACTION),
        ("faction", {}),
        ("faction", {"FID": "2", "TID": -1}),
        ("faction", {"FID": 2, "PMT": 1.5}),
        ("faction", {"FID": True, "PMS": None}),
        ("faction", {**FACTION, "XX": 5}),
        ("faction", {**FACTION, "XX": (5,)}),
    ],
)
def test_a_shared_block_reads_as_a_fresh_one(field: str, block: dict[str, Any]):
    model, key = BLOCKS[field]
    record = MapObject.model_validate(_record(1, **{key: block}))
    again = MapObject.model_validate(_record(2, **{key: block}))
    shared, fresh = getattr(record, field), model.model_validate(block)
    assert shared == fresh == getattr(again, field)
    assert shared.model_dump() == fresh.model_dump()
    assert shared.model_fields_set == fresh.model_fields_set
    assert shared.model_extra == fresh.model_extra


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ({"FID": 1, "PMS": 1}, {"FID": True, "PMS": True}),
        ({"FID": 1, "XX": [1]}, {"FID": 1, "XX": (1,)}),
        ({"FID": 1, "XX": 1}, {"FID": 1, "XX": 1.0}),
        ({"FID": 1, "XX": "1"}, {"FID": 1, "XX": 1}),
    ],
)
def test_blocks_that_only_look_alike_are_not_one_instance(one: dict[str, Any], other: dict[str, Any]):
    first = MapObject.model_validate(_record(1, FN=one))
    second = MapObject.model_validate(_record(2, FN=other))
    assert first.faction is not second.faction
    assert second.faction == OwnerFaction.model_validate(other)


def test_a_block_that_is_not_an_object_is_none():
    record = MapObject.model_validate(_record(1, aee=[1], FN="x"))
    assert (record.alliance_emblem, record.faction) == (None, None)


@pytest.mark.parametrize("field", BLOCKS)
def test_the_shared_blocks_are_frozen(field: str):
    block = getattr(MapObject.model_validate(_record(1)), field)
    name = next(iter(type(block).model_fields))
    with pytest.raises(ValidationError):
        setattr(block, name, None)


def test_an_alliance_crest_is_frozen_and_holds_its_colours_in_a_tuple():
    crest = AllianceCrest.model_validate({"ACLI": 19, "ACCS": [1, 9, "18"]})
    assert crest.color_ids == (AllianceCrestColor.COLOR_1, AllianceCrestColor.COLOR_9, AllianceCrestColor.COLOR_18)
    assert hash(crest) == hash(AllianceCrest.model_validate({"ACLI": 19, "ACCS": [1, 9, 18]}))
    with pytest.raises(ValidationError):
        setattr(crest, "layout_id", None)  # noqa: B010


def test_an_alliance_crest_dumped_in_python_mode_reads_back():
    crest = AllianceCrest.model_validate({"ACLI": 19, "ACCS": [1, 9]})
    assert AllianceCrest.model_validate(crest.model_dump()) == crest
    assert AllianceCrest(layout_id=19, color_ids=(1, 9)) == crest
