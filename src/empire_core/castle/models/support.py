"""Sending support to a castle.

Commands:
- cds: Send support
"""

from __future__ import annotations

from pydantic import Field

from empire_core.protocol.base import BaseRequest, BaseResponse

# =============================================================================
# CDS - Send Support (Create Deployment - Support)
# =============================================================================


class SendSupportRequest(BaseRequest):
    """
    Send support troops to a castle.

    Command: cds
    Payload: {
        "SID": source_castle_id,
        "TX": target_x,
        "TY": target_y,
        "LID": commander_id,
        "WT": wait_time,
        "HBW": horses_type (-1 when PTT is set),
        "BPC": use_premium_commander,
        "PTT": feathers,
        "SD": slowdown,
        "A": [[unit_id, count], ...]
    }

    The client sends no kingdom id. Fields follow its key order. ``BPC`` is
    1 only when the premium commander (``LID`` -14,
    ``TravelConst.COMMANDER_PREMIUM``) leads the army, which uses one of the
    player's premium commanders or, when none are left, costs rubies
    (``CastlePostAttackDialog.startAttack`` sends ``sendMovement(0)`` for any
    other commander). ``PTT`` 1 pays for the movement with feathers.

    Client: ``C2SCreateDefenceSupportMovementVO`` (bundle line 133893), built
    by ``CastleAttackData.sendSupport`` (bundle line 133855)
    """

    command = "cds"

    source_castle_id: int = Field(
        alias="SID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    target_x: int = Field(alias="TX")
    target_y: int = Field(alias="TY")
    commander_id: int = Field(
        alias="LID",
        description=(
            "A Commander.commander_id from client.commanders.get_commanders(); "
            "0 is the free starting commander, -14 the premium one"
        ),
    )
    wait_time: int = Field(alias="WT", default=12, ge=0, le=12)
    horses_type: int = Field(alias="HBW", default=-1)
    use_premium_commander: int = Field(alias="BPC", default=0, description="1 when the premium commander leads")
    feathers: int = Field(alias="PTT", default=0, description="1 to pay with feathers")
    slowdown: int = Field(alias="SD", default=0)
    units: list[list[int]] = Field(alias="A")


class SendSupportResponse(BaseResponse):
    """
    Response to sending support.

    Command: cds
    """

    command = "cds"


__all__ = [
    "SendSupportRequest",
    "SendSupportResponse",
]
