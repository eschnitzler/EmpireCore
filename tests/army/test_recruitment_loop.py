"""Recruitment loops, queue copies, production skips and camp capacity."""

from __future__ import annotations

import pytest

from empire_core.army import (
    CancelRecruitmentLoopResponse,
    DuplicateRecruitmentInfoResponse,
    GetCampUnitCapacityResponse,
    LoopRecruitmentInfoResponse,
    RecruitmentCopyTarget,
    SkipProductionSlotResponse,
)
from empire_core.enums import GGEError, Kingdom
from empire_core.exceptions import CommandError, ProductionSlotsNeededError
from empire_core.protocol.models import ProductionListId, parse_response
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

OWN = [(12345, Kingdom.GREEN), (777, Kingdom.ICE)]

SOLDIER_LIST = {
    "LID": 0,
    "QS": [
        {"P": {"WID": 620, "TUA": 30, "CBS": 1}, "SI": {"RUT": -1}},
        {"SI": {"RUT": -1}},
    ],
    "PS": {"ICT": 60, "RCT": 20, "WID": 621, "TUA": 5},
    "RM": 0,
    "TCT": 900,
}

UNIT_TARGET = {
    "LID": 0,
    "AID": 777,
    "SID": 2,
    "CN": "North",
    "EID": 0,
    "ART": 3600,
    "CW": 500,
    "CS": 300,
    "C1": 40,
    "DC": 12,
    "F": 9000,
    "DF": 1505,
    "AFC": 30,
    "U": 31,
}


class TestModels:
    def test_lri_reads_what_a_loop_costs(self):
        reply = parse_response(
            "lri", {"LID": 1, "CRT": 120, "CFC": 50, "FCAL": 7, "CW": 10, "CS": 20, "C1": 30, "DC": 4}
        )

        assert isinstance(reply, LoopRecruitmentInfoResponse)
        assert reply.list_id is ProductionListId.TOOLS
        assert (reply.list_id, reply.recruitment_seconds, reply.food_consumption, reply.food_consumption_per_loop) == (
            1,
            120,
            50,
            7,
        )
        assert (reply.wood_cost, reply.stone_cost, reply.coin_cost, reply.doubling_ruby_cost) == (10, 20, 30, 4)

    def test_crl_is_read_as_sent(self):
        assert isinstance(parse_response("crl", {}), CancelRecruitmentLoopResponse)

    def test_dri_reads_each_castle(self):
        reply = parse_response("dri", {"A": [UNIT_TARGET, {**UNIT_TARGET, "AID": 778, "EID": 63}]})

        assert isinstance(reply, DuplicateRecruitmentInfoResponse)
        first, second = reply.targets
        assert (first.castle_id, first.kingdom, first.castle_name, first.recruitment_seconds) == (
            777,
            Kingdom.ICE,
            "North",
            3600,
        )
        assert first.can_copy
        assert first.list_id is ProductionListId.SOLDIERS
        assert first.food_production == 150.5
        assert first.food_production_after_copy == 120.5
        assert second.refusal is GGEError.NO_FREE_CONSTRUCTION_SLOT
        assert not second.can_copy

    def test_dri_keeps_an_unknown_refusal(self):
        reply = DuplicateRecruitmentInfoResponse.model_validate({"A": [{"EID": 99999}]})

        assert reply.targets[0].refusal == 99999

    def test_dri_without_a_list_has_no_targets(self):
        assert DuplicateRecruitmentInfoResponse.model_validate({"A": None}).targets == []

    def test_sou_reads_the_list_and_currencies(self):
        reply = parse_response("sou", {"spl": SOLDIER_LIST, "gcu": {"C1": 5, "C2": 6}})

        assert isinstance(reply, SkipProductionSlotResponse)
        assert reply.production_list is not None
        assert reply.production_list.current.wod_id == 621

    @pytest.mark.parametrize("value,capacity", [(250, 250), (-3, 0), (None, 0)])
    def test_fuc_is_never_below_zero(self, value, capacity):
        reply = parse_response("fuc", {"FUC": value})

        assert isinstance(reply, GetCampUnitCapacityResponse)
        assert reply.capacity == capacity


class TestRecruitmentLoop:
    def test_sends_the_queued_slots_after_reading_the_list(self):
        client = make_client({"spl": xt_packet("spl", SOLDIER_LIST)}, castles=OWN)

        client.army.start_recruitment_loop(12345, ProductionListId.SOLDIERS, 3, spend_rubies=True)

        sent = conn(client).request_payloads
        assert sent == [
            ("jaa", {"CID": 12345, "KID": 0}),
            ("spl", {"LID": 0}),
            (
                "url",
                {
                    "LID": 0,
                    "L": 3,
                    "RS": [{"ID": 620, "A": 30, "CBS": 1, "IA": 30}, {"ID": 0, "A": 0, "CBS": 0, "IA": 0}],
                },
            ),
        ]
        assert list(sent[-1][1]) == ["LID", "L", "RS"]

    def test_missing_slots_raise_with_the_count(self):
        script = {
            "spl": xt_packet("spl", SOLDIER_LIST),
            "url": xt_packet("url", {"LID": 0, "AMT": 2}, error_code=GGEError.NO_FREE_CONSTRUCTION_SLOT),
        }
        client = make_client(script, castles=OWN)

        with pytest.raises(ProductionSlotsNeededError) as raised:
            client.army.start_recruitment_loop(12345, ProductionListId.SOLDIERS, 1, spend_rubies=True)

        assert raised.value.list_id is ProductionListId.SOLDIERS
        assert raised.value.missing_slots == 2

    def test_another_refusal_stays_a_command_error(self):
        script = {"spl": xt_packet("spl", SOLDIER_LIST), "url": xt_packet("url", error_code=21)}
        client = make_client(script, castles=OWN)

        with pytest.raises(CommandError) as raised:
            client.army.start_recruitment_loop(12345, ProductionListId.SOLDIERS, 1, spend_rubies=True)

        assert not isinstance(raised.value, ProductionSlotsNeededError)

    @pytest.mark.parametrize(
        "list_id,loops,spend_rubies",
        [
            (ProductionListId.SOLDIERS, 1, False),
            (ProductionListId.HOSPITAL, 1, True),
            (ProductionListId.SOLDIERS, 0, True),
        ],
    )
    def test_refuses_what_the_client_would_not_send(self, list_id, loops, spend_rubies):
        client = make_client(castles=OWN)

        with pytest.raises(ValueError):
            client.army.start_recruitment_loop(12345, list_id, loops, spend_rubies=spend_rubies)
        assert conn(client).request_payloads == []


class TestQueueCopy:
    def test_targets_come_for_the_joined_castle(self):
        client = make_client({"dri": xt_packet("dri", {"A": [UNIT_TARGET]})}, castles=OWN)

        targets = client.army.get_recruitment_copy_targets(12345, ProductionListId.TOOLS)

        sent = conn(client).request_payloads
        assert sent == [("jaa", {"CID": 12345, "KID": 0}), ("dri", {"LID": 1, "AID": 12345, "SID": 0})]
        assert list(sent[-1][1]) == ["LID", "AID", "SID"]
        assert [target.castle_id for target in targets] == [777]

    def test_copy_sends_each_target_castle(self):
        client = make_client(castles=OWN)
        target = RecruitmentCopyTarget.model_validate(UNIT_TARGET)

        client.army.copy_recruitment(12345, ProductionListId.SOLDIERS, [target], spend_rubies=True)

        sent = conn(client).request_payloads
        assert sent == [
            ("jaa", {"CID": 12345, "KID": 0}),
            ("drl", {"LID": 0, "SID": 0, "AID": 12345, "A": [{"SID": 2, "AID": 777}]}),
        ]
        assert list(sent[-1][1]) == ["LID", "SID", "AID", "A"]

    def test_a_copy_without_rubies_needs_no_consent(self):
        client = make_client(castles=OWN)
        target = RecruitmentCopyTarget.model_validate({**UNIT_TARGET, "DC": 0})

        client.army.copy_recruitment(12345, ProductionListId.SOLDIERS, [target])

        assert conn(client).request_payloads[-1][0] == "drl"

    @pytest.mark.parametrize(
        "targets,spend_rubies",
        [
            ([], True),
            ([UNIT_TARGET], False),
            ([{**UNIT_TARGET, "EID": 88}], True),
        ],
    )
    def test_refuses_what_the_client_would_not_send(self, targets, spend_rubies):
        client = make_client(castles=OWN)
        picked = [RecruitmentCopyTarget.model_validate(target) for target in targets]

        with pytest.raises(ValueError):
            client.army.copy_recruitment(12345, ProductionListId.SOLDIERS, picked, spend_rubies=spend_rubies)
        assert conn(client).request_payloads == []

    def test_missing_slots_raise_with_the_count(self):
        reply = xt_packet("drl", {"LID": 1, "AMT": 1}, error_code=GGEError.NO_FREE_CONSTRUCTION_SLOT)
        client = make_client({"drl": reply}, castles=OWN)
        target = RecruitmentCopyTarget.model_validate(UNIT_TARGET)

        with pytest.raises(ProductionSlotsNeededError) as raised:
            client.army.copy_recruitment(12345, ProductionListId.TOOLS, [target], spend_rubies=True)

        assert raised.value.list_id is ProductionListId.TOOLS
        assert raised.value.missing_slots == 1

    def test_missing_resources_raise(self):
        reply = xt_packet("drl", error_code=GGEError.NOT_ENOUGH_RESOURCES)
        client = make_client({"drl": reply}, castles=OWN)
        target = RecruitmentCopyTarget.model_validate(UNIT_TARGET)

        with pytest.raises(CommandError) as raised:
            client.army.copy_recruitment(12345, ProductionListId.SOLDIERS, [target], spend_rubies=True)

        assert raised.value.error is GGEError.NOT_ENOUGH_RESOURCES


class TestSkipProductionSlot:
    def test_sends_the_slot_and_returns_the_list(self):
        reply = xt_packet("sou", {"spl": SOLDIER_LIST, "gcu": {"C1": 5, "C2": 6}})
        client = make_client({"sou": reply}, castles=OWN)

        production = client.army.skip_production_slot(12345, ProductionListId.SOLDIERS, 1, spend_rubies=True)

        assert conn(client).request_payloads == [("jaa", {"CID": 12345, "KID": 0}), ("sou", {"LID": 0, "S": 1})]
        assert production is not None
        assert production.queue[0].wod_id == 620

    def test_the_reply_reaches_the_coins_and_rubies(self):
        state = logged_in_state()

        state.update_from_packet("sou", {"spl": SOLDIER_LIST, "gcu": {"C1": 5, "C2": 6}})

        assert (state.get_local_player().coins, state.get_local_player().rubies) == (5, 6)
        state.shutdown()

    def test_a_refused_reply_leaves_the_currencies(self):
        state = logged_in_state()
        before = (state.get_local_player().coins, state.get_local_player().rubies)

        state.update_from_packet("sou", {"gcu": {"C1": 5, "C2": 6}}, error_code=11)

        assert (state.get_local_player().coins, state.get_local_player().rubies) == before
        state.shutdown()

    def test_a_refused_skip_raises(self):
        client = make_client({"sou": xt_packet("sou", error_code=11)}, castles=OWN)

        with pytest.raises(CommandError):
            client.army.skip_production_slot(12345, ProductionListId.SOLDIERS, 0, spend_rubies=True)

    @pytest.mark.parametrize(
        "list_id,spend_rubies", [(ProductionListId.SOLDIERS, False), (ProductionListId.HOSPITAL, True)]
    )
    def test_refuses_what_the_client_would_not_send(self, list_id, spend_rubies):
        client = make_client(castles=OWN)

        with pytest.raises(ValueError):
            client.army.skip_production_slot(12345, list_id, 0, spend_rubies=spend_rubies)
        assert conn(client).request_payloads == []


class TestCampUnitCapacity:
    def test_asks_for_the_camp_without_joining(self):
        client = make_client({"fuc": xt_packet("fuc", {"FUC": 1200})}, castles=OWN)

        assert client.army.get_camp_unit_capacity(4242) == 1200
        assert conn(client).request_payloads == [("fuc", {"CID": 4242})]

    def test_a_refusal_raises(self):
        client = make_client({"fuc": xt_packet("fuc", error_code=21)}, castles=OWN)

        with pytest.raises(CommandError):
            client.army.get_camp_unit_capacity(4242)
