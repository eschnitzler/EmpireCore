"""
The attack counter: past a threshold, every attack's travel costs more.

Commands:
- gai: the attack counter, a login section of ``gbd`` and a push
"""

from __future__ import annotations

import math

from pydantic import ConfigDict, Field

from empire_core.protocol.base import BaseResponse
from empire_core.protocol.js import ClientNumber


class AttackCounterResponse(BaseResponse):
    """
    Your recent attacks and the threshold past which their travel costs grow.

    Command: gai, as a login section of ``gbd`` and a push the client never asks for.

    Client: ``GAICommand`` (bundle line 122051), ``AttackCounterVO.parseParamObject`` (bundle line 65960),
    read by ``CastleAttackInfoVO.getTravelCost`` (bundle line 30651) and
    ``AttackDialogWaveHandler.fillAttackCosts`` (bundle line 102551)
    """

    model_config = ConfigDict(frozen=True)

    command = "gai"

    attack_count: ClientNumber = Field(alias="AC", default=0, description="Attacks counted")
    attack_count_threshold: ClientNumber = Field(
        alias="ACTH", default=0, description="Attacks counted before travel costs grow"
    )
    growth_rate: ClientNumber = Field(
        alias="ACGR", default=0, description="How fast the travel costs grow per attack past the threshold"
    )

    @property
    def travel_cost_surcharge(self) -> float:
        """
        The coins an attack costs on top, as a multiple of its travel cost before bonuses; 0 up to the threshold.

        Client: ``TravelConst.getAttackTravelCostC1`` (dll line 19839)
        """
        if self.attack_count <= self.attack_count_threshold:
            return 0.0
        return math.exp(self.growth_rate * (self.attack_count - self.attack_count_threshold)) - 1


__all__ = ["AttackCounterResponse"]
