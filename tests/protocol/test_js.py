"""
The client's JavaScript conversions.

Every expectation below is what node prints for the same value: ``int`` is the
client's own function (dll line 16098) run verbatim, the rest are
``parseInt(v)``, ``!!v``, ``1 == v`` and ``0 == v``. Two readings cannot match
node: NaN from ``parseInt`` is None here, and an infinity from ``int()``, which
no Python int holds, is 0.
"""

import math
from typing import Any

import pytest

from empire_core.protocol.js import (
    _text,
    js_falsy,
    js_int,
    js_loose_equals,
    js_number,
    js_number_or_none,
    js_parse_int,
    js_parse_int_or_zero,
    js_truthy,
)

# (value, int(v), parseInt(v), !!v, 1 == v, 0 == v)
CASES: list[tuple[Any, int, int | None, bool, bool, bool]] = [
    (None, 0, None, False, False, False),
    (True, 1, None, True, True, False),
    (False, 0, None, False, False, True),
    (0, 0, 0, False, False, True),
    (1, 1, 1, True, True, False),
    (-1, -1, -1, True, False, False),
    (1.5, 1, 1, True, False, False),
    (1.9, 1, 1, True, False, False),
    (-1.9, -1, -1, True, False, False),
    (0.5, 0, 0, True, False, False),
    (1.0, 1, 1, True, True, False),
    (float("nan"), 0, None, False, False, False),
    (float("inf"), 0, None, True, False, False),
    (float("-inf"), 0, None, True, False, False),
    (1e21, 1000000000000000000000, 1, True, False, False),
    (1e-07, 0, 1, True, False, False),
    (123456789.5, 123456789, 123456789, True, False, False),
    ("", 0, None, False, False, True),
    (" ", 0, None, True, False, True),
    ("0", 0, 0, True, False, True),
    ("1", 1, 1, True, True, False),
    ("-0", 0, 0, True, False, True),
    (" 12 ", 12, 12, True, False, False),
    (" 12abc", 0, 12, True, False, False),
    ("12abc", 0, 12, True, False, False),
    ("abc", 0, None, True, False, False),
    ("1e3", 1000, 1, True, False, False),
    ("1E3", 1000, 1, True, False, False),
    ("0x1A", 26, 26, True, False, False),
    ("0X1a", 26, 26, True, False, False),
    ("-0x1A", 0, -26, True, False, False),
    ("0x", 0, None, True, False, False),
    ("0xg", 0, None, True, False, False),
    ("0b101", 5, 0, True, False, False),
    ("0o17", 15, 0, True, False, False),
    ("1_000", 0, 1, True, False, False),
    ("Infinity", 0, None, True, False, False),
    ("-Infinity", 0, None, True, False, False),
    ("infinity", 0, None, True, False, False),
    ("inf", 0, None, True, False, False),
    ("NaN", 0, None, True, False, False),
    ("1.0", 1, 1, True, True, False),
    ("1.", 1, 1, True, True, False),
    (".5", 0, None, True, False, False),
    (".", 0, None, True, False, False),
    ("+5", 5, 5, True, False, False),
    ("-5", -5, -5, True, False, False),
    ("+-5", 0, None, True, False, False),
    ("5 6", 0, 5, True, False, False),
    ("1e", 0, 1, True, False, False),
    ("#ff0000", 16711680, None, True, False, False),
    ("#FF00FF", 16711935, None, True, False, False),
    ("#ff00zz", 0, None, True, False, False),
    ("#ff00001", 0, None, True, False, False),
    ("#ff0000\n", 0, None, True, False, False),
    ("\t\n 7 \u00a0", 7, 7, True, False, False),
    ("\ufeff7", 7, 7, True, False, False),
    ("\x1c7", 0, None, True, False, False),
    ("\u0085 7", 0, None, True, False, False),
    ("\u0661\u0662", 0, None, True, False, False),
    ("true", 0, None, True, False, False),
    ("1,2", 0, 1, True, False, False),
    ([], 0, None, True, False, True),
    ([5], 5, 5, True, False, False),
    (["7"], 7, 7, True, False, False),
    ([1, 2], 0, 1, True, False, False),
    ([[1]], 1, 1, True, True, False),
    ([None], 0, None, True, False, True),
    ([True], 0, None, True, False, False),
    ([1.5], 1, 1, True, False, False),
    ([[]], 0, None, True, False, True),
    ([" 1 "], 1, 1, True, True, False),
    ([float("inf")], 0, None, True, False, False),
    ({}, 0, None, True, False, False),
    ({"a": 1}, 0, None, True, False, False),
]

IDS = [repr(case[0]) for case in CASES]


@pytest.mark.parametrize(("value", "expected"), [(c[0], c[1]) for c in CASES], ids=IDS)
def test_js_int(value, expected):
    assert js_int(value) == expected


@pytest.mark.parametrize(("value", "expected"), [(c[0], c[2]) for c in CASES], ids=IDS)
def test_js_parse_int(value, expected):
    assert js_parse_int(value) == expected
    assert js_parse_int_or_zero(value) == (0 if expected is None else expected)


@pytest.mark.parametrize(("value", "expected"), [(c[0], c[3]) for c in CASES], ids=IDS)
def test_js_truthy(value, expected):
    assert js_truthy(value) is expected
    assert js_falsy(value) is (not expected)


@pytest.mark.parametrize(("value", "expected"), [(c[0], c[4]) for c in CASES], ids=IDS)
def test_js_loose_equals_one(value, expected):
    assert js_loose_equals(value, 1) is expected


@pytest.mark.parametrize(("value", "expected"), [(c[0], c[5]) for c in CASES], ids=IDS)
def test_js_loose_equals_zero(value, expected):
    assert js_loose_equals(value, 0) is expected


# node: [..].map(String)
@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (1e21, "1e+21"),
        (1.5e21, "1.5e+21"),
        (1e-7, "1e-7"),
        (1.5e-7, "1.5e-7"),
        (1e-6, "0.000001"),
        (0.000001234, "0.000001234"),
        (123.456, "123.456"),
        (1e16, "10000000000000000"),
        (9007199254740994.0, "9007199254740994"),
        (-1e-7, "-1e-7"),
        (5e-324, "5e-324"),
        (1.7976931348623157e308, "1.7976931348623157e+308"),
        (0.1 + 0.2, "0.30000000000000004"),
        (-0.0, "0"),
        (100.0, "100"),
        (1e20, "100000000000000000000"),
        (123456789012345680000.0, "123456789012345680000"),
        (math.nan, "NaN"),
        (-math.inf, "-Infinity"),
    ],
)
def test_number_text_matches_string(number, expected):
    assert _text(number) == expected


# node: [..].map(v => parseInt(v))
@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (1e21, 1),
        (1.5e21, 1),
        (1e-7, 1),
        (1.5e-7, 1),
        (1e-6, 0),
        (0.000001234, 0),
        (-1e-7, -1),
        (5e-324, 5),
        (1.7976931348623157e308, 1),
        (0.1 + 0.2, 0),
        (1e20, 100000000000000000000),
        (123456789012345680000.0, 123456789012345680000),
    ],
)
def test_parse_int_reads_a_float_through_its_text(number, expected):
    assert js_parse_int(number) == expected


@pytest.mark.parametrize(
    ("value", "expected"), [("0x10", 16.0), ("1.5", 1.5), ("x", 0.0), (None, 0.0), ("Infinity", 0.0)]
)
def test_js_number(value, expected):
    assert js_number(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0x10", 16.0), ("1.5", 1.5), ("x", None), (None, None), ("Infinity", None), ("", 0.0), (7, 7), (True, 1.0)],
)
def test_js_number_or_none(value, expected):
    assert js_number_or_none(value) == expected


def test_huge_int_compares_without_overflow():
    assert js_loose_equals(2**1024 - 2**969, 1) is False
    assert js_loose_equals(10**400, 1) is False


@pytest.mark.parametrize("value", [0, -1, 2**53 - 1, -(2**53) + 1, 2**53, 2**70, -(2**70), 2**1023 + 2**1000])
def test_js_number_reads_an_int_as_its_float(value):
    assert js_number(value) == float(value) and type(js_number(value)) is float


def test_js_number_reads_an_int_too_large_for_a_number_as_zero():
    assert js_number(2**1024 - 1) == 0.0
    assert js_number(-(10**400)) == 0.0


def test_js_number_or_none_reads_an_int_too_large_for_a_number_as_none():
    assert js_number_or_none(10**400) is None
    assert js_number_or_none(-(10**400)) is None
