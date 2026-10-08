"""Tests for the commanders models."""

import logging

from empire_core.army.models.units import AttackWave
from empire_core.attack.models.send import CreateAttackResponse
from empire_core.combat import Bonus, commander_bonuses
from empire_core.commanders import AlienEquipment
from empire_core.commanders.models.roster import GetCommandersResponse
from empire_core.gamedata import GameData, Gem
from empire_core.protocol.models import (
    Castellan,
    Commander,
    Equipment,
    EquipmentType,
    RenameCommanderRequest,
    RenameCommanderResponse,
)


class TestEquipment:
    def test_a_plain_items_bonuses(self):
        # Shape of a live gli entry: [effect_id, [values]]
        item = Equipment.model_validate([4058749069, 1, 2, 4, 0, [[53, [25.0]]], -1, -1, 0, -1, -1, 0])

        assert [(b.effect_id, b.values) for b in item.bonuses] == [(53, [25.0])]
        assert item.relic_bonuses == []
        assert not item.is_relic

    def test_the_slotted_gem_is_a_gem_and_no_gem_is_none(self):
        # BasicEquipmentVO.parseEquipFromArray: int(e[10]), a gem unless NO_GEM_ID
        with_gem = Equipment.model_validate([1, 1, 2, 4, 0, [], -1, -1, 0, -1, "101", 0])
        without = Equipment.model_validate([1, 1, 2, 4, 0, [], -1, -1, 0, -1, -1, 0])

        assert (with_gem.gem_id, with_gem.has_gem) == (Gem.STONE_OF_THE_HUNTER_101, True)
        assert (without.gem_id, without.has_gem) == (None, False)
        assert Equipment.model_validate([1, 1, 2]).gem_id is None

    def test_a_scalar_value_is_wrapped_like_the_client(self):
        item = Equipment.model_validate([1, 1, 2, 4, 0, [[53, 25.0]]])

        assert item.bonuses[0].values == [25.0]

    def test_a_relic_items_bonuses(self):
        # Shape of a live relic entry: [relic_effect_id, power, [values]]
        item = Equipment.model_validate([6109572530, 1, 2, 5, -1, [[4, 84, [116.2]]], -1, -1, 0, -1, -1, 3])

        assert item.is_relic
        assert item.bonuses == []
        bonus = item.relic_bonuses[0]
        assert (bonus.relic_effect_id, bonus.power, bonus.values) == (4, 84, [116.2])

    def test_the_relic_check_reads_the_type_through_int(self):
        # CastleEquipmentFactory compares with ==, so "3" is a relic too.
        item = Equipment.model_validate([1, 1, 2, 5, -1, [[4, 84, [116.2]]], -1, -1, 0, -1, -1, "3"])

        assert item.is_relic
        assert item.equipment_type == EquipmentType.RELIC

    def test_a_hero_item_with_a_string_at_index_11_is_kept(self):
        # CastleHeroVO keeps index 11 as alienString; the type is still int() of it.
        item = Equipment.model_validate([1, 6, 2, 10, 0, [[242, [25.0]]], 802, 22, 0, -1, -1, "242&25"])

        assert (item.slot, item.equipment_type) == (6, EquipmentType.GENERATED)
        assert item.alien_string == "242&25"
        assert item.bonuses[0].effect_id == 242

    def test_only_a_hero_item_keeps_an_alien_string(self):
        hero = Equipment.model_validate([1, 6, 2, 10, 0, [], 802, 22, 0, -1, -1, 1])
        weapon = Equipment.model_validate([1, 2, 2, 4, 0, [], 802, 22, 0, -1, -1, 1])
        relic_hero = Equipment.model_validate([1, 6, 2, 15, -1, [[4, 84, [116.2]]], -1, -1, 0, -1, -1, 3])
        # The factory switches on row[1] with ===, so "6" is not a hero slot
        string_slot = Equipment.model_validate([1, "6", 2, 10, 0, [], 802, 22, 0, -1, -1, "242&25"])

        assert (hero.alien_string, weapon.alien_string, relic_hero.alien_string) == ("1", None, None)
        assert string_slot.alien_string is None

    def test_a_unique_temporary_item(self):
        item = Equipment.model_validate([1, 2, 2, 0, 0, [], 802, -1, 0, 3600, -1, 2])

        assert item.equipment_type == EquipmentType.UNIQUE_TEMPORARY
        assert not item.is_relic

    def test_has_set_reads_minus_one_as_no_set(self):
        assert Equipment.model_validate([1, 2, 2, 4, 0, [], 802, 22]).has_set
        assert not Equipment.model_validate([1, 2, 2, 4, 0, [], 802, -1]).has_set

    def test_a_row_without_a_set_id_counts_as_set_0_like_the_client(self):
        # parseEquipFromArray leaves _setID undefined, so hasSetbonus is true and int() reads it as 0
        item = Equipment.model_validate([880, 2, 2])

        assert (item.set_id, item.has_set) == (0, True)

    def test_an_unreadable_bonus_costs_only_itself(self):
        item = Equipment.model_validate([1, 1, 2, 4, 0, ["junk", [53, [25.0]]]])

        assert [b.effect_id for b in item.bonuses] == [53]


class TestCommanderEffects:
    def test_effects_are_typed(self):
        commander = Commander.model_validate({"ID": 1, "E": [[110, [40.0], "AB"]], "AE": [[120, [50.0], "RH"]]})

        assert [(e.effect_id, e.values, e.source) for e in commander.effects] == [(110, [40.0], "AB")]
        assert [(e.effect_id, e.values, e.source) for e in commander.area_effects] == [(120, [50.0], "RH")]

    def test_unreadable_effects_are_skipped(self):
        commander = Commander.model_validate({"ID": 1, "E": ["junk", [110, [40.0]], {"x": 1}], "AE": "junk"})

        assert [e.effect_id for e in commander.effects] == [110]
        assert commander.area_effects == []

    def test_equipment_is_typed_on_the_commander(self):
        commander = Commander.model_validate({"ID": 1, "EQ": [[880, 2, 2]], "AE": []})

        assert [(i.equipment_id, i.slot) for i in commander.equipment] == [(880, 2)]

    def test_commander_bonuses_read_the_typed_rows(self):
        commander = Commander.model_validate(
            {
                "ID": 1,
                "EQ": [
                    [1, 1, 2, 4, 0, [[53, [25.0]]], -1, -1, 0, -1, -1, 0],
                    [2, 2, 2, 5, -1, [[4, 84, [116.2]]], -1, -1, 0, -1, -1, 3],
                ],
            }
        )

        assert commander_bonuses(GameData(version="test"), commander) == [
            Bonus(effect_id=53, value=25.0, via_equipment=True, raw_values=(25.0,)),
            Bonus(effect_id=4, value=116.2, via_relic=True, raw_values=(116.2,)),
        ]


class TestCastellanAvailability:
    # Captured shape of a gli B entry
    ENTRY = {"ID": 1, "WID": 1, "VIS": 0, "N": "", "GID": -1, "W": 2, "D": 9, "SPR": 1, "EQ": []}

    def castellan(self, **keys):
        return Castellan.model_validate({**self.ENTRY, **keys})

    def test_a_castellan_locked_in_a_castle_is_not_available(self):
        castellan = self.castellan(LICID=2003)

        assert castellan.locked_in_castle_id == 2003
        assert castellan.is_locked_in_castle
        assert not castellan.is_available_for_movement(0)

    def test_a_free_castellan_is_available_in_any_kingdom(self):
        castellan = self.castellan(LICID=-1)

        assert not castellan.is_locked_in_castle
        assert all(castellan.is_available_for_movement(kingdom) for kingdom in (0, 1, 2, 3, 4, 10))

    def test_a_missing_licid_reads_as_0_like_the_client(self):
        # BaronVO.parseLord reads int(t.LICID), and int(undefined) is 0
        castellan = self.castellan()

        assert castellan.locked_in_castle_id == 0
        assert not castellan.is_available_for_movement(0)

    def test_an_island_portrait_moves_only_in_the_storm_islands(self):
        castellan = self.castellan(LICID=-1, VIS=13)

        assert castellan.is_available_for_movement(4)
        assert not castellan.is_available_for_movement(0)

    def test_a_faction_portrait_is_compared_with_the_faction_baron_id(self):
        # The client checks activeKingdomID == FactionConst.BARON_ID (-16), not the Berimond kingdom (10)
        castellan = self.castellan(LICID=-1, VIS=5)

        assert not castellan.is_available_for_movement(10)
        assert not castellan.is_available_for_movement(0)
        assert castellan.is_available_for_movement(-16)


class TestAlienEquipment:
    def test_a_flat_alien_block_is_all_equipment(self):
        commander = Commander.model_validate({"ID": 1, "EQ": [], "AIE": [[53, [25.0]], [54, [10]]], "GEM": [12, 13]})

        assert [(b.effect_id, b.values) for b in commander.alien_bonuses] == [(53, [25.0]), (54, [10])]
        assert commander.alien_hero_bonuses == []
        assert commander.alien_gem_ids == (12, 13)

    def test_a_two_part_block_splits_hero_and_equipment(self):
        commander = Commander.model_validate({"ID": 1, "AIE": [[[242, [25.0]]], [[53, [25.0]]]]})

        assert [b.effect_id for b in commander.alien_hero_bonuses] == [242]
        assert [b.effect_id for b in commander.alien_bonuses] == [53]

    def test_a_two_part_block_with_an_empty_hero_half(self):
        commander = Commander.model_validate({"ID": 1, "AIE": [[], [[53, [25.0]]]]})

        assert commander.alien_hero_bonuses == []
        assert [b.effect_id for b in commander.alien_bonuses] == [53]

    def test_two_flat_rows_are_not_mistaken_for_halves(self):
        # [53, [25.0]] has a number first, so the block is flat
        commander = Commander.model_validate({"ID": 1, "TAE": [[53, [25.0]], [54, [10]]]})

        assert commander.alien_hero_bonuses == []
        assert [b.effect_id for b in commander.alien_bonuses] == [53, 54]

    def test_the_block_is_split_into_hero_and_equipment_bonuses(self):
        block = AlienEquipment.model_validate([[[242, [25.0]]], [[53, [25.0]], [54, 10]]])
        assert [b.effect_id for b in block.hero_bonuses] == [242]
        assert [(b.effect_id, b.values) for b in block.bonuses] == [(53, [25.0]), (54, [10])]

    def test_aie_wins_over_tae_even_when_empty(self):
        commander = Commander.model_validate({"ID": 1, "AIE": [], "TAE": [[53, [25.0]]]})

        assert commander.alien_equipment == AlienEquipment()
        assert commander.temporary_equipment is not None
        assert [b.effect_id for b in commander.temporary_equipment.bonuses] == [53]
        assert commander.alien_bonuses == []

    def test_equipment_in_eq_hides_the_alien_block(self):
        commander = Commander.model_validate(
            {"ID": 1, "EQ": [[1, 1, 2, 4, 0, [[53, [25.0]]], -1, -1, 0, -1, -1, 0]], "AIE": [[54, [10]]]}
        )

        assert commander.alien_bonuses == []

    def test_unreadable_blocks_cost_only_themselves(self):
        commander = Commander.model_validate(
            {"ID": 1, "N": "x", "AIE": "junk", "GEM": 5, "TAE": [["junk"], [54, [10]]]}
        )

        assert commander.name == "x"
        assert (commander.alien_equipment, commander.alien_gem_ids) == (None, ())
        assert [b.effect_id for b in commander.alien_bonuses] == [54]


class TestRenameCommander:
    def test_the_payload_matches_c2s_rename_lord_vo(self):
        request = RenameCommanderRequest(commander_id=91, name="farm-1")

        assert request.command == "arl"
        assert list(request.to_payload().items()) == [("LID", 91), ("N", "farm-1")]

    def test_a_reply_without_gli_is_an_empty_roster(self):
        response = RenameCommanderResponse.model_validate({})

        assert response.commander_roster.commanders == []


class TestAlienEquipmentBonuses:
    def test_aie_rows_count_through_the_equipment_effect_table(self):
        game_data = GameData.parse(
            "test",
            {
                "effects": [{"effectID": "326", "name": "x", "effectTypeID": "1"}],
                "equipment_effects": [{"equipmentEffectID": "37", "effectID": "326"}],
            },
        )
        commander = Commander.model_validate({"ID": 1, "EQ": [], "AIE": [[[37, [5]]], [[37, [10]]]]})
        bonuses = commander_bonuses(game_data, commander)
        assert sorted(bonus.via_equipment for bonus in bonuses) == [True, True]
        assert [bonus.effect_id for bonus in bonuses] == [37, 37]

    def test_aie_is_ignored_while_eq_has_items(self):
        game_data = GameData.parse("test", {})
        item = [1, 1, 1, 1, 0, [[37, [5]]], 0, -1, 0, -1, -1, 0]
        commander = Commander.model_validate({"ID": 1, "EQ": [item], "AIE": [[37, [10]]]})
        assert len(commander_bonuses(game_data, commander)) == 1


def test_a_null_set_id_or_odd_rarity_keeps_the_item():
    # parseEquipFromArray stores e[3] and e[7] raw; getUniqueBoni reads the set through int()
    item = Equipment.model_validate([4, 2, 2, "rare", 0, [], 802, None])
    assert (item.rarity_id, item.set_id, item.has_set) == (0, 0, True)


def test_alien_equipment_gems_count_while_it_stands_in_for_eq():
    game_data = GameData.parse(
        "test",
        {
            "effects": [{"effectID": "504", "name": "x", "effectTypeID": "1"}],
            "gems": [{"gemID": "333", "effects": "504&20"}],
        },
    )
    alien = Commander.model_validate({"ID": 1, "EQ": [], "AIE": [], "GEM": [333, "333", 999]})
    # getGemVO looks the id up as sent in an int-keyed table, so "333" and 999 find nothing
    assert [(b.effect_id, b.value) for b in commander_bonuses(game_data, alien)] == [(504, 20.0)]
    worn = Commander.model_validate({"ID": 1, "EQ": [[1, 1, 1, 1, 0, [], 0, -1, 0, -1, -1, 0]], "GEM": [333]})
    assert commander_bonuses(game_data, worn) == []


def test_equipment_bonuses_come_before_the_commanders_own():
    game_data = GameData.parse("test", {})
    item = [1, 1, 1, 1, 0, [[37, [5]]], 0, -1, 0, -1, -1, 0]
    commander = Commander.model_validate({"ID": 1, "EQ": [item], "E": [[2111, [150]]]})
    assert [b.effect_id for b in commander_bonuses(game_data, commander)] == [37, 2111]


def test_items_count_in_slot_order_and_one_per_slot():
    game_data = GameData.parse("test", {})

    def item(slot: int, effect_id: int) -> list:
        return [slot * 10 + effect_id, slot, 1, 1, 0, [[effect_id, [1]]], 0, -1, 0, -1, -1, 0]

    # Armor (1), then two helmets (3), then a slot the client has no place for (9)
    commander = Commander.model_validate({"ID": 1, "EQ": [item(1, 11), item(3, 31), item(3, 32), item(9, 91)]})
    # parseLord's slots run helmet, armor, weapon, ...; the second helmet replaces the first
    assert [b.effect_id for b in commander_bonuses(game_data, commander)] == [32, 11]


def test_unreadable_eq_rows_still_keep_aie_out():
    commander = Commander.model_validate({"ID": 1, "EQ": [None], "AIE": [[37, [10]]]})
    assert commander.equipment == []
    assert not commander.uses_alien_equipment and commander.alien_bonuses == []


class TestRelicInfo:
    # A captured relic row: index 12 is [relic_type_id, relic_category_id, might, gem]
    RELIC = [
        6109572530, 1, 2, 5, -1,
        [[4, 84, [116.2]], [5, 61, [75.1]], [103, 53, [11.7]]],
        -1, -1, 0, -1, -1, 3,
        [1, 6, 2980, [890593, 32, 6, 2770, [[302, 61, [34.7]], [305, 62, [10.0]], [307, 54, [4.6]]], 0]],
    ]  # fmt: skip

    def test_a_relic_carries_its_type_might_and_gem(self):
        from empire_core.commanders.models.roster import Equipment

        item = Equipment.model_validate(self.RELIC)
        assert item.is_relic and len(item.relic_bonuses) == 3
        info = item.relic_info
        assert info is not None and (info.relic_type_id, info.relic_category_id, info.might) == (1, 6, 2980)
        assert info.gem is not None
        assert (info.gem.gem_id, info.gem.relic_type_id, info.gem.might, info.gem.enchantment_level) == (
            890593, 32, 2770, 0,
        )  # fmt: skip
        assert [b.relic_effect_id for b in info.gem.bonuses] == [302, 305, 307]

    def test_no_gem_and_ordinary_items(self):
        from empire_core.commanders.models.roster import Equipment

        assert Equipment.model_validate([*self.RELIC[:12], [1, 6, 2980, []]]).relic_info.gem is None  # type: ignore[union-attr]
        assert Equipment.model_validate([*self.RELIC[:12], "junk"]).relic_info is None
        ordinary = [*self.RELIC[:11], 0, [1, 6, 2980, []]]
        assert Equipment.model_validate(ordinary).relic_info is None


class TestDriftedEquipmentEntries:
    """A drifted EQ entry must be skipped, not raised through the accessor."""

    def test_unparseable_entries_are_skipped_and_logged(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.commanders.models.roster"):
            response = GetCommandersResponse.model_validate(
                {"C": [{"ID": 91, "EQ": [{"nested": 1}, 5, [880, "not-a-slot"], [880, 2, 2]]}]}
            )
        items = response.commanders[0].equipment

        assert [(i.equipment_id, i.slot) for i in items] == [(880, 2)]
        assert "3/4" in caplog.text

    def test_a_flank_entry_that_is_not_a_pair_counts_as_no_units(self):
        # A padded or truncated slot must not raise out of the wave check.
        assert AttackWave.model_validate({"L": {"U": [[487]]}}).unit_count() == 0
        assert AttackWave.model_validate({"L": {"U": [[487, 5, 1], [488, 2]]}}).unit_count() == 7
        assert AttackWave.model_validate({"L": {"U": [[-1, 0]]}}).is_complete() is False

    def test_a_movement_without_a_usable_id_reports_none(self):
        assert CreateAttackResponse.model_validate({"AAM": {"M": []}}).movement_id is None
        assert CreateAttackResponse.model_validate({"AAM": {"M": {"MID": "x"}}}).movement_id is None
        assert CreateAttackResponse.model_validate({"AAM": {"M": {"MID": "7"}}}).movement_id == 7

    def test_leader_comes_back_under_um(self):
        # Captured from an accepted live cra: LID=0 selected commander 0, and the
        # server echoed that commander, equipment included, under AAM.UM.L.
        response = CreateAttackResponse.model_validate(
            {
                "AAM": {
                    "M": {"MID": 58246863},
                    "UM": {
                        "PWD": 0,
                        "TWD": 0,
                        "L": {
                            "ID": 0,
                            "WID": 2,
                            "N": "",
                            "W": 1,
                            "D": 0,
                            "SPR": 1,
                            "EQ": [[6515211113, 6, 2, 10, 0, [[242, [25.0]]], 802, 22, 0, -1, -1, 1]],
                            "AE": [],
                        },
                    },
                    "FA": {"L": [[10, 1]], "M": [], "R": [], "RW": []},
                }
            }
        )

        leader = response.leader
        assert leader is not None
        assert (leader.commander_id, leader.wins, leader.win_spree) == (0, 1, 1)
        assert leader.equipment[0].slot == 6

    def test_leader_is_none_when_the_server_sends_no_commander(self):
        assert CreateAttackResponse.model_validate({"AAM": {"M": {}}}).leader is None
        assert CreateAttackResponse.model_validate({"AAM": {"UM": {"L": []}}}).leader is None
        assert CreateAttackResponse.model_validate({"AAM": {"UM": {"L": {"N": "no id"}}}}).leader is None


class TestGeneralData:
    def test_a_battle_log_commander_carries_its_general(self):
        # A battle log's AL: a default commander by DLID, with GeneralVO.parseData's keys
        commander = Commander.model_validate(
            {"DLID": -45, "GID": 115, "GEM": [], "XP": 1200, "LU": 1, "OXP": 900, "SIDS": [3, 4], "AE": []}
        )
        assert commander.commander_id == -45
        assert (commander.general_xp, commander.general_old_xp) == (1200, 900)
        assert commander.general_has_level_up is True
        assert commander.general_is_new is False
        assert commander.general_skill_ids == (3, 4)
        assert commander.general_selected_abilities == ()

    def test_a_default_commander_with_a_general_has_the_client_defaults(self):
        commander = Commander.model_validate({"DLID": -45, "GID": 115})
        assert (commander.general_xp, commander.general_old_xp) == (0, 0)
        assert (commander.general_is_new, commander.general_has_level_up) == (False, False)
        assert (commander.general_skill_ids, commander.general_selected_abilities) == ((), ())

    def test_sent_values_read_as_parse_data_reads_them(self):
        commander = Commander.model_validate({"ID": 1, "SIDS": None, "IN": "1", "XP": None})
        assert commander.general_xp == 0
        assert commander.general_skill_ids == ()
        assert commander.general_is_new is True

    def test_a_skill_entry_that_is_not_an_id_costs_only_itself(self, caplog):
        commander = Commander.model_validate({"DLID": -45, "GID": 115, "SIDS": [3, "x", 4]})
        assert commander.general_skill_ids == (3, 4)
        assert "Skipped 1/3 general skills that are not ids, first: 'x'" in caplog.text

    def test_an_entry_without_general_data_leaves_it_none(self):
        # The client reads it only for default or battle-log commanders; a roster entry carries none
        commander = Commander.model_validate({"ID": 1, "GID": 115})
        assert commander.general_xp is None
        assert commander.general_skill_ids is None
        assert commander.general_has_level_up is None
