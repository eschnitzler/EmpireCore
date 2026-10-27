"""
Your research, starting it and shortening it with a minute skip.

Commands:
- rei: read your research; also a login section of ``gbd``, a push, and inside the ``res`` and ``msr`` replies
- res: start a research
- msr: shorten the running research with a minute skip

Finishing a research at once for rubies (``C2SResearchFinishInstantVO``, bundle line 49093) is left out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import BeforeValidator, Field

from empire_core.castle.models.resources import CastleResources
from empire_core.gamedata import EnumOrInt, EnumOrStr
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock, TimedResponse
from empire_core.protocol.js import ClientNumber, js_int

if TYPE_CHECKING:
    from empire_core.gamedata import Currency, Research


def _ints(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(entry for entry in value if isinstance(entry, int) and not isinstance(entry, bool))


class ResearchInfoRequest(BaseRequest):
    """
    Read your research.

    Command: rei
    Payload: {}

    Client: ``C2SResearchInfoVO`` (bundle line 79687), sent by ``CastleResearchDialog.showLoaded``
    (bundle line 16731)
    """

    command = "rei"


class ResearchInfoResponse(TimedResponse):
    """
    Your research: what is finished and what runs now.

    Command: rei, as a login section of ``gbd``, a push, and inside the ``res`` and ``msr`` replies.

    Client: ``CastleResearchData.parse_REI`` (bundle line 139330), ``remainingResearchTimeInSeconds``
    and ``isSomeResearchActive`` (bundle lines 139337-139338)
    """

    command = "rei"

    bought_research_ids: Annotated[tuple[EnumOrInt["Research"], ...], BeforeValidator(_ints)] = Field(
        validation_alias="BR", default=(), description="Finished researches"
    )
    current_research_id: Annotated[
        Literal[-1, 0] | EnumOrInt["Research"], Field(union_mode="left_to_right"), BeforeValidator(js_int)
    ] = Field(
        validation_alias="ARID",
        default=0,
        description="The research running now, -1 for none; 0 when not sent",
    )
    research_seconds: ClientNumber = Field(
        validation_alias="ARRT",
        default=0,
        description="Seconds left on the running research when the values were read",
    )

    def remaining_research_seconds(self, now: float | None = None) -> int:
        """Whole seconds left on the running research, 0 when none runs."""
        return js_int(max(self.research_seconds - self._elapsed(now), 0))

    def is_research_active(self, now: float | None = None) -> bool:
        """Whether a research runs: an id other than -1 with time left."""
        return self.current_research_id != -1 and self.remaining_research_seconds(now) > 0


class StartResearchRequest(BaseRequest):
    """
    Start a research, paying what it costs: resources and coins, or rubies for a research that costs them.

    Command: res
    Payload: {"RID": research_id, "PO": -1, "PWR": 0}

    ``PWR`` 1 would pay missing resources with rubies (``CastleResourceWaitDialogProperties.getResourceSkipCommand``,
    bundle line 35216); this request always sends 0. A research whose own costs hold rubies
    (``ResearchDef.cost_rubies``) is sent the same way and spends them; ``client.castle.start_research``
    refuses it unless asked to spend rubies.

    Client: ``C2SResearchStartVO`` (bundle line 47697), sent by ``ResearchInfo.buyResearch`` (bundle line 79704)
    with the private offer -1 and ``PWR`` 0
    """

    command = "res"

    research_id: EnumOrInt["Research"] = Field(validation_alias="RID", description="The research to start")
    private_offer_id: int = Field(
        validation_alias="PO",
        default=-1,
        description="The private offer the purchase uses, -1 for none",
    )
    pay_with_rubies: Literal[0] = Field(
        validation_alias="PWR",
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
        validation_alias="rei", default=None, description="Your research after"
    )
    currencies: CurrencyBlock = Field(validation_alias="gcu", default=None, description="Coins and rubies after")
    resources: CastleResources | None = Field(
        validation_alias="grc",
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
        validation_alias="rei", default=None, description="Your research after"
    )


__all__ = [
    "ResearchInfoRequest",
    "ResearchInfoResponse",
    "SkipResearchRequest",
    "SkipResearchResponse",
    "StartResearchRequest",
    "StartResearchResponse",
]
