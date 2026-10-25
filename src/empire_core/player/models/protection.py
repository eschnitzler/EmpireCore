"""Your protection: beginner protection, peace mode and Berimond faction protection.

Commands:
- uap: Get your protection in a kingdom (also pushed)
- mps: Start or cancel peace mode
- ffp: Start Berimond faction protection
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from empire_core.enums import Kingdom
from empire_core.events.faction_models import FactionStanding
from empire_core.map.models.areas import KingdomProtection
from empire_core.protocol.base import (
    BaseRequest,
    BaseResponse,
    CurrencyBlock,
    object_or_none,
)
from empire_core.protocol.js import js_same_number

# =============================================================================
# UAP - Protection
# =============================================================================


class GetProtectionRequest(BaseRequest):
    """
    Ask for your protection in a kingdom.

    The client asks for the kingdom it shows while a peace mode stage runs out, and for
    Berimond while a faction protection stage runs out.

    Command: uap
    Payload: {"KID": kingdom}
    Client: ``C2SUserAttackProtectionVO`` (bundle line 65923), sent by ``CastleUserData.executeUpdate``
    (bundle line 9932); ``C2SUpdateFactionProtectionVO`` (bundle line 87993), the same command with
    ``KID`` fixed to Berimond, sent by ``FactionEventVO.update`` (bundle line 7416)
    """

    command = "uap"

    kingdom: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="The kingdom to ask about")

    def accepts_reply(self, payload: Any) -> bool:
        return not isinstance(payload, dict) or js_same_number(payload.get("KID"), int(self.kingdom))


class ProtectionResponse(BaseResponse, KingdomProtection):
    """
    Your protection in one kingdom: the reply to :class:`GetProtectionRequest`, and a push when it changes.

    Command: uap
    Client: ``UAPCommand.executeCommand`` (bundle line 129888), which hands the body to
    ``CastleUserData.parse_UAP`` (bundle line 9906)
    """

    command = "uap"


# =============================================================================
# MPS - Peace mode
# =============================================================================

CANCEL_PEACE_MODE = -1
"""The ``mps`` duration that ends a running peace mode."""


class StartPeaceModeRequest(BaseRequest):
    """
    Start peace mode for one of the offered lengths, or end the running one.

    Command: mps
    Payload: {"CD": duration}
    Client: ``C2SPeaceModeStartVO`` (bundle line 47478), sent with the start dialog's selected list
    index by ``CastleStartPeaceModeDialog.onClick`` (bundle line 35192) and with -1 by
    ``CastleManagementDialog.cancelPeaceMode`` (bundle line 24682)
    """

    command = "mps"

    duration: int = Field(
        validation_alias="CD",
        description="A PeaceModeDuration, or CANCEL_PEACE_MODE to end the running peace mode",
    )


class StartPeaceModeResponse(BaseResponse):
    """
    The server took the peace mode change; the new state follows as a ``uap`` push.

    Command: mps
    Client: ``MPSCommand.executeCommand`` (bundle line 125133), which reads nothing from the body
    """

    command = "mps"


# =============================================================================
# FFP - Berimond faction protection
# =============================================================================


FACTION_PROTECTION_RUBIES = 7500
"""Berimond faction protection's price before ruby discounts: ``FactionConst.getPeaceC2Cost`` (dll line 19316)."""


class StartFactionProtectionRequest(BaseRequest):
    """
    Buy Berimond faction protection.

    Command: ffp
    Payload: {"ID": option}
    Client: ``C2SStartFactionProtectionVO`` (bundle line 64929), sent by
    ``CastleFactionProtectionModeDialog.onClick`` (bundle line 64918) with the selected index of a
    list ``fillPeaceTimeList`` fills with one option (bundle line 64910)
    """

    command = "ffp"

    option: int = Field(validation_alias="ID", default=0, description="The offered protection, 0 being the only one")


class StartFactionProtectionResponse(BaseResponse):
    """
    Your coins and rubies after buying faction protection, and your faction standing with it.

    Command: ffp
    Client: ``FFPCommand.executeCommand`` (bundle line 127785): ``parseGCU(gcu)``, then
    ``CastleSpecialEventData.parse_FN(FN)`` (bundle line 139876)
    """

    command = "ffp"

    currencies: CurrencyBlock = Field(validation_alias="gcu", default=None, description="Coins and rubies after")
    faction: FactionStanding | None = Field(
        validation_alias="FN", default=None, description="Your faction and its protection"
    )

    @field_validator("faction", mode="before")
    @classmethod
    def _faction_needs_an_object(cls, value: Any) -> Any:
        return object_or_none(value)


__all__ = [
    "CANCEL_PEACE_MODE",
    "FACTION_PROTECTION_RUBIES",
    "GetProtectionRequest",
    "ProtectionResponse",
    "StartFactionProtectionRequest",
    "StartFactionProtectionResponse",
    "StartPeaceModeRequest",
    "StartPeaceModeResponse",
]
