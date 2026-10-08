"""
Units and tools by amount: the ``[wod_id, amount]`` pairs of armies, inventories and container slots.

The client reads a ``[[wod_id, amount], ...]`` array two ways, and the types here follow it:

- slot by slot, keeping the order and an id that comes twice (attack waves, defense containers
  and the requests built from them): :data:`WodAmountSlots`, a tuple of :class:`WodAmount`
- into a unit inventory, which adds up an id that comes twice and drops amounts of 0 or less:
  :data:`WodAmounts`, ``{Unit or Tool: amount}``

Units and tools are rows of the one ``units`` items table, so an id is looked up as a ``Unit``,
then as a ``Tool`` (:data:`UnitOrTool`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from enum import Enum
from typing import TYPE_CHECKING, Annotated, Any, NamedTuple, Protocol, TypeAlias, runtime_checkable

from pydantic import BeforeValidator, PlainSerializer, TypeAdapter

from empire_core.protocol.js import js_int

from .lenient import EnumOrInt

if TYPE_CHECKING:
    from .ids import Tool, Unit

UnitOrTool: TypeAlias = EnumOrInt["Unit", "Tool"]
"""A ``units`` row's ``wodID``: the ``Unit`` member, else the ``Tool`` member, else the plain int."""

EMPTY_WOD_ID = -1
"""The wod id of an empty slot.

Client: ``CastleFightItemVO.getWodId`` (bundle line 12515) returns -1 for a slot without a unit
"""


def wod_amount_pairs(value: object) -> list[tuple[int, int]]:
    """
    ``[[wod_id, amount], ...]`` as ``(wod_id, amount)`` pairs, before any inventory adds them up.

    Client: ``AUnitInventory.fillFromWodAmountArray`` (bundle line 42572), which
    skips entries that are not arrays and reads ``int(i[0])``, ``int(i[1])``.
    """
    if not isinstance(value, list | tuple):
        return []
    return [
        (js_int(entry[0] if entry else None), js_int(entry[1] if len(entry) > 1 else None))
        for entry in value
        if isinstance(entry, list | tuple)
    ]


@runtime_checkable
class WodAmountMapping(Protocol):
    """
    Units and tools by amount, as a caller writes them: ``{Unit.SWORDMAN: 100, Tool.LADDER: 5}``.

    Any mapping does, keyed by ``Unit``, ``Tool``, both, or plain wod ids.
    """

    def items(self) -> AbstractSet[tuple[UnitOrTool, int]]: ...


def _wod_id(value: Any) -> Any:
    if value is None or isinstance(value, Enum):
        return value
    wod_id = js_int(value)
    return None if wod_id == EMPTY_WOD_ID else wod_id


class WodAmount(NamedTuple):
    """
    One ``[wod_id, amount]`` pair: a unit or tool and how many, or an empty container slot.

    A pair unpacks like the list it comes from, ``for unit, amount in flank.units``. Read from a
    packet, both places go through ``int()`` as in the client, and an empty slot's ``[-1, 0]``
    becomes ``item`` None, so it logs no unknown id; :data:`WodAmountSlots` writes it back as the
    same two-entry list.

    Build one as ``WodAmount(Unit.SWORDMAN, 100)``, or a whole container with :meth:`slots`.

    Client: ``CastleFightItemContainer.getSlotList`` (bundle line 20573) writes
    ``[getWodId(), getAmount()]`` per slot, -1 and 0 for an empty one (``CastleFightItemVO``,
    bundle lines 12515-12516); ``CastleFightItemContainer.fillFromParamArray`` (bundle line 20554)
    reads each pair with ``int()`` and skips a wod id of -1
    """

    item: Annotated[UnitOrTool | None, BeforeValidator(_wod_id)]
    """The unit or tool; None for an empty slot."""
    amount: Annotated[int, BeforeValidator(js_int)] = 0
    """How many."""

    @property
    def count(self) -> int:  # type: ignore[override]
        """Not the amount: read ``amount``. Raises, where ``tuple.count`` would quietly be a method."""
        raise AttributeError("WodAmount has no count; the number of units or tools is .amount")

    @classmethod
    def slots(cls, amounts: WodAmountMapping | Iterable[WodAmount | Sequence[int]]) -> tuple[WodAmount, ...]:
        """
        A container's slots, one per entry in order: ``WodAmount.slots({Unit.SWORDMAN: 100})``.

        Pairs, built or as ``[wod_id, amount]`` lists, are read as a packet's are, empty slots included.
        """
        if isinstance(amounts, WodAmountMapping):
            return tuple(cls(item, amount) for item, amount in amounts.items())
        return _SLOTS.validate_python(list(amounts))


EMPTY_SLOT = WodAmount(None, 0)
"""An empty container slot, ``[-1, 0]`` on the wire."""


def _slots(value: Any) -> Any:
    # Client: fillFromParamArray shift()s two places off each pair and ignores the rest; a place a short
    # pair lacks is int(undefined), 0, so [] holds no unit and reads as an empty slot
    if isinstance(value, Mapping):
        return WodAmount.slots(value)
    if not isinstance(value, list | tuple):
        return value
    return [[*slot, None, None][:2] if isinstance(slot, list) else slot for slot in value]


def _wire_pairs(slots: tuple[WodAmount, ...]) -> list[list[int]]:
    return [[EMPTY_WOD_ID if item is None else item, amount] for item, amount in slots]


WodAmountSlots = Annotated[tuple[WodAmount, ...], BeforeValidator(_slots), PlainSerializer(_wire_pairs)]
"""A container's ``[[wod_id, amount], ...]``, one pair per slot, in order, an id that comes twice
kept twice and an empty slot ``[-1, 0]``. A mapping is read as one slot per entry.

Client: ``CastleFightItemContainer.getSlotList`` / ``fillFromParamArray`` (bundle lines 20573, 20554)
"""

WodAmountSlotsInput: TypeAlias = "WodAmountMapping | Iterable[WodAmount | Sequence[int]]"
"""What a model with :data:`WodAmountSlots` fields takes when built: ``{Unit.SWORDMAN: 100}``,
``WodAmount`` slots, or ``[wod_id, amount]`` pairs."""

_SLOTS: TypeAdapter[tuple[WodAmount, ...]] = TypeAdapter(WodAmountSlots)


def _merged(value: Any) -> Any:
    """
    ``[[wod_id, amount], ...]`` as ``{wod_id: amount}``; a mapping is taken as it is.

    Client: :func:`wod_amount_pairs` into a ``UnitInventoryDictionary``: ``addUnit``
    clamps at 0, ``changeUnitAmount`` adds (bundle lines 5533-5535) and
    ``setUnit`` drops a total of 0 or less (bundle line 5538).
    """
    if isinstance(value, Mapping):
        return value
    totals: dict[int, int] = {}
    for wod_id, amount in wod_amount_pairs(value):
        totals[wod_id] = totals.get(wod_id, 0) + max(0, amount)
    return {wod_id: amount for wod_id, amount in totals.items() if amount > 0}


WodAmounts = Annotated[dict[UnitOrTool, int], BeforeValidator(_merged)]
"""A wod/amount array read as an inventory, ``{Unit or Tool: amount}``: an id sent twice adds up,
and an amount of 0 or less is dropped, as the client's unit inventories do."""


def _tool_slots(value: Any) -> Any:
    if not isinstance(value, list | tuple):
        return value
    return tuple(_wod_id(tool) for tool in value)


def _tool_ids(slots: tuple[Tool | int | None, ...]) -> list[int]:
    return [EMPTY_WOD_ID if tool is None else tool for tool in slots]


SupportToolSlots = Annotated[
    tuple[EnumOrInt["Tool"] | None, ...], BeforeValidator(_tool_slots), PlainSerializer(_tool_ids)
]
"""The support tools of an attack, one wod id per slot: None for an empty slot, -1 on the wire.

Client: ``CastleAttackInfoVO.toolsSupportWodIds`` (bundle lines 30678-30680) pushes each slot's
``wodId`` or -1; ``FightPresetVO.getSupportTools`` (bundle line 141847) defaults to ``[-1,-1,-1]``;
a movement's ``AST`` is read through ``int()`` (``CastleCompactArmyVO.parseSupportTools`` into
``fillFromWodAmountArray``, bundle lines 67526-67528, 42572), so ``"-1"`` and a missing entry are empty too
"""


__all__ = [
    "EMPTY_SLOT",
    "EMPTY_WOD_ID",
    "SupportToolSlots",
    "UnitOrTool",
    "WodAmount",
    "WodAmountMapping",
    "WodAmountSlots",
    "WodAmountSlotsInput",
    "WodAmounts",
    "wod_amount_pairs",
]
