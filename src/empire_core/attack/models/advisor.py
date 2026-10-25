"""The attack advisor: activating it for an event and its summary of the attacks it sent.

Commands:
- aa: Activate the attack advisor
- aao: The attack advisor's overview
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from empire_core.enums import AttackAdvisorType
from empire_core.gamedata import CollectableRows, EnumOrInt
from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.protocol.js import ClientInt, js_truthy

# =============================================================================
# AA - Activate the attack advisor
# =============================================================================


class ActivateAttackAdvisorRequest(BaseRequest):
    """
    Activate an attack advisor, using one of its activation tokens.

    Command: aa
    Payload: {"AAT": advisor}
    Client: ``C2SActivateAttackAdvisorVO`` (bundle line 101534), sent by
    ``AdvisorAttackActivationComponent.onClick`` (bundle line 56251), whose activate button shows
    only while you hold the advisor's activation currency (bundle line 56237)
    """

    command = "aa"

    advisor: EnumOrInt[AttackAdvisorType] = Field(validation_alias="AAT", description="The advisor to activate")


class ActivateAttackAdvisorResponse(BaseResponse):
    """
    The advisor now active.

    Command: aa
    Client: ``AACommand.executeCommand`` (bundle line 121193), which reads a missing ``AAT`` as the nomad advisor
    """

    command = "aa"

    advisor: EnumOrInt[AttackAdvisorType] = Field(
        validation_alias="AAT", default=AttackAdvisorType.NOMAD, description="The advisor activated"
    )

    @field_validator("advisor", mode="before")
    @classmethod
    def _missing_is_nomad(cls, value: Any) -> Any:
        return value if js_truthy(value) else AttackAdvisorType.NOMAD


# =============================================================================
# AAO - Attack advisor overview
# =============================================================================


class AttackAdvisorOverviewRequest(BaseRequest):
    """
    Ask for the attack advisor's summary of the attacks it sent.

    Command: aao
    Payload: {"AAT": advisor}
    Client: ``C2SAdvisorAttackOverviewVO`` (bundle line 105059), sent by
    ``AdvisorAttackOverviewDialog.onMovementsUpdated`` (bundle line 57305)
    """

    command = "aao"

    advisor: EnumOrInt[AttackAdvisorType] = Field(validation_alias="AAT", description="The advisor to sum up")


class AttackAdvisorOverviewResponse(BaseResponse):
    """
    What the attack advisor's attacks won and cost.

    Command: aao
    Client: ``AAOCommand.executeCommand`` (bundle line 121210), ``AdvisorAttackOverviewVO.parseServerData``
    (bundle line 60401), shown by ``AdvisorAttackOverviewComponent.update`` (bundle line 57363)
    """

    command = "aao"

    advisor: EnumOrInt[AttackAdvisorType] = Field(
        validation_alias="AAT", default=AttackAdvisorType.NONE, description="The advisor summed up"
    )
    gained: CollectableRows = Field(validation_alias="G", default=(), description="Loot the attacks won")
    lost: CollectableRows = Field(validation_alias="L", default=(), description="Currencies the attacks cost")
    lost_units: ClientInt = Field(validation_alias="LU", default=0, description="Soldiers lost")
    lost_tools: ClientInt = Field(validation_alias="LT", default=0, description="Tools lost")
    wins: ClientInt = Field(validation_alias="W", default=0, description="Attacks won")
    defeats: ClientInt = Field(validation_alias="D", default=0, description="Attacks lost")
    stopped: ClientInt = Field(validation_alias="P", default=0, description="Attacks not sent")
    commanders: ClientInt = Field(validation_alias="C", default=0, description="Commanders the advisor used")
    gallantry_points: ClientInt = Field(
        validation_alias="GP", default=0, description="Gallantry points won, for the Berimond advisor"
    )


__all__ = [
    "ActivateAttackAdvisorRequest",
    "ActivateAttackAdvisorResponse",
    "AttackAdvisorOverviewRequest",
    "AttackAdvisorOverviewResponse",
]
