"""
The hunter: how much of the castle's wood and stone production it turns into food.

Commands:
- hin: Set the hunter's food boost; the server answers, and a castle join's reply carries, the hunter's values
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.protocol.js import ClientNumber


class SetHunterRequest(BaseRequest):
    """
    Set the hunter's food boost (``hin``).

    Client: ``C2SHunterInfoVO`` (bundle line 85274), sent by ``CastleHunterDialog.onClick`` (bundle line 51530)
    with the slider's value, from 0 to the hunter building's ``hunterMax``
    """

    command: ClassVar[str] = "hin"

    food_boost: int = Field(validation_alias="FB", description="The food boost, from 0 to the hunter's maximum")


class HunterInfo(BaseResponse):
    """
    The hunter's values: its food boost and the wood and stone production that boost costs.

    Command: hin, as a reply and as a section of a castle join's ``jaa``.

    Client: ``HINCommand.executeCommand`` (bundle line 124591), ``JAACommand.executeCommand`` (bundle line
    130239) when its ``hin`` is set, ``CastleHunterData.parse_HIN`` (bundle line 25211)
    """

    command: ClassVar[str] = "hin"

    food_boost: ClientNumber = Field(validation_alias="FB", default=0, description="The food boost, 0 for none")
    wood_stone_reduction: ClientNumber = Field(
        validation_alias="WSR", default=0, description="How much the boost lowers wood and stone production"
    )

    @property
    def is_boosted(self) -> bool:
        """Whether the hunter boosts food at all."""
        return self.food_boost > 0


__all__ = ["HunterInfo", "SetHunterRequest"]
