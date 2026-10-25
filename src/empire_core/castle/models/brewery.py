"""
The relic brewery: how much of a castle's food and honey becomes mead.

Commands:
- abpi: read or set a brewery's production, and inside the ``jaa`` reply
- bfl: whether mead production comes before the castle's other food use
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_serializer, field_validator

from empire_core.enums import Kingdom
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse
from empire_core.protocol.js import ClientNumber, js_truthy


class MeadShare(BasePayload):
    """The share of the brewery's capacity that makes mead, a brewery's ``PA``."""

    mead_percent: ClientNumber = Field(validation_alias="MEAD", default=0, description="Percent producing mead")


class BreweryStops(BasePayload):
    """The stocks at which the brewery stops, a brewery's ``MS``."""

    food: ClientNumber = Field(validation_alias="F", default=0, description="Food left when production stops")
    honey: ClientNumber = Field(validation_alias="HONEY", default=0, description="Honey left when production stops")


class MeadPriority(BasePayload):
    """Whether mead comes first, a brewery's ``bfl``."""

    enabled: bool = Field(validation_alias="PPOT", default=False, description="Mead production has priority")

    @field_validator("enabled", mode="before")
    @classmethod
    def _enabled(cls, value: Any) -> bool:
        return value == 1


class GetBreweryProductionRequest(BaseRequest):
    """
    Read a castle's brewery production.

    Command: abpi
    Payload: {"KID": kingdom, "AID": castle_id, "WID": wod_id, "OID": object_id}

    Client: ``C2SGetAreaBuildingProductionVO`` (bundle line 138256), sent by
    ``CastleBreweryShortageDialog.showLoaded`` (bundle line 138227)
    """

    command = "abpi"

    kingdom_id: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    castle_id: int = Field(validation_alias="AID", description="The castle's id")
    wod_id: int = Field(validation_alias="WID", description="The brewery's wod id")
    object_id: int = Field(validation_alias="OID", description="The brewery's object id")


class SetBreweryProductionRequest(BaseRequest):
    """
    Set a castle's brewery production.

    Command: abpi
    Payload: {"KID": kingdom, "AID": castle_id, "WID": wod_id, "OID": object_id,
    "PA": {"MEAD": percent}, "MS": {"F": food, "HONEY": honey}}

    Client: ``C2SSetBreweryProductionVO`` (bundle line 83379), sent by the brewery dialog's save
    button (bundle line 36458)
    """

    command = "abpi"

    kingdom_id: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    castle_id: int = Field(validation_alias="AID", description="The castle's id")
    wod_id: int = Field(validation_alias="WID", description="The brewery's wod id")
    object_id: int = Field(validation_alias="OID", description="The brewery's object id")
    share: MeadShare = Field(validation_alias="PA", description="The share producing mead")
    stops: BreweryStops = Field(validation_alias="MS", description="The stocks at which production stops")


class BreweryProductionResponse(BaseResponse):
    """
    A castle's brewery production.

    Command: abpi, the reply to both requests and the first entry of a ``jaa`` reply's ``abpi``
    Payload: {"PA": {"MEAD": percent}, "MS": {"F": food, "HONEY": honey}, "SRPF": frozen, "bfl": {"PPOT": 0 or 1}}

    Client: ``ABPICommand.executeCommand`` (bundle line 122711), ``CastleBreweryData.parse_ABPI`` and
    ``parse_ABPI_intern`` (bundle lines 36498-36499); ``JAACommand`` (bundle line 130249)
    """

    command = "abpi"

    share: MeadShare = Field(validation_alias="PA", default_factory=MeadShare, description="The share producing mead")
    stops: BreweryStops = Field(
        validation_alias="MS", default_factory=BreweryStops, description="The stocks at which production stops"
    )
    production_frozen: bool = Field(
        validation_alias="SRPF", default=False, description="The server has stopped the production"
    )
    mead_priority: MeadPriority = Field(
        validation_alias="bfl", default_factory=MeadPriority, description="Whether mead production comes first"
    )

    _frozen = field_validator("production_frozen", mode="before")(js_truthy)

    @field_validator("share", "stops", "mead_priority", mode="before")
    @classmethod
    def _block(cls, value: Any) -> Any:
        return value if isinstance(value, (dict, BasePayload)) else {}


class SetMeadPriorityRequest(BaseRequest):
    """
    Give the joined castle's mead production priority, or take it away.

    Command: bfl
    Payload: {"KID": kingdom, "AID": castle_id, "PPOT": 0 or 1}

    Client: ``C2SSetMeadPrioVO`` (bundle line 83444), sent by the brewery dialog's priority checkbox
    (bundle line 36462)
    """

    command = "bfl"

    kingdom_id: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    castle_id: int = Field(validation_alias="AID", description="The castle's id")
    enabled: bool = Field(validation_alias="PPOT", description="Whether mead production comes first")

    @field_serializer("enabled")
    def _flag(self, value: bool) -> int:
        return 1 if value else 0


class SetMeadPriorityResponse(BaseResponse):
    """
    The priority was set; the client reads nothing from the reply.

    Command: bfl

    Client: ``BFLCommand.executeCommand`` (bundle line 122726)
    """

    command = "bfl"


__all__ = [
    "BreweryProductionResponse",
    "BreweryStops",
    "GetBreweryProductionRequest",
    "MeadPriority",
    "MeadShare",
    "SetBreweryProductionRequest",
    "SetMeadPriorityRequest",
    "SetMeadPriorityResponse",
]
