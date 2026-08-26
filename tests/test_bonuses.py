"""Effect resolution: parsing, area and fight scoping, and the cap semantics."""

from empire_core.combat import (
    AttackerFlankEffects,
    Bonus,
    CombatEffectType,
    EffectResolver,
    alliance_buff_bonuses,
    attacker_flank_effects,
    commander_bonuses,
    construction_item_bonuses,
    general_skill_bonuses,
    global_effect_bonuses,
    global_unit_attack_bonuses,
    legend_skill_value,
    parse_bonus_entries,
    parse_effect_spec,
    sceat_skill_bonuses,
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
        {"effectID": "160", "name": "atkOneSpace", "effectTypeID": "36", "capID": "99", "spaceIDs": "10"},
        {
            "effectID": "161",
            "name": "atkWarOnly",
            "effectTypeID": "36",
            "capID": "99",
            "playerRelation": "allianceInWar",
        },
        {"effectID": "162", "name": "atkOneBoss", "effectTypeID": "36", "capID": "99", "raidBossID": "7"},
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
        assert parse_bonus_entries([[111, [40.0], "AB"]]) == [Bonus(effect_id=111, value=40.0, raw_values=(40.0,))]

    def test_equipment_bonus_shape(self):
        # Live EQ shape: [effect_id, strength_id, [value]]
        assert parse_bonus_entries([[4, 86, [116.3]]]) == [Bonus(effect_id=4, value=116.3, raw_values=(116.3,))]

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

    def test_space_scoped_effect(self):
        bonuses = [Bonus(effect_id=160, value=10)]

        assert resolver().accumulate(bonuses, 36, space_id=10) == 10
        assert resolver().accumulate(bonuses, 36, space_id=0) == 0.0
        # Unknown space keeps it rather than guessing.
        assert resolver().accumulate(bonuses, 36) == 10

    def test_player_relation_scoped_effect(self):
        bonuses = [Bonus(effect_id=161, value=10)]

        assert resolver().accumulate(bonuses, 36, relation="allianceInWar") == 10
        assert resolver().accumulate(bonuses, 36, relation="sameAlliance") == 0.0
        assert resolver().accumulate(bonuses, 36) == 10

    def test_raid_boss_scoped_effect(self):
        bonuses = [Bonus(effect_id=162, value=10)]

        assert resolver().accumulate(bonuses, 36, raid_boss_id=7) == 10
        assert resolver().accumulate(bonuses, 36, raid_boss_id=8) == 0.0

    def test_an_unconditioned_effect_survives_every_filter(self):
        bonuses = [Bonus(effect_id=100, value=10)]

        assert (
            resolver().accumulate(
                bonuses,
                36,
                area_type=2,
                player_target=False,
                space_id=3,
                relation="samePlayer",
                raid_boss_id=1,
            )
            == 10
        )

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

        assert Bonus(effect_id=110, value=40.0, raw_values=(40.0,)) in bonuses
        assert Bonus(effect_id=120, value=50.0, raw_values=(50.0,)) in bonuses
        assert Bonus(effect_id=100, value=10.0, via_relic=False, raw_values=(10.0,)) in bonuses

    def test_relic_equipment_bonuses_are_tagged(self):
        # equipmentTypeID 3 = relic.
        commander = Commander.model_validate(
            {"ID": 1, "EQ": [[6291449662, 6, 2, 15, -1, [[100, 91, [13.7]]], -1, -1, 0, -1, -1, 3]]}
        )

        bonuses = commander_bonuses(commander)

        assert bonuses == [Bonus(effect_id=100, value=13.7, via_relic=True, raw_values=(13.7,))]
        # Resolved in the relic space, this is a flank unit bonus, not an
        # attack bonus.
        assert resolver().flank_unit_bonus(bonuses) == 13.7
        assert resolver().attack_multiplier(bonuses, melee=True) == 1.0

    def test_a_bare_commander_grants_nothing(self):
        assert commander_bonuses(Commander.model_validate({"ID": 1})) == []

    def test_malformed_equipment_is_skipped(self):
        commander = Commander.model_validate({"ID": 1, "EQ": [[1, 2], "junk", [1, 2, 3, 4, 5, "not a list"]]})
        assert commander_bonuses(commander) == []


# =============================================================================
# Non-equipment bonus sources
# =============================================================================

SOURCE_PAYLOAD = dict(
    PAYLOAD,
    constructionItems=[
        # The real shape: the flank unit limit item grants +2% per level, so
        # level 15 is the +30% a player sees on the flanks.
        {"constructionItemID": "440", "name": "attackUnitAmountFlank", "level": "15", "effects": "120&30"},
        {"constructionItemID": "1", "name": "barracksCost", "level": "1", "effects": "140&5"},
    ],
    alliancebuffs=[{"allianceBuffID": "7", "allianceBuffSeriesID": "3", "level": "4", "effects": "100&12"}],
    globalEffects=[{"globalEffectID": "5", "name": "attackBoost", "effects": "100&13,110&4"}],
    sceatSkills=[{"skillID": "41", "level": "1", "effects": "100&6"}],
    generalSkills=[{"skillID": "10110201", "generalID": "101", "name": "Aspect", "effects": "110&9"}],
    legendskills=[
        {"skillID": "1", "level": "1", "effectType": "gateReduction", "totalEffectValue": "3"},
        {"skillID": "2", "level": "2", "effectType": "gateReduction", "totalEffectValue": "7"},
        {"skillID": "9", "level": "1", "effectType": "wallReduction", "totalEffectValue": "5"},
    ],
)


def source_data() -> GameData:
    return GameData.parse("test", SOURCE_PAYLOAD)


class TestEffectSpec:
    def test_single_and_multiple(self):
        assert parse_effect_spec("66&30") == [Bonus(effect_id=66, value=30)]
        assert parse_effect_spec("100&13,110&4") == [
            Bonus(effect_id=100, value=13),
            Bonus(effect_id=110, value=4),
        ]

    def test_junk_is_skipped(self):
        assert parse_effect_spec("66&30,broken,&,7&") == [Bonus(effect_id=66, value=30)]
        assert parse_effect_spec(None) == []


class TestSources:
    def test_construction_items(self):
        game = source_data()

        bonuses = construction_item_bonuses(game, [440])

        assert bonuses == [Bonus(effect_id=120, value=30)]
        # Resolves as a flank unit limit, which is what the item is named for.
        assert EffectResolver(game).flank_unit_bonus(bonuses) == 30

    def test_unknown_ids_are_ignored(self):
        assert construction_item_bonuses(source_data(), [999999]) == []

    def test_alliance_global_sceat_and_general_sources(self):
        game = source_data()

        assert alliance_buff_bonuses(game, [7]) == [Bonus(effect_id=100, value=12)]
        assert global_effect_bonuses(game, [5]) == [
            Bonus(effect_id=100, value=13),
            Bonus(effect_id=110, value=4),
        ]
        assert sceat_skill_bonuses(game, [41]) == [Bonus(effect_id=100, value=6)]
        assert general_skill_bonuses(game, [10110201]) == [Bonus(effect_id=110, value=9)]

    def test_sources_combine_into_one_total(self):
        game = source_data()
        r = EffectResolver(game)
        bonuses = [
            *alliance_buff_bonuses(game, [7]),
            *global_effect_bonuses(game, [5]),
            *sceat_skill_bonuses(game, [41]),
        ]

        # Effect 100 is an attack bonus in cap 10, which tops out at 50.
        assert r.accumulate(bonuses, CombatEffectType.ATTACK_BONUS) == 12 + 13 + 6

    def test_legend_skills_sum_by_effect_type_name(self):
        game = source_data()

        assert legend_skill_value(game, [1, 2], "gateReduction") == 10
        assert legend_skill_value(game, [1, 9], "wallReduction") == 5
        assert legend_skill_value(game, [1], "moatReduction") == 0
        assert legend_skill_value(game, [999], "gateReduction") == 0


class TestAttackerFlankEffects:
    def test_built_from_a_commander_s_bonuses(self):
        game = source_data()
        r = EffectResolver(game)
        # attackBonus 10 + meleeBonus 5 + offensiveMeleeBonus 20 = +35% melee,
        # attackBonus alone for ranged, plus a wall reduction.
        bonuses = [
            Bonus(effect_id=100, value=10),
            Bonus(effect_id=110, value=5),
            Bonus(effect_id=111, value=20),
            Bonus(effect_id=130, value=25),
        ]

        effects = attacker_flank_effects(r, bonuses)

        assert effects.melee_bonus == 1.35
        assert effects.range_bonus == 1.10
        assert effects.wall_reduction == 0.25
        assert (effects.gate_reduction, effects.moat_reduction) == (0.0, 0.0)

    def test_no_bonuses_is_an_unbuffed_attack(self):
        effects = attacker_flank_effects(EffectResolver(source_data()), [])

        assert effects.melee_bonus == 1.0
        assert effects.range_bonus == 1.0

    def test_scoping_is_passed_through(self):
        game = source_data()
        r = EffectResolver(game)
        # Effect 150 is scoped to area types 1 and 3.
        bonuses = [Bonus(effect_id=150, value=30)]

        assert attacker_flank_effects(r, bonuses, area_type=1).melee_bonus == 1.30
        assert attacker_flank_effects(r, bonuses, area_type=2).melee_bonus == 1.0

    def test_a_buffed_attacker_changes_which_unit_wins(self):
        # The whole point of wiring this in: multipliers decide the pick.
        from empire_core.combat import Inventory, pick_soldier_stack
        from empire_core.gamedata import GameData

        units = GameData.parse(
            "test",
            {
                "units": [
                    {"wodID": 1, "role": "melee", "meleeAttack": "100", "fightType": "0"},
                    {"wodID": 2, "role": "ranged", "rangeAttack": "120", "fightType": "0"},
                ]
            },
        )
        unbuffed = pick_soldier_stack(10, Inventory({1: 100, 2: 100}), units)
        melee_buffed = pick_soldier_stack(
            10,
            Inventory({1: 100, 2: 100}),
            units,
            attacker=AttackerFlankEffects(melee_bonus=2.0),
        )

        assert unbuffed[0] == 2
        assert melee_buffed[0] == 1


class TestGlobalUnitAttackBonus:
    """The only thing that buffs a unit's attack value."""

    PAYLOAD = dict(
        PAYLOAD,
        effecttypes=[*PAYLOAD["effecttypes"], {"effectTypeID": "148", "name": "attackBonusUnit"}],
        effects=[
            *PAYLOAD["effects"],
            {"effectID": "273", "name": "attackBonusUnit", "effectTypeID": "148", "capID": "99"},
        ],
        # Live shape: a per-unit map, not a single value.
        globalEffects=[
            {"globalEffectID": "5", "name": "attackBoostSpeermanBowman", "effects": "273&602+13#608+13"},
            {"globalEffectID": "9", "name": "attackBoostElite", "effects": "273&9+60#10+60"},
            {"globalEffectID": "1", "name": "CooldownReduction", "effects": "100&50"},
            {
                "globalEffectID": "11",
                "name": "attackBoostLowLevels",
                "effects": "273&602+13",
                "minLevel": 10,
                "maxLevel": "30",
            },
        ],
    )

    def data(self):
        return GameData.parse("test", self.PAYLOAD)

    def test_per_unit_map_is_parsed(self):
        bonuses = global_unit_attack_bonuses(self.data(), [5])

        assert bonuses == {602: 13.0, 608: 13.0}

    def test_only_active_effects_count(self):
        assert global_unit_attack_bonuses(self.data(), []) == {}
        assert global_unit_attack_bonuses(self.data(), [999]) == {}

    def test_effects_of_other_types_are_ignored(self):
        # Effect 100 is an attack bonus, not a per-unit one.
        assert global_unit_attack_bonuses(self.data(), [1]) == {}

    def test_several_active_effects_combine(self):
        bonuses = global_unit_attack_bonuses(self.data(), [5, 9])

        assert bonuses == {602: 13.0, 608: 13.0, 9: 60.0, 10: 60.0}

    def test_a_live_strength_replaces_the_tables(self):
        # bie sends [id, seconds_left, strength]; one scalar lands on every unit
        # in the map.
        bonuses = global_unit_attack_bonuses(self.data(), [[5, 3600, 25]])

        assert bonuses == {602: 25.0, 608: 25.0}

    def test_a_strength_of_minus_one_leaves_the_table_alone(self):
        assert global_unit_attack_bonuses(self.data(), [[5, 3600, -1]]) == {602: 13.0, 608: 13.0}

    def test_an_effect_is_skipped_outside_its_level_bracket(self):
        game = self.data()

        assert global_unit_attack_bonuses(game, [11], player_level=20) == {602: 13.0}
        assert global_unit_attack_bonuses(game, [11], player_level=70) == {}
        assert global_unit_attack_bonuses(game, [11], player_level=5) == {}
        # No level to check against, so the bracket is not applied.
        assert global_unit_attack_bonuses(game, [11]) == {602: 13.0}

    def test_an_absent_ceiling_is_not_a_bar(self):
        assert global_unit_attack_bonuses(self.data(), [5], player_level=70) == {602: 13.0, 608: 13.0}

    def test_the_buff_is_added_before_the_multiplier(self):
        # The client adds the flat buff to the raw attack, then multiplies.
        from empire_core.gamedata import UnitStats

        unit = UnitStats.model_validate({"wodID": 602, "role": "melee", "meleeAttack": "100"})
        effects = AttackerFlankEffects(melee_bonus=2.0)

        plain = effects.soldier_stack_attack_value(unit, 10, 10)
        buffed = effects.soldier_stack_attack_value(unit, 10, 10, attack_bonus=13)

        assert plain == 2000
        assert buffed == (100 + 13) * 2 * 10

    def test_the_buff_never_lifts_a_unit_off_the_floor(self):
        # buffedMeleeAttack guards on the raw column: a melee unit with no melee
        # attack is worth nothing, buffed or not.
        from empire_core.gamedata import UnitStats

        unit = UnitStats.model_validate({"wodID": 602, "role": "melee", "meleeAttack": "0"})

        assert AttackerFlankEffects().soldier_stack_attack_value(unit, 10, 10, attack_bonus=13) == 0

    def test_a_commander_carrying_the_same_effect_type_does_not_buff_units(self):
        # Verified in the client: buffedMeleeAttack reads only the active
        # global-effect event, so a lord-side type 148 bonus does nothing here.
        game = self.data()
        commander_side = EffectResolver(game).accumulate([Bonus(effect_id=273, value=195)], 148)

        assert commander_side == 195  # it resolves...
        assert global_unit_attack_bonuses(game, []) == {}  # ...but never reaches a unit


class TestKeyedEffectValues:
    """A wod-id-keyed effect sends [wod_id, value]; the id is not the strength."""

    PAYLOAD = dict(
        PAYLOAD,
        effecttypes=[*PAYLOAD["effecttypes"], {"effectTypeID": "148", "name": "attackBonusUnit"}],
        effects=[
            *PAYLOAD["effects"],
            # A live relic row: despite the name it sits in the plain table.
            {
                "effectID": "22001",
                "name": "relicAttackBonusUnitKingsguardAttacker",
                "effectTypeID": "148",
                "capID": "99",
            },
        ],
    )

    def game(self):
        return GameData.parse("test", self.PAYLOAD)

    def test_the_strength_is_the_value_not_the_wod_id(self):
        # [wod_id 602, 13%] - a naive read makes this a 602% bonus.
        bonus = parse_bonus_entries([[22001, 86, [602, 13]]])[0]

        assert bonus.raw_values == (602.0, 13.0)
        assert bonus.strength(148) == 13.0
        assert EffectResolver(self.game()).accumulate([bonus], 148) == 13.0

    def test_a_live_keyed_entry_from_the_wire(self):
        # Straight out of an aci capture: effect 97 unitSpeedBoost, type 102,
        # four units at 6/6/5/5. The first number is a wod id.
        payload = dict(
            self.PAYLOAD,
            effecttypes=[*self.PAYLOAD["effecttypes"], {"effectTypeID": "102", "name": "unitSpeedBoost"}],
            effects=[
                *self.PAYLOAD["effects"],
                {"effectID": "97", "name": "unitSpeedBoost", "effectTypeID": "102", "capID": "99"},
            ],
        )
        game = GameData.parse("test", payload)
        bonus = parse_bonus_entries([[97, [628, 6.0, 630, 6.0, 631, 5.0, 636, 5.0], "RH"]])[0]

        assert bonus.strength(102) == 6.0
        assert EffectResolver(game).accumulate([bonus], 102) == 6.0

    def test_an_id_list_effect_keeps_its_first_number(self):
        # EffectValueIdList's strength getter returns idList[0], so for these
        # types the first number really is the value.
        bonus = parse_bonus_entries([[90, [12.0, 34.0]]])[0]

        assert bonus.strength(90) == 12.0

    def test_an_unkeyed_effect_still_reads_its_first_number(self):
        bonus = parse_bonus_entries([[100, 86, [40.0]]])[0]

        assert bonus.strength(36) == 40.0

    def test_a_keyed_spec_string_is_parsed_as_pairs(self):
        bonus = parse_effect_spec("22001&602+13#608+13")[0]

        assert bonus.raw_values == (602.0, 13.0, 608.0, 13.0)
        assert bonus.strength(148) == 13.0
