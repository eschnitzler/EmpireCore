"""Recruitment loops: repeating a production list's queue, and copying it to other castles.

Commands:
- lri: What a loop of a list costs (reply only)
- url: Loop a list's queue
- crl: Cancel a loop (reply only)
- dri: The castles a list's queue can be copied to, and what each copy costs
- drl: Copy a list's queue to other castles

``dri`` and ``drl`` act on the castle the session has joined (``jca``).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field

from empire_core.enums import GGEError, Kingdom, ProductionListId
from empire_core.gamedata import UnitOrTool
from empire_core.gamedata.lenient import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, list_or_empty
from empire_core.protocol.js import ClientInt, js_int

from .production import ProductionSlot


class RecruitmentCosts(BasePayload):
    """
    The resources and rubies one loop or one copy of a list's queue costs.

    Client: ``AutoRecruitmentCosts.fillByServerData`` (bundle line 23833)
    """

    wood_cost: ClientInt = Field(validation_alias="CW", default=0, description="Wood")
    stone_cost: ClientInt = Field(validation_alias="CS", default=0, description="Stone")
    coin_cost: ClientInt = Field(validation_alias="C1", default=0, description="Coins")
    doubling_ruby_cost: ClientInt = Field(
        validation_alias="DC",
        default=0,
        description="Rubies for doubling the units of the queue's doubled slots again",
    )


# =============================================================================
# LRI - Loop Recruitment Info
# =============================================================================


class LoopRecruitmentInfoResponse(BaseResponse, RecruitmentCosts):
    """
    What one loop of a list's queue costs and takes.

    Command: lri
    Payload: {"LID": list_id, "CRT": seconds, "CFC": food, "FCAL": food, "CW": wood, "CS": stone,
              "C1": coins, "DC": rubies}

    The client has no request for it: ``C2S_LOOP_RECRUITMENT_INFO`` is never sent, and this reply
    is what opens the loop purchase dialog.

    Client: ``LRICommand.executeCommand`` (bundle line 126727) builds
    ``AutoRecruitmentPurchaseDialogProperties`` (bundle line 126787) from it
    """

    command = "lri"

    list_id: EnumOrInt[ProductionListId] = Field(
        validation_alias="LID", default=ProductionListId.SOLDIERS, description="The list"
    )
    recruitment_seconds: ClientInt = Field(
        validation_alias="CRT", default=0, description="Seconds until the list's current production is done"
    )
    food_consumption: ClientInt = Field(
        validation_alias="CFC", default=0, description="Food per hour the list's units eat now"
    )
    food_consumption_per_loop: ClientInt = Field(
        validation_alias="FCAL", default=0, description="Food per hour each loop adds to that"
    )


# =============================================================================
# URL - Update Recruitment Loop
# =============================================================================


class RecruitmentLoopSlot(BasePayload):
    """
    One queued slot a loop repeats.

    Client: ``AutoRecruitmentHelper.createAutoRecruitSnapshot`` (bundle line 36599) sends
    ``{ID, A, CBS, IA}`` for each queued slot, ``IA`` being the amount again
    """

    wod_id: UnitOrTool = Field(validation_alias="ID", description="The slot's unit or tool; 0 for an empty slot")
    amount: int = Field(validation_alias="A", description="Units in the slot")
    boost_count: int = Field(validation_alias="CBS", description="How often the slot's units were doubled")
    initial_amount: int = Field(validation_alias="IA", description="Units in the slot, again")

    @classmethod
    def from_slot(cls, slot: ProductionSlot) -> RecruitmentLoopSlot:
        """The loop entry the client sends for a queued slot."""
        return cls(wod_id=slot.wod_id, amount=slot.amount, boost_count=slot.boost_count, initial_amount=slot.amount)


class UpdateRecruitmentLoopRequest(BaseRequest):
    """
    Loop a list's queue, for rubies.

    Command: url
    Payload: {"LID": list_id, "L": loops, "RS": [{"ID": wod_id, "A": amount, "CBS": boosts, "IA": amount}, ...]}

    ``RS`` is every queued slot of the list (``slotsArray``, without the slot producing now).

    Client: ``C2SUpdateRecruitmentLoopVO`` (bundle line 126752), sent by
    ``AAutoRecruitmentPurchaseDialog.sendConfirmToServer`` (bundle line 60527)
    """

    command = "url"

    list_id: ProductionListId = Field(validation_alias="LID", description="The list to loop")
    loops: int = Field(validation_alias="L", description="How many times to repeat the queue")
    slots: list[RecruitmentLoopSlot] = Field(validation_alias="RS", description="The queue to repeat")


class UpdateRecruitmentLoopResponse(BaseResponse):
    """
    The server's answer to a ``url``: empty on success.

    ``NO_FREE_CONSTRUCTION_SLOT`` comes with ``{"LID": list_id, "AMT": slots}``, the slots to unlock first.

    Command: url

    Client: ``URLCommand.executeCommand`` (bundle line 126836)
    """

    command = "url"


# =============================================================================
# CRL - Cancel Recruitment Loop
# =============================================================================


class CancelRecruitmentLoopResponse(BaseResponse):
    """
    The server's ``crl``.

    Command: crl

    The client has no request for it (``C2S_CANCEL_RECRUITMENT_LOOP`` is never sent; cancelling
    a slot sends ``mcu``) and reads nothing of the reply.

    Client: ``CRLCommand.executeCommand`` (bundle line 126675)
    """

    command = "crl"


# =============================================================================
# DRI - Duplicate Recruitment Info
# =============================================================================


class RecruitmentCopyTarget(RecruitmentCosts):
    """
    One of your castles a list's queue can be copied to, an entry of ``dri``'s ``A``.

    The soldier and auxiliary lists send ``F``, ``DF``, ``AFC`` and ``U``; the tool list sends
    ``P``, ``T``, ``W`` and ``S``.

    Client: ``AutoRecruitmentCopyListItemVO`` (bundle line 84074); the columns are
    ``AutoRecruitmentCopyListItemUnitsVE.applyNewVO`` and ``AutoRecruitmentCopyListItemToolsVE.applyNewVO``
    (bundle lines 84118, 84100), headed by the tooltips ``AutoRecruitmentCopyUnitsDialog.initLoaded`` and
    ``AutoRecruitmentCopyToolsDialog.initLoaded`` set (bundle lines 51338, 51190)
    """

    list_id: EnumOrInt[ProductionListId] = Field(
        validation_alias="LID", default=ProductionListId.SOLDIERS, description="The list"
    )
    castle_id: ClientInt = Field(validation_alias="AID", default=0, description="The castle")
    kingdom: Annotated[Kingdom, BeforeValidator(js_int)] = Field(
        validation_alias="SID", default=Kingdom.GREEN, description="The castle's kingdom"
    )
    castle_name: str = Field(validation_alias="CN", default="", description="The castle's name")
    refusal: Annotated[EnumOrInt[GGEError], BeforeValidator(js_int)] = Field(
        validation_alias="EID",
        default=GGEError.ALL_OK,
        description="Why the castle cannot take the copy, ALL_OK when it can",
    )
    recruitment_seconds: ClientInt = Field(
        validation_alias="ART", default=0, description="Seconds the copied queue takes there"
    )
    food: int | float = Field(validation_alias="F", default=0, description="Food in the castle")
    food_production_tenths: int | float = Field(
        validation_alias="DF", default=0, description="The castle's food production per hour, in tenths"
    )
    added_food_consumption: int | float = Field(
        validation_alias="AFC", default=0, description="Food per hour the copied units eat"
    )
    units: int = Field(validation_alias="U", default=0, description="All units in the castle")
    production: int | float = Field(validation_alias="P", default=0, description="The castle's tool production speed")
    tools: int = Field(validation_alias="T", default=0, description="Tools available in the castle")
    wood: int | float = Field(validation_alias="W", default=0, description="Wood in the castle")
    stone: int | float = Field(validation_alias="S", default=0, description="Stone in the castle")

    @property
    def can_copy(self) -> bool:
        """The client lets you pick the castle: ``hasError`` is false."""
        return self.refusal == GGEError.ALL_OK

    @property
    def food_production(self) -> float:
        """Food production per hour, as the copy dialog shows it."""
        return self.food_production_tenths / 10

    @property
    def food_production_after_copy(self) -> float:
        """Food production per hour once the copied units eat."""
        return self.food_production - self.added_food_consumption


class DuplicateRecruitmentInfoRequest(BaseRequest):
    """
    Ask which castles a list's queue can be copied to, and what each copy costs.

    Command: dri
    Payload: {"LID": list_id, "AID": castle_id, "SID": kingdom_id}

    Client: ``C2SDuplicateRecruitmentInfoVO`` (bundle line 83912), sent by
    ``AAutoRecruitmentCopyDialog.requestDRI`` (bundle line 51219) with the castle the session is in
    """

    command = "dri"

    list_id: ProductionListId = Field(validation_alias="LID", description="The list to copy")
    castle_id: int = Field(
        validation_alias="AID",
        description=(
            "The castle the session is in, a Castle.id from client.state.get_castles(); ArmyService joins it first"
        ),
    )
    kingdom: Kingdom = Field(validation_alias="SID", description="The joined castle's kingdom")


class DuplicateRecruitmentInfoResponse(BaseResponse):
    """
    The castles a list's queue can be copied to.

    Command: dri
    Payload: {"A": [{...}, ...]}

    Client: ``DRICommand.executeCommand`` (bundle line 126686) hands it to
    ``AutoRecruitmentCopyDialogProperties.parseServerInformation`` (bundle line 84148)
    """

    command = "dri"

    targets: Annotated[list[RecruitmentCopyTarget], BeforeValidator(list_or_empty)] = Field(
        validation_alias="A", default_factory=list, description="Your other castles, one entry each"
    )


# =============================================================================
# DRL - Duplicate Recruitment Loop
# =============================================================================


class RecruitmentCopyDestination(BasePayload):
    """
    One castle ``drl`` copies the queue to.

    Client: ``AAutoRecruitmentCopyDialog.onOkButton`` (bundle line 51255) sends ``{SID, AID}``
    for each picked castle
    """

    kingdom: Kingdom = Field(validation_alias="SID", description="The castle's kingdom")
    castle_id: int = Field(validation_alias="AID", description="The castle")


class DuplicateRecruitmentLoopRequest(BaseRequest):
    """
    Copy a list's queue to other castles, for resources and rubies.

    Command: drl
    Payload: {"LID": list_id, "SID": kingdom_id, "AID": castle_id, "A": [{"SID": kingdom_id, "AID": castle_id}, ...]}

    Client: ``C2SDuplicateRecruitmentLoopVO`` (bundle line 83921), sent by
    ``AAutoRecruitmentCopyDialog.onOkButton`` (bundle line 51260)
    """

    command = "drl"

    list_id: ProductionListId = Field(validation_alias="LID", description="The list to copy")
    kingdom: Kingdom = Field(validation_alias="SID", description="The joined castle's kingdom")
    castle_id: int = Field(
        validation_alias="AID",
        description=(
            "The castle the session is in, a Castle.id from client.state.get_castles(); ArmyService joins it first"
        ),
    )
    destinations: list[RecruitmentCopyDestination] = Field(validation_alias="A", description="The castles to copy to")


class DuplicateRecruitmentLoopResponse(BaseResponse):
    """
    The server's answer to a ``drl``: empty on success.

    ``NO_FREE_CONSTRUCTION_SLOT`` comes with ``{"LID": list_id, "AMT": slots}``, the slots to unlock first.

    Command: drl

    Client: ``DRLCommand.executeCommand`` (bundle line 126706)
    """

    command = "drl"


__all__ = [
    "RecruitmentCosts",
    "LoopRecruitmentInfoResponse",
    "RecruitmentLoopSlot",
    "UpdateRecruitmentLoopRequest",
    "UpdateRecruitmentLoopResponse",
    "CancelRecruitmentLoopResponse",
    "RecruitmentCopyTarget",
    "DuplicateRecruitmentInfoRequest",
    "DuplicateRecruitmentInfoResponse",
    "RecruitmentCopyDestination",
    "DuplicateRecruitmentLoopRequest",
    "DuplicateRecruitmentLoopResponse",
]
