"""
The JavaScript conversions the game client applies to reply values.

The client reads most values through its own ``int()``, through ``parseInt``,
through ``!!value`` or by comparing them loosely (``1 == value``). Each helper
here reproduces one of them for the JSON values a reply can carry.
"""

from __future__ import annotations

import math
import re
from typing import Annotated, Any

from pydantic import BeforeValidator

from .base import js_number_text as _number_text

_JS_WHITESPACE = "\t\n\v\f\r                  　﻿"
_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_RADIX_LITERAL = re.compile(r"0(?:([xX][0-9A-Fa-f]+)|([oO][0-7]+)|([bB][01]+))")
_LEADING_INT = re.compile(r"([+-]?)(?:0[xX]([0-9A-Fa-f]*)|([0-9]+))")
_FLOAT_BOUND = 2**1024  # An int this large is Infinity as a JS number
_EXACT_FLOAT_BOUND = 2**53  # Every int below this is exactly a float


def _text(value: Any) -> str:
    """``String(value)`` for a JSON value."""
    if isinstance(value, str):
        return value
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value) if abs(value) < 10**21 else _number_text(float(value))
    if isinstance(value, float):
        return _number_text(value)
    if isinstance(value, (list, tuple)):
        return ",".join("" if entry is None else _text(entry) for entry in value)
    return "[object Object]"


def js_string(value: Any) -> str:
    """``String(value)``: a number as JavaScript writes it, an object as ``[object Object]``."""
    return _text(value)


def _number(value: Any) -> float:
    """``Number(value)`` for a JSON value, None read as ``undefined`` (NaN)."""
    if value is None:
        return math.nan
    if isinstance(value, (bool, float)):
        return float(value)
    if isinstance(value, int):
        try:
            return float(value)
        except OverflowError:
            return math.inf if value > 0 else -math.inf
    if isinstance(value, (list, tuple)):
        return _number(_text(value))
    if not isinstance(value, str):
        return math.nan
    text = value.strip(_JS_WHITESPACE)
    if not text:
        return 0.0
    if radix := _RADIX_LITERAL.fullmatch(text):
        hex_digits, octal_digits, binary_digits = radix.groups()
        if hex_digits:
            return float(int(hex_digits[1:], 16))
        return float(int(octal_digits[1:], 8)) if octal_digits else float(int(binary_digits[1:], 2))
    if text in ("Infinity", "+Infinity", "-Infinity"):
        return -math.inf if text[0] == "-" else math.inf
    return float(text) if _DECIMAL.fullmatch(text) else math.nan


def js_int(value: Any) -> int:
    """
    The client's ``int()``: a ``#rrggbb`` string as hex, else ``Math.trunc(Number(value))``, NaN as 0.

    An infinity, which no int holds, reads as 0.

    Client: ``int`` (dll line 16098)
    """
    if type(value) is int:
        return value
    if isinstance(value, str) and _HEX_COLOR.fullmatch(value):
        return int(value[1:], 16)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    number = _number(value)
    return 0 if math.isnan(number) or math.isinf(number) else math.trunc(number)


def js_number(value: Any) -> float:
    """``Number(value)``, NaN and infinities as 0."""
    if type(value) is int and -_EXACT_FLOAT_BOUND < value < _EXACT_FLOAT_BOUND:
        return float(value)
    number = _number(value)
    return 0.0 if math.isnan(number) or math.isinf(number) else number


def js_number_or_none(value: Any) -> int | float | None:
    """``Number(value)``, None read as ``undefined``; None where it gives NaN or an infinity, an int kept as is."""
    if isinstance(value, int) and not isinstance(value, bool) and -_FLOAT_BOUND < value < _FLOAT_BOUND:
        return value
    number = _number(value)
    return None if math.isnan(number) or math.isinf(number) else number


def js_same_number(value: Any, expected: int) -> bool:
    """Whether ``Number(value)`` is ``expected``; ``633.0`` is 633."""
    return js_number_or_none(value) == expected


def row_is_at(row: Any, x: int, y: int) -> bool:
    """Whether a map row ``[area_type, x, y, ...]`` lies at ``(x, y)``."""
    return isinstance(row, list) and len(row) >= 3 and js_same_number(row[1], x) and js_same_number(row[2], y)


def movement_targets(wrapper: Any, x: int, y: int) -> bool:
    """Whether a movement wrapper's target area row (``M.TA``), when it has one, lies at ``(x, y)``."""
    movement = wrapper.get("M") if isinstance(wrapper, dict) else None
    row = movement.get("TA") if isinstance(movement, dict) else None
    return not (isinstance(row, list) and len(row) >= 3) or row_is_at(row, x, y)


def js_floor(value: Any) -> int:
    """``Math.floor(Number(value))``, NaN and infinities as 0."""
    return math.floor(js_number(value))


def js_parse_int(value: Any) -> int | None:
    """
    JavaScript's ``parseInt(value)``: the leading integer of ``String(value)``, None where it gives NaN.

    ``"12abc"`` reads as 12, ``"1e3"`` as 1 and ``"0x1A"`` as 26.
    """
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) < 10**21:
        return value
    match = _LEADING_INT.match(_text(value).lstrip(_JS_WHITESPACE))
    if not match or not (match[2] or match[3]):
        return None
    number = int(match[2], 16) if match[2] else int(match[3])
    return -number if match[1] == "-" else number


def js_parse_int_or_zero(value: Any) -> int:
    """:func:`js_parse_int` with NaN read as 0."""
    parsed = js_parse_int(value)
    return 0 if parsed is None else parsed


def js_truthy(value: Any) -> bool:
    """JavaScript's ``!!value``: false only for null, false, 0, NaN and ``""``."""
    if value is None or isinstance(value, (bool, str)):
        return bool(value)
    if isinstance(value, (int, float)):
        return value != 0 and not math.isnan(value)
    return True


def js_falsy(value: Any) -> bool:
    """JavaScript's ``!value``."""
    return not js_truthy(value)


def js_loose_equals(value: Any, number: float) -> bool:
    """
    JavaScript's ``number == value``, as the client compares a reply value with a literal.

    null never equals a number; anything else is compared as ``Number(value)``,
    so ``"1"``, ``"1.0"``, ``true`` and ``[1]`` all equal 1, and ``""`` equals 0.
    """
    if value is None:
        return False
    if isinstance(value, (bool, int, float, str, list, tuple)):
        return _number(value) == number
    return False


ClientInt = Annotated[int, BeforeValidator(js_int)]
"""An int read through the client's ``int()``."""

ParseInt = Annotated[int, BeforeValidator(js_parse_int_or_zero)]
"""An int read through ``parseInt``, NaN as 0."""


def _number_or_zero(value: Any) -> int | float:
    number = js_number_or_none(value)
    return 0 if number is None else number


ClientNumber = Annotated[int | float, BeforeValidator(_number_or_zero)]
"""A number read through ``Number()``, an int kept as is; NaN and infinities as 0, as a time the client counts down."""


__all__ = [
    "ClientInt",
    "ClientNumber",
    "ParseInt",
    "js_falsy",
    "js_int",
    "js_loose_equals",
    "js_number_or_none",
    "js_same_number",
    "movement_targets",
    "row_is_at",
    "js_parse_int",
    "js_parse_int_or_zero",
    "js_truthy",
]
