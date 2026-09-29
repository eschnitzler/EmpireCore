"""The shared readers that let one unreadable entry or block cost only itself."""

import logging

import pytest
from pydantic import Field

from empire_core.protocol.models.base import (
    BasePayload,
    CurrencyTotals,
    list_or_empty,
    object_or_none,
    read_or_none,
    readable_list,
)
from empire_core.protocol.models.movement import MovementSpy, MovementWrapper

logger = logging.getLogger("tests.readers")


class Row(BasePayload):
    row_id: int = Field(alias="ID")


class TestReadableList:
    @pytest.mark.parametrize("value", [None, {}, "rows", 3])
    def test_anything_but_an_array_is_no_rows(self, value):
        assert readable_list(Row, value) == []

    def test_an_unreadable_entry_costs_only_itself(self):
        rows = readable_list(Row, [{"ID": 1}, {"ID": "x"}, None, {"ID": 3}])
        assert [row.row_id for row in rows] == [1, 3]

    def test_a_model_instance_is_kept(self):
        row = Row(ID=2)
        assert readable_list(Row, [row]) == [row]

    def test_accept_and_parse(self):
        rows = readable_list(Row, [[4], {"ID": 5}], accept=lambda e: isinstance(e, list), parse=lambda e: Row(ID=e[0]))
        assert [row.row_id for row in rows] == [4]

    def test_unreadable_entries_are_counted_once_with_the_first_shown(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tests.readers"):
            readable_list(Row, [{"ID": 1}, {"ID": "x"}, {"ID": "y"}, None], warn=logger, what="test rows")
        assert caplog.text.count("Skipped 2/4 unreadable test rows, first: {'ID': 'x'}") == 1

    def test_null_and_unkept_entries_are_skipped_quietly(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tests.readers"):
            rows = readable_list(Row, [{"ID": 1}, None, {"ID": 0}], keep=lambda e: e["ID"], warn=logger)
        assert [row.row_id for row in rows] == [1]
        assert caplog.text == ""

    def test_unaccepted_entries_count_as_unreadable(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tests.readers"):
            rows = readable_list(Row, [{"ID": 1}, 5], accept=lambda e: isinstance(e, dict), warn=logger)
        assert [row.row_id for row in rows] == [1]
        assert "Skipped 1/2 unreadable entries, first: 5" in caplog.text

    def test_nothing_is_logged_without_skips(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tests.readers"):
            readable_list(Row, [{"ID": 1}], warn=logger)
        assert caplog.text == ""


class TestReadOrNone:
    def test_a_readable_block(self):
        row = read_or_none(Row.model_validate, {"ID": 1})
        assert row is not None and row.row_id == 1

    def test_an_unreadable_block_is_none_and_logged(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tests.readers"):
            assert read_or_none(Row.model_validate, {"ID": "x"}, warn=logger, what="the row") is None
        assert "Could not read the row" in caplog.text


class TestBlockGuards:
    @pytest.mark.parametrize(
        ("value", "expected"), [({}, {}), ({"a": 1}, {"a": 1}), ([], None), ("x", None), (0, None)]
    )
    def test_object_or_none(self, value, expected):
        assert object_or_none(value) == expected

    def test_object_or_none_keeps_a_model(self):
        totals = CurrencyTotals(C1=5)
        assert object_or_none(totals) is totals

    def test_a_block_built_by_name_is_kept(self):
        spy = MovementSpy.model_validate({})
        assert MovementWrapper.model_validate({"M": {"MID": 1}, "S": spy}).spy is spy

    @pytest.mark.parametrize(("value", "expected"), [([1], [1]), ([], []), ({}, []), (None, []), ("ab", [])])
    def test_list_or_empty(self, value, expected):
        assert list_or_empty(value) == expected
