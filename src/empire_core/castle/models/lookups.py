"""
Reads behind single castle dialogs: where a building can be upgraded, what a castle transport takes
along, and the feast discount.

Commands:
- sub: your castles holding a building that can be upgraded, for a prime sale
- gctb: the main castle's buildings a castle transport to the Outer Realms takes along
- fce: the discount on feasts
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BeforeValidator, Field, field_validator, model_validator

from empire_core.enums import Kingdom
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, ClientNumber, js_int, js_truthy

if TYPE_CHECKING:
    from empire_core.gamedata import Building

logger = logging.getLogger(__name__)


class ShowUpgradableBuildingsRequest(BaseRequest):
    """
    Find your castles holding a building of one type that a prime sale can upgrade.

    Command: sub
    Payload: {"WOD": wod_id, "PSU": prime_sale_upgrade}

    Client: ``C2SShowMeUpgradeBuildingsVO`` (bundle line 96695), sent by ``CastlePrimeSaleDialog.onOkButton``
    (bundle line 37771)
    """

    command = "sub"

    wod_id: EnumOrInt["Building"] = Field(validation_alias="WOD", description="The building type the sale is for")
    prime_sale_upgrade: bool = Field(
        validation_alias="PSU", default=True, description="The sale discounts the upgrade of every level"
    )


class UpgradableBuilding(BasePayload):
    """
    Where a building can be upgraded, sent as ``[kingdom, castle_id, object_id?]``.

    Client: ``CastlePrimeSaleDialog.goToCastleAndObject`` (bundle line 37786) joins ``[1]`` in kingdom ``[0]``
    and centres on object ``[2]`` when it is above 0
    """

    kingdom: EnumOrInt[Kingdom] = Field(description="The castle's kingdom")
    castle_id: ClientInt = Field(description="The castle's id")
    object_id: ClientInt = Field(default=-1, description="The building's object id, -1 when not sent")

    @model_validator(mode="before")
    @classmethod
    def _from_list(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        return dict(zip(("kingdom", "castle_id", "object_id"), data, strict=False))

    _kingdom = field_validator("kingdom", mode="before")(js_int)


def _upgradable(value: Any) -> list[UpgradableBuilding]:
    return readable_list(UpgradableBuilding, value, warn=logger, what="upgradable buildings")


class ShowUpgradableBuildingsResponse(BaseResponse):
    """
    Your castles holding the building.

    Command: sub
    Payload: {"WOD": wod_id, "UD": [[kingdom, castle_id, object_id?], ...], "BE": exists}

    With no castle listed, the client tells by ``BE`` whether the building exists at all.

    Client: ``SUBCommand.executeCommand`` (bundle line 129862), ``CastlePrimeSaleDialog.onShowmeUpgradeDataReceived``
    (bundle line 37772)
    """

    command = "sub"

    wod_id: Annotated[EnumOrInt["Building"], BeforeValidator(js_int)] = Field(
        validation_alias="WOD", default=-1, description="The building type asked for"
    )
    buildings: list[UpgradableBuilding] = Field(
        validation_alias="UD", default_factory=list, description="Where it can be upgraded"
    )
    building_exists: bool = Field(
        validation_alias="BE", default=False, description="Whether you have the building at all"
    )

    _buildings = field_validator("buildings", mode="before")(_upgradable)
    _exists = field_validator("building_exists", mode="before")(js_truthy)


class GetTransportationBuildingsRequest(BaseRequest):
    """
    Read the buildings a castle transport to the Outer Realms takes along.

    Command: gctb
    Payload: {}

    Client: ``C2SGetCastleTransportationBuildingsVO`` (bundle line 71622), sent by
    ``CastleSpecialServerPreBuildCastleSelectionDialog.showLoaded`` (bundle line 27960)
    """

    command = "gctb"


class TransportationBuilding(BasePayload):
    """
    A building type and how many go along, sent as ``[wod_id, amount]``.

    Client: ``PrebuiltCastleData.parseCastleTransportationBuildings`` (bundle line 142315)
    """

    wod_id: Annotated[EnumOrInt["Building"], BeforeValidator(js_int)] = Field(description="The building type")
    amount: ClientInt = Field(default=0, description="How many go along")

    @model_validator(mode="before")
    @classmethod
    def _from_list(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        return dict(zip(("wod_id", "amount"), data, strict=False))


def _transported(value: Any) -> list[TransportationBuilding]:
    return readable_list(TransportationBuilding, value, warn=logger, what="transportation buildings")


class TransportationBuildingsResponse(BaseResponse):
    """
    The main castle's buildings a castle transport takes along.

    Command: gctb
    Payload: {"BL": [[wod_id, amount], ...]}

    Client: ``GCTBCommand.executeCommand`` (bundle line 128860),
    ``PrebuiltCastleData.parseCastleTransportationBuildings`` (bundle line 142315)
    """

    command = "gctb"

    buildings: list[TransportationBuilding] = Field(
        validation_alias="BL", default_factory=list, description="The buildings and their counts"
    )

    _buildings = field_validator("buildings", mode="before")(_transported)


class GetFeastCostReductionRequest(BaseRequest):
    """
    Read the discount on feasts.

    Command: fce
    Payload: {}

    Client: ``C2SGetFeastCostReductionVO`` (bundle line 41496), sent by ``CastleFestivalDialog`` and
    ``CastleExtendFestivalDialog`` (bundle lines 65030, 64943)
    """

    command = "fce"


class FeastCostReductionResponse(BaseResponse):
    """
    The discount on feasts.

    Command: fce
    Payload: {"FRM": percent}

    Client: ``FCECommand`` (bundle line 122929), ``CastleFestivalDialog.onFCEArrived`` (bundle line 65044)
    """

    command = "fce"

    reduction_percent: ClientNumber = Field(validation_alias="FRM", default=0, description="Percent off a feast")


__all__ = [
    "FeastCostReductionResponse",
    "GetFeastCostReductionRequest",
    "GetTransportationBuildingsRequest",
    "ShowUpgradableBuildingsRequest",
    "ShowUpgradableBuildingsResponse",
    "TransportationBuilding",
    "TransportationBuildingsResponse",
    "UpgradableBuilding",
]
