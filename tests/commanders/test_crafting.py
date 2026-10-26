"""Equipment and gem crafting and enchanting (ceq, eqe, ere, cge, ege), the inventory reads (ggm, esl, gnr)
and the merchant pushes (beq, bri, bgm)."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.commanders import (
    BoughtEquipmentResponse,
    BoughtGemsResponse,
    BoughtRelicsResponse,
    Equipment,
    GemStack,
    RelicGem,
)
from empire_core.enums import GGEError, PackageBuyType
from empire_core.exceptions import CommandError
from empire_core.gamedata import Gem, PackageId
from empire_core.gamedata.ids.events import Event
from empire_core.protocol.models import parse_response
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

ITEM = [6515211559, 1, 1, 3, 12, [[105, [6]]], 0, -1, 1, -1, 333, 0]
RELIC_GEM = [88123, 2, 1, 3500, [], 1]
RELIC_ITEM = [6109572530, 2, 1, 5, 7, [[401, 120, [9]]], 0, -1, 2, -1, -1, 3, [4, 1, 9000, []]]
ESL = {"E": 12, "TE": 50, "G": 3, "TG": 40}


def state_client(script: dict[str, Any]):
    client = make_client(script, state=logged_in_state())
    conn(client).on_packet = lambda packet: client.state.update_from_packet(
        packet.command_id, packet.payload, packet.error_code
    )
    return client


class TestInventoryReads:
    def test_get_gems_sends_ggm_and_keeps_the_gems(self):
        client = state_client({"ggm": xt_packet("ggm", {"GEM": [[333, 2]], "RGEM": [RELIC_GEM]})})
        gems = client.equipment.get_gems()
        assert conn(client).request_payloads == [("ggm", {})]
        assert gems.amount(Gem.IGNIS) == 2 and gems.relic_gems[0].gem_id == 88123
        assert client.equipment.gems == gems

    def test_get_inventory_space_reads_the_reply_into_state(self):
        client = state_client({"esl": xt_packet("esl", ESL)})
        space = client.equipment.get_inventory_space()
        assert conn(client).request_payloads == [("esl", {})]
        assert (space.equipment_space, space.gem_total_space) == (12, 40)
        assert client.equipment.inventory_space == space

    def test_gnr_lists_the_new_relics(self):
        client = make_client({"gnr": xt_packet("gnr", {"E": [6109572530], "RGEM": [88123]})})
        new = client.equipment.get_new_relics()
        assert (new.equipment_ids, new.relic_gem_ids) == ((6109572530,), (88123,))


class TestCraftEquipment:
    def test_ceq_sends_the_items_and_returns_the_crafted_one(self):
        client = state_client({"ceq": xt_packet("ceq", {"E": ITEM, "esl": ESL})})
        crafted = client.equipment.craft_equipment([1, 2, 3])
        assert conn(client).request_payloads == [("ceq", {"EX": 0, "I": [1, 2, 3]})]
        # C2SCraftEquipmentVO sets EX before I
        assert list(conn(client).request_payloads[0][1]) == ["EX", "I"]
        assert crafted.equipment_id == 6515211559 and crafted.gem_id is Gem.IGNIS
        assert client.equipment.inventory_space is not None

    def test_taking_the_gems_back_needs_consent(self):
        client = make_client({"ceq": xt_packet("ceq", {"E": ITEM})})
        with pytest.raises(ValueError, match="spend_rubies"):
            client.equipment.craft_equipment([1, 2], extract_gems=True)
        client.equipment.craft_equipment([1, 2], extract_gems=True, spend_rubies=True)
        assert conn(client).request_payloads == [("ceq", {"EX": 1, "I": [1, 2]})]


class TestEnchant:
    def test_eqe_pays_in_coins_by_default(self):
        client = make_client({"eqe": xt_packet("eqe", {"E": ITEM})})
        enchanted = client.equipment.enchant_equipment(6515211559)
        assert conn(client).request_payloads == [("eqe", {"C2": 0, "EID": 6515211559})]
        assert enchanted.enchantment_level == 1

    def test_eqe_in_rubies_needs_consent(self):
        client = make_client({"eqe": xt_packet("eqe", {"E": ITEM})})
        with pytest.raises(ValueError, match="spend_rubies"):
            client.equipment.enchant_equipment(1, pay_with_rubies=True)
        client.equipment.enchant_equipment(1, pay_with_rubies=True, spend_rubies=True)
        assert conn(client).request_payloads == [("eqe", {"C2": 1, "EID": 1})]

    def test_a_failed_enchantment_raises(self):
        client = make_client({"eqe": xt_packet("eqe", error_code=GGEError.ENCHANTING_FAILED)})
        with pytest.raises(CommandError) as raised:
            client.equipment.enchant_equipment(1)
        assert raised.value.error is GGEError.ENCHANTING_FAILED

    def test_ere_enchants_a_relic_item(self):
        client = make_client({"ere": xt_packet("ere", {"E": RELIC_ITEM})})
        relic = Equipment.model_validate(RELIC_ITEM)
        upgraded = client.equipment.enchant_relic(relic)
        assert conn(client).request_payloads == [("ere", {"C2": 0, "RIID": 6109572530, "EQ": 1})]
        assert isinstance(upgraded, Equipment) and upgraded.is_relic

    def test_ere_enchants_a_relic_gem(self):
        client = make_client({"ere": xt_packet("ere", {"E": RELIC_GEM})})
        upgraded = client.equipment.enchant_relic(RelicGem.model_validate(RELIC_GEM))
        assert conn(client).request_payloads == [("ere", {"C2": 0, "RIID": 88123, "EQ": 0})]
        assert isinstance(upgraded, RelicGem) and upgraded.enchantment_level == 1

    def test_an_item_that_is_no_relic_sends_nothing(self):
        client = make_client()
        with pytest.raises(ValueError, match="no relic"):
            client.equipment.enchant_relic(Equipment.model_validate(ITEM))
        assert conn(client).request_payloads == []


class TestGems:
    def test_cge_sends_the_centre_and_the_outer_gems(self):
        client = state_client({"cge": xt_packet("cge", {"S": 1, "esl": ESL})})
        result = client.equipment.craft_gem(Gem.IGNIS, [GemStack(gem_id=Gem.IGNIS, amount=3), Gem.IGNIS])
        assert conn(client).request_payloads == [("cge", {"MID": 333, "C2": 0, "UG": [333, 333]})]
        assert result.crafted is True
        assert client.equipment.inventory_space is not None

    def test_a_failed_craft_is_an_outcome(self):
        client = make_client({"cge": xt_packet("cge", {"S": 0})})
        assert client.equipment.craft_gem(Gem.IGNIS, [Gem.IGNIS]).crafted is False

    def test_the_ruby_craft_needs_consent(self):
        client = make_client()
        with pytest.raises(ValueError, match="spend_rubies"):
            client.equipment.craft_gem(Gem.IGNIS, [Gem.IGNIS], pay_with_rubies=True)

    def test_ege_takes_a_gem_out_for_rubies(self):
        client = make_client()
        item = Equipment.model_validate(ITEM)
        with pytest.raises(ValueError, match="spend_rubies"):
            client.equipment.extract_gem(item)
        client.equipment.extract_gem(item, commander_id=91, spend_rubies=True)
        assert conn(client).request_payloads == [("ege", {"EID": 6515211559, "LID": 91})]

    def test_ege_takes_a_relic_gem_out_for_fragments(self):
        client = make_client()
        relic = Equipment.model_validate([*RELIC_ITEM[:12], [4, 1, 9000, RELIC_GEM]])
        client.equipment.extract_gem(relic)
        assert conn(client).request_payloads == [("ege", {"EID": 6109572530, "LID": -1})]

    def test_an_item_without_a_gem_sends_nothing(self):
        client = make_client()
        with pytest.raises(ValueError, match="no gem"):
            client.equipment.extract_gem(Equipment.model_validate(RELIC_ITEM), spend_rubies=True)


class TestMerchantPushes:
    def test_beq_reads_the_items(self):
        push = parse_response("beq", {"I": [ITEM], "PID": "17", "TID": "117", "BT": 1})
        assert isinstance(push, BoughtEquipmentResponse)
        assert push.items[0].equipment_id == 6515211559 and (push.package_id, push.event_id) == (
            PackageId(17),
            Event(117),
        )
        assert push.buy_type is PackageBuyType.PRIVATE_OFFER

    def test_bri_reads_relic_items_and_gems(self):
        push = parse_response("bri", {"I": [[0, {"EQ": RELIC_ITEM}], [0, {"GEM": RELIC_GEM}]], "PID": 3})
        assert isinstance(push, BoughtRelicsResponse)
        item, gem = push.relics
        assert item.equipment is not None and item.relic_gem is None
        assert gem.relic_gem is not None and gem.equipment is None

    def test_bgm_reads_the_gems_and_its_inventory_space_reaches_state(self):
        payload = {"GEM": [333, "334"], "PID": 2, "esl": ESL}
        push = parse_response("bgm", payload)
        assert isinstance(push, BoughtGemsResponse)
        assert push.gem_ids == (Gem.IGNIS, Gem.AQUA)
        state = logged_in_state()
        state.update_from_packet("bgm", payload)
        assert state.get_inventory_space() == push.inventory_space
