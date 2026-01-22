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


# =============================================================================
# CDS - Send Support (Create Deployment - Support)
# =============================================================================


class SendSupportRequest(BaseRequest):
    """
    Send support troops to a location.

    Command: cds
    Payload: {
        "SID": source_castle_id,
        "TX": target_x,
        "TY": target_y,
        "KID": kingdom_id (0=Green, 2=Ice, 1=Sand, 3=Fire),
        "LID": lord_id (-14 for coordinates/no lord),
        "WT": wait_time (station duration in hours, 0-12),
        "HBW": horses_type (-1 for default/none),
        "BPC": boost_with_coins (1 = use coins for faster travel, 0 = normal speed),
        "PTT": feathers (speed boost item, 1 = use, 0 = don't use),
        "SD": slowdown (movement slowdown modifier, 0 = none),
        "A": [[unit_id, count], ...]
    }
    """

    command = "cds"

    source_castle_id: int = Field(alias="SID")
    target_x: int = Field(alias="TX")
    target_y: int = Field(alias="TY")
    kingdom_id: int = Field(alias="KID", default=0)
    lord_id: int = Field(alias="LID", default=-14)
    wait_time: int = Field(alias="WT", default=12, ge=0, le=12)
    horses_type: int = Field(alias="HBW", default=-1)
    boost_with_coins: int = Field(alias="BPC", default=1)
    feathers: int = Field(alias="PTT", default=1)
    slowdown: int = Field(alias="SD", default=0)
    units: list[list[int]] = Field(alias="A")


class SendSupportResponse(BaseResponse):
    """
    Response to sending support.

    Command: cds
    """

    command = "cds"

    success: bool = Field(default=True)
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
    # SSP - Send Support
    "SendSupportRequest",
    "SendSupportResponse",
]
