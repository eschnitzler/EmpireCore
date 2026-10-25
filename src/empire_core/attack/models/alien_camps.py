"""Alien invasion camps: rerolling one, and the camps the server hides.

Commands:
- rae: Replace (reroll) an alien camp
- hac: Alien camps hidden from the map (push)
- rce: How often you rerolled alien camps (push)
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.protocol.js import ClientInt, js_int

# =============================================================================
# RAE - Reroll an alien camp
# =============================================================================


class RerollAlienCampRequest(BaseRequest):
    """
    Replace an alien camp on the map with another, paying in rubies or one of the event's reroll currencies.

    Command: rae
    Payload: {"XPOS": x, "YPOS": y, "RCK": key}
    Client: ``C2SReplaceAlienCampVO`` (bundle line 109782), sent by ``CastleRerollAlienDialog.onSendReroll``
    (bundle line 109749) with ``"C2"`` or one of the event's ``rerollCurrencyKeys`` (bundle line 109770)
    """

    command = "rae"

    x: int = Field(validation_alias="XPOS", description="Map x of the camp")
    y: int = Field(validation_alias="YPOS", description="Map y of the camp")
    currency_key: str = Field(
        validation_alias="RCK",
        description='What pays: "C2" for rubies, "C1" for coins, or a reroll currency\'s key',
    )


class RerollAlienCampResponse(BaseResponse):
    """
    The server replaced the camp; the map shows the new one on its next read.

    Command: rae
    Client: ``RAECommand.executeCommand`` (bundle line 127100), which reads nothing from the body
    """

    command = "rae"


# =============================================================================
# HAC - Hidden alien camps
# =============================================================================


def _points(value: Any) -> list[tuple[int, int]]:
    if not isinstance(value, list):
        return []
    return [(js_int(row[0]), js_int(row[1])) for row in value if isinstance(row, list) and len(row) >= 2]


class HiddenAlienCampsResponse(BaseResponse):
    """
    Alien camps the server took off your map: a push.

    Command: hac
    Client: ``HACCommand.executeCommand`` (bundle line 130210), which hides the alien map object at each
    ``[x, y]`` of ``CP``
    """

    command = "hac"

    positions: tuple[tuple[int, int], ...] = Field(
        validation_alias="CP", default=(), description="The (x, y) of each camp hidden"
    )

    @field_validator("positions", mode="before")
    @classmethod
    def _read_points(cls, value: Any) -> list[tuple[int, int]]:
        return _points(value)


# =============================================================================
# RCE - Alien reroll counts
# =============================================================================


class AlienRerollCountsResponse(BaseResponse):
    """
    How often you rerolled alien camps, which sets each reroll's price; a push, and part of an alien invasion's entry.

    A count the block leaves out keeps its earlier value.

    Command: rce, which the client never sends
    Client: ``RCECommand.executeCommand`` (bundle line 127142) and ``AAlienInvasionEventVO.parseData``
    (bundle line 58933) hand it to ``CastleAlienRerollData.parse_RCE`` (bundle line 133595)
    """

    command = "rce"

    soft_rerolls: ClientInt | None = Field(
        validation_alias="RCSC", default=None, description="Rerolls paid with coins or event currencies"
    )
    ruby_rerolls: ClientInt | None = Field(
        validation_alias="RCHC", default=None, description="Rerolls paid with rubies"
    )

    def merged_into(self, previous: AlienRerollCountsResponse | None) -> AlienRerollCountsResponse | None:
        """These counts over ``previous``: a count this block leaves out keeps the earlier one; None while none came."""
        sent = {"soft_rerolls": self.soft_rerolls, "ruby_rerolls": self.ruby_rerolls}
        sent = {name: count for name, count in sent.items() if count is not None}
        if previous is None:
            return self if sent else None
        return previous.model_copy(update=sent)


__all__ = [
    "AlienRerollCountsResponse",
    "HiddenAlienCampsResponse",
    "RerollAlienCampRequest",
    "RerollAlienCampResponse",
]
