"""
Building protocol models.

Commands:
- ebu: Build (erect building)
- eup: Upgrade building
- emo: Move building
- sbd: Sell building
- edo: Destroy building
- fco: Fast complete (skip construction with rubies)
- msb: Time skip building
- eud: Upgrade wall/defense
- rbu: Repair building
- ira: Repair all buildings
- ebe: Buy castle extension
- etc: Collect extension gift
"""

from __future__ import annotations

from pydantic import Field

from .base import BaseRequest, BaseResponse

# =============================================================================
# EBU - Build (Erect Building)
# =============================================================================


class BuildRequest(BaseRequest):
    """
    Build a new building.

    Command: ebu
    Payload: {"CID": castle_id, "BT": building_type, "X": x, "Y": y}
    """

    command = "ebu"

    castle_id: int = Field(alias="CID")
    building_type: int = Field(alias="BT")
    x: int = Field(alias="X")
    y: int = Field(alias="Y")


class BuildResponse(BaseResponse):
    """
    Response to building construction.

    Command: ebu
    """

    command = "ebu"

    building_id: int = Field(alias="BID", default=0)
    completion_time: int = Field(alias="CT", default=0)  # Unix timestamp
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# EUP - Upgrade Building
# =============================================================================


class UpgradeBuildingRequest(BaseRequest):
    """
    Upgrade an existing building.

    Command: eup
    Payload: {"CID": castle_id, "BID": building_id}
    """

    command = "eup"

    castle_id: int = Field(alias="CID")
    building_id: int = Field(alias="BID")


class UpgradeBuildingResponse(BaseResponse):
    """
    Response to building upgrade.

    Command: eup
    """

    command = "eup"

    new_level: int = Field(alias="L", default=0)
    completion_time: int = Field(alias="CT", default=0)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# EMO - Move Building
# =============================================================================


class MoveBuildingRequest(BaseRequest):
    """
    Move a building to a new position.

    Command: emo
    Payload: {"CID": castle_id, "BID": building_id, "X": x, "Y": y}
    """

    command = "emo"

    castle_id: int = Field(alias="CID")
    building_id: int = Field(alias="BID")
    x: int = Field(alias="X")
    y: int = Field(alias="Y")


class MoveBuildingResponse(BaseResponse):
    """
    Response to building move.

    Command: emo
    """

    command = "emo"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# SBD - Sell Building
# =============================================================================


class SellBuildingRequest(BaseRequest):
    """
    Sell a building for resources.

    Command: sbd
    Payload: {"CID": castle_id, "BID": building_id}
    """

    command = "sbd"

    castle_id: int = Field(alias="CID")
    building_id: int = Field(alias="BID")


class SellBuildingResponse(BaseResponse):
    """
    Response to selling a building.

    Command: sbd
    """

    command = "sbd"

    resources_gained: int = Field(alias="RG", default=0)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# EDO - Destroy Building
# =============================================================================


class DestroyBuildingRequest(BaseRequest):
    """
    Destroy a building (no resources returned).

    Command: edo
    Payload: {"CID": castle_id, "BID": building_id}
    """

    command = "edo"

    castle_id: int = Field(alias="CID")
    building_id: int = Field(alias="BID")


class DestroyBuildingResponse(BaseResponse):
    """
    Response to destroying a building.

    Command: edo
    """

    command = "edo"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# FCO - Fast Complete (Skip Construction)
# =============================================================================


class FastCompleteRequest(BaseRequest):
    """
    Complete construction instantly using rubies.

    Command: fco
    Payload: {"CID": castle_id, "BID": building_id}
    """

    command = "fco"

    castle_id: int = Field(alias="CID")
    building_id: int = Field(alias="BID")


class FastCompleteResponse(BaseResponse):
    """
    Response to fast completion.

    Command: fco
    """

    command = "fco"

    success: bool = Field(default=True)
    rubies_spent: int = Field(alias="RS", default=0)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# MSB - Time Skip Building
# =============================================================================


class TimeSkipBuildingRequest(BaseRequest):
    """
    Skip some construction time using an item.

    Command: msb
    Payload: {"CID": castle_id, "BID": building_id, "IID": item_id}
    """

    command = "msb"

    castle_id: int = Field(alias="CID")
    building_id: int = Field(alias="BID")
    item_id: int = Field(alias="IID")


class TimeSkipBuildingResponse(BaseResponse):
    """
    Response to time skip.

    Command: msb
    """

    command = "msb"

    new_completion_time: int = Field(alias="CT", default=0)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# EUD - Upgrade Wall/Defense
# =============================================================================


class UpgradeWallRequest(BaseRequest):
    """
    Upgrade castle wall/defense level.

    Command: eud
    Payload: {"CID": castle_id, "WT": wall_type}
    """

    command = "eud"

    castle_id: int = Field(alias="CID")
    wall_type: int = Field(alias="WT", default=0)


class UpgradeWallResponse(BaseResponse):
    """
    Response to wall upgrade.

    Command: eud
    """

    command = "eud"

    new_level: int = Field(alias="L", default=0)
    completion_time: int = Field(alias="CT", default=0)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# RBU - Repair Building
# =============================================================================


class RepairBuildingRequest(BaseRequest):
    """
    Repair a damaged building.

    Command: rbu
    Payload: {"CID": castle_id, "BID": building_id}
    """

    command = "rbu"

    castle_id: int = Field(alias="CID")
    building_id: int = Field(alias="BID")


class RepairBuildingResponse(BaseResponse):
    """
    Response to building repair.

    Command: rbu
    """

    command = "rbu"

    completion_time: int = Field(alias="CT", default=0)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# IRA - Repair All Buildings
# =============================================================================


class RepairAllRequest(BaseRequest):
    """
    Repair all damaged buildings in a castle.

    Command: ira
    Payload: {"CID": castle_id}
    """

    command = "ira"

    castle_id: int = Field(alias="CID")


class RepairAllResponse(BaseResponse):
    """
    Response to repairing all buildings.

    Command: ira
    """

    command = "ira"

    buildings_repaired: int = Field(alias="BR", default=0)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# EBE - Buy Extension
# =============================================================================


class BuyExtensionRequest(BaseRequest):
    """
    Buy a castle extension (more building space).

    Command: ebe
    Payload: {"CID": castle_id, "ET": extension_type}
    """

    command = "ebe"

    castle_id: int = Field(alias="CID")
    extension_type: int = Field(alias="ET")


class BuyExtensionResponse(BaseResponse):
    """
    Response to buying extension.

    Command: ebe
    """

    command = "ebe"

    success: bool = Field(default=True)
    rubies_spent: int = Field(alias="RS", default=0)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# ETC - Collect Extension Gift
# =============================================================================


class CollectExtensionGiftRequest(BaseRequest):
    """
    Collect gift from extension.

    Command: etc
    Payload: {"CID": castle_id, "EID": extension_id}
    """

    command = "etc"

    castle_id: int = Field(alias="CID")
    extension_id: int = Field(alias="EID")


class CollectExtensionGiftResponse(BaseResponse):
    """
    Response to collecting extension gift.

    Command: etc
    """

    command = "etc"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


__all__ = [
    # EBU - Build
    "BuildRequest",
    "BuildResponse",
    # EUP - Upgrade
    "UpgradeBuildingRequest",
    "UpgradeBuildingResponse",
    # EMO - Move
    "MoveBuildingRequest",
    "MoveBuildingResponse",
    # SBD - Sell
    "SellBuildingRequest",
    "SellBuildingResponse",
    # EDO - Destroy
    "DestroyBuildingRequest",
    "DestroyBuildingResponse",
    # FCO - Fast Complete
    "FastCompleteRequest",
    "FastCompleteResponse",
    # MSB - Time Skip
    "TimeSkipBuildingRequest",
    "TimeSkipBuildingResponse",
    # EUD - Upgrade Wall
    "UpgradeWallRequest",
    "UpgradeWallResponse",
    # RBU - Repair
    "RepairBuildingRequest",
    "RepairBuildingResponse",
    # IRA - Repair All
    "RepairAllRequest",
    "RepairAllResponse",
    # EBE - Buy Extension
    "BuyExtensionRequest",
    "BuyExtensionResponse",
    # ETC - Collect Extension Gift
    "CollectExtensionGiftRequest",
    "CollectExtensionGiftResponse",
]
