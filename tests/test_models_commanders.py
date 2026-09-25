from empire_core.combat import Bonus, commander_bonuses
from empire_core.gamedata import GameData
from empire_core.protocol.models import Commander, Equipment, EquipmentType


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
        assert item.bonuses[0].effect_id == 242

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
