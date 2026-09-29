"""Army and hospital models against the client's command objects and parsers.

Request payloads are JSON.stringify of the client's C2S...VO constructors run in
node; slot expectations are the results of the client's fillFromParamObject and
fillFromParamArray run in node.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from empire_core.enums import Kingdom
from empire_core.protocol.models import (
    BUY_UNIT_PACKAGE_SK,
    CancelHealRequest,
    CancelProductionRequest,
    CurrentProductionSlot,
    DismissManyWoundedRequest,
    DismissUnitsRequest,
    DismissWoundedRequest,
    DoubleProductionSlotRequest,
    DoubleProductionSlotResponse,
    GetProductionListRequest,
    GetProductionListResponse,
    HealAllRequest,
    HealAllResponse,
    HealUnitsRequest,
    ProduceUnitsRequest,
    ProduceUnitsResponse,
    ProductionListId,
    ProductionSlot,
    SkipHealRequest,
    SlotType,
    WoundedUnits,
)


def wire(request: Any) -> str:
    """The JSON the request puts on the wire, key order included."""
    return request.to_packet().split("%", 5)[5][:-1]


def js(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


class TestRequests:
    @pytest.mark.parametrize(
        "request_,expected",
        [
            (
                ProduceUnitsRequest(LID=ProductionListId.SOLDIERS, WID=620, AMT=150, SID=Kingdom.GREEN, AID=12345),
                {"LID": 0, "WID": 620, "AMT": 150, "PO": -1, "PWR": 0, "SK": 73, "SID": 0, "AID": 12345},
            ),
            (
                ProduceUnitsRequest(
                    LID=ProductionListId.TOOLS, WID=649, AMT=20, PO=88, PWR=1, SID=Kingdom.ICE, AID=12345
                ),
                {"LID": 1, "WID": 649, "AMT": 20, "PO": 88, "PWR": 1, "SK": 73, "SID": 2, "AID": 12345},
            ),
            (GetProductionListRequest(LID=ProductionListId.AUXILIARIES), {"LID": 3}),
            (
                DoubleProductionSlotRequest(
                    LID=ProductionListId.SOLDIERS, S=2, AID=12345, SID=Kingdom.GREEN, ST=SlotType.QUEUE
                ),
                {"LID": 0, "S": 2, "AID": 12345, "SID": 0, "ST": "queue"},
            ),
            (
                CancelProductionRequest(LID=ProductionListId.TOOLS, S=0, ST=SlotType.PRODUCTION),
                {"LID": 1, "S": 0, "ST": "production"},
            ),
            (DismissUnitsRequest(WID=620, A=30, S=1), {"WID": 620, "A": 30, "S": 1}),
            (DismissUnitsRequest(WID=620, A=30), {"WID": 620, "A": 30, "S": 0}),
            (HealUnitsRequest(U=620, A=12), {"U": 620, "A": 12}),
            (CancelHealRequest(S=1), {"S": 1}),
            (SkipHealRequest(S=2), {"S": 2}),
            (HealAllRequest(C2=417), {"C2": 417}),
            (DismissWoundedRequest(U=620, A=5), {"U": 620, "A": 5}),
            (
                DismissManyWoundedRequest(UT=[WoundedUnits(U=620, A=5), WoundedUnits(U=621, A=3)]),
                {"UT": [{"U": 620, "A": 5}, {"U": 621, "A": 3}]},
            ),
        ],
    )
    def test_payload_matches_the_client_vo(self, request_, expected):
        assert wire(request_) == js(expected)

    def test_sk_is_the_client_default(self):
        assert BUY_UNIT_PACKAGE_SK == 73

    def test_slot_type_values_are_the_client_names(self):
        assert [t.value for t in SlotType] == ["production", "queue"]

    def test_list_ids_are_the_client_constants(self):
        assert [(i.name, i.value) for i in ProductionListId] == [
            ("SOLDIERS", 0),
            ("TOOLS", 1),
            ("HOSPITAL", 2),
            ("AUXILIARIES", 3),
        ]


SLOT_FIELDS = (
    "wod_id",
    "amount",
    "boost_count",
    "received_alliance_help",
    "recruitment_id",
    "remaining_seconds",
    "production_seconds",
    "source_recruitment_id",
    "seconds_till_locked",
    "is_vip",
    "is_locked",
    "is_free",
)


def slot_values(slot: ProductionSlot) -> dict[str, Any]:
    return {name: getattr(slot, name) for name in SLOT_FIELDS}


def client_slot(*values: Any) -> dict[str, Any]:
    return dict(zip(SLOT_FIELDS, values, strict=True))


class TestProductionSlots:
    @pytest.mark.parametrize(
        "model,entry,expected",
        [
            (
                CurrentProductionSlot,
                {"ICT": 600, "WID": 620, "TUA": 40, "CBS": 1, "RAH": 1, "PID": 77, "RCT": 250, "SPID": 5},
                client_slot(620, 40, 1, True, 77, 250, 600, 5, -1, False, False, False),
            ),
            (
                CurrentProductionSlot,
                {"ICT": 600, "WID": 620, "TUA": 40, "RCT": 250, "P": {"WID": 621, "TUA": 80, "CBS": 2, "PID": 78}},
                client_slot(621, 80, 2, False, 78, 250, 600, 0, -1, False, False, False),
            ),
            (CurrentProductionSlot, {}, client_slot(0, 0, 0, False, 0, 0, 0, 0, -1, False, False, True)),
            (
                ProductionSlot,
                {"P": {"WID": 620, "TUA": "30", "CBS": 0, "RAH": 0, "PID": 79}, "SI": {"RUT": -1, "VIP": 0}},
                client_slot(620, 30, 0, False, 79, 0, 0, 0, -1, False, False, False),
            ),
            (
                ProductionSlot,
                {"SI": {"RUT": 3600, "VIP": 1}},
                client_slot(0, 0, 0, False, 0, 0, 0, 0, 3600, True, False, True),
            ),
            (ProductionSlot, {"SI": {"RUT": 0}}, client_slot(0, 0, 0, False, 0, 0, 0, 0, 0, False, True, False)),
            (
                ProductionSlot,
                {"SI": {"RUT": "soon"}},
                client_slot(0, 0, 0, False, 0, 0, 0, 0, "soon", False, False, True),
            ),
            (
                ProductionSlot,
                {"WID": 620, "TUA": 40},
                client_slot(0, 0, 0, False, 0, 0, 0, 0, 0, False, False, False),
            ),
        ],
    )
    def test_slot_reads_as_the_client_fills_it(self, model, entry, expected):
        assert slot_values(model.model_validate(entry)) == expected


class TestProductionList:
    def test_military_list(self):
        reply = GetProductionListResponse.model_validate(
            {
                "LID": 0,
                "QS": [{"P": {"WID": 620, "TUA": 30}, "SI": {"RUT": -1}}, "bad", {"SI": {"RUT": 0}}],
                "PS": {"ICT": 600, "WID": 621, "TUA": 40, "RCT": 250},
                "RM": "1",
                "TCT": 900,
            }
        )

        assert reply.list_id == ProductionListId.SOLDIERS
        assert [(s.position, s.wod_id, s.amount, s.is_locked) for s in reply.queue] == [
            (0, 620, 30, False),
            (1, 0, 0, False),
            (2, 0, 0, True),
        ]
        assert (reply.current.position, reply.current.wod_id, reply.current.remaining_seconds) == (0, 621, 250)
        assert (reply.recruitment_mode, reply.remaining_seconds) == (1, 900)

    def test_hospital_list(self):
        reply = GetProductionListResponse.model_validate(
            {"LID": 2, "PIDL": [[620, 5, 30, 150, 4, 9, -1], [-1, 0, 0, 0, 0, 0, 3600], [-2], "bad"], "ASI": "1"}
        )

        first, free, locked, bad = reply.hospital_slots
        assert (first.wod_id, first.amount, first.remaining_seconds, first.recruitment_speed) == (620, 5, 30, 1.5)
        assert (first.heal_time_reduction, first.recruitment_id, first.seconds_till_locked) == (4, 9, -1)
        assert (free.position, free.is_free, free.is_locked) == (1, True, False)
        assert (locked.position, locked.is_free, locked.is_locked) == (2, False, True)
        assert (bad.position, bad.wod_id) == (3, 0)
        assert reply.active_slot_index == 1

    def test_a_block_without_lid_is_ignored_by_the_client(self):
        assert GetProductionListResponse.model_validate({"QS": []}).list_id is None


class TestReplies:
    def test_bup_reply(self):
        reply = ProduceUnitsResponse.model_validate(
            {
                "spl": {"LID": 1, "QS": [], "PS": {"ICT": 60, "WID": 649, "TUA": 20}},
                "grc": {"W": 100},
                "gcu": {"C1": 5000, "C2": 30},
                "gui": {"I": [[649, 3]]},
                "O": {"W": 649, "AMT": "2"},
            }
        )

        assert reply.production_list is not None and reply.production_list.current.wod_id == 649
        assert reply.unit_inventory is not None and reply.unit_inventory.units == {649: 3}
        assert reply.added_unit is not None and (reply.added_unit.wod_id, reply.added_unit.amount) == (649, 2)
        assert reply.currencies is not None and (reply.currencies.coins, reply.currencies.rubies) == (5000, 30)
        assert reply.resources == {"W": 100}

    def test_an_o_of_zero_adds_nothing(self):
        # BUPCommand: i.O && 0 != i.O && addUnit(...)
        assert ProduceUnitsResponse.model_validate({"O": 0}).added_unit is None

    def test_blocks_that_are_not_objects_read_as_missing(self):
        reply = HealAllResponse.model_validate({"gcu": None, "gui": [], "gpa": "x"})
        assert (reply.currencies, reply.unit_inventory, reply.production_area) == (None, None, None)

    def test_bou_reply(self):
        reply = DoubleProductionSlotResponse.model_validate({"spl": {"LID": 0}, "gcu": {"C2": 10}})
        assert reply.production_list is not None and reply.production_list.list_id == 0


def test_an_empty_or_zero_rut_array_reads_as_locked():
    # UnitPackageSlotVO: isLocked = 0 == secondsTillLocked, and 0 == [] and 0 == [0] in JavaScript
    from empire_core.army.models.production import ProductionSlot

    for rut in ([], [0], "0", 0):
        assert ProductionSlot.model_validate({"SI": {"RUT": rut}}).is_locked, rut
    assert not ProductionSlot.model_validate({"SI": {"RUT": [5]}}).is_locked


def test_a_gcu_value_that_is_no_number_reads_as_none():
    from empire_core.protocol.base import CurrencyTotals

    totals = CurrencyTotals.model_validate({"C1": "abc", "C2": 30})
    assert (totals.coins, totals.rubies) == (None, 30)
