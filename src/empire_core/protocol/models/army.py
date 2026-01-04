"""
Army and hospital protocol models.

Commands:
- bup: Build units / produce
- spl: Get production list/queue
- bou: Double production slot
- mcu: Cancel production
- gui: Get units inventory
- dup: Delete units
- hru: Heal units
- hcs: Cancel heal
- hss: Skip heal (rubies)
- hdu: Delete wounded
- hra: Heal all
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from .base import BaseRequest, BaseResponse, UnitCount

# =============================================================================
# BUP - Build Units / Produce
# =============================================================================


class ProduceUnitsRequest(BaseRequest):
    """
    Start production of units or tools.

    Command: bup
    Payload: {
        "CID": castle_id,
        "BID": building_id,
        "UID": unit_type_id,
        "C": count,
        "LID": list_id  # 0=soldiers, 1=tools
    }
    """

    command = "bup"

    castle_id: int = Field(alias="CID")
    building_id: int = Field(alias="BID")
    unit_id: int = Field(alias="UID")
    count: int = Field(alias="C")
    list_id: int = Field(alias="LID", default=0)  # 0=soldiers, 1=tools


class ProduceUnitsResponse(BaseResponse):
    """
    Response to production request.

    Command: bup
    """

    command = "bup"

    queue_id: int = Field(alias="QID", default=0)
    completion_time: int = Field(alias="CT", default=0)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# SPL - Get Production List
# =============================================================================


class GetProductionQueueRequest(BaseRequest):
    """
    Get production queue for a building.

    Command: spl
    Payload: {"CID": castle_id, "BID": building_id, "LID": list_id}

    List types (LID):
    - 0: Soldiers
    - 1: Tools
    """

    command = "spl"

    castle_id: int = Field(alias="CID")
    building_id: int = Field(alias="BID")
    list_id: int = Field(alias="LID", default=0)


class ProductionQueueItem(BaseResponse):
    """An item in the production queue."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    queue_id: int = Field(alias="QID")
    unit_id: int = Field(alias="UID")
    count: int = Field(alias="C")
    remaining: int = Field(alias="R", default=0)
    completion_time: int = Field(alias="CT", default=0)


class GetProductionQueueResponse(BaseResponse):
    """
    Response containing production queue.

    Command: spl
    """

    command = "spl"

    queue: list[ProductionQueueItem] = Field(alias="Q", default_factory=list)


# =============================================================================
# BOU - Double Production Slot
# =============================================================================


class DoubleProductionRequest(BaseRequest):
    """
    Double a production slot (produce twice as fast).

    Command: bou
    Payload: {"CID": castle_id, "BID": building_id, "QID": queue_id}
    """

    command = "bou"

    castle_id: int = Field(alias="CID")
    building_id: int = Field(alias="BID")
    queue_id: int = Field(alias="QID")


class DoubleProductionResponse(BaseResponse):
    """
    Response to doubling production.

    Command: bou
    """

    command = "bou"

    success: bool = Field(default=True)
    rubies_spent: int = Field(alias="RS", default=0)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# MCU - Cancel Production
# =============================================================================


class CancelProductionRequest(BaseRequest):
    """
    Cancel a production queue item.

    Command: mcu
    Payload: {"CID": castle_id, "BID": building_id, "QID": queue_id}
    """

    command = "mcu"

    castle_id: int = Field(alias="CID")
    building_id: int = Field(alias="BID")
    queue_id: int = Field(alias="QID")


class CancelProductionResponse(BaseResponse):
    """
    Response to canceling production.

    Command: mcu
    """

    command = "mcu"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# GUI - Get Units Inventory
# =============================================================================


class GetUnitsRequest(BaseRequest):
    """
    Get units inventory for a castle.

    Command: gui
    Payload: {"CID": castle_id}
    """

    command = "gui"

    castle_id: int = Field(alias="CID")


class GetUnitsResponse(BaseResponse):
    """
    Response containing units inventory.

    Command: gui
    """

    command = "gui"

    units: list[UnitCount] = Field(alias="U", default_factory=list)
    tools: list[UnitCount] = Field(alias="T", default_factory=list)


# =============================================================================
# DUP - Delete Units
# =============================================================================


class DeleteUnitsRequest(BaseRequest):
    """
    Delete units from inventory.

    Command: dup
    Payload: {"CID": castle_id, "UID": unit_id, "C": count}
    """

    command = "dup"

    castle_id: int = Field(alias="CID")
    unit_id: int = Field(alias="UID")
    count: int = Field(alias="C")


class DeleteUnitsResponse(BaseResponse):
    """
    Response to deleting units.

    Command: dup
    """

    command = "dup"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# HRU - Heal Units
# =============================================================================


class HealUnitsRequest(BaseRequest):
    """
    Heal wounded units.

    Command: hru
    Payload: {"CID": castle_id, "UID": unit_id, "C": count}
    """

    command = "hru"

    castle_id: int = Field(alias="CID")
    unit_id: int = Field(alias="UID")
    count: int = Field(alias="C")


class HealUnitsResponse(BaseResponse):
    """
    Response to healing units.

    Command: hru
    """

    command = "hru"

    queue_id: int = Field(alias="QID", default=0)
    completion_time: int = Field(alias="CT", default=0)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# HCS - Cancel Heal
# =============================================================================


class CancelHealRequest(BaseRequest):
    """
    Cancel healing queue item.

    Command: hcs
    Payload: {"CID": castle_id, "QID": queue_id}
    """

    command = "hcs"

    castle_id: int = Field(alias="CID")
    queue_id: int = Field(alias="QID")


class CancelHealResponse(BaseResponse):
    """
    Response to canceling heal.

    Command: hcs
    """

    command = "hcs"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# HSS - Skip Heal (Rubies)
# =============================================================================


class SkipHealRequest(BaseRequest):
    """
    Skip healing time using rubies.

    Command: hss
    Payload: {"CID": castle_id, "QID": queue_id}
    """

    command = "hss"

    castle_id: int = Field(alias="CID")
    queue_id: int = Field(alias="QID")


class SkipHealResponse(BaseResponse):
    """
    Response to skipping heal.

    Command: hss
    """

    command = "hss"

    success: bool = Field(default=True)
    rubies_spent: int = Field(alias="RS", default=0)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# HDU - Delete Wounded
# =============================================================================


class DeleteWoundedRequest(BaseRequest):
    """
    Delete wounded units (don't heal them).

    Command: hdu
    Payload: {"CID": castle_id, "UID": unit_id, "C": count}
    """

    command = "hdu"

    castle_id: int = Field(alias="CID")
    unit_id: int = Field(alias="UID")
    count: int = Field(alias="C")


class DeleteWoundedResponse(BaseResponse):
    """
    Response to deleting wounded.

    Command: hdu
    """

    command = "hdu"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# HRA - Heal All
# =============================================================================


class HealAllRequest(BaseRequest):
    """
    Heal all wounded units.

    Command: hra
    Payload: {"CID": castle_id}
    """

    command = "hra"

    castle_id: int = Field(alias="CID")


class HealAllResponse(BaseResponse):
    """
    Response to healing all.

    Command: hra
    """

    command = "hra"

    units_healed: int = Field(alias="UH", default=0)
    completion_time: int = Field(alias="CT", default=0)
    error_code: int = Field(alias="E", default=0)


__all__ = [
    # BUP - Produce Units
    "ProduceUnitsRequest",
    "ProduceUnitsResponse",
    # SPL - Production Queue
    "GetProductionQueueRequest",
    "GetProductionQueueResponse",
    "ProductionQueueItem",
    # BOU - Double Production
    "DoubleProductionRequest",
    "DoubleProductionResponse",
    # MCU - Cancel Production
    "CancelProductionRequest",
    "CancelProductionResponse",
    # GUI - Get Units
    "GetUnitsRequest",
    "GetUnitsResponse",
    # DUP - Delete Units
    "DeleteUnitsRequest",
    "DeleteUnitsResponse",
    # HRU - Heal Units
    "HealUnitsRequest",
    "HealUnitsResponse",
    # HCS - Cancel Heal
    "CancelHealRequest",
    "CancelHealResponse",
    # HSS - Skip Heal
    "SkipHealRequest",
    "SkipHealResponse",
    # HDU - Delete Wounded
    "DeleteWoundedRequest",
    "DeleteWoundedResponse",
    # HRA - Heal All
    "HealAllRequest",
    "HealAllResponse",
]
