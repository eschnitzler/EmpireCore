"""Hospital protocol models.

Commands:
- hru: Heal wounded units
- hcs: Cancel a hospital slot
- hss: Skip a hospital slot (rubies)
- hdu: Dismiss wounded units
- hra: Heal all wounded units (rubies)
- hfl: Read or set the hospital flags

These act on the castle the session has joined (``jca``); ``hfl`` also names it.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from empire_core.enums import Kingdom
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, CurrencyBlock
from empire_core.protocol.js import js_same_number, js_truthy

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

    wod_id: int = Field(validation_alias="U")
    amount: int = Field(validation_alias="A")


class HealUnitsResponse(BaseResponse):
    """
    The joined castle after an ``hru``.

    Command: hru

    Client: ``HRUCommand.executeCommand`` (bundle line 124532)
    """

    command = "hru"

    production_list: ProductionListBlock = Field(validation_alias="spl", default=None)
    currencies: CurrencyBlock = Field(
        validation_alias="gcu", default=None, description="Coins and rubies after the change"
    )
    unit_inventory: UnitInventoryBlock = Field(validation_alias="gui", default=None)


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

    position: int = Field(validation_alias="S", description="The slot's index in the hospital list")


class CancelHealResponse(BaseResponse):
    """
    The joined castle after an ``hcs``.

    Command: hcs

    Client: ``HCSCommand.executeCommand`` (bundle line 124454)
    """

    command = "hcs"

    production_list: ProductionListBlock = Field(validation_alias="spl", default=None)
    unit_inventory: UnitInventoryBlock = Field(validation_alias="gui", default=None)


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

    position: int = Field(validation_alias="S", description="The slot's index in the hospital list")


class SkipHealResponse(BaseResponse):
    """
    Currencies after an ``hss``.

    Command: hss

    Client: ``HSSCommand.executeCommand`` (bundle line 50856)
    """

    command = "hss"

    currencies: CurrencyBlock = Field(
        validation_alias="gcu", default=None, description="Coins and rubies after the change"
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

    wod_id: int = Field(validation_alias="U")
    amount: int = Field(validation_alias="A")


class WoundedUnits(BasePayload):
    """One ``UT`` entry of a many-type ``hdu``."""

    wod_id: int = Field(validation_alias="U")
    amount: int = Field(validation_alias="A")


class DismissManyWoundedRequest(BaseRequest):
    """
    Dismiss wounded units of several types in the joined castle.

    Command: hdu
    Payload: {"UT": [{"U": wod_id, "A": amount}, ...]}

    Client: ``C2SDismissManyHospitalUnits`` (bundle line 83834), built by
    ``CastleRecruitDialogHospital.onConfirmDeleteAll`` (bundle line 83498)
    """

    command = "hdu"

    units: list[WoundedUnits] = Field(validation_alias="UT")


class DismissWoundedResponse(BaseResponse):
    """
    The joined castle after an ``hdu``.

    Command: hdu

    Client: ``HDUCommand.executeCommand`` (bundle line 124470)
    """

    command = "hdu"

    unit_inventory: UnitInventoryBlock = Field(validation_alias="gui", default=None)


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

    ruby_cost: int = Field(validation_alias="C2")


class HealAllResponse(BaseResponse):
    """
    The joined castle after an ``hra``.

    Command: hra

    Client: ``HRACommand.executeCommand`` (bundle line 124513)
    """

    command = "hra"

    currencies: CurrencyBlock = Field(
        validation_alias="gcu", default=None, description="Coins and rubies after the change"
    )
    unit_inventory: UnitInventoryBlock = Field(validation_alias="gui", default=None)
    production_area: RawBlock = Field(
        validation_alias="gpa",
        default=None,
        description="The castle's production and storage figures, as a raw block",
    )


# =============================================================================
# HFL - Hospital Flags
# =============================================================================


class HospitalFlagsRequest(BaseRequest):
    """
    Read or set the hospital flags of the joined castle.

    Command: hfl
    Payload: {"KID": kingdom_id, "AID": castle_id, "HRF": -1, 0 or 1}

    ``HRF`` -1 only reads the flags, as the hospital dialog does when it opens
    (``CastleRecruitDialogHospital.show``, bundle line 83456); 0 or 1 sets whether wounded
    ruby units are admitted, as its checkbox does (``toggleRubyBlock``, bundle line 83605).

    Client: ``C2SHospitalFlagsVO`` (bundle line 84184)
    """

    command = "hfl"

    kingdom_id: Kingdom = Field(validation_alias="KID", description="The joined castle's kingdom")
    castle_id: int = Field(
        validation_alias="AID",
        description=(
            "The castle the session is in, a Castle.id from client.state.get_castles(); ArmyService joins it first"
        ),
    )
    admit_ruby_units: int = Field(
        validation_alias="HRF",
        default=-1,
        description="-1 to only read the flags, 1 to admit wounded ruby units, 0 not to",
    )

    def accepts_reply(self, payload: Any) -> bool:
        """Whether an hfl reply is about this castle: its ``KID`` and ``AID`` are the ones sent.

        Client: ``CastleRecruitDialogHospital.onHospitalFlagsReceived`` (bundle line 83606) takes
        only flags for which ``HospitalFlagsVO.isCurrentCastle`` (bundle line 124502) holds.
        """
        if not isinstance(payload, dict):
            return False
        return js_same_number(payload.get("KID"), self.kingdom_id) and js_same_number(
            payload.get("AID"), self.castle_id
        )


class HospitalFlags(BasePayload):
    """
    The hospital flags of a castle, the ``hfl`` reply.

    Client: ``HospitalFlagsVO.parse_HFL`` (bundle line 124501). ``HRF`` is the dialog's checkbox
    "Admit wounded ruby units to the hospital" (``dialog_hospital_rubyUnitsFilter_desc``), ticked
    while ``HRF`` is 1 (``onHospitalFlagsReceived``, bundle line 83606)
    """

    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN)
    castle_id: int = Field(validation_alias="AID", default=0)
    admits_ruby_units: bool = Field(
        validation_alias="HRF",
        default=False,
        description="Wounded ruby units are admitted to the hospital",
    )

    @field_validator("admits_ruby_units", mode="before")
    @classmethod
    def _client_truthy(cls, value: Any) -> bool:
        return js_truthy(value)


class HospitalFlagsResponse(BaseResponse, HospitalFlags):
    """
    The hospital flags of the joined castle.

    Command: hfl

    Client: ``HFLCommand.executeCommand`` (bundle line 124489)
    """

    command = "hfl"


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
    "HospitalFlagsRequest",
    "HospitalFlags",
    "HospitalFlagsResponse",
]
