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

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from empire_core.enums import SpyArmySection
from empire_core.gamedata import WodAmount, wod_amount_pairs


def _stacks(value: Any) -> Any:
    """
    One position's stacks, read as the client reads them.

    Client: ``AUnitInventory.fillFromWodAmountArray`` (bundle line 42572) into a
    ``UnitInventoryList``, whose ``addUnit`` skips an amount of 0 or less and
    appends without adding up an id sent twice (bundle line 21826).
    """
    if isinstance(value, tuple) and all(isinstance(stack, WodAmount) for stack in value):
        return value
    return tuple(WodAmount(wod_id, amount) for wod_id, amount in wod_amount_pairs(value) if amount > 0)


SpyStacks = Annotated[tuple[WodAmount, ...], BeforeValidator(_stacks)]
"""One position of a spied army: its stacks in the order sent, an id sent twice kept twice."""


class SpyArmy(BaseModel):
    """
    A spied castle's defenders, by the position they hold.

    Reads a report's ``S`` block: ``SpyArmy.model_validate(report_s)``. A block shorter
    than the full seven positions is normal (the server omits trailing ones), so a
    missing position is empty.

    Client: ``CastleSpyArmyInfoVO.parseArmyInfo`` (bundle line 30699)
    """

    model_config = ConfigDict(frozen=True)

    left: SpyStacks = Field(default=(), description="Defenders on the left wall flank")
    middle: SpyStacks = Field(default=(), description="Defenders on the middle wall flank")
    right: SpyStacks = Field(default=(), description="Defenders on the right wall flank")
    keep: SpyStacks = Field(default=(), description="Defenders in the keep (courtyard)")
    stronghold: SpyStacks = Field(default=(), description="Units in the stronghold")
    support: SpyStacks = Field(default=(), description="Alliance support, which holds every flank")
    reserve: SpyStacks = Field(default=(), description="The reserve, when the report lists one")

    @model_validator(mode="before")
    @classmethod
    def _by_position(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        return {section.value: data[index] for index, section in enumerate(SpyArmySection) if index < len(data)}

    def section(self, section: SpyArmySection) -> tuple[WodAmount, ...]:
        """The stacks at one position."""
        stacks: tuple[WodAmount, ...] = getattr(self, section.value)
        return stacks

    def sections(self) -> list[tuple[SpyArmySection, tuple[WodAmount, ...]]]:
        """Every position in wire order, for display."""
        return [(section, self.section(section)) for section in SpyArmySection]

    def total(self) -> int:
        """Every defender in the castle, wherever they stand."""
        return sum(stack.amount for _, stacks in self.sections() for stack in stacks)

    def wall_total(self) -> int:
        """Defenders on the wall: the flanks an attack meets first."""
        return sum(stack.amount for section in SpyArmySection if section.is_wall for stack in self.section(section))


def _spied(value: Any) -> Any:
    # Client: parseArmyInfo reads the positions only when e && 0 != e.length
    return value if value else None


SpyArmyBlock = Annotated[SpyArmy | None, BeforeValidator(_spied)]
"""A reply's ``S`` block as a :class:`SpyArmy`, None when it is missing or empty (no spy report)."""


__all__ = ["SpyArmy", "SpyArmyBlock", "SpyStacks"]
