"""Positional army data from a spy report.

The report's ``S`` block is consumed positionally by the game client
(``CastleSpyArmyInfoVO.parseArmyInfo``), which shifts one entry per position in
this order:

    left, middle, right, keep, stronghold, support, reserve (optional)

Each entry is a list of ``[wod_id, amount]`` pairs. Summing the whole block
flattens the three wall flanks together with keep, stronghold, support and
reserve troops — a number the game never shows and which says nothing about
where a castle is actually strong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Order matters: it is the wire order the client relies on.
SECTION_NAMES = ("left", "middle", "right", "keep", "stronghold", "support", "reserve")

# The flanks an attack on the wall actually meets.
WALL_SECTIONS = ("left", "middle", "right")


@dataclass(frozen=True)
class UnitStack:
    """A count of one unit type at one position."""

    wod_id: int
    count: int


def _stacks(entry: Any) -> list[UnitStack]:
    """Parse one position, skipping anything that is not a [wod_id, amount] pair.

    A drifted or truncated stack costs its own entry, never the whole report.
    """
    if not isinstance(entry, list):
        return []
    stacks = []
    for pair in entry:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        wod_id, count = pair[0], pair[1]
        if isinstance(wod_id, int) and isinstance(count, int):
            stacks.append(UnitStack(wod_id, count))
    return stacks


@dataclass
class SpyArmy:
    """A spied castle's defenders, by the position they hold."""

    left: list[UnitStack] = field(default_factory=list)
    middle: list[UnitStack] = field(default_factory=list)
    right: list[UnitStack] = field(default_factory=list)
    keep: list[UnitStack] = field(default_factory=list)
    stronghold: list[UnitStack] = field(default_factory=list)
    support: list[UnitStack] = field(default_factory=list)
    reserve: list[UnitStack] = field(default_factory=list)

    @classmethod
    def from_spy_data(cls, spy_data: Any) -> "SpyArmy | None":
        """Split a report's ``S`` block by position, or None if it is unusable.

        A report shorter than the full seven positions is normal — the server
        omits trailing ones — so missing sections stay empty.
        """
        if not isinstance(spy_data, list):
            return None
        sections = {
            name: _stacks(spy_data[index] if index < len(spy_data) else None)
            for index, name in enumerate(SECTION_NAMES)
        }
        return cls(**sections)

    def sections(self) -> list[tuple[str, list[UnitStack]]]:
        """Every position in wire order, for display."""
        return [(name, getattr(self, name)) for name in SECTION_NAMES]

    def total(self) -> int:
        """Every defender in the castle, wherever they stand."""
        return sum(stack.count for _, stacks in self.sections() for stack in stacks)

    def wall_total(self) -> int:
        """Defenders on the wall: the flanks an attack meets first."""
        return sum(stack.count for name in WALL_SECTIONS for stack in getattr(self, name))


__all__ = ["SECTION_NAMES", "WALL_SECTIONS", "SpyArmy", "UnitStack"]
