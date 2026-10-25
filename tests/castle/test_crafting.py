"""The refinery and toolsmith crafting queues (crin, crst, crca, crqm, crsk, crun) and construction item
crafting (gcc, cic, sci)."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.castle import (
    ConstructionCraftingResponse,
    CraftingInfoResponse,
    CraftingQueue,
    CraftingSlotType,
    StartCraftingResponse,
)
from empire_core.enums import BuildingState, Kingdom
from empire_core.exceptions import CommandError, UnknownCastleError
from empire_core.gamedata import ConstructionItem, Currency
from empire_core.protocol.models import parse_response
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

# CastleCraftingData.parseBuildingQueueData reads KID, AID, S, CQID, OID, PS and QS (bundle line 111405)
QUEUE: dict[str, Any] = {
    "KID": 0,
    "AID": 5001,
    "S": 4,
    "CQID": 2,
    "OID": 77,
    "PS": {"CRID": [12, -1], "RCT": [300, 0], "RUT": [3600], "BV": [5]},
    "QS": {"CRID": [13], "RCT": [600]},
}


def queue(**changes: Any) -> CraftingQueue:
    return CraftingQueue.model_validate({**QUEUE, **changes})


def state_client(script: dict[str, Any]):
    client = make_client(script, state=logged_in_state())
    conn(client).on_packet = lambda packet: client.state.update_from_packet(
        packet.command_id, packet.payload, packet.error_code
    )
    return client


class TestReplies:
    def test_crin_reads_every_area_s_buildings(self):
        # parseAllQueueData: CAI an area or a list of areas, each with CBI queues
        reply = parse_response("crin", {"CAI": [{"CE": [], "CBI": [QUEUE]}, {"CBI": [{**QUEUE, "AID": 6001}]}]})
        assert isinstance(reply, CraftingInfoResponse)
        assert [q.castle_id for q in reply.queues] == [5001, 6001]

    def test_crin_reads_a_single_area_and_a_bare_queue(self):
        assert len(CraftingInfoResponse.model_validate({"CAI": {"CBI": [QUEUE]}}).queues) == 1
        (bare,) = CraftingInfoResponse.model_validate(QUEUE).queues
        assert bare.object_id == 77

    def test_a_queue_reads_its_slots_as_parallel_lists(self):
        reply = parse_response("crst", QUEUE)
        assert isinstance(reply, StartCraftingResponse)
        assert reply.kingdom is Kingdom.GREEN and reply.building_state is BuildingState.BUILD_COMPLETED
        assert reply.production.recipe_ids == (12, -1) and reply.production.unlock_seconds == (3600,)
        assert reply.queue.remaining_seconds == (600,) and reply.queue.booster_values == ()

    def test_a_missing_slot_block_is_empty(self):
        assert queue(QS=None).queue.recipe_ids == ()

    @pytest.mark.parametrize(
        ("state", "working"), [(4, True), (13, True), (2, False), (0, False), (6, False), (99, False)]
    )
    def test_a_building_works_unless_it_is_built_or_taken_down(self, state, working):
        # IsoBuildingStateEnum.isFunctionally; an unknown id reads as INITIAL
        assert queue(S=state).is_working is working


class TestCraftingQueue:
    def test_get_crafting_queues_sends_crin_and_keeps_the_queues(self):
        client = state_client({"crin": xt_packet("crin", {"CAI": [{"CBI": [QUEUE]}]})})

        (got,) = client.castle.get_crafting_queues()

        assert conn(client).request_payloads == [("crin", {})]
        assert got.queue_id == 2
        assert client.castle.crafting_queues == (got,)

    def test_start_sends_the_queue_s_building_and_replaces_its_queue(self):
        after = {**QUEUE, "QS": {"CRID": [13, 14], "RCT": [600, 900]}}
        client = state_client({"crin": xt_packet("crin", QUEUE), "crst": xt_packet("crst", after)})
        (known,) = client.castle.get_crafting_queues()

        started = client.castle.start_crafting(known, 14)

        assert conn(client).request_payloads[-1] == ("crst", {"KID": 0, "AID": 5001, "OID": 77, "PWR": 0, "CRID": 14})
        assert started.queue.recipe_ids == (13, 14)
        kept = client.castle.crafting_queues
        assert kept is not None and kept[0].queue.recipe_ids == (13, 14)

    def test_a_full_queue_raises(self):
        client = make_client({"crst": xt_packet("crst", error_code=63)})
        with pytest.raises(CommandError):
            client.castle.start_crafting(queue(), 14)

    def test_a_building_not_working_sends_nothing(self):
        client = make_client()
        with pytest.raises(ValueError, match="not working"):
            client.castle.cancel_crafting(queue(S=2), 0, CraftingSlotType.PRODUCTION)
        assert conn(client).request_payloads == []

    def test_cancel_sends_the_slot_type_as_text(self):
        client = make_client({"crca": xt_packet("crca", QUEUE)})
        client.castle.cancel_crafting(queue(), 1, CraftingSlotType.QUEUE)
        assert conn(client).request_payloads == [("crca", {"KID": 0, "AID": 5001, "OID": 77, "S": 1, "ST": "queue"})]

    def test_move_sends_old_and_new_place(self):
        client = make_client({"crqm": xt_packet("crqm", QUEUE)})
        client.castle.move_crafting_slot(queue(), 2, 0)
        assert conn(client).request_payloads == [("crqm", {"KID": 0, "AID": 5001, "OID": 77, "OS": 2, "NS": 0})]

    def test_skip_needs_consent_and_sends_its_price(self):
        client = make_client({"crsk": xt_packet("crsk", QUEUE)})
        with pytest.raises(ValueError, match="spend_rubies"):
            client.castle.skip_crafting(queue(), 0, CraftingSlotType.PRODUCTION, 35)
        client.castle.skip_crafting(queue(), 0, CraftingSlotType.PRODUCTION, 35, spend_rubies=True)
        assert conn(client).request_payloads == [
            ("crsk", {"KID": 0, "AID": 5001, "OID": 77, "S": 0, "ST": "production", "PC2": 35})
        ]

    def test_unlock_sends_every_slot_first_to_last(self):
        client = make_client({"crun": xt_packet("crun", QUEUE)})
        client.castle.unlock_crafting_slots(queue(), [1, 2], CraftingSlotType.PRODUCTION)
        assert conn(client).request_payloads == [
            ("crun", {"KID": 0, "AID": 5001, "OID": 77, "S": [1, 2], "ST": "production"})
        ]

    def test_a_refused_action_leaves_the_queues(self):
        client = state_client({"crin": xt_packet("crin", QUEUE), "crca": xt_packet("crca", error_code=1)})
        (known,) = client.castle.get_crafting_queues()
        with pytest.raises(CommandError):
            client.castle.cancel_crafting(known, 0, CraftingSlotType.PRODUCTION)
        assert client.castle.crafting_queues == (known,)

    def test_a_castle_join_brings_its_crafting_queues(self):
        # JAACommand parses crai with parseAllQueueData (bundle line 130249)
        state = logged_in_state()
        state.update_from_packet("jaa", {"KID": 0, "crai": {"CAI": [{"CBI": [QUEUE]}]}})
        (joined,) = state.get_crafting_queues() or ()
        assert (joined.castle_id, joined.queue_id) == (5001, 2)

    def test_a_join_without_crafting_areas_keeps_none(self):
        state = logged_in_state()
        state.update_from_packet("jaa", {"KID": 0, "crai": {}})
        assert state.get_crafting_queues() is None


class TestConstructionCrafting:
    def test_gcc_reads_the_running_craft(self):
        client = make_client({"gcc": xt_packet("gcc", {"CID": "12", "RS": 40})})
        crafting = client.castle.get_construction_crafting()
        assert conn(client).request_payloads == [("gcc", {})]
        assert crafting.construction_item_id is ConstructionItem.BARRACKS_STACKS_G2_L2
        assert crafting.remaining_seconds == 40

    def test_gcc_without_a_craft_reads_none(self):
        crafting = ConstructionCraftingResponse.model_validate({})
        assert crafting.construction_item_id is None and crafting.remaining_seconds is None

    def test_cic_sends_the_recipe_and_the_castle(self):
        client = make_client(castles=[(5001, Kingdom.FIRE)])
        client.castle.craft_construction_item(5001, 301)
        assert conn(client).request_payloads == [("cic", {"RID": 301, "KID": 3, "AID": 5001})]

    def test_cic_for_a_castle_not_yours_sends_nothing(self):
        client = make_client(castles=[(5001, Kingdom.GREEN)])
        with pytest.raises(UnknownCastleError):
            client.castle.craft_construction_item(9, 301)
        assert conn(client).request_payloads == []

    def test_sci_sends_a_minute_skip_key_without_rubies(self):
        client = make_client(castles=[(5001, Kingdom.GREEN)])
        client.castle.skip_construction_crafting_time(5001, Currency.SKIP_5_MINUTES)
        assert conn(client).request_payloads == [("sci", {"KID": 0, "AID": 5001, "PWR": 0, "MST": "MS2"})]

    def test_sci_finishes_for_rubies_with_a_dash(self):
        client = make_client(castles=[(5001, Kingdom.GREEN)])
        with pytest.raises(ValueError, match="spend_rubies"):
            client.castle.finish_construction_crafting(5001)
        client.castle.finish_construction_crafting(5001, spend_rubies=True)
        assert conn(client).request_payloads == [("sci", {"KID": 0, "AID": 5001, "PWR": 1, "MST": "-"})]
