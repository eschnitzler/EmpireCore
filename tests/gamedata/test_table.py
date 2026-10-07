"""A game-data table validates a row the first time it is read."""

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

    def spy(row):
        seen.append(row)
        return validate(row)

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
