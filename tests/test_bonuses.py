"""Effect resolution: parsing, area and fight scoping, and the cap semantics."""

from empire_core.combat import (
    Bonus,
    CombatEffectType,
    EffectResolver,
    commander_bonuses,
    parse_bonus_entries,
)
from empire_core.gamedata import GameData
from empire_core.protocol.models import Commander

# Effect ids invented for the test; effect *types* are the real ones.
PAYLOAD = {
    "units": [],
    "effecttypes": [
        {"effectTypeID": "36", "name": "attackBonus", "sortCategory": "1"},
        {"effectTypeID": "9", "name": "meleeBonus", "sortCategory": "1"},
        {"effectTypeID": "23", "name": "offensiveMeleeBonus", "sortCategory": "1"},
        {"effectTypeID": "28", "name": "attackUnitAmountFlank", "sortCategory": "4"},
        {"effectTypeID": "19", "name": "wallReduction", "sortCategory": "1"},
        {"effectTypeID": "99", "name": "someEconomyThing", "sortCategory": "7"},
    ],
    "effects": [
        {"effectID": "100", "name": "atk", "effectTypeID": "36", "capID": "10"},
        {"effectID": "101", "name": "atkAlso", "effectTypeID": "36", "capID": "10"},
        {"effectID": "102", "name": "atkOtherCap", "effectTypeID": "36", "capID": "11"},
        {"effectID": "103", "name": "atkUncapped", "effectTypeID": "36", "capID": "99"},
        {"effectID": "110", "name": "melee", "effectTypeID": "9", "capID": "10"},
        {"effectID": "111", "name": "offMelee", "effectTypeID": "23", "capID": "10"},
        {"effectID": "120", "name": "flankUnits", "effectTypeID": "28", "capID": "99"},
        {"effectID": "130", "name": "wallRed", "effectTypeID": "19", "capID": "99"},
        {"effectID": "140", "name": "econ", "effectTypeID": "99", "capID": "99"},
        # Scoped: castles only, and a PvE-only variant.
        {"effectID": "150", "name": "atkCastlesOnly", "effectTypeID": "36", "capID": "99", "areaTypeID": "1,3"},
        {"effectID": "151", "name": "atkPvEOnly", "effectTypeID": "36", "capID": "99", "isPvEFight": "1"},
        {"effectID": "152", "name": "atkPvPOnly", "effectTypeID": "36", "capID": "99", "isPvPFight": "1"},
    ],
    "relicEffects": [
        # Same ids as the plain effects above, deliberately pointing elsewhere:
        # this is the real overlap that makes the id space matter.
        {"id": "100", "effectID": "120", "minimumValue": "5", "maximumValue": "35"},
        {"id": "120", "effectID": "100", "minimumValue": "5", "maximumValue": "35"},
    ],
    "effectCaps": [
        {"capID": "10", "maxTotalBonus": "50"},
        {"capID": "11", "maxTotalBonus": "20"},
        {"capID": "99"},
    ],
}


def data() -> GameData:
    return GameData.parse("test", PAYLOAD)


def resolver() -> EffectResolver:
    return EffectResolver(data())


class TestParsing:
    def test_plain_pair(self):
        assert parse_bonus_entries([[100, 25]]) == [Bonus(effect_id=100, value=25)]

    def test_commander_effect_shape(self):
        # Live gli shape: [effect_id, [value], source_tag]
        assert parse_bonus_entries([[111, [40.0], "AB"]]) == [Bonus(effect_id=111, value=40.0)]

    def test_equipment_bonus_shape(self):
        # Live EQ shape: [effect_id, strength_id, [value]]
        assert parse_bonus_entries([[4, 86, [116.3]]]) == [Bonus(effect_id=4, value=116.3)]

    def test_junk_entries_are_skipped(self):
        parsed = parse_bonus_entries([[100, 5], "nope", [], [999], [None, [1]], 42])
        assert parsed == [Bonus(effect_id=100, value=5)]

    def test_empty_input(self):
        assert parse_bonus_entries([]) == []
        assert parse_bonus_entries(None) == []


class TestAccumulation:
    def test_unknown_effects_contribute_nothing(self):
        assert resolver().accumulate([Bonus(effect_id=999999, value=99)], 36) == 0.0

    def test_bonuses_of_one_cap_are_summed(self):
        total = resolver().accumulate([Bonus(effect_id=100, value=10), Bonus(effect_id=101, value=15)], 36)
        assert total == 25

    def test_a_cap_limits_its_own_group(self):
        # Cap 10 tops out at 50.
        total = resolver().accumulate([Bonus(effect_id=100, value=40), Bonus(effect_id=101, value=40)], 36)
        assert total == 50

    def test_separate_caps_add_beyond_either_ceiling(self):
        # 50 from cap 10, 20 from cap 11, and cap 99 is uncapped: the group
        # totals are added with no further ceiling.
        total = resolver().accumulate(
            [
                Bonus(effect_id=100, value=90),
                Bonus(effect_id=102, value=90),
                Bonus(effect_id=103, value=7),
            ],
            36,
        )
        assert total == 50 + 20 + 7

    def test_cap_without_a_ceiling_is_uncapped(self):
        total = resolver().accumulate([Bonus(effect_id=103, value=500), Bonus(effect_id=103, value=500)], 36)
        assert total == 1000

    def test_ignore_cap(self):
        bonuses = [Bonus(effect_id=100, value=40), Bonus(effect_id=101, value=40)]
        assert resolver().accumulate(bonuses, 36, ignore_cap=True) == 80

    def test_other_effect_types_are_not_counted(self):
        total = resolver().accumulate([Bonus(effect_id=100, value=10), Bonus(effect_id=110, value=10)], 36)
        assert total == 10

    def test_economy_effects_are_dropped(self):
        bonuses = [Bonus(effect_id=140, value=10)]
        assert resolver().accumulate(bonuses, 99) == 0.0
        assert resolver().accumulate(bonuses, 99, include_economy=True) == 10


class TestScoping:
    def test_area_scoped_effect_only_counts_for_its_areas(self):
        bonuses = [Bonus(effect_id=150, value=30)]

        assert resolver().accumulate(bonuses, 36, area_type=1) == 30
        assert resolver().accumulate(bonuses, 36, area_type=2) == 0.0
        # Unknown target area keeps everything rather than guessing.
        assert resolver().accumulate(bonuses, 36) == 30

    def test_unscoped_effect_counts_everywhere(self):
        assert resolver().accumulate([Bonus(effect_id=100, value=5)], 36, area_type=99) == 5

    def test_pve_and_pvp_flags(self):
        pve = [Bonus(effect_id=151, value=10)]
        pvp = [Bonus(effect_id=152, value=10)]

        assert resolver().accumulate(pve, 36, player_target=False) == 10
        assert resolver().accumulate(pve, 36, player_target=True) == 0.0
        assert resolver().accumulate(pvp, 36, player_target=True) == 10
        assert resolver().accumulate(pvp, 36, player_target=False) == 0.0
        # Unknown target kind keeps both.
        assert resolver().accumulate(pve, 36) == 10


class TestCombatQuantities:
    def test_attack_multiplier_sums_three_effect_types(self):
        # attackBonus 10 + meleeBonus 5 + offensiveMeleeBonus 20 = 35%
        bonuses = [
            Bonus(effect_id=100, value=10),
            Bonus(effect_id=110, value=5),
            Bonus(effect_id=111, value=20),
        ]

        assert resolver().attack_multiplier(bonuses, melee=True) == 1.35
        # Ranged reads different types, so the melee-only bonuses do not apply.
        assert resolver().attack_multiplier(bonuses, melee=False) == 1.10

    def test_no_bonuses_means_an_unbuffed_multiplier(self):
        assert resolver().attack_multiplier([], melee=True) == 1.0

    def test_flank_unit_bonus_is_a_percentage(self):
        assert resolver().flank_unit_bonus([Bonus(effect_id=120, value=50)]) == 50

    def test_fortification_reductions_are_fractions(self):
        wall, gate, moat = resolver().fortification_reductions([Bonus(effect_id=130, value=25)])

        assert wall == 0.25
        assert (gate, moat) == (0.0, 0.0)


class TestIdSpaces:
    def test_the_same_id_means_different_things(self):
        # id 100 is an attack bonus as a plain effect, but points at the flank
        # unit amount effect as a relic effect.
        plain = Bonus(effect_id=100, value=10)
        relic = Bonus(effect_id=100, value=10, via_relic=True)
        r = resolver()

        assert r.effect_for(plain).effect_type_id == CombatEffectType.ATTACK_BONUS
        assert r.effect_for(relic).effect_type_id == CombatEffectType.ATTACK_UNIT_AMOUNT_FLANK

    def test_a_relic_bonus_is_not_counted_in_the_plain_space(self):
        relic = [Bonus(effect_id=100, value=10, via_relic=True)]

        assert resolver().accumulate(relic, CombatEffectType.ATTACK_BONUS) == 0.0
        assert resolver().accumulate(relic, CombatEffectType.ATTACK_UNIT_AMOUNT_FLANK) == 10

    def test_unknown_relic_id_contributes_nothing(self):
        assert resolver().accumulate([Bonus(effect_id=99999, value=5, via_relic=True)], 36) == 0.0


class TestCommanderBonuses:
    def test_bonuses_come_from_effects_area_effects_and_equipment(self):
        commander = Commander.model_validate(
            {
                "ID": 1,
                "E": [[110, [40.0], "AB"]],
                "AE": [[120, [50.0], "RH"]],
                # equipmentTypeID 1 = not a relic, so plain effect ids.
                "EQ": [[6406756464, 1, 2, 5, -1, [[100, 86, [10.0]]], -1, -1, 0, -1, -1, 1]],
            }
        )

        bonuses = commander_bonuses(commander)

        assert Bonus(effect_id=110, value=40.0) in bonuses
        assert Bonus(effect_id=120, value=50.0) in bonuses
        assert Bonus(effect_id=100, value=10.0, via_relic=False) in bonuses

    def test_relic_equipment_bonuses_are_tagged(self):
        # equipmentTypeID 3 = relic.
        commander = Commander.model_validate(
            {"ID": 1, "EQ": [[6291449662, 6, 2, 15, -1, [[100, 91, [13.7]]], -1, -1, 0, -1, -1, 3]]}
        )

        bonuses = commander_bonuses(commander)

        assert bonuses == [Bonus(effect_id=100, value=13.7, via_relic=True)]
        # Resolved in the relic space, this is a flank unit bonus, not an
        # attack bonus.
        assert resolver().flank_unit_bonus(bonuses) == 13.7
        assert resolver().attack_multiplier(bonuses, melee=True) == 1.0

    def test_a_bare_commander_grants_nothing(self):
        assert commander_bonuses(Commander.model_validate({"ID": 1})) == []

    def test_malformed_equipment_is_skipped(self):
        commander = Commander.model_validate({"ID": 1, "EQ": [[1, 2], "junk", [1, 2, 3, 4, 5, "not a list"]]})
        assert commander_bonuses(commander) == []
