"""A castle's resources and production.

Commands:
- grc: Get a castle's resources
- gpa: Get the joined castle's production area
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from empire_core.enums import Kingdom
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse
from empire_core.protocol.js import ClientInt, js_same_number

from .details import CastleProductionArea


class CastleResources(BasePayload):
    """
    A castle's resources, the ``grc`` block.

    Client: ``CastleResourcesVO.parseGRC`` (bundle line 131537), which reads
    ``AID`` and ``KID`` through ``int()``; ``AreaDataStorageItem.parseGRC``
    (bundle line 131382) reads each amount through ``int()``
    """

    castle_id: ClientInt = Field(alias="AID", default=0, description="The castle's object id")
    kingdom_id: ClientInt = Field(alias="KID", default=0, description="The castle's kingdom")
    wood: ClientInt = Field(alias="W", default=0, description="Wood in stock")
    stone: ClientInt = Field(alias="S", default=0, description="Stone in stock")
    food: ClientInt = Field(alias="F", default=0, description="Food in stock")
    coal: ClientInt = Field(alias="C", default=0, description="Coal in stock")
    oil: ClientInt = Field(alias="O", default=0, description="Oil in stock")
    glass: ClientInt = Field(alias="G", default=0, description="Glass in stock")
    iron: ClientInt = Field(alias="I", default=0, description="Iron in stock")
    aquamarine: ClientInt = Field(alias="A", default=0, description="Aquamarine in stock")
    honey: ClientInt = Field(alias="HONEY", default=0, description="Honey in stock")
    mead: ClientInt = Field(alias="MEAD", default=0, description="Mead in stock")
    beef: ClientInt = Field(alias="BEEF", default=0, description="Beef in stock")


# =============================================================================
# GRC - Get Castle Resources
# =============================================================================


class GetResourcesRequest(BaseRequest):
    """
    Get one of your castles' resources.

    Command: grc
    Payload: {"AID": castle_id, "KID": kingdom_id}

    Client: ``C2SGetCastleResourcesVO`` (bundle line 19925), sent for a
    castle picked in the resource transfer dialog (bundle line 38076)
    """

    command = "grc"

    castle_id: int = Field(
        alias="AID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    kingdom_id: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The castle's kingdom")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a grc reply is about this castle: its ``AID``, when sent, is the one asked for.

        Client: ``GRCCommand.exec`` (bundle line 123063) through
        ``AreaDataUpdater.parseGRC`` (bundle line 131501), which applies a reply only
        to the area whose id is its ``AID``.
        """
        if not isinstance(payload, dict) or "AID" not in payload:
            return True
        return js_same_number(payload["AID"], self.castle_id)


class GetResourcesResponse(CastleResources, BaseResponse):
    """
    A castle's resources.

    Command: grc
    Payload: {"AID": castle_id, "KID": kingdom_id, "W": .., "S": .., "F": .., ...}

    Client: ``GRCCommand.exec`` (bundle line 123063), which hands the reply to
    ``AreaDataUpdater.parseGRC`` (bundle line 131501)
    """

    command = "grc"


# =============================================================================
# GPA - Get Production Area
# =============================================================================


class GetProductionRequest(BaseRequest):
    """
    Get the joined castle's production area.

    Command: gpa
    Payload: {}

    The server answers for the castle joined with ``jca``.

    Client: ``C2SGetCastleProductionDataVO`` (bundle line 25082)
    """

    command = "gpa"


class GetProductionResponse(CastleProductionArea, BaseResponse):
    """
    The joined castle's production area.

    Command: gpa

    Client: ``GPACommand.exec`` (bundle line 123031), which hands the reply to
    ``AreaDataUpdater.parseGPA`` (bundle line 131506)
    """

    command = "gpa"


__all__ = [
    "CastleResources",
    "GetResourcesRequest",
    "GetResourcesResponse",
    "GetProductionRequest",
    "GetProductionResponse",
]
