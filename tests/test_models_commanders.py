from empire_core.combat import Bonus, commander_bonuses
from empire_core.gamedata import GameData
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

        assert (hero.alien_string, weapon.alien_string, relic_hero.alien_string) == (1, None, None)
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
        castellan = self.castellan(LICID=16654603)

        assert castellan.locked_in_castle_id == 16654603
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
        assert commander.alien_gem_ids == [12, 13]

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

    def test_aie_wins_over_tae_even_when_empty(self):
        commander = Commander.model_validate({"ID": 1, "AIE": [], "TAE": [[53, [25.0]]]})

        assert commander.temporary_equipment == [[53, [25.0]]]
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
        assert (commander.alien_equipment, commander.alien_gem_ids) == (None, [])
        assert [b.effect_id for b in commander.alien_bonuses] == [54]


class TestRenameCommander:
    def test_the_payload_matches_c2s_rename_lord_vo(self):
        request = RenameCommanderRequest(LID=91, N="farm-1")

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
