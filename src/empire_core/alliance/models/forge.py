"""The alliance forge, which crafts an equipment item or a gem.

Commands:
- frc: Craft in the alliance forge
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field, field_serializer, field_validator, model_validator

from empire_core.commanders.models.equipment import Equipment, RelicGem
from empire_core.commanders.models.inventory import InventorySpace
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.protocol.js import js_int, js_truthy

from .info import AllianceInfo, alliance_of_ain

if TYPE_CHECKING:
    from empire_core.gamedata import Gem

RELIC_FORGE_MIN_LEGEND_LEVEL = 1
"""The legend level from which the relic forge replaces the alliance forge.

Client: ``AllianceForgeConst.MINIMUM_LEGEND_LEVEL_FOR_RELIC_ALLIANCE_FORGE`` (dll line 18812), read by
``CastleAllianceDialog`` when the forge tab opens (bundle line 4911)
"""


def relic_forge_coin_cost(uses: int) -> int:
    """Coins the relic forge asks after ``uses`` coin crafts today.

    Client: ``AllianceForgeConst.calculateC1CostForSoftCurrencyRelicAllianceForge`` (dll line 18808)
    """
    return int(6e4 * 1.5**uses)


def relic_forge_ruby_cost(uses: int) -> int:
    """Rubies the relic forge asks after ``uses`` ruby crafts today.

    Client: ``AllianceForgeConst.calculateC2CostForHardCurrencyRelicAllianceForge`` (dll line 18809)
    """
    return int(1e4 * 1.25**uses)


class ForgeCraftRequest(BaseRequest):
    """
    Craft in the alliance forge.

    Command: frc
    Payload: {"UPRAF": 0 or 1}

    Client: ``C2SRequestForgeCraftVO`` (bundle line 45133), sent with 0 by
    ``CastleAllianceDialogForge.onCraftButtonPressed`` (bundle line 45116) and with 1 for a ruby
    payment, else 0, by ``CastleAllianceDialogForgeHigh.onCraftButtonPressed`` (bundle line 69578)
    """

    command = "frc"

    pay_with_rubies: bool = Field(
        validation_alias="UPRAF", default=False, description="Pay the relic forge in rubies instead of coins"
    )

    @field_serializer("pay_with_rubies")
    def _flag(self, value: bool) -> int:
        return int(value)


class ForgeCraftResponse(BaseResponse):
    """
    What the forge crafted, with the alliance and your inventory space after.

    Command: frc
    Payload: {"ain": {"A": {...}}, "E": [...]} or {"ain": ..., "GEM": gem_id} or {"ain": ..., "RGEM": [...]},
    with "esl"

    Client: ``FRCCommand.executeCommand`` (bundle line 123955): ``ain.A`` fills your alliance, an ``E`` is an
    equipment item (``CastleEquipmentData.parse_FRC``, bundle line 143849), else ``RGEM`` a relic gem or
    ``GEM`` a gem (``CastleGemData.parse_FRC``, bundle line 144434)
    """

    command = "frc"

    alliance: AllianceInfo = Field(validation_alias="ain", description="Your alliance after the craft")
    equipment: Equipment | None = Field(
        validation_alias="E", default=None, description="The crafted equipment item; None for a gem"
    )
    relic_gem: RelicGem | None = Field(
        validation_alias="RGEM", default=None, description="The crafted relic gem; None otherwise"
    )
    gem_id: EnumOrInt["Gem"] | None = Field(
        validation_alias="GEM", default=None, description="The crafted gem; None otherwise"
    )
    inventory_space: InventorySpace | None = Field(
        validation_alias="esl", default=None, description="Your inventory space after the craft"
    )

    @field_validator("alliance", mode="before")
    @classmethod
    def _alliance(cls, value: Any) -> Any:
        return value if isinstance(value, AllianceInfo) else alliance_of_ain(value)

    @field_validator("equipment", "relic_gem", "inventory_space", mode="before")
    @classmethod
    def _truthy(cls, value: Any) -> Any:
        return value if js_truthy(value) else None

    @field_validator("gem_id", mode="before")
    @classmethod
    def _gem(cls, value: Any) -> Any:
        return js_int(value) if js_truthy(value) else None

    @model_validator(mode="after")
    def _one_item(self) -> ForgeCraftResponse:
        # The client reads a gem only without an equipment item, and a gem only without a relic gem
        if self.equipment is not None:
            self.relic_gem = self.gem_id = None
        elif self.relic_gem is not None:
            self.gem_id = None
        return self


__all__ = [
    "RELIC_FORGE_MIN_LEGEND_LEVEL",
    "ForgeCraftRequest",
    "ForgeCraftResponse",
    "relic_forge_coin_cost",
    "relic_forge_ruby_cost",
]
