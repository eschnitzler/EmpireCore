"""Sending support to a castle, and troops between your own areas.

Commands:
- cds: Send support
- cat: Send troops to another of your own areas
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from empire_core.enums import Kingdom
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock
from empire_core.protocol.js import movement_targets

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
        "HBW": horse_booster_id (-1 when PTT is set),
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
    horse_booster_id: int = Field(
        alias="HBW", default=-1, description="The horse booster's wod id, -1 for none or when paid with feathers"
    )
    use_premium_commander: int = Field(alias="BPC", default=0, description="1 when the premium commander leads")
    feathers: int = Field(alias="PTT", default=0, description="1 when the horse is paid with feathers")
    slowdown: int = Field(alias="SD", default=0, description="Seconds the arrival is delayed by")
    units: list[list[int]] = Field(alias="A")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a cds reply is the movement this sent: its target area (``A.M.TA``) is ``TX``/``TY``.

        Client: ``CDSCommand`` (bundle line 125939) reads the new movement from ``A``,
        whose ``TA`` is the target area (``BasicMapmovementVO``). An army heading home
        targets your own castle and is not taken.
        """
        return isinstance(payload, dict) and movement_targets(payload.get("A"), self.target_x, self.target_y)


class SendSupportResponse(BaseResponse):
    """
    The support on its way.

    Command: cds
    Payload: {"gcu": {...}, "O": [owner, ...], "A": movement}

    ``O`` (the owners involved) and ``A`` (the new movement) are kept as sent.

    Client: ``CDSCommand.executeCommand`` (bundle line 125939)
    """

    command = "cds"

    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after")


# =============================================================================
# CAT - Send Troops (Create Army Travel movement)
# =============================================================================


class SendTroopsRequest(BaseRequest):
    """
    Send troops from one of your areas to another of your own areas, where they stay.

    Command: cat
    Payload: {
        "SX": source_x,
        "SY": source_y,
        "TX": target_x,
        "TY": target_y,
        "KID": kingdom_id,
        "LID": commander_id,
        "WT": 0,
        "HBW": horse_booster_id (-1 when PTT is set),
        "BPC": use_premium_commander,
        "PTT": feathers,
        "SD": slowdown,
        "A": [[wod_id, amount], ...]
    }

    Fields follow the client's key order: the constructor initialises SX to SD
    and sets A after them. The source is named by its map position, not its
    id. ``KID`` is the target's kingdom, and the source must sit in the same
    one. ``A`` lists the units, then the tools. The client always sends ``WT``
    0: only a support sets a wait time. A support (``cds``) to your own area is
    refused with NO_SELF_DESTRUCTION (92); this is the command the client uses
    for it.

    Client: ``C2SCreateArmyTravelMovementVO`` (bundle line 99772), built by
    ``CastleTroopSupportData.sendTroops`` (bundle line 38420) from
    ``CastlePostAttackDialog.sendTroops`` (bundle line 38373); the army from
    ``CastleTroopSupportVO.getArmy`` (bundle line 99737)
    """

    command = "cat"

    source_x: int = Field(alias="SX", description="Map x of the area the troops leave from")
    source_y: int = Field(alias="SY", description="Map y of the area the troops leave from")
    target_x: int = Field(alias="TX", description="Map x of the area they go to")
    target_y: int = Field(alias="TY", description="Map y of the area they go to")
    kingdom_id: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The kingdom both areas sit in")
    commander_id: int = Field(
        alias="LID",
        description=(
            "A Commander.commander_id from client.commanders.get_commanders(); "
            "0 is the free starting commander, -14 the premium one"
        ),
    )
    wait_time: int = Field(alias="WT", default=0, description="Wait time at the target")
    horse_booster_id: int = Field(
        alias="HBW", default=-1, description="The horse booster's wod id, -1 for none or when paid with feathers"
    )
    use_premium_commander: int = Field(alias="BPC", default=0, description="1 when the premium commander leads")
    feathers: int = Field(alias="PTT", default=0, description="1 when the horse is paid with feathers")
    slowdown: int = Field(alias="SD", default=0, description="Seconds the arrival is delayed by")
    units: list[list[int]] = Field(alias="A", description="The units and tools, as [wod_id, amount] pairs")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a cat reply is the movement this sent: its target area (``A.M.TA``) is ``TX``/``TY``.

        Client: ``CATCommand`` (bundle line 125924) reads the new movement from ``A``,
        whose ``TA`` is the target area (``BasicMapmovementVO``). An army heading home
        targets its source and is not taken.
        """
        return isinstance(payload, dict) and movement_targets(payload.get("A"), self.target_x, self.target_y)


class SendTroopsResponse(BaseResponse):
    """
    The troops on their way.

    Command: cat
    Payload: {"O": [owner, ...], "A": movement, "gcu": {...}}

    ``O`` (the owners involved) and ``A`` (the new movement) are kept as sent.

    Client: ``CATCommand.executeCommand`` (bundle line 125924)
    """

    command = "cat"

    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after")


__all__ = [
    "SendSupportRequest",
    "SendSupportResponse",
    "SendTroopsRequest",
    "SendTroopsResponse",
]
