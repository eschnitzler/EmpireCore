"""Spy protocol models.

Commands:
- csm: Send spy mission
- ssi: Spy screen info
"""

from __future__ import annotations

import logging

from pydantic import Field, ValidatorFunctionWrapHandler, field_validator

from empire_core.enums import Kingdom, SpyType
from empire_core.movements.models import MovementOwner, MovementSpy, MovementWrapper
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock, read_or_none, readable_list
from empire_core.protocol.js import js_truthy

logger = logging.getLogger(__name__)

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
    The spy mission the server created.

    Command: csm
    Payload::

        {"A": {"M": {movement}, "S": {"ST": spy_type, "SA": accuracy, "SC": spies, "SR": risk}},
         "O": [owner record, ...], "gcu": {currencies}}

    ``A`` is read like a ``gam`` entry; ``gcu`` may be missing.

    Client: ``CSMCommand.executeCommand`` (bundle line 125993), which passes
    ``[i.A]`` to ``CastleArmyData.parseMapMovementArray`` (bundle line 133626),
    ``i.O`` to ``CastleOtherPlayerData.parseOwnerInfoArray`` (bundle line 139005)
    and ``i.gcu`` to ``CurrencyData.parseGCU`` (bundle line 141191);
    ``SpyMapmovementVO.loadFromParamObject`` (bundle line 43748)
    """

    command = "csm"

    spy_movement: MovementWrapper | None = Field(
        alias="A", default=None, description="The spy movement; None when there is none"
    )
    owners: list[MovementOwner] = Field(
        alias="O", default_factory=list, description="Owner records for the movement's areas"
    )
    currencies: CurrencyBlock = Field(
        alias="gcu", default=None, description="Coins and rubies after the send; None when the reply has none"
    )

    @field_validator("spy_movement", mode="wrap")
    @classmethod
    def _movement_or_none(cls, value: object, handler: ValidatorFunctionWrapHandler) -> MovementWrapper | None:
        if not value:
            return None
        return read_or_none(handler, value, warn=logger, what="the movement created by csm")

    @field_validator("owners", mode="before")
    @classmethod
    def _readable_owners(cls, value: object) -> list[MovementOwner]:
        return readable_list(
            MovementOwner,
            value,
            accept=lambda record: isinstance(record, dict),
            keep=lambda record: js_truthy(record.get("OID")),
            warn=logger,
            what="owner records sent with csm",
        )

    @property
    def movement_id(self) -> int | None:
        """The spy movement's id, or None when the reply has no movement."""
        return self.spy_movement.movement.movement_id if self.spy_movement else None

    @property
    def seconds_until_arrival(self) -> int | None:
        """
        Seconds from the reply until the spies arrive: ``TT - PT``, never below 0.

        Client: ``BasicMapmovementVO.loadFromParamObject`` (bundle line 19382)
        """
        if not self.spy_movement:
            return None
        movement = self.spy_movement.movement
        return max(0, movement.total_time - movement.progress_time)

    @property
    def spy(self) -> MovementSpy | None:
        """The mission's spy type, accuracy, spy count and risk."""
        return self.spy_movement.spy if self.spy_movement else None


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
