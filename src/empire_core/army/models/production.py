"""Unit and tool production models.

Commands:
- bup: Produce units or tools
- spl: Get a production list
- bou: Double the units of a production slot
- mcu: Cancel a production slot

These act on the castle the session has joined (``jca``);
``bup`` and ``bou`` also name that castle and its kingdom.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, Field, model_validator

from empire_core.enums import Kingdom, ProductionListId, SlotType
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, CurrencyBlock, object_or_none
from empire_core.protocol.js import ParseInt, js_int, js_loose_equals, js_number, js_truthy

from .units import BUY_UNIT_PACKAGE_SK, RawBlock, UnitInventoryBlock

# =============================================================================
# Production lists (the spl block)
# =============================================================================


class ProductionSlot(BasePayload):
    """
    One slot of a soldier, tool or auxiliary list: a ``QS`` entry or the ``PS`` block.

    The client reads three optional parts of the same object: the top-level
    keys only when ``ICT`` is set, then ``P`` (which overrides the unit, amount,
    boosts, alliance help and recruitment id), then ``SI`` (the lock state).
    Numbers go through ``int()``, ``RAH`` and ``VIP`` through ``!!``, and
    ``RUT`` is kept as sent. An entry that is not an object reads as an empty slot.

    Client: ``UnitPackageSlotVO.fillFromParamObject`` (bundle line 61416);
    ``PS`` first goes through ``initProductionSlot`` (bundle line 61417)
    """

    starts_free: ClassVar[bool] = False

    position: int = Field(
        default=0,
        description="Index in the queue, the position boost and cancel requests take; 0 for the slot producing now",
    )
    wod_id: int = Field(alias="WID", default=0, description="Unit or tool wod id")
    amount: int = Field(alias="TUA", default=0, description="Units in the slot")
    boost_count: int = Field(alias="CBS", default=0, description="How often the slot's units were doubled")
    received_alliance_help: bool = Field(alias="RAH", default=False)
    recruitment_id: int = Field(alias="PID", default=0)
    remaining_seconds: int = Field(alias="RCT", default=0, description="Seconds left on the slot")
    production_seconds: int = Field(alias="ICT", default=0, description="Total production time, in seconds")
    source_recruitment_id: int = Field(alias="SPID", default=0, description="Source recruitment id")
    seconds_till_locked: int | float | str | None = Field(
        default=0, description="Seconds until the slot locks while it is empty, else -1; 0 means locked"
    )
    is_vip: bool = Field(default=False, description="The slot is a VIP slot")
    is_locked: bool = Field(default=False)
    is_free: bool = Field(default=False, description="Unlocked and empty")

    @model_validator(mode="before")
    @classmethod
    def _fill_as_the_client_does(cls, data: Any) -> Any:
        slot: dict[str, Any] = {
            "wod_id": 0,
            "amount": 0,
            "boost_count": 0,
            "received_alliance_help": False,
            "recruitment_id": 0,
            "remaining_seconds": 0,
            "production_seconds": 0,
            "source_recruitment_id": 0,
            "seconds_till_locked": -1 if cls.starts_free else 0,
            "is_vip": False,
            "is_locked": False,
            "is_free": cls.starts_free,
        }
        if not isinstance(data, dict):
            return slot
        if "position" in data:
            slot["position"] = data["position"]

        def package(block: Any) -> None:
            get = block.get if isinstance(block, dict) else (lambda _key: None)
            slot["wod_id"] = js_int(get("WID"))
            slot["amount"] = js_int(get("TUA"))
            slot["boost_count"] = js_int(get("CBS"))
            slot["received_alliance_help"] = js_truthy(get("RAH"))
            slot["recruitment_id"] = js_int(get("PID"))

        if js_truthy(data.get("ICT")):
            package(data)
            slot["remaining_seconds"] = js_int(data.get("RCT"))
            slot["production_seconds"] = js_int(data.get("ICT"))
            slot["source_recruitment_id"] = js_int(data.get("SPID"))
            slot["is_free"] = False
        if js_truthy(data.get("P")):
            package(data["P"])
        info = data.get("SI")
        if js_truthy(info):
            get = info.get if isinstance(info, dict) else (lambda _key: None)
            rut = get("RUT")
            if isinstance(rut, list):
                # 0 == [] and 0 == [0] hold in JavaScript: an array compares as its joined text
                rut = ",".join("" if entry is None else str(entry) for entry in rut)
            elif isinstance(rut, dict):
                rut = None
            slot["seconds_till_locked"] = rut if slot["amount"] <= 0 else -1
            slot["is_vip"] = js_truthy(get("VIP"))
            slot["is_locked"] = js_loose_equals(slot["seconds_till_locked"], 0)
            slot["is_free"] = not slot["is_locked"] and slot["amount"] <= 0
        return slot


class CurrentProductionSlot(ProductionSlot):
    """
    The slot producing now, the ``PS`` block: free until the block says otherwise.

    Client: ``UnitPackageList.parseCurrentProductionSlot`` (bundle line 138906)
    """

    starts_free: ClassVar[bool] = True


class HospitalSlot(BasePayload):
    """
    One slot of the hospital list, a positional ``PIDL`` entry.

    ``[wod_id, amount, remaining_seconds, speed * 100, heal_time_reduction,
    recruitment_id, seconds_till_locked]``, which the client reads in that order
    with no ``int()``; here each goes through ``js_int`` so the fields are
    ints, and a missing value reads as 0. An entry that is not an array reads as
    an empty slot here, where the client would stop reading the list.

    Client: ``UnitHealPackageSlotVO.fillFromParamArray`` (bundle line 138964)
    """

    position: int = Field(
        default=0, description="Index in the hospital list, the position cancel and skip requests take"
    )
    wod_id: int = Field(default=0, description="Unit wod id; -1 for a free slot, -2 for a locked one")
    amount: int = Field(default=0)
    remaining_seconds: int = Field(default=0)
    recruitment_speed: float = Field(default=0.0, description="Recruitment speed")
    heal_time_reduction: int = Field(default=0)
    recruitment_id: int = Field(default=0)
    seconds_till_locked: int = Field(default=0)

    @property
    def is_free(self) -> bool:
        """``ConstructionConst.SLOTSTATEUNLOCKED`` -1 (dll line 18983)."""
        return self.wod_id == -1

    @property
    def is_locked(self) -> bool:
        """``ConstructionConst.SLOTSTATELOCKED`` -2 (dll line 18983)."""
        return self.wod_id == -2


def _queue_slots(value: Any) -> Any:
    if not isinstance(value, list):
        return []
    return [{"position": index, **(entry if isinstance(entry, dict) else {})} for index, entry in enumerate(value)]


def _current_slot(value: Any) -> Any:
    return {"position": 0, **(value if isinstance(value, dict) else {})}


def _hospital_slots(value: Any) -> Any:
    if not isinstance(value, list):
        return []
    slots = []
    for index, entry in enumerate(value):
        values = list(entry) if isinstance(entry, list) else []
        values += [None] * (7 - len(values))
        slots.append(
            {
                "position": index,
                "wod_id": js_int(values[0]),
                "amount": js_int(values[1]),
                "remaining_seconds": js_int(values[2]),
                "recruitment_speed": js_number(values[3]) / 100,
                "heal_time_reduction": js_int(values[4]),
                "recruitment_id": js_int(values[5]),
                "seconds_till_locked": js_int(values[6]),
            }
        )
    return slots


class ProductionList(BasePayload):
    """
    One production list, the ``spl`` block.

    The client ignores a block without ``LID``. The hospital list
    (``ProductionListId.HOSPITAL``) sends ``PIDL`` and ``ASI``; every other list
    sends ``QS``, ``PS``, ``RM`` and ``TCT``.

    Client: ``CastleMilitaryData.parse_SPL`` (bundle line 138830),
    ``UnitPackageList.parseList`` / ``parseMilitaryList`` (bundle lines 138899, 138907);
    ``RecruitmentConst`` (dll line 19660) for the ``RM`` modes
    """

    list_id: int | None = Field(alias="LID", default=None, description="A ProductionListId; None when missing")
    queue: Annotated[list[ProductionSlot], BeforeValidator(_queue_slots)] = Field(
        alias="QS", default_factory=list, description="Queued slots, by position"
    )
    current: Annotated[CurrentProductionSlot, BeforeValidator(_current_slot)] = Field(
        alias="PS",
        default_factory=lambda: CurrentProductionSlot.model_validate({"position": 0}),
        description="The slot producing now",
    )
    recruitment_mode: int = Field(
        alias="RM",
        default=0,
        description="0 finishes the first stack first, 1 finishes the stacks equally",
    )
    remaining_seconds: int = Field(alias="TCT", default=0, description="Seconds until the list's production is done")
    hospital_slots: Annotated[list[HospitalSlot], BeforeValidator(_hospital_slots)] = Field(
        alias="PIDL", default_factory=list, description="Hospital list only: slots by position"
    )
    active_slot_index: ParseInt = Field(
        alias="ASI", default=0, description="Index of the active hospital slot; hospital list only"
    )

    @model_validator(mode="before")
    @classmethod
    def _client_ints(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "LID" in data:
            data["LID"] = js_int(data["LID"])
        for key in ("RM", "TCT"):
            if key in data:
                data[key] = js_int(data[key])
        return data


ProductionListBlock = Annotated[ProductionList | None, BeforeValidator(object_or_none)]


# =============================================================================
# BUP - Produce Units
# =============================================================================


class ProduceUnitsRequest(BaseRequest):
    """
    Produce units or tools in the joined castle.

    Command: bup
    Payload: {"LID": list_id, "WID": wod_id, "AMT": amount, "PO": -1, "PWR": 0,
              "SK": 73, "SID": kingdom_id, "AID": castle_id}

    ``PWR`` 1 pays rubies for missing resources: the client sends it from the
    resource wait dialog's skip (``CastleResourceWaitDialog.skipForRubies``,
    bundle line 32069), with ``PO`` set to the resource merchant's private offer
    id (``CastlePrivateOfferData.getPrivateOfferMerchantID``, bundle line 131979,
    -1 when there is none). ``SK`` is always 73 (``BUY_UNIT_PACKAGE_SK``).

    Client: ``C2SBuyUnitPackageVO`` (bundle line 35277), built by
    ``CastleRecruitSelectedUnitComponent`` (bundle line 51107) and
    ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (bundle line 35218)
    """

    command = "bup"

    list_id: ProductionListId = Field(alias="LID", description="The list to produce into")
    wod_id: int = Field(alias="WID", description="Unit or tool wod id")
    amount: int = Field(alias="AMT", description="How many to produce")
    private_offer_id: int = Field(alias="PO", default=-1, description="Resource merchant offer id, -1 for none")
    pay_with_rubies: int = Field(alias="PWR", default=0, description="1 to pay rubies for missing resources")
    sk: int = Field(alias="SK", default=BUY_UNIT_PACKAGE_SK, description="Always 73")
    kingdom_id: Kingdom = Field(alias="SID", description="The joined castle's kingdom")
    castle_id: int = Field(
        alias="AID",
        description=(
            "The castle the session is in, a Castle.id from client.state.get_castles(); ArmyService joins it first"
        ),
    )


class AddedUnit(BasePayload):
    """
    Units ``bup`` put straight into the inventory, the ``O`` block.

    Client: ``BUPCommand.executeCommand`` (bundle line 125531) calls
    ``unitInventory.addUnit(O.W, O.AMT)`` when ``O`` is set and not 0
    """

    wod_id: int = Field(alias="W", default=0)
    amount: int = Field(alias="AMT", default=0)

    @model_validator(mode="before")
    @classmethod
    def _client_ints(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {**data, "W": js_int(data.get("W")), "AMT": js_int(data.get("AMT"))}


class ProduceUnitsResponse(BaseResponse):
    """
    The joined castle after a ``bup``.

    Command: bup
    Payload: {"spl": {...}, "grc": {...}, "gcu": {...}, "gui": {...}, "O": {"W": wod_id, "AMT": amount}}

    Client: ``BUPCommand.executeCommand`` (bundle line 125531): ``spl`` to
    ``parse_SPL``, ``grc`` to ``AreaDataUpdater.parseGRC``, ``gcu`` to
    ``CurrencyData.parseGCU``, ``gui`` to ``parse_GUI``
    """

    command = "bup"

    production_list: ProductionListBlock = Field(alias="spl", default=None)
    resources: RawBlock = Field(alias="grc", default=None, description="The castle's resources, as a raw block")
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after the change")
    unit_inventory: UnitInventoryBlock = Field(alias="gui", default=None)
    added_unit: Annotated[AddedUnit | None, BeforeValidator(object_or_none)] = Field(alias="O", default=None)


# =============================================================================
# SPL - Get Production List
# =============================================================================


class GetProductionListRequest(BaseRequest):
    """
    Get one production list of the joined castle.

    Command: spl
    Payload: {"LID": list_id}

    Client: ``C2SShowPackageListVO`` (bundle line 22860)
    """

    command = "spl"

    list_id: ProductionListId = Field(alias="LID")


class GetProductionListResponse(BaseResponse, ProductionList):
    """
    One production list of the joined castle.

    Command: spl

    Client: ``SPLCommand.executeCommand`` (bundle line 125676) hands the reply to
    ``CastleMilitaryData.parse_SPL``
    """

    command = "spl"


# =============================================================================
# BOU - Double Production Slot
# =============================================================================


class DoubleProductionSlotRequest(BaseRequest):
    """
    Double the units of a production slot, for rubies.

    Command: bou
    Payload: {"LID": list_id, "S": position, "AID": castle_id, "SID": kingdom_id, "ST": slot_type}

    ``S`` is the slot's position: 0 for the slot producing now, its index in
    ``QS`` for a queued one.

    Client: ``C2SBoostUnitPackageVO`` (bundle line 79040), built by
    ``RecruitmentHelper.boostCurrentSlot`` (bundle line 23165) from the recruit
    dialog's boost button (``onDoubleUnitsConfirmation``, bundle line 23694)
    """

    command = "bou"

    list_id: ProductionListId = Field(alias="LID", description="The list the slot belongs to")
    position: int = Field(alias="S", description="0 for the slot producing now, its index in QS for a queued one")
    castle_id: int = Field(
        alias="AID",
        description=(
            "The castle the session is in, a Castle.id from client.state.get_castles(); ArmyService joins it first"
        ),
    )
    kingdom_id: Kingdom = Field(alias="SID", description="The joined castle's kingdom")
    slot_type: SlotType = Field(alias="ST", description="Whether the slot is producing now or queued")


class DoubleProductionSlotResponse(BaseResponse):
    """
    The production list after a ``bou``.

    Command: bou

    Client: ``BOUCommand.executeCommand`` (bundle line 125515)
    """

    command = "bou"

    production_list: ProductionListBlock = Field(alias="spl", default=None)
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Coins and rubies after the change")


# =============================================================================
# MCU - Cancel Production
# =============================================================================


class CancelProductionRequest(BaseRequest):
    """
    Cancel a production slot of the joined castle.

    Command: mcu
    Payload: {"LID": list_id, "S": position, "ST": slot_type}

    Client: ``C2SCancelUnitPackageVO`` (bundle line 83843), built by
    ``CastleRecruitDialogUnits.onCancelCurrentSlotConfirmed`` (bundle line 23655)
    """

    command = "mcu"

    list_id: ProductionListId = Field(alias="LID")
    position: int = Field(alias="S", description="0 for the slot producing now, else its index in the queue")
    slot_type: SlotType = Field(alias="ST")


class CancelProductionResponse(BaseResponse):
    """
    The production list after an ``mcu``.

    Command: mcu

    Client: ``MCUCommand.executeCommand`` (bundle line 125616)
    """

    command = "mcu"

    production_list: ProductionListBlock = Field(alias="spl", default=None)


__all__ = [
    "ProductionList",
    "ProductionSlot",
    "CurrentProductionSlot",
    "HospitalSlot",
    "ProduceUnitsRequest",
    "ProduceUnitsResponse",
    "AddedUnit",
    "GetProductionListRequest",
    "GetProductionListResponse",
    "DoubleProductionSlotRequest",
    "DoubleProductionSlotResponse",
    "CancelProductionRequest",
    "CancelProductionResponse",
]
