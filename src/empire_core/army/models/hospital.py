"""Hospital protocol models.

Commands:
- hru: Heal wounded units
- hcs: Cancel a hospital slot
- hss: Skip a hospital slot (rubies)
- hdu: Dismiss wounded units
- hra: Heal all wounded units (rubies)

These act on the castle the session has joined (``jca``).
"""

from __future__ import annotations

from pydantic import Field

from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, CurrencyBlock

from .production import ProductionListBlock
from .units import RawBlock, UnitInventoryBlock

# =============================================================================
# HRU - Heal Units
# =============================================================================


class HealUnitsRequest(BaseRequest):
    """
    Queue wounded units of the joined castle for healing.

    Command: hru
    Payload: {"U": wod_id, "A": amount}

    Client: ``C2SReviveUnitPackageVO`` (bundle line 84175), built by
    ``CastleRecruitSelectedUnitComponent.onReviveClick`` (bundle line 51105)
    """

    command = "hru"

    wod_id: int = Field(validation_alias="U", serialization_alias="U")
    amount: int = Field(validation_alias="A", serialization_alias="A")


class HealUnitsResponse(BaseResponse):
    """
    The joined castle after an ``hru``.

    Command: hru

    Client: ``HRUCommand.executeCommand`` (bundle line 124532)
    """

    command = "hru"

    production_list: ProductionListBlock = Field(validation_alias="spl", serialization_alias="spl", default=None)
    currencies: CurrencyBlock = Field(
        validation_alias="gcu", serialization_alias="gcu", default=None, description="Coins and rubies after the change"
    )
    unit_inventory: UnitInventoryBlock = Field(validation_alias="gui", serialization_alias="gui", default=None)


# =============================================================================
# HCS - Cancel Hospital Slot
# =============================================================================


class CancelHealRequest(BaseRequest):
    """
    Cancel a hospital slot of the joined castle.

    Command: hcs
    Payload: {"S": position}

    Client: ``C2SCancelHospitalSlot`` (bundle line 83616), built by
    ``CastleRecruitDialogHospital.onCurrentSlotCancelled`` (bundle line 83508)
    """

    command = "hcs"

    position: int = Field(
        validation_alias="S", serialization_alias="S", description="The slot's index in the hospital list"
    )


class CancelHealResponse(BaseResponse):
    """
    The joined castle after an ``hcs``.

    Command: hcs

    Client: ``HCSCommand.executeCommand`` (bundle line 124454)
    """

    command = "hcs"

    production_list: ProductionListBlock = Field(validation_alias="spl", serialization_alias="spl", default=None)
    unit_inventory: UnitInventoryBlock = Field(validation_alias="gui", serialization_alias="gui", default=None)


# =============================================================================
# HSS - Skip Hospital Slot
# =============================================================================


class SkipHealRequest(BaseRequest):
    """
    Finish a hospital slot of the joined castle now, for rubies.

    Command: hss
    Payload: {"S": position}

    Client: ``C2SSkipHospitalSlot`` (bundle line 83625), built by
    ``CastleRecruitDialogHospital`` (bundle line 83504)
    """

    command = "hss"

    position: int = Field(
        validation_alias="S", serialization_alias="S", description="The slot's index in the hospital list"
    )


class SkipHealResponse(BaseResponse):
    """
    Currencies after an ``hss``.

    Command: hss

    Client: ``HSSCommand.executeCommand`` (bundle line 50856)
    """

    command = "hss"

    currencies: CurrencyBlock = Field(
        validation_alias="gcu", serialization_alias="gcu", default=None, description="Coins and rubies after the change"
    )


# =============================================================================
# HDU - Dismiss Wounded
# =============================================================================


class DismissWoundedRequest(BaseRequest):
    """
    Dismiss wounded units of one type in the joined castle.

    Command: hdu
    Payload: {"U": wod_id, "A": amount}

    Client: ``C2SDismissHospitalUnits`` (bundle line 83748), built by
    ``CastleHospitalDismissUnitsDialog.dismissUnits`` (bundle line 83737)
    """

    command = "hdu"

    wod_id: int = Field(validation_alias="U", serialization_alias="U")
    amount: int = Field(validation_alias="A", serialization_alias="A")


class WoundedUnits(BasePayload):
    """One ``UT`` entry of a many-type ``hdu``."""

    wod_id: int = Field(validation_alias="U", serialization_alias="U")
    amount: int = Field(validation_alias="A", serialization_alias="A")


class DismissManyWoundedRequest(BaseRequest):
    """
    Dismiss wounded units of several types in the joined castle.

    Command: hdu
    Payload: {"UT": [{"U": wod_id, "A": amount}, ...]}

    Client: ``C2SDismissManyHospitalUnits`` (bundle line 83834), built by
    ``CastleRecruitDialogHospital.onConfirmDeleteAll`` (bundle line 83498)
    """

    command = "hdu"

    units: list[WoundedUnits] = Field(validation_alias="UT", serialization_alias="UT")


class DismissWoundedResponse(BaseResponse):
    """
    The joined castle after an ``hdu``.

    Command: hdu

    Client: ``HDUCommand.executeCommand`` (bundle line 124470)
    """

    command = "hdu"

    unit_inventory: UnitInventoryBlock = Field(validation_alias="gui", serialization_alias="gui", default=None)


# =============================================================================
# HRA - Heal All
# =============================================================================


class HealAllRequest(BaseRequest):
    """
    Heal every wounded unit of the joined castle at once, for rubies.

    Command: hra
    Payload: {"C2": ruby_cost}

    ``C2`` is the price the client shows: the sum over the hospital of
    ``int(amount * reviveAllCostC2)``, less the active prime-sales revive-all
    discount percent, rounded up. The server answers ``INVALID_AMOUNT`` when
    the hospital changed ("alert_hospital_amountOutdated").

    Client: ``C2SReviveAllHospitalUnits`` (bundle line 83677), sent by
    ``CastleHospitalReviveAllDialog.reviveAll`` (bundle line 83667) with the
    price from ``CastleRecruitDialogHospital.openReviveAllDialog`` (bundle line 83509)
    """

    command = "hra"

    ruby_cost: int = Field(validation_alias="C2", serialization_alias="C2")


class HealAllResponse(BaseResponse):
    """
    The joined castle after an ``hra``.

    Command: hra

    Client: ``HRACommand.executeCommand`` (bundle line 124513)
    """

    command = "hra"

    currencies: CurrencyBlock = Field(
        validation_alias="gcu", serialization_alias="gcu", default=None, description="Coins and rubies after the change"
    )
    unit_inventory: UnitInventoryBlock = Field(validation_alias="gui", serialization_alias="gui", default=None)
    production_area: RawBlock = Field(
        validation_alias="gpa",
        serialization_alias="gpa",
        default=None,
        description="The castle's production and storage figures, as a raw block",
    )


__all__ = [
    "HealUnitsRequest",
    "HealUnitsResponse",
    "CancelHealRequest",
    "CancelHealResponse",
    "SkipHealRequest",
    "SkipHealResponse",
    "DismissWoundedRequest",
    "DismissManyWoundedRequest",
    "WoundedUnits",
    "DismissWoundedResponse",
    "HealAllRequest",
    "HealAllResponse",
]
