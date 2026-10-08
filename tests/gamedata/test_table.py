"""A game-data table validates a row the first time it is read."""

import logging
from concurrent.futures import ThreadPoolExecutor

import pytest

from empire_core.gamedata import BuildingDef, GameData, Table, ids

ROWS = {
    171: {"wodID": "171", "name": "Keep"},
    999999: {"wodID": "999999", "name": "Future"},
    5: {"wodID": "none"},
}


@pytest.fixture
def table() -> Table:
    return Table(BuildingDef, "building_id", ROWS)


def test_reading_one_row_validates_that_row_alone(table, monkeypatch):
    seen = []
    validate = BuildingDef.model_validate

    def spy(row, **kwargs):
        seen.append(row)
        return validate(row, **kwargs)

    monkeypatch.setattr(BuildingDef, "model_validate", spy)

    assert table[ids.Building.KEEP_L1].name == "Keep"
    assert table.get(171) is table[171]
    assert seen == [ROWS[171]]


def test_iterating_gives_every_valid_row_by_its_id(table):
    assert list(table) == [ids.Building.KEEP_L1, 999999]
    assert type(list(table)[1]) is int
    assert len(table) == 2
    assert {key: row.name for key, row in table.items()} == {171: "Keep", 999999: "Future"}


def test_a_row_that_does_not_fit_is_not_in_the_table(table):
    assert 5 not in table and table.get(5) is None
    with pytest.raises(KeyError):
        table[5]
    assert "171" not in table and True not in table


def test_a_table_is_read_only(table):
    with pytest.raises(TypeError):
        table[1] = BuildingDef(building_id=1)  # type: ignore[index]


def test_parsing_validates_no_lazy_row(monkeypatch):
    def refuse(row):
        raise AssertionError("validated at parse")

    monkeypatch.setattr(BuildingDef, "model_validate", refuse)
    data = GameData.parse("786.03", {"buildings": [{"wodID": "171", "name": "Keep", "comment1": "dropped"}]})

    assert data._table_rows["buildings"] == {171: {"wodID": "171", "name": "Keep"}}


def test_a_row_that_does_not_fit_is_warned_once_naming_table_id_and_model(caplog):
    table: Table[int, BuildingDef] = Table(BuildingDef, "building_id", ROWS, name="buildings")

    with caplog.at_level(logging.WARNING, logger="empire_core.gamedata.table"):
        assert 5 not in table and table.get(5) is None and len(table) == 2

    [record] = caplog.records
    assert record.getMessage().startswith("buildings row 5 does not fit BuildingDef and is left out: wodID")


def test_an_id_not_in_the_table_caches_nothing(table):
    assert 4711 not in table and table.get(4711) is None
    assert 4711 not in table._read


def test_threads_reading_one_row_get_the_same_object(table):
    with ThreadPoolExecutor(8) as pool:
        rows = list(pool.map(lambda _: table[171], range(64)))
    assert all(row is rows[0] for row in rows)


def test_rows_without_an_id_and_repeated_ids_are_warned_once_per_table(caplog):
    units = [
        {"wodID": "1", "type": "A"},
        {"type": "NoId"},
        {"wodID": "x", "type": "Bad"},
        "junk",
        {"wodID": "1", "type": "B"},
    ]
    with caplog.at_level(logging.WARNING, logger="empire_core.gamedata.data"):
        data = GameData.parse("786.03", {"units": units})

    assert data.units[1].unit_type == "B"
    assert [r.getMessage() for r in caplog.records] == [
        "units: left out 3 rows without a numeric wodID (None, 'x', 'junk')",
        "units: 1 ids have more than one row, the last is kept: 1",
    ]
