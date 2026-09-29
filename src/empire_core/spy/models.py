"""Spy protocol models.

Commands:
- csm: Send spy mission
- ssi: Spy screen info
"""

from __future__ import annotations

from pydantic import Field

from empire_core.enums import Kingdom, SpyType
from empire_core.protocol.base import BaseRequest, BaseResponse

# =============================================================================
# CSM - Send Spy Mission
# =============================================================================


class SendSpyRequest(BaseRequest):
    """
    Send a spy mission to a target.

    Command: csm
    Payload: {"SID": castle_id, "TX": target_x, "TY": target_y, "SC": spy_count, "ST": spy_type,
              "SE": precision, "HBW": horses_type, "KID": target_kingdom, "PTT": pay_to_travel,
              "SD": slowdown}

    The keys follow the client's order. ``SE`` is the sabotage damage for a
    sabotage mission and the accuracy for any other. A horse paid with
    feathers is sent as ``HBW`` -1 with ``PTT`` 1.

    Client: ``C2SCreateSpyMovementVO`` (bundle line 100126), built by
    ``CastlePostSpyDialog.spyCastle`` (bundle line 38457)
    """

    command = "csm"

    castle_id: int = Field(
        alias="SID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")
    spy_count: int = Field(alias="SC", default=1, description="How many spies to send")
    spy_type: SpyType = Field(alias="ST", default=SpyType.MILITARY, description="What the spies are sent to do")
    precision: int = Field(
        alias="SE", default=100, description="Sabotage damage for a sabotage mission, accuracy for any other"
    )
    horses_type: int = Field(alias="HBW", default=-1, description="The horse's wod id, -1 for none or for feathers")
    target_kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The target's kingdom")
    pay_to_travel: int = Field(alias="PTT", default=0, description="1 when the horse is paid with feathers")
    slowdown: int = Field(alias="SD", default=0, description="Slowdown offset in seconds")


class SendSpyResponse(BaseResponse):
    """
    Response to spy mission.

    Command: csm
    """

    command = "csm"

    movement_id: int = Field(alias="MID", default=0)
    arrival_time: int = Field(alias="AT", default=0)


# =============================================================================
# SSI - Spy Screen Info
# =============================================================================


class SpyScreenInfoRequest(BaseRequest):
    """
    Get what a spy mission against a target would face: its guards and the spies at hand.

    Command: ssi
    Payload: {"TX": target_x, "TY": target_y, "KID": target_kingdom}

    Client: ``C2SGetSpyInfo`` (bundle line 22504), sent with the target's
    ``absAreaPos`` and ``kingdomID`` when the spy dialog opens (bundle line 14800)
    """

    command = "ssi"

    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")
    target_kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The target's kingdom")


class SpyScreenInfoResponse(BaseResponse):
    """
    Response to spy screen info.

    Command: ssi
    """

    command = "ssi"

    available_spies: int = Field(alias="AS", default=0)
    guard_count: int = Field(alias="GC", default=0)


__all__ = [
    "SendSpyRequest",
    "SendSpyResponse",
    "SpyScreenInfoRequest",
    "SpyScreenInfoResponse",
]
