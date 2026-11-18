"""
Hiring a booster with rubies.

Commands:
- bis: Hire the instructor
- bms: Hire the marauder
- ovs: Hire an overseer
- bcs: Hire the caravan overloader
- brs: Buy the return speed booster
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field

from empire_core.castle.models.details import CastleProductionArea
from empire_core.enums import BoosterId
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock, object_or_none

from .progress import BoosterInfoResponse

NO_OFFER = -1
"""The ``PO`` of a hire that uses no booster sale."""

OVERSEERS = frozenset(
    {
        BoosterId.OVERSEER_WOOD,
        BoosterId.OVERSEER_STONE,
        BoosterId.OVERSEER_FOOD,
        BoosterId.OVERSEER_HONEY,
        BoosterId.OVERSEER_MEAD,
        BoosterId.OVERSEER_BEEF,
    }
)
"""The boosters ``ovs`` hires."""


class HireRequest(BaseRequest):
    """What every booster hire sends: the booster sale it uses."""

    private_offer_id: int = Field(
        validation_alias="PO", default=NO_OFFER, description="The booster sale the hire uses, -1 for none"
    )


class HireInstructorRequest(HireRequest):
    """
    Hire the instructor.

    Command: bis
    Payload: {"PO": offer_id}

    Client: ``C2SInstructorStartVO`` (bundle line 270788), sent by ``BuyBoosterCommand.execute``
    (bundle line 459673) and ``CastleBuyInstructorDialog.onClick`` (bundle line 461410) with
    ``CastleBoosterSaleData.getOfferId`` (bundle line 52882)
    """

    command = "bis"


class HireMarauderRequest(HireRequest):
    """
    Hire the marauder.

    Command: bms
    Payload: {"PO": offer_id}

    Client: ``C2SMarauderStartVO`` (bundle line 270811), sent by ``BuyBoosterCommand.execute``
    (bundle line 459673) with ``CastleBoosterSaleData.getOfferId`` (bundle line 52882)
    """

    command = "bms"


class HireOverseerRequest(HireRequest):
    """
    Hire the overseer of one resource.

    Command: ovs
    Payload: {"T": overseer, "PO": offer_id}

    Client: ``C2SOverseerStartVO`` (bundle line 213906); ``BuyBoosterCommand.execute`` (bundle line
    459673) sends ``CastlePremiumBoostData.BOOST_*`` (bundle line 81830) for each ``BoosterConst.OVERSEER_*``,
    the same numbers, and ``CastleBuyResourceBoostDialog.onClick`` (bundle line 82986) sends the booster id itself
    """

    command = "ovs"

    overseer: BoosterId = Field(validation_alias="T", description="The overseer, one of OVERSEERS")


class HireCaravanOverloaderRequest(HireRequest):
    """
    Hire the caravan overloader.

    Command: bcs
    Payload: {"PO": offer_id}

    Client: ``C2SCaravanOverloaderStartVO`` (bundle line 229369), sent by ``BuyBoosterCommand.execute``
    (bundle line 459673) with ``CastleBoosterSaleData.getOfferId`` (bundle line 52882)
    """

    command = "bcs"


class BuyReturnSpeedBoosterRequest(HireRequest):
    """
    Buy the return speed booster.

    Command: brs
    Payload: {"PO": offer_id}

    Client: ``C2SReturnSpeedBoosterStartVO`` (bundle line 463110), sent by
    ``CastleBuyReturnSpeedBoosterDialog.onClick`` (bundle line 463069) with
    ``CastleBoosterSaleData.getOfferId`` (bundle line 52882)
    """

    command = "brs"


class HireResponse(BaseResponse):
    """
    Your coins and rubies and your boosters after a hire; the boosters also reach ``client.player.boosts``.

    Client: ``BCSCommand``, ``BMSCommand``, ``BRSCommand``, ``OVSCommand`` and ``BISCommand``
    ``executeCommand`` (bundle lines 627398, 627622, 627711, 627756, 627576) hand ``gcu`` to
    ``parseGCU`` and ``boi`` to ``CastlePremiumBoostData.parse_BOI``, which skips a falsy one
    """

    currencies: CurrencyBlock = Field(validation_alias="gcu", default=None, description="Coins and rubies after")
    boosts: Annotated[BoosterInfoResponse | None, BeforeValidator(object_or_none)] = Field(
        validation_alias="boi", default=None, description="The boosters after; None when the reply has none"
    )


class HireInstructorResponse(HireResponse):
    """
    The reply to hiring the instructor, with the joined castle's production area.

    Command: bis
    Client: ``BISCommand.executeCommand`` (bundle line 627576) also hands ``gpa`` to the active
    area's ``parseGPA``
    """

    command = "bis"

    production_area: Annotated[CastleProductionArea | None, BeforeValidator(object_or_none)] = Field(
        validation_alias="gpa",
        default=None,
        description="The joined castle's production area after; None when the reply has none",
    )


class HireMarauderResponse(HireResponse):
    """
    The reply to hiring the marauder.

    Command: bms
    Client: ``BMSCommand.executeCommand`` (bundle line 627622)
    """

    command = "bms"


class HireOverseerResponse(HireResponse):
    """
    The reply to hiring an overseer.

    Command: ovs
    Client: ``OVSCommand.executeCommand`` (bundle line 627756)
    """

    command = "ovs"


class HireCaravanOverloaderResponse(HireResponse):
    """
    The reply to hiring the caravan overloader.

    Command: bcs
    Client: ``BCSCommand.executeCommand`` (bundle line 627398)
    """

    command = "bcs"


class BuyReturnSpeedBoosterResponse(HireResponse):
    """
    The reply to buying the return speed booster.

    Command: brs
    Client: ``BRSCommand.executeCommand`` (bundle line 627711)
    """

    command = "brs"


__all__ = [
    "NO_OFFER",
    "OVERSEERS",
    "BuyReturnSpeedBoosterRequest",
    "BuyReturnSpeedBoosterResponse",
    "HireCaravanOverloaderRequest",
    "HireCaravanOverloaderResponse",
    "HireInstructorRequest",
    "HireInstructorResponse",
    "HireMarauderRequest",
    "HireMarauderResponse",
    "HireOverseerRequest",
    "HireOverseerResponse",
    "HireRequest",
    "HireResponse",
]
