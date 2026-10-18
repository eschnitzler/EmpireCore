"""Models, lists and dicts as indented Python-like text, one line when they fit."""

from enum import Enum
from typing import Any

from pydantic import BaseModel

INDENT = 4


def pretty(value: Any, *, width: int = 88, max_items: int = 50) -> str:
    return _render(value, 0, 0, width, max_items)


def _render(value: Any, indent: int, used: int, width: int, max_items: int) -> str:
    flat = _flat(value, max_items)
    parts = _parts(value, max_items)
    if parts is None or used + len(flat) <= width:
        return flat
    opener, closer, items, more = parts
    pad = " " * (indent + INDENT)
    lines = [opener]
    for label, child in items:
        lines.append(f"{pad}{label}{_render(child, indent + INDENT, len(pad) + len(label), width, max_items)},")
    if more:
        lines.append(f"{pad}… {more} more")
    lines.append(" " * indent + closer)
    return "\n".join(lines)


def _flat(value: Any, max_items: int) -> str:
    parts = _parts(value, max_items)
    if parts is None:
        return f"{type(value).__name__}.{value.name}" if isinstance(value, Enum) else repr(value)
    opener, closer, items, more = parts
    shown = [label + _flat(child, max_items) for label, child in items] + ([f"… {more} more"] if more else [])
    return opener + ", ".join(shown) + closer


def _parts(value: Any, max_items: int) -> tuple[str, str, list[tuple[str, Any]], int] | None:
    """How ``value`` opens and closes, its labelled children and how many were left out; None for a scalar."""
    if isinstance(value, BaseModel):
        fields = [(f"{name}=", getattr(value, name)) for name in type(value).model_fields]
        extra = [(f"{name}=", child) for name, child in (value.model_extra or {}).items()]
        return f"{type(value).__name__}(", ")", fields + extra, 0
    if isinstance(value, (list, tuple)):
        return "[", "]", [("", child) for child in value[:max_items]], max(len(value) - max_items, 0)
    if isinstance(value, dict):
        entries = list(value.items())
        shown = [(f"{key!r}: ", child) for key, child in entries[:max_items]]
        return "{", "}", shown, max(len(entries) - max_items, 0)
    return None
