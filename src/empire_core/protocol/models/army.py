"""
Army and hospital protocol models.

Commands:
- bup: Produce units or tools
- spl: Get a production list
- bou: Double the units of a production slot
- mcu: Cancel a production slot
- gui: Get units inventory
- dup: Dismiss units
- hru: Heal wounded units
- hcs: Cancel a hospital slot
- hss: Skip a hospital slot (rubies)
- hdu: Dismiss wounded units
- hra: Heal all wounded units (rubies)

Apart from gui these act on the castle the session has joined (``jca``);
``bup`` and ``bou`` also name that castle and its kingdom.
"""

from __future__ import annotations

import math
from enum import Enum, IntEnum
from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, Field, model_validator

from .base import BasePayload, BaseRequest, BaseResponse, CurrencyBlock, Kingdom, ParseInt, UnitCount, client_int


class ProductionListId(IntEnum):
    """
    The client's unit package lists, one per kind of production.

    Client: ``UnitProductionConst`` (dll line 19891), picked by
    ``CastleMilitaryData.getListIdByCategory`` (bundle line 138870)
    """

    SOLDIERS = 0
    TOOLS = 1
    HOSPITAL = 2
    AUXILIARIES = 3


class SlotType(str, Enum):
    """
    Whether a slot is the one producing now or one waiting in the queue.

    Client: ``RecruitmentConst.PRODUCTION_SLOT_TYPE_NAME`` / ``QUEUE_SLOT_TYPE_NAME``
    (dll line 19660)
    """

    PRODUCTION = "production"
    QUEUE = "queue"


BUY_UNIT_PACKAGE_SK = 73
"""``SK`` of every ``bup``: each client caller leaves ``C2SBuyUnitPackageVO``'s
default; nothing in the client reads it or says what it means."""


def _js_truthy(value: Any) -> bool:
    """The client's ``!!value``."""
    if isinstance(value, float) and math.isnan(value):
        return False
    if isinstance(value, (list, dict)):
        return True
    return bool(value)


def _loose_zero(value: Any) -> bool:
    """The client's ``0 == value``."""
    if value is None:
        return False
    if isinstance(value, (bool, int, float)):
        return value == 0
    if isinstance(value, str):
        if not value.strip():
            return True
        try:
            return float(value) == 0
        except ValueError:
            return False
    return False


def _block(value: Any) -> Any:
    """A nested reply block, or None where the client would find nothing to parse."""
    return value if isinstance(value, dict) else None


RawBlock = Annotated[dict[str, Any] | None, BeforeValidator(_block)]
"""A reply block this module keeps as sent; the docstring names the client parser."""


# =============================================================================
# GUI - Get Units Inventory
# =============================================================================


class GetUnitsRequest(BaseRequest):
    """
    Get the unit inventories of the castle the session is in.

    Command: gui
    Payload: {}

    The request names no castle: the server answers for the joined castle, and
    with ``NOT_IN_OWNED_CASTLE`` once a map scan has moved the session away.

    Client: ``C2SGetUnitInventoryVO`` (no fields)
    """

    command = "gui"


def _wod_amounts(value: object) -> object:
    """
    ``[[wod_id, amount], ...]`` as ``{wod_id: amount}``.

    Client: ``AUnitInventory.fillFromWodAmountArray`` (bundle line 42572), which
    reads both through ``int()``, into a ``UnitInventoryDictionary``: ``addUnit``
    clamps at 0, ``changeUnitAmount`` adds (bundle lines 5533-5535) and
    ``setUnit`` drops a total of 0 or less (bundle line 5538).
    """
    if not isinstance(value, list):
        return {}
    totals: dict[int, int] = {}
    for entry in value:
        if isinstance(entry, list):
            wod_id = client_int(entry[0] if entry else None)
            amount = client_int(entry[1] if len(entry) > 1 else None)
            totals[wod_id] = totals.get(wod_id, 0) + max(0, amount)
    return {wod_id: amount for wod_id, amount in totals.items() if amount > 0}


WodAmounts = Annotated[dict[int, int], BeforeValidator(_wod_amounts)]
"""A wod/amount array read as ``{wod_id: amount}``, as the client's unit inventories do."""


def _spy_positions(value: object) -> object:
    """
    One wod/amount array per position, each pair read through ``int()``.

    Client: ``CastleSpyArmyInfoVO.parseArmyInfo`` (bundle line 30699) hands each
    position to ``AUnitInventory.fillFromWodAmountArray`` (bundle line 42572),
    which skips entries that are not arrays and reads ``int(i[0])``, ``int(i[1])``,
    into a ``UnitInventoryList``, whose ``addUnit`` skips an amount of 0 or less
    (bundle line 21826). A position that is not an array fills nothing, so it
    reads as empty; it is kept, since the client reads positions by order.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        return value
    positions = []
    for position in value:
        pairs = []
        for pair in position if isinstance(position, list) else []:
            if isinstance(pair, list):
                amount = client_int(pair[1] if len(pair) > 1 else None)
                if amount > 0:
                    pairs.append([client_int(pair[0] if pair else None), amount])
        positions.append(pairs)
    return positions


SpyPositions = Annotated[list[list[list[int]]], BeforeValidator(_spy_positions)]
"""A spy report's ``S``: ``[wod_id, amount]`` pairs per position, in the order
left, middle, right, keep, stronghold, support, then an optional reserve."""


class UnitInventory(BasePayload):
    """
    A castle's unit inventories, the ``gui`` block.

    Client: ``CastleMilitaryData.parse_GUI``, which fills each inventory with
    ``AUnitInventory.fillFromWodAmountArray`` (bundle line 42572)
    """

    units: WodAmounts = Field(alias="I", default_factory=dict, description="Units and tools in the castle")
    in_production: WodAmounts = Field(alias="TU", default_factory=dict, description="Units on their way in")
    stronghold: WodAmounts = Field(alias="SHI", default_factory=dict, description="Units stored in the stronghold")
    hospital: WodAmounts = Field(alias="HI", default_factory=dict, description="Wounded units in the hospital")


class GetUnitsResponse(BaseResponse, UnitInventory):
    """
    The unit inventories of the castle the session is in.

    Command: gui
    Payload: {"I": [[wod_id, amount], ...], "TU": [...], "SHI": [...], "HI": [...]}

    Client: ``GUICommand.exec`` (bundle line 125600) hands the reply to
    ``CastleMilitaryData.parse_GUI``, which reads I, TU, SHI and HI and nothing else.
    """

    command = "gui"

    @staticmethod
    def _as_counts(amounts: dict[int, int]) -> list[UnitCount]:
        return [UnitCount(UID=wod_id, C=amount) for wod_id, amount in amounts.items()]

    def get_inventory(self) -> list[UnitCount]:
        """Available units and tools."""
        return self._as_counts(self.units)

    def get_in_production(self) -> list[UnitCount]:
        """Units on their way in."""
        return self._as_counts(self.in_production)

    def get_stronghold(self) -> list[UnitCount]:
        """Units stored in the stronghold."""
        return self._as_counts(self.stronghold)

    def get_hospital(self) -> list[UnitCount]:
        """Wounded units in the hospital."""
        return self._as_counts(self.hospital)


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

    position: int = Field(default=0, description="Index in QS, the S of mcu and bou; 0 for PS")
    wod_id: int = Field(alias="WID", default=0, description="Unit or tool wod id")
    amount: int = Field(alias="TUA", default=0, description="Units in the slot")
    boost_count: int = Field(alias="CBS", default=0, description="How often the slot's units were doubled (bou)")
    received_alliance_help: bool = Field(alias="RAH", default=False)
    recruitment_id: int = Field(alias="PID", default=0)
    remaining_seconds: int = Field(alias="RCT", default=0, description="Seconds left; top level only")
    production_seconds: int = Field(alias="ICT", default=0, description="Total production time; top level only")
    source_recruitment_id: int = Field(alias="SPID", default=0, description="Top level only")
    seconds_till_locked: int | float | str | None = Field(
        default=0, description="SI.RUT as sent while the slot is empty, else -1; 0 means locked"
    )
    is_vip: bool = Field(default=False, description="SI.VIP")
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
            slot["wod_id"] = client_int(get("WID"))
            slot["amount"] = client_int(get("TUA"))
            slot["boost_count"] = client_int(get("CBS"))
            slot["received_alliance_help"] = _js_truthy(get("RAH"))
            slot["recruitment_id"] = client_int(get("PID"))

        if _js_truthy(data.get("ICT")):
            package(data)
            slot["remaining_seconds"] = client_int(data.get("RCT"))
            slot["production_seconds"] = client_int(data.get("ICT"))
            slot["source_recruitment_id"] = client_int(data.get("SPID"))
            slot["is_free"] = False
        if _js_truthy(data.get("P")):
            package(data["P"])
        info = data.get("SI")
        if _js_truthy(info):
            get = info.get if isinstance(info, dict) else (lambda _key: None)
            rut = get("RUT")
            if isinstance(rut, list):
                # 0 == [] and 0 == [0] hold in JavaScript: an array compares as its joined text
                rut = ",".join("" if entry is None else str(entry) for entry in rut)
            elif isinstance(rut, dict):
                rut = None
            slot["seconds_till_locked"] = rut if slot["amount"] <= 0 else -1
            slot["is_vip"] = _js_truthy(get("VIP"))
            slot["is_locked"] = _loose_zero(slot["seconds_till_locked"])
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
    with no ``int()``; here each goes through ``client_int`` so the fields are
    ints, and a missing value reads as 0. An entry that is not an array reads as
    an empty slot here, where the client would stop reading the list.

    Client: ``UnitHealPackageSlotVO.fillFromParamArray`` (bundle line 138964)
    """

    position: int = Field(default=0, description="Index in PIDL, the S of hcs and hss")
    wod_id: int = Field(default=0, description="Unit wod id; -1 for a free slot, -2 for a locked one")
    amount: int = Field(default=0)
    remaining_seconds: int = Field(default=0)
    recruitment_speed: float = Field(default=0.0, description="The fourth value / 100")
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


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(number) or math.isinf(number) else number


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
                "wod_id": client_int(values[0]),
                "amount": client_int(values[1]),
                "remaining_seconds": client_int(values[2]),
                "recruitment_speed": _number(values[3]) / 100,
                "heal_time_reduction": client_int(values[4]),
                "recruitment_id": client_int(values[5]),
                "seconds_till_locked": client_int(values[6]),
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
    ``UnitPackageList.parseList`` / ``parseMilitaryList`` (bundle lines 138899, 138907)
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
        description="RecruitmentConst FINISH_FIRST_STACK_MODE_ID 0 or FINISH_STACKS_EQUALLY_MODE_ID 1 (dll line 19660)",
    )
    remaining_seconds: int = Field(alias="TCT", default=0, description="Seconds until the list's production is done")
    hospital_slots: Annotated[list[HospitalSlot], BeforeValidator(_hospital_slots)] = Field(
        alias="PIDL", default_factory=list, description="Hospital list only: slots by position"
    )
    active_slot_index: ParseInt = Field(alias="ASI", default=0, description="Hospital list only")

    @model_validator(mode="before")
    @classmethod
    def _client_ints(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "LID" in data:
            data["LID"] = client_int(data["LID"])
        for key in ("RM", "TCT"):
            if key in data:
                data[key] = client_int(data[key])
        return data


ProductionListBlock = Annotated[ProductionList | None, BeforeValidator(_block)]
UnitInventoryBlock = Annotated[UnitInventory | None, BeforeValidator(_block)]


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
    amount: int = Field(alias="AMT")
    private_offer_id: int = Field(alias="PO", default=-1, description="Resource merchant offer id, -1 for none")
    pay_with_rubies: int = Field(alias="PWR", default=0, description="1 to pay rubies for missing resources")
    sk: int = Field(alias="SK", default=BUY_UNIT_PACKAGE_SK, description="Always 73; meaning not in the client")
    kingdom_id: Kingdom | int = Field(alias="SID", description="The joined castle's kingdom")
    castle_id: int = Field(
        alias="AID",
        description=(
            "The castle joined with jca, as the client sends it; ArmyService joins it first. Castle.id from "
            "client.state.get_castles()"
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
        return {**data, "W": client_int(data.get("W")), "AMT": client_int(data.get("AMT"))}


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
    resources: RawBlock = Field(alias="grc", default=None, description="As sent; read by AreaDataUpdater.parseGRC")
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Gold and rubies after the change")
    unit_inventory: UnitInventoryBlock = Field(alias="gui", default=None)
    added_unit: Annotated[AddedUnit | None, BeforeValidator(_block)] = Field(alias="O", default=None)


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

    list_id: ProductionListId = Field(alias="LID")
    position: int = Field(alias="S")
    castle_id: int = Field(
        alias="AID",
        description=(
            "The castle joined with jca, as the client sends it; ArmyService joins it first. Castle.id from "
            "client.state.get_castles()"
        ),
    )
    kingdom_id: Kingdom | int = Field(alias="SID", description="The joined castle's kingdom")
    slot_type: SlotType = Field(alias="ST")


class DoubleProductionSlotResponse(BaseResponse):
    """
    The production list after a ``bou``.

    Command: bou

    Client: ``BOUCommand.executeCommand`` (bundle line 125515)
    """

    command = "bou"

    production_list: ProductionListBlock = Field(alias="spl", default=None)
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Gold and rubies after the change")


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
    position: int = Field(alias="S", description="0 for the slot producing now, else its index in QS")
    slot_type: SlotType = Field(alias="ST")


class CancelProductionResponse(BaseResponse):
    """
    The production list after an ``mcu``.

    Command: mcu

    Client: ``MCUCommand.executeCommand`` (bundle line 125616)
    """

    command = "mcu"

    production_list: ProductionListBlock = Field(alias="spl", default=None)


# =============================================================================
# DUP - Dismiss Units
# =============================================================================


class DismissUnitsRequest(BaseRequest):
    """
    Dismiss units of the joined castle.

    Command: dup
    Payload: {"WID": wod_id, "A": amount, "S": 0 or 1}

    Client: ``C2SDismissUnitPackageVO`` (bundle line 84341), built by
    ``CastleRecruitDismissUnitsDialog.dismissUnits`` (bundle line 84330)
    """

    command = "dup"

    wod_id: int = Field(alias="WID")
    amount: int = Field(alias="A")
    from_stronghold: int = Field(alias="S", default=0, description="1 to dismiss from the stronghold")


class DismissUnitsResponse(BaseResponse):
    """
    The joined castle after a ``dup``.

    Command: dup

    Client: ``DUPCommand.executeCommand`` (bundle line 125585)
    """

    command = "dup"

    production_area: RawBlock = Field(
        alias="gpa", default=None, description="As sent; read by AreaDataUpdater.parseGPA"
    )
    unit_inventory: UnitInventoryBlock = Field(alias="gui", default=None)


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

    wod_id: int = Field(alias="U")
    amount: int = Field(alias="A")


class HealUnitsResponse(BaseResponse):
    """
    The joined castle after an ``hru``.

    Command: hru

    Client: ``HRUCommand.executeCommand`` (bundle line 124532)
    """

    command = "hru"

    production_list: ProductionListBlock = Field(alias="spl", default=None)
    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Gold and rubies after the change")
    unit_inventory: UnitInventoryBlock = Field(alias="gui", default=None)


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

    position: int = Field(alias="S", description="The slot's index in PIDL")


class CancelHealResponse(BaseResponse):
    """
    The joined castle after an ``hcs``.

    Command: hcs

    Client: ``HCSCommand.executeCommand`` (bundle line 124454)
    """

    command = "hcs"

    production_list: ProductionListBlock = Field(alias="spl", default=None)
    unit_inventory: UnitInventoryBlock = Field(alias="gui", default=None)


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

    position: int = Field(alias="S", description="The slot's index in PIDL")


class SkipHealResponse(BaseResponse):
    """
    Currencies after an ``hss``.

    Command: hss

    Client: ``HSSCommand.executeCommand`` (bundle line 50856)
    """

    command = "hss"

    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Gold and rubies after the change")


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

    wod_id: int = Field(alias="U")
    amount: int = Field(alias="A")


class WoundedUnits(BasePayload):
    """One ``UT`` entry of a many-type ``hdu``."""

    wod_id: int = Field(alias="U")
    amount: int = Field(alias="A")


class DismissManyWoundedRequest(BaseRequest):
    """
    Dismiss wounded units of several types in the joined castle.

    Command: hdu
    Payload: {"UT": [{"U": wod_id, "A": amount}, ...]}

    Client: ``C2SDismissManyHospitalUnits`` (bundle line 83834), built by
    ``CastleRecruitDialogHospital.onConfirmDeleteAll`` (bundle line 83498)
    """

    command = "hdu"

    units: list[WoundedUnits] = Field(alias="UT")


class DismissWoundedResponse(BaseResponse):
    """
    The joined castle after an ``hdu``.

    Command: hdu

    Client: ``HDUCommand.executeCommand`` (bundle line 124470)
    """

    command = "hdu"

    unit_inventory: UnitInventoryBlock = Field(alias="gui", default=None)


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

    ruby_cost: int = Field(alias="C2")


class HealAllResponse(BaseResponse):
    """
    The joined castle after an ``hra``.

    Command: hra

    Client: ``HRACommand.executeCommand`` (bundle line 124513)
    """

    command = "hra"

    currencies: CurrencyBlock = Field(alias="gcu", default=None, description="Gold and rubies after the change")
    unit_inventory: UnitInventoryBlock = Field(alias="gui", default=None)
    production_area: RawBlock = Field(
        alias="gpa", default=None, description="As sent; read by AreaDataUpdater.parseGPA"
    )


# =============================================================================
# CDS - Send Support (Create Deployment - Support)
# =============================================================================


class SendSupportRequest(BaseRequest):
    """
    Send support troops to a castle.

    Command: cds
    Payload: {
        "SID": source_castle_id,
        "TX": target_x,
        "TY": target_y,
        "LID": commander_id,
        "WT": wait_time,
        "HBW": horses_type (-1 when PTT is set),
        "BPC": use_premium_commander,
        "PTT": feathers,
        "SD": slowdown,
        "A": [[unit_id, count], ...]
    }

    The client sends no kingdom id. Fields follow its key order. ``BPC`` is
    1 only when the premium commander (``LID`` -14,
    ``TravelConst.COMMANDER_PREMIUM``) leads the army, which uses one of the
    player's premium commanders or, when none are left, costs rubies
    (``CastlePostAttackDialog.startAttack`` sends ``sendMovement(0)`` for any
    other commander). ``PTT`` 1 pays for the movement with feathers.

    Client: ``C2SCreateDefenceSupportMovementVO`` (bundle line 133893), built
    by ``CastleAttackData.sendSupport`` (bundle line 133855)
    """

    command = "cds"

    source_castle_id: int = Field(
        alias="SID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    target_x: int = Field(alias="TX")
    target_y: int = Field(alias="TY")
    commander_id: int = Field(
        alias="LID",
        description=(
            "A Commander.commander_id from client.commanders.get_commanders(); "
            "0 is the free starting commander, -14 the premium one"
        ),
    )
    wait_time: int = Field(alias="WT", default=12, ge=0, le=12)
    horses_type: int = Field(alias="HBW", default=-1)
    use_premium_commander: int = Field(alias="BPC", default=0, description="1 when the premium commander leads")
    feathers: int = Field(alias="PTT", default=0, description="1 to pay with feathers")
    slowdown: int = Field(alias="SD", default=0)
    units: list[list[int]] = Field(alias="A")


class SendSupportResponse(BaseResponse):
    """
    Response to sending support.

    Command: cds
    """

    command = "cds"


__all__ = [
    "BUY_UNIT_PACKAGE_SK",
    "ProductionListId",
    "SlotType",
    "UnitInventory",
    # Production lists
    "ProductionList",
    "ProductionSlot",
    "CurrentProductionSlot",
    "HospitalSlot",
    # BUP - Produce Units
    "ProduceUnitsRequest",
    "ProduceUnitsResponse",
    "AddedUnit",
    # SPL - Production List
    "GetProductionListRequest",
    "GetProductionListResponse",
    # BOU - Double Production Slot
    "DoubleProductionSlotRequest",
    "DoubleProductionSlotResponse",
    # MCU - Cancel Production
    "CancelProductionRequest",
    "CancelProductionResponse",
    # GUI - Get Units
    "GetUnitsRequest",
    "GetUnitsResponse",
    # DUP - Dismiss Units
    "DismissUnitsRequest",
    "DismissUnitsResponse",
    # HRU - Heal Units
    "HealUnitsRequest",
    "HealUnitsResponse",
    # HCS - Cancel Heal
    "CancelHealRequest",
    "CancelHealResponse",
    # HSS - Skip Heal
    "SkipHealRequest",
    "SkipHealResponse",
    # HDU - Dismiss Wounded
    "DismissWoundedRequest",
    "DismissManyWoundedRequest",
    "WoundedUnits",
    "DismissWoundedResponse",
    # HRA - Heal All
    "HealAllRequest",
    "HealAllResponse",
    # CDS - Send Support
    "SendSupportRequest",
    "SendSupportResponse",
]
