"""
Starting research and shortening it with a minute skip.

Commands:
- res: start a research
- msr: shorten the running research with a minute skip

Finishing a research at once for rubies (``C2SResearchFinishInstantVO``, bundle line 49093) is left out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from empire_core.castle.models.resources import CastleResources
from empire_core.gamedata import EnumOrInt, EnumOrStr
from empire_core.player.models.progress import ResearchInfoResponse
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock

if TYPE_CHECKING:
    from empire_core.gamedata import Currency, Research


class StartResearchRequest(BaseRequest):
    """
    Start a research, paying what it costs: resources and coins, or rubies for a research that costs them.

    Command: res
    Payload: {"RID": research_id, "PO": -1, "PWR": 0}

    ``PWR`` 1 would pay missing resources with rubies (``CastleResourceWaitDialogProperties.getResourceSkipCommand``,
    bundle line 35216); this request always sends 0. A research whose own costs hold rubies
    (``ResearchDef.cost_rubies``) is sent the same way and spends them; ``client.player.start_research``
    refuses it unless asked to spend rubies.

    Client: ``C2SResearchStartVO`` (bundle line 47697), sent by ``ResearchInfo.buyResearch`` (bundle line 79704)
    with the private offer -1 and ``PWR`` 0
    """

    command = "res"

    research_id: EnumOrInt["Research"] = Field(
        validation_alias="RID", serialization_alias="RID", description="The research to start"
    )
    private_offer_id: int = Field(
        validation_alias="PO",
        serialization_alias="PO",
        default=-1,
        description="The private offer the purchase uses, -1 for none",
    )
    pay_with_rubies: Literal[0] = Field(
        validation_alias="PWR",
        serialization_alias="PWR",
        default=0,
        description="Always 0: missing resources are never paid with rubies",
    )


class StartResearchResponse(BaseResponse):
    """
    Your research, coins and rubies, and the joined castle's resources after starting a research.

    Command: res
    Payload: {"rei": {..}, "gcu": {..}, "grc": {..}}

    Client: ``RESCommand.executeCommand`` (bundle line 126876), which parses all three
    """

    command = "res"

    research: ResearchInfoResponse | None = Field(
        validation_alias="rei", serialization_alias="rei", default=None, description="Your research after"
    )
    currencies: CurrencyBlock = Field(
        validation_alias="gcu", serialization_alias="gcu", default=None, description="Coins and rubies after"
    )
    resources: CastleResources | None = Field(
        validation_alias="grc",
        serialization_alias="grc",
        default=None,
        description="The joined castle's resources after",
    )


class SkipResearchRequest(BaseRequest):
    """
    Shorten the running research with a minute skip.

    Command: msr
    Payload: {"MST": minute_skip}

    Client: ``C2SMinuteSkipResearchVO`` (bundle line 79810), built by
    ``ResearchMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 79784); ``CastleMinuteSkipDialog``
    passes the currency's ``jsonKey`` (bundle line 7722)
    """

    command = "msr"

    minute_skip: EnumOrStr["Currency"] = Field(
        validation_alias="MST",
        serialization_alias="MST",
        description="The minute skip used, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``; sent as its key",
    )


class SkipResearchResponse(BaseResponse):
    """
    Your research after a minute skip.

    Command: msr
    Payload: {"rei": {..}}

    Client: ``MSRCommand.executeCommand`` (bundle line 125829)
    """

    command = "msr"

    research: ResearchInfoResponse | None = Field(
        validation_alias="rei", serialization_alias="rei", default=None, description="Your research after"
    )


__all__ = ["SkipResearchRequest", "SkipResearchResponse", "StartResearchRequest", "StartResearchResponse"]
