"""
The JavaScript conversions the game client applies to reply values.

The client reads most values through its own ``int()``, through ``parseInt``,
through ``!!value`` or by comparing them loosely (``1 == value``). Each helper
here reproduces one of them for the JSON values a reply can carry.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BeforeValidator

_JS_WHITESPACE = "\t\n\v\f\r                  　﻿"
_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_RADIX_LITERAL = re.compile(r"0(?:([xX][0-9A-Fa-f]+)|([oO][0-7]+)|([bB][01]+))")
_LEADING_INT = re.compile(r"([+-]?)(?:0[xX]([0-9A-Fa-f]*)|([0-9]+))")


def _number_text(number: float) -> str:
    """``String(number)``: the ECMAScript ``Number::toString`` layout of the shortest round-trip digits."""
    if math.isnan(number):
        return "NaN"
    if math.isinf(number):
        return "Infinity" if number > 0 else "-Infinity"
    if number == 0:
        return "0"
    sign = "-" if number < 0 else ""
    _, digit_tuple, exponent = Decimal(repr(abs(number))).normalize().as_tuple()
    digits = "".join(map(str, digit_tuple))
    k, n = len(digits), len(digits) + int(exponent)
    if k <= n <= 21:
        return sign + digits + "0" * (n - k)
    if 0 < n <= 21:
        return sign + digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * -n + digits
    mantissa = digits[0] + ("." + digits[1:] if k > 1 else "")
    return f"{sign}{mantissa}e{'+' if n - 1 >= 0 else '-'}{abs(n - 1)}"


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
    if isinstance(value, str) and _HEX_COLOR.fullmatch(value):
        return int(value[1:], 16)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    number = _number(value)
    return 0 if math.isnan(number) or math.isinf(number) else math.trunc(number)


def js_number(value: Any) -> float:
    """``Number(value)``, NaN and infinities as 0."""
    number = _number(value)
    return 0.0 if math.isnan(number) or math.isinf(number) else number


def js_number_or_none(value: Any) -> int | float | None:
    """``Number(value)``, None read as ``undefined``; None where it gives NaN or an infinity, an int kept as is."""
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) < 2**1024:
        return value
    number = _number(value)
    return None if math.isnan(number) or math.isinf(number) else number


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


__all__ = [
    "ClientInt",
    "ParseInt",
    "js_falsy",
    "js_int",
    "js_loose_equals",
    "js_number_or_none",
    "js_parse_int",
    "js_parse_int_or_zero",
    "js_truthy",
]
