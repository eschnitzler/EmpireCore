"""Taunts: making the nomad khan or the wolf king attack you.

Commands:
- lta: Taunt the khan of the alliance nomad invasion
- lwta: Taunt the wolf king
- rpr: Rage points received on the khan camp (push)
"""

from __future__ import annotations

from pydantic import Field

from empire_core.gamedata import EnumOrInt
from empire_core.gamedata.ids.events import Event
from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.protocol.js import ClientInt

# =============================================================================
# LTA - Khan taunt
# =============================================================================


class LaunchTauntAttackRequest(BaseRequest):
    """
    Taunt the nomad khan into attacking you.

    Command: lta
    Payload: {"AV": 0 or 1, "EID": event}
    Client: ``C2SLaunchTauntAttackVO`` (bundle line 98553), sent by
    ``CastleNomadInvasionTauntDialog.tauntKhan`` (bundle line 55677) with its show-to-alliance
    checkbox and the alliance nomad invasion's id (its ``eventVO``, bundle line 55678)
    """

    command = "lta"

    share_with_alliance: int = Field(
        validation_alias="AV", default=0, description="1 to show the attack to your alliance, else 0"
    )
    event: EnumOrInt[Event] = Field(
        validation_alias="EID", default=Event.NOMAD_INVASION_72, description="The nomad invasion taunted"
    )


class LaunchTauntAttackResponse(BaseResponse):
    """
    The server took the taunt.

    Command: lta
    Client: ``LTACommand.executeCommand`` (bundle line 128204), which reads nothing from the body
    """

    command = "lta"


# =============================================================================
# LWTA - Wolf king taunt
# =============================================================================


class LaunchWolfKingTauntRequest(BaseRequest):
    """
    Taunt the wolf king into attacking you.

    Command: lwta
    Payload: {}
    Client: ``C2SLaunchWolfkingTauntAttackVO`` (bundle line 110112), sent by
    ``ButtonTauntComponent.onClick`` (bundle line 110098) on a wolf king map object
    """

    command = "lwta"


class LaunchWolfKingTauntResponse(BaseResponse):
    """
    The server took the taunt.

    Command: lwta
    Client: ``LWTACommand.executeCommand`` (bundle line 124329), which reads nothing from the body
    """

    command = "lwta"


# =============================================================================
# RPR - Rage points
# =============================================================================


class RagePointsResponse(BaseResponse):
    """
    Your rage points on the khan camp of an event: a push.

    Command: rpr
    Client: ``RPRCommand.executeCommand`` (bundle line 128217) hands it to the running event's
    ``parse_RPR``, which only ``AllianceNomadInvasionEventVO`` has (bundle line 114369)
    """

    command = "rpr"

    event_id: EnumOrInt[Event] = Field(validation_alias="EID", description="The event the rage is for")
    player_rage: ClientInt = Field(validation_alias="PCRP", default=0, description="Your current rage points")
    player_total_rage: ClientInt = Field(validation_alias="PTRP", default=0, description="Your total rage points")


__all__ = [
    "LaunchTauntAttackRequest",
    "LaunchTauntAttackResponse",
    "LaunchWolfKingTauntRequest",
    "LaunchWolfKingTauntResponse",
    "RagePointsResponse",
]
