"""
The equipment and gem inventory, as the login data and its pushes send it.

Commands:
- ggm: the gems and relic gems you hold (gec: a change to the gems)
- esl: the equipment and gem inventory space
- nrf: whether new relics wait to be seen
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

from pydantic import BeforeValidator, ConfigDict, Field, field_validator

from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, ParseInt, js_int, js_loose_equals

from .equipment import RelicGem

if TYPE_CHECKING:
    from empire_core.gamedata import Gem


class GemStack(BasePayload):
    """How many of one gem you hold."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    gem_id: EnumOrInt["Gem"] = Field(description="The gem")
    amount: int = Field(description="How many you hold")


def _gem_counts(counts: dict[int, int], rows: Any) -> dict[int, int]:
    # Each [gem_id, amount] adds that many, a negative amount takes away from what is held
    if not isinstance(rows, list):
        return counts
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        gem_id, amount = js_int(row[0]), js_int(row[1])
        if amount > 0:
            counts[gem_id] = counts.get(gem_id, 0) + amount
        elif amount < 0 and gem_id in counts:
            counts[gem_id] = max(0, counts[gem_id] + amount)
    return {gem_id: amount for gem_id, amount in counts.items() if amount > 0}


def _stacks(counts: dict[int, int]) -> tuple[GemStack, ...]:
    return tuple(GemStack(gem_id=gem_id, amount=amount) for gem_id, amount in counts.items())


class GemInventoryResponse(BaseResponse):
    """
    The gems and relic gems in your inventory, not set in any equipment.

    Command: ggm, as a login section of ``gbd`` and a reply. A ``gec`` push changes the gems;
    ``client.state.get_gems()`` applies it with :meth:`changed`.

    Client: ``GGMCommand`` (bundle line 123957), ``CastleGemData.parseGGM``, ``updateInventory`` and
    ``updateRelicInventory`` (bundle lines 144327, 144334, 144427); ``GECCommand`` (bundle line 123927) and
    ``parse_GEC`` (bundle line 144326). The client keeps one entry per gem and takes a negative amount
    off from the first entry of that gem on; here the gems are counted per id.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "ggm"

    gems: tuple[GemStack, ...] = Field(
        validation_alias="GEM", serialization_alias="GEM", default=(), description="The gems you hold, per gem id"
    )
    relic_gems: Annotated[tuple[RelicGem, ...], BeforeValidator(partial(readable_list, RelicGem))] = Field(
        validation_alias="RGEM", serialization_alias="RGEM", default=(), description="The relic gems you hold"
    )

    @field_validator("gems", mode="before")
    @classmethod
    def _gems(cls, value: Any) -> Any:
        return _stacks(_gem_counts({}, value)) if isinstance(value, list) else value

    def amount(self, gem_id: int) -> int:
        """How many of a gem you hold."""
        return next((stack.amount for stack in self.gems if stack.gem_id == gem_id), 0)

    def changed(self, rows: Any) -> GemInventoryResponse:
        """This inventory after a ``gec``'s ``GEM`` rows: ``[gem_id, amount]``, a negative amount taken away."""
        counts = _gem_counts({stack.gem_id: stack.amount for stack in self.gems}, rows)
        return self.model_copy(update={"gems": _stacks(counts)})


class InventorySpace(BasePayload):
    """
    Free and total space in the equipment and gem inventory.

    Not a response model: its ``E`` is the equipment space, not an error code.

    Command: esl, as a login section of ``gbd``, a push and a reply, and inside the ``bgm``, ``ceq``,
    ``cge``, ``frc`` and ``seq`` replies.

    Client: ``ESLCommand`` (bundle line 123895), ``CastleEquipmentData.parse_ESL`` (bundle line 143746) and
    ``CastleGemData.parse_ESL`` (bundle line 144410). The client recounts the free gem space from the total
    and the gems it holds whenever they change (``updateInventorySpace``, bundle line 144417); ``gem_space``
    is the value the server sent. The equipment inventory counts as full at ``equipment_space`` 0 or
    less, and holds ``equipment_total_space - equipment_space`` items (``isInventoryFull`` and
    ``filledInventorySpace``, bundle lines 143839, 143841).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    equipment_space: ParseInt = Field(
        validation_alias="E",
        serialization_alias="E",
        default=0,
        description="Free equipment inventory space; negative when you hold more than fits, full at 0 or less",
    )
    equipment_total_space: ParseInt = Field(
        validation_alias="TE", serialization_alias="TE", default=0, description="Total equipment inventory space"
    )
    gem_space: ClientInt = Field(
        validation_alias="G", serialization_alias="G", default=0, description="Free gem inventory space, as sent"
    )
    gem_total_space: ClientInt = Field(
        validation_alias="TG", serialization_alias="TG", default=0, description="Total gem inventory space"
    )


class NewRelicsResponse(BaseResponse):
    """
    Whether new relic equipment waits to be seen.

    Command: nrf, as a login section of ``gbd`` and a push.

    Client: ``NRFCommand`` (bundle line 124002), ``CastleEquipmentData.parseNRF`` (bundle line 143756)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "nrf"

    has_new_relics: bool = Field(
        validation_alias="NR", serialization_alias="NR", default=False, description="Whether new relics wait to be seen"
    )

    @field_validator("has_new_relics", mode="before")
    @classmethod
    def _flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)


__all__ = ["GemInventoryResponse", "GemStack", "InventorySpace", "NewRelicsResponse"]
