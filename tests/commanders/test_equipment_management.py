"""Selling equipment and gems, binding gems, and the auto-sell rules."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.commanders import AutoSellEquipment, AutoSellRules, GemStack, RelicGem
from empire_core.enums import EquipmentSlot, Rareness
from empire_core.exceptions import CommandError
from empire_core.gamedata import GameData, Gem, GemColor, GemColorDef
from empire_core.protocol.models import GetAutoSellResponse
from tests.service_helpers import conn, make_client, xt_packet

GEM_COLORS: dict[str, Any] = {
    "gemColors": [{"gemColorID": str(color), "colorCode": "0x29ABE2"} for color in range(1, 10)],
}


def gem_client(script: dict[str, Any] | None = None):
    client = make_client(script)
    client.game_data = GameData.parse("787.03", GEM_COLORS)
    return client


class TestSellEquipment:
    """``CastleEquipmentData.sell`` sends ``seq`` (bundle lines 143798, 143923)."""

    def test_an_inventory_item_is_sold_from_no_commander(self):
        client = make_client()

        client.equipment.sell_equipment(6515211559)

        assert conn(client).request_payloads == [("seq", {"EID": 6515211559, "LID": -1, "EX": 0, "LFID": -1})]

    def test_a_worn_relic_is_sold_off_its_commander(self):
        client = make_client()

        client.equipment.sell_equipment(6109572530, commander_id=91)

        assert conn(client).request_payloads == [("seq", {"EID": 6109572530, "LID": 91, "EX": 0, "LFID": -1})]

    def test_a_refusal_raises(self):
        client = make_client({"seq": xt_packet("seq", error_code=114)})

        with pytest.raises(CommandError):
            client.equipment.sell_equipment(1)


class TestSellGem:
    """``CastleGemData.sell`` sends ``sge`` (bundle line 144376), ``RGEM`` 1 for a relic gem."""

    @pytest.mark.parametrize(
        ("gem", "payload"),
        [
            (Gem.IGNIS, {"GID": 333, "RGEM": 0, "LFID": -1}),
            (GemStack(gem_id=Gem.IGNIS, amount=4), {"GID": 333, "RGEM": 0, "LFID": -1}),
            (RelicGem.model_validate([88123, 2, 1, 3500, [], 0]), {"GID": 88123, "RGEM": 1, "LFID": -1}),
        ],
        ids=["gem", "gem stack", "relic gem"],
    )
    def test_the_gem_type_names_the_inventory(self, gem, payload):
        client = make_client()

        client.equipment.sell_gem(gem)

        assert conn(client).request_payloads == [("sge", payload)]


class TestBindGem:
    """``CastleGemData.bindGem`` sends ``bge`` (bundle lines 144353, 144452) with ``M`` 0."""

    def test_a_gem_is_bound_to_a_worn_item(self):
        client = make_client()

        client.equipment.bind_gem(Gem.IGNIS, 6515211559, 91)

        assert conn(client).request_payloads == [("bge", {"GID": 333, "EID": 6515211559, "LID": 91, "M": 0, "RGEM": 0})]

    def test_a_relic_gem_is_sent_as_one(self):
        client = make_client()

        client.equipment.bind_gem(RelicGem.model_validate([88123, 2, 1, 3500, [], 0]), 6109572530, 91)

        assert conn(client).request_payloads == [
            ("bge", {"GID": 88123, "EID": 6109572530, "LID": 91, "M": 0, "RGEM": 1})
        ]


class TestAutoSellModels:
    """``AutoSellEquipmentsVO.parseASG`` and ``AutoSellGemsVO.parseASG`` (bundle lines 46676, 120149)."""

    def test_the_hero_rarity_is_read_back_to_its_base(self):
        rules = GetAutoSellResponse.model_validate({"ECS": [[6, 11], [6, 14], [3, 2]], "GCS": [[5, 1], [0, 2]]})

        assert rules.equipment == (
            AutoSellEquipment(slot=EquipmentSlot.HERO, rareness=Rareness.COMMON),
            AutoSellEquipment(slot=EquipmentSlot.HERO, rareness=Rareness.LEGENDARY),
            AutoSellEquipment(slot=EquipmentSlot.HELMET, rareness=Rareness.RARE),
        )
        assert rules.gems == {GemColor.LIGHT_BLUE: 5, GemColor.DARK_BLUE: 0}

    def test_entries_outside_the_dialog_are_ignored(self):
        rules = GetAutoSellResponse.model_validate({"ECS": [[5, 1], [1, 5], "x", [2]], "GCS": None})

        assert (rules.equipment, rules.gems) == ((), {})

    def test_a_gem_color_names_its_row(self):
        assert GemColorDef.model_validate({"gemColorID": "6", "colorCode": "0xD3222F"}).color_id is GemColor.RED


class TestAutoSell:
    def test_get_auto_sell_reads_the_rules(self):
        client = gem_client({"asg": xt_packet("asg", {"ECS": [[1, 4]], "GCS": [[13, 9]]})})

        rules = client.equipment.get_auto_sell()

        assert conn(client).request_payloads == [("asg", {})]
        assert rules.equipment == (AutoSellEquipment(slot=EquipmentSlot.ARMOR, rareness=Rareness.LEGENDARY),)
        assert rules.gems == {GemColor.ORANGE: 13}

    def test_set_auto_sell_sends_both_lists_with_the_hero_on_its_wire_rarity(self):
        client = gem_client()
        rules = AutoSellRules(
            equipment=(
                AutoSellEquipment(slot=EquipmentSlot.HERO, rareness=Rareness.EPIC),
                AutoSellEquipment(slot=EquipmentSlot.WEAPON, rareness=Rareness.COMMON),
            ),
            gems={GemColor.RED: 4},
        )

        client.equipment.set_auto_sell(rules)

        sent = conn(client).request_payloads
        assert sent[0] == ("aes", {"ECS": [[6, 13], [2, 1]]})
        assert sent[1][0] == "ags"
        assert sorted(sent[1][1]["GCS"], key=lambda row: row[1]) == [
            [4 if color == 6 else 0, color] for color in range(1, 10)
        ]

    @pytest.mark.parametrize(
        "rules",
        [
            AutoSellRules(equipment=(AutoSellEquipment(slot=EquipmentSlot.SKIN, rareness=Rareness.COMMON),)),
            AutoSellRules(equipment=(AutoSellEquipment(slot=EquipmentSlot.ARMOR, rareness=Rareness.RELIC),)),
            AutoSellRules(gems={GemColor.RED: 14}),
            AutoSellRules(gems={42: 1}),
        ],
        ids=["skin slot", "relic rarity", "gem level", "unknown color"],
    )
    def test_rules_the_dialog_cannot_set_send_nothing(self, rules):
        client = gem_client()

        with pytest.raises(ValueError):
            client.equipment.set_auto_sell(rules)

        assert conn(client).request_payloads == []
