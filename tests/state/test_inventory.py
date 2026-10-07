"""GameState inventory and economy sections: ggm, gls, esl, kpi, mpe, txi, nec and irc."""

from typing import Any

import pytest
from pydantic import ValidationError

from empire_core.castle import KingdomInfoResponse, ResourcePoolResponse, TaxStatus
from empire_core.commanders import GemInventoryResponse
from empire_core.enums import CollectableKind, Kingdom
from empire_core.gamedata import Currency, LootBox, LootBoxType, Tool, Unit
from empire_core.player import MercenaryMissionsResponse
from tests.state.test_castle_pushes import jaa_payload

RELIC_GEM = [5550001, 31, 4, 2900, [[311, 30, [9.5]], [317, 50, [5.5]]], 0]

# Shapes as a live login's gbd sends them, values changed
LOGIN: dict[str, Any] = {
    "gpi": {"PID": 7, "PN": "me"},
    "ggm": {"GEM": [], "RGEM": [RELIC_GEM]},
    "esl": {"E": 390, "G": 478, "TE": 400, "TG": 480},
    "kpi": {
        "UL": [
            {"KID": 0, "U": 1, "C": 0},
            {"KID": 1, "U": 0, "C": 0},
            {"KID": 4, "KRS": 500000, "CRS": 2, "U": 0, "C": 0},
        ],
        "fki": {"PA": 0, "RCR": 1, "BCR": 0, "RFLMS": False, "BFLMS": False},
    },
    "mpe": {
        "NM": 5000,
        "M": [
            {"D": 600, "RD": 0, "P": 190, "Q": 1, "S": 0, "R": [["S", 100], ["VP", 15], ["MS3", 2]], "ID": 1},
            {"D": 300, "RD": 0, "P": 0, "Q": 0, "S": 2, "R": [["U", [602, 3]]], "ID": 3},
        ],
    },
    "txi": {"TX": {"TT": 4, "RT": -17000000, "EM": 240, "IB": 0, "PO": 80, "VB": 5}},
}
GLS = {"ALL": [{"ID": 5, "AMT": 2}, {"ID": 9, "AMT": 1}], "KEY": [{"ID": 1, "AMT": 3}]}


class TestLoginSections:
    def test_every_section_is_read(self, state):
        state.update_from_packet("gbd", LOGIN)

        gems = state.get_gems()
        assert gems.gems == () and [gem.gem_id for gem in gems.relic_gems] == [5550001]
        assert gems.relic_gems[0].might == 2900
        space = state.get_inventory_space()
        assert (space.equipment_space, space.equipment_total_space, space.gem_space, space.gem_total_space) == (
            390,
            400,
            478,
            480,
        )
        kingdoms = state.get_kingdoms()
        assert [kingdom.kingdom_id for kingdom in kingdoms.kingdoms] == [Kingdom.GREEN, Kingdom.SANDS, Kingdom.STORM]
        assert kingdoms.kingdoms[2].kingdom_id is Kingdom.STORM
        assert kingdoms.kingdom(0).is_unlocked and not kingdoms.kingdom(1).is_unlocked
        assert kingdoms.kingdom(0).remaining_reset_seconds() is None
        assert 499990 < kingdoms.kingdom(4).remaining_reset_seconds() <= 500000
        assert kingdoms.unit_transfers == () and kingdoms.goods_transfers == ()
        missions = state.get_mercenary_missions()
        assert [mission.mission_id for mission in missions.missions] == [1, 3]
        rewards = [(reward.kind, reward.item, reward.amount) for reward in missions.missions[0].rewards]
        assert rewards == [
            (CollectableKind.STONE, None, 100),
            (CollectableKind.VIP_POINTS, None, 15),
            (CollectableKind.CURRENCY, Currency.SKIP_10_MINUTES, 2),
        ]
        assert missions.missions[1].rewards[0].item is Unit(602)
        assert 4990 < missions.remaining_next_missions_seconds() <= 5001
        tax = state.get_tax()
        assert tax.tax_type == 4 and tax.status is TaxStatus.WAIT_FOR_COLLECT
        for section in ("ggm", "esl", "kpi", "mpe", "txi"):
            assert state.get_last_packet_time(section) is not None

    def test_the_loot_boxes_pushed_before_the_gbd_stay(self, state):
        # The server sends gls before gbd; GBDCommand.exec's parse_GLS(undefined) changes nothing
        state.update_from_packet("gls", GLS)
        state.update_from_packet("gbd", LOGIN)
        boxes = state.get_loot_boxes()
        assert boxes.amount(5) == 2 and boxes.keys(1) == 3

    def test_reset_forgets_them(self, state):
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet("gls", GLS)
        state.reset()
        assert state.get_gems() is None and state.get_loot_boxes() is None and state.get_kingdoms() is None
        assert state.get_tax() is None and state.get_last_packet_time("txi") is None

    @pytest.mark.parametrize("section", ["ggm", "esl", "kpi", "mpe", "txi", "nec"])
    def test_a_falsy_section_is_not_applied(self, state, section):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, section: None})
        assert state.get_last_packet_time(section) is None


class TestGems:
    def test_a_ggm_counts_each_gem(self, state):
        state.update_from_packet("ggm", {"GEM": [[101, 2], [102, 1], [101, 1]], "RGEM": []})
        gems = state.get_gems()
        assert (gems.amount(101), gems.amount(102), gems.amount(103)) == (3, 1, 0)

    def test_a_gec_adds_and_takes_gems(self, state):
        # CastleGemData.updateInventory: a positive amount adds, a negative one takes away
        state.update_from_packet("ggm", {"GEM": [[101, 2]], "RGEM": [RELIC_GEM]})
        state.update_from_packet("gec", {"GEM": [[101, -1], [102, 2], [103, -1]]})
        gems = state.get_gems()
        assert {stack.gem_id: stack.amount for stack in gems.gems} == {101: 1, 102: 2}
        assert len(gems.relic_gems) == 1, "a gec keeps the relic gems"

    def test_a_gec_cannot_take_more_than_held(self):
        gems = GemInventoryResponse.model_validate({"GEM": [[101, 1]]}).changed([[101, -5]])
        assert gems.gems == ()

    def test_a_refused_gec_is_not_applied(self, state):
        state.update_from_packet("ggm", {"GEM": [[101, 2]], "RGEM": []})
        state.update_from_packet("gec", {"GEM": [[101, -2]]}, error_code=1)
        assert state.get_gems().amount(101) == 2

    @pytest.mark.parametrize("command", ["bgm", "ceq", "cge", "frc", "esl"])
    def test_replies_carrying_the_space(self, state, command):
        state.update_from_packet("gbd", LOGIN)
        body: dict[str, Any] = {"E": 380, "G": 470, "TE": 400, "TG": 480}
        state.update_from_packet(command, body if command == "esl" else {"esl": body})
        assert state.get_inventory_space().gem_space == 470

    def test_a_seq_reply_applies_its_space_with_the_commanders(self, state):
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet("seq", {"gli": {"C": [], "B": []}, "gcu": {"C1": 5}, "esl": {"E": 391, "TE": 400}})
        assert state.get_inventory_space().equipment_space == 391

    def test_the_free_equipment_space_can_be_negative(self, state):
        # parse_ESL keeps E as sent; isInventoryFull is E <= 0, filledInventorySpace TE - E
        state.update_from_packet("esl", {"E": -18, "TE": 400, "G": 226, "TG": 480})
        space = state.get_inventory_space()
        assert (space.equipment_space, space.equipment_total_space) == (-18, 400)
        assert space.equipment_total_space - space.equipment_space == 418


class TestLootBoxes:
    def test_a_gls_keeps_the_key_progress_it_does_not_list(self, state):
        # CastleLootboxData.parse_GLS sets the progress of each type KEY lists
        state.update_from_packet("gls", GLS)
        state.update_from_packet("gls", {"ALL": [{"ID": 5, "AMT": 1}], "KEY": [{"ID": 2, "AMT": 4}]})
        boxes = state.get_loot_boxes()
        assert boxes.amount(5) == 1 and boxes.amount(9) == 0
        assert (boxes.keys(1), boxes.keys(2)) == (3, 4)
        assert boxes.loot_boxes[0].loot_box_id is LootBox(5)
        assert boxes.key_progress[0].loot_box_type_id is LootBoxType.MYSTERY_BOX
        assert boxes.key_progress[1].loot_box_type_id == 2


class TestKingdoms:
    def test_a_kpi_updates_only_the_kingdoms_it_lists(self, state):
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet(
            "kpi", {"UL": [{"KID": 1, "U": 1, "C": 1, "SL": 2}], "UT": [{"KID": 1, "RS": 3600, "I": [[620, 5]]}]}
        )
        kingdoms = state.get_kingdoms()
        assert [kingdom.kingdom_id for kingdom in kingdoms.kingdoms] == [0, 1, 4]
        sands = kingdoms.kingdom(Kingdom.SANDS)
        assert sands.is_unlocked and sands.has_warehouse and sands.slum_level == 2
        (transfer,) = kingdoms.unit_transfers
        assert [(unit.kind, unit.item, unit.amount) for unit in transfer.units] == [
            (CollectableKind.UNITS, Tool.SHIELDS, 5)
        ]
        assert transfer.kingdom_id is Kingdom.SANDS and 3590 < transfer.remaining_seconds() <= 3600

    def test_a_kpi_without_transfers_clears_them(self, state):
        state.update_from_packet("kpi", {"UL": [], "RT": [{"KID": 2, "RS": 60, "G": [["W", 500]]}]})
        state.update_from_packet("kpi", {"UL": []})
        assert state.get_kingdoms().goods_transfers == ()

    @pytest.mark.parametrize("command", ["kgt", "kst", "kut", "msk", "fjf"])
    def test_replies_carrying_the_kingdoms(self, state, command):
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet(command, {"kpi": {"UL": [{"KID": 2, "U": 1, "C": 0}]}})
        assert state.get_kingdoms().kingdom(2).is_unlocked

    def test_a_goods_transfer_reply_applies_its_coins(self, state):
        state.update_from_packet("gbd", {**LOGIN, "gcu": {"C1": 100, "C2": 5}})
        state.update_from_packet("kgt", {"gcu": {"C1": 60, "C2": 5}, "kpi": {"UL": []}})
        assert state.get_local_player().coins == 60


class TestTax:
    @pytest.mark.parametrize(
        ("command", "body"),
        [
            ("txi", {"TX": {"TT": 2, "RT": 5400, "EM": 100, "IB": 0, "PO": 80, "VB": 5}}),
            ("txs", {"gcu": {"C1": 90}, "txi": {"TX": {"TT": 2, "RT": 5400, "EM": 100, "IB": 0, "PO": 80, "VB": 5}}}),
            ("btx", {"gcu": {"C1": 90}, "txi": {"TX": {"TT": 2, "RT": 5400, "EM": 100, "IB": 1, "PO": 80, "VB": 5}}}),
        ],
    )
    def test_replies_carrying_the_tax(self, state, command, body):
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet(command, body)
        tax = state.get_tax()
        assert tax.tax_type == 2 and tax.status is TaxStatus.COLLECTING

    def test_a_txc_reply_starts_over(self, state):
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet("txc", {"gcu": {"C1": 400}, "CT": 240, "txi": {"TX": {"TT": -1, "RT": 0}}})
        assert state.get_tax().status is TaxStatus.NONE

    def test_the_tax_handed_out_is_a_copy(self, state):
        state.update_from_packet("gbd", LOGIN)
        state.get_tax().tax_type = 0
        assert state.get_tax().tax_type == 4


class TestPushes:
    def test_an_mpe_reply_drops_collected_missions(self, state):
        # parse_MPE keeps missions below MISSION_STATE_COLLECTED (3)
        state.update_from_packet("mpe", {"NM": 60, "M": [{"ID": 1, "S": 3}, {"ID": 2, "S": 1, "RD": 120}]})
        (mission,) = state.get_mercenary_missions().missions
        assert mission.mission_id == 2 and 110 < mission.remaining_seconds() <= 120

    def test_an_nec_push(self, state):
        state.update_from_packet("nec", {"NCRS": 900, "LECT": 1700000000})
        expiry = state.get_construction_item_expiry()
        assert 890 < expiry.remaining_seconds() <= 900 and expiry.last_expired_at == 1700000000
        state.update_from_packet("nec", {"NCRS": -1, "LECT": 1700000900})
        assert state.get_construction_item_expiry().remaining_seconds() is None

    def test_an_irc_push(self, state):
        state.update_from_packet("irc", {"G": [["W", 120]], "EG": 1})
        pool = state.get_resource_pool()
        assert [(good.kind, good.amount) for good in pool.goods] == [
            (CollectableKind.WOOD, 120)
        ] and pool.has_extra_goods
        assert state.get_last_packet_time("irc") is not None

    def test_joining_a_castle_drops_the_resource_pool(self, state):
        # JAACommand.executeCommand calls resourcePoolData.reset() for the area it joins
        state.update_from_packet("irc", {"G": [["W", 120]]})
        state.update_from_packet("jaa", jaa_payload())
        assert state.get_resource_pool() is None


class TestModels:
    def test_a_mission_without_time_has_none_left(self):
        missions = MercenaryMissionsResponse.model_validate({"NM": 0, "M": [{"ID": 1, "S": 0, "RD": 0}]})
        assert missions.missions[0].remaining_seconds() == 0

    def test_the_collectables_cannot_change(self):
        missions = MercenaryMissionsResponse.model_validate({"M": [{"ID": 1, "R": [["S", 1]]}]})
        kingdoms = KingdomInfoResponse.model_validate({"UT": [{"KID": 1, "I": [[620, 5]]}], "RT": [{"G": [["W", 9]]}]})
        pool = ResourcePoolResponse.model_validate({"G": [["W", 120]]})
        rows = (
            missions.missions[0].rewards[0],
            kingdoms.unit_transfers[0].units[0],
            kingdoms.goods_transfers[0].goods[0],
            pool.goods[0],
        )
        assert rows[1].item is Tool.SHIELDS
        for row in rows:
            with pytest.raises(ValidationError):
                row.amount = 0  # type: ignore[misc]
