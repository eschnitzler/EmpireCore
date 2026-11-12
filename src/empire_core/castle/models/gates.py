"""Open Gate: let attackers loot a castle without a battle, so its buildings take no damage.

Commands:
- mos: Open a castle's gate for one of the offered durations, or close it
"""

from __future__ import annotations

import math

from pydantic import Field, field_validator

from empire_core.enums import Kingdom, OpenGateDuration, OpenGateRefusal
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock, EmpireModel
from empire_core.protocol.js import js_int

CLOSE_GATE = -1
"""The ``mos`` duration that closes an open gate."""

_FIRST_USE_RUBIES = {OpenGateDuration.HOURS_6: 450, OpenGateDuration.HOURS_12: 700}
_USE_CAP = 9


def open_gate_rubies(duration: OpenGateDuration, use: int) -> int:
    """
    The Open Gate's price before ruby discounts for a castle's ``use``-th opening this week (1 for the first).

    Client: ``PlayerConst.getOpenGateCosts`` (dll) with ``OPEN_GATE_C2`` and ``OPEN_GATE_COUNT_CAP``,
    called by ``CastleStartOpenGateDialog.updateCosts`` (bundle line 35144) with the castle's
    ``openGateCounter + 1``
    """
    capped = min(_USE_CAP, use)
    return 10 * math.floor(_FIRST_USE_RUBIES[duration] * capped ** (1.1 + capped / 10) / 10 + 0.5)


class OpenGateRequest(BaseRequest):
    """
    Open one of your castles' gate for an offered duration, extend an open one, or close it.

    Command: mos
    Payload: {"CID": castle, "KID": kingdom, "CD": duration}
    Client: ``C2SOpenGateStartVO`` (bundle line 47469), sent with the start dialog's selected list index by
    ``CastleStartOpenGateDialog.onClick`` (bundle line 35154) and with -1 by
    ``CastleManagementDialog.cancelOpenGateMode`` (bundle line 24683)
    """

    command = "mos"

    castle_id: int = Field(validation_alias="CID", description="The castle's object id")
    kingdom: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    duration: int = Field(validation_alias="CD", description="An OpenGateDuration, or CLOSE_GATE")


class OpenGateResponse(BaseResponse):
    """
    The castle's gate after an Open Gate change, and your coins and rubies after it.

    Command: mos
    Client: ``MOSCommand.executeCommand`` (bundle line 125119): ``parseGCU(gcu)``, then
    ``CastleUserData.parse_MOS`` (bundle line 9897)
    """

    command = "mos"

    castle_id: int = Field(validation_alias="CID", default=0, description="The castle's object id")
    kingdom: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")
    open_seconds: int = Field(
        validation_alias="RPT", default=0, description="Seconds the gate stays open; not positive once closed"
    )
    currencies: CurrencyBlock = Field(validation_alias="gcu", default=None, description="Coins and rubies after")

    _ints = field_validator("castle_id", "open_seconds", mode="before")(js_int)


class OpenGateQuote(EmpireModel):
    """
    What opening a castle's gate would cost now, read from state; nothing is sent.

    The prices are before ruby discounts and follow the castle's opening count as state tracked it;
    the server decides what it charges.

    Client: ``CastleStartOpenGateDialog.updateCosts`` (bundle line 35144)
    """

    castle_id: int = Field(description="The castle's object id")
    kingdom: Kingdom = Field(description="The castle's kingdom")
    open_seconds: float = Field(description="Seconds the gate stays open, 0 while it is closed")
    uses: int = Field(description="How often the gate has been opened since the last Monday reset")
    prices: dict[OpenGateDuration, int] = Field(
        description="Each duration's price before ruby discounts for the next opening"
    )
    rubies: int = Field(description="Your rubies")
    refusal: OpenGateRefusal | None = Field(description="Why the client offers no Open Gate here; None when it does")


__all__ = ["CLOSE_GATE", "OpenGateQuote", "OpenGateRequest", "OpenGateResponse", "open_gate_rubies"]
