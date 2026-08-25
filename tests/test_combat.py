"""Flank effect maths, ported from the client's combat helpers."""

from empire_core.combat import (
    AttackerFlankEffects,
    DefenderFlankEffects,
    Flank,
    defender_flank_effects,
    npc_camp_defence,
)
from empire_core.gamedata import GameData

# Live rows: 211 is a ranged MeadRanger, 601 a melee unit, 646 a defence tool.
PAYLOAD = {
    "units": [
        {
            "wodID": 211,
            "name": "Barracks",
            "type": "MeadRanger",
            "role": "ranged",
            "rangeAttack": "270",
            "meleeDefence": "25",
            "rangeDefence": "42",
        },
        {
            "wodID": 601,
            "name": "Barracks",
            "type": "Swordsman",
            "role": "melee",
            "meleeAttack": "100",
            "meleeDefence": "60",
            "rangeDefence": "20",
        },
        {
            "wodID": 646,
            "name": "Dworkshop",
            "type": "Premiumstakes",
            "typ": "Defence",
            "slotTypes": "4,9",
            "moatBonus": "80",
        },
    ],
    "dungeons": [
        {
            "countVictories": "-6",
            "kID": "0",
            "lordID": "-21",
            "unitsM": "601+10#211+5",
            "toolM": "646+2",
            "unitsL": "601+2",
        },
    ],
}


def data() -> GameData:
    return GameData.parse("test", PAYLOAD)


class TestAttackerEffects:
    def test_stack_value_scales_with_capacity(self):
        effects = AttackerFlankEffects()
        unit = data().get_unit(211)

        # Capacity binds: 10 of a 270-attack unit.
        assert effects.soldier_stack_attack_value(unit, free_items=10, available=500) == 2700
        # Stock binds instead.
        assert effects.soldier_stack_attack_value(unit, free_items=500, available=3) == 810

    def test_bonus_is_applied_per_unit_and_truncated(self):
        # int() per unit, as the client does, not on the stack total.
        effects = AttackerFlankEffects(range_bonus=1.005)
        unit = data().get_unit(211)

        assert effects.soldier_stack_attack_value(unit, 10, 10) == 2710

    def test_role_selects_the_matching_bonus(self):
        effects = AttackerFlankEffects(melee_bonus=2.0, range_bonus=1.0)
        game = data()

        assert effects.soldier_stack_attack_value(game.get_unit(601), 1, 1) == 200
        assert effects.soldier_stack_attack_value(game.get_unit(211), 1, 1) == 270

    def test_a_tool_has_no_stack_attack_value(self):
        # Tools are not units and carry no role.
        effects = AttackerFlankEffects()
        tool_as_unit = data().get_unit(646)

        assert tool_as_unit is None

    def test_no_capacity_means_no_value(self):
        effects = AttackerFlankEffects()
        assert effects.soldier_stack_attack_value(data().get_unit(211), 0, 100) == 0


class TestDefenderAggregation:
    def test_defenders_credit_both_defences_to_their_own_role(self):
        effects = defender_flank_effects([(601, 10), (211, 5)], data())

        # 601 is melee: 60 melee / 20 range defence, ten of them.
        assert effects.melee_units_melee_strength == 600
        assert effects.melee_units_range_strength == 200
        # 211 is ranged: 25 melee / 42 range defence, five of them.
        assert effects.range_units_melee_strength == 125
        assert effects.range_units_range_strength == 210

    def test_defence_values_combine_both_groups(self):
        effects = defender_flank_effects([(601, 10), (211, 5)], data())

        assert effects.melee_defence_value() == 600 + 125
        assert effects.range_defence_value() == 210 + 200

    def test_reductions_are_subtracted_from_the_matching_bonus(self):
        effects = defender_flank_effects([(601, 10)], data())

        # melee_units_melee_strength * (1.0 - 0.25)
        assert effects.melee_defence_value(melee_reduction=0.25) == 450

    def test_bonuses_multiply(self):
        effects = defender_flank_effects([(601, 10)], data(), melee_bonus=1.5)
        assert effects.melee_defence_value() == 900

    def test_tools_among_the_stacks_are_not_counted_as_units(self):
        effects = defender_flank_effects([(646, 2)], data())
        assert effects.is_empty()

    def test_unknown_ids_are_reported_not_guessed(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="empire_core.combat.defence"):
            effects = defender_flank_effects([(999999, 5)], data())

        assert effects.is_empty()
        assert "matched no known unit or tool" in caplog.text

    def test_zero_and_negative_counts_are_ignored(self):
        assert defender_flank_effects([(601, 0), (211, -3)], data()).is_empty()


class TestNpcCampDefence:
    def test_camp_defence_is_read_per_flank(self):
        effects = npc_camp_defence(data(), victories=-6, kingdom_id=0)

        assert effects is not None
        middle = effects[Flank.MIDDLE]
        assert middle.melee_units_melee_strength == 600
        assert middle.range_units_range_strength == 210
        # Left flank holds two melee units, the right and keep nothing.
        assert effects[Flank.LEFT].melee_units_melee_strength == 120
        assert effects[Flank.RIGHT].is_empty()
        assert effects[Flank.YARD].is_empty()

    def test_unknown_camp_returns_none(self):
        assert npc_camp_defence(data(), victories=-6, kingdom_id=2) is None
        assert npc_camp_defence(data(), victories=99) is None

    def test_defending_tools_are_not_folded_in_yet(self):
        # toolM is "646+2"; its fortification is not resolvable yet, so the
        # bonuses stay at zero rather than being guessed.
        effects = npc_camp_defence(data(), victories=-6)

        assert effects[Flank.MIDDLE].moat_bonus == 0.0


class TestValueObjects:
    def test_an_empty_defence_has_no_value(self):
        effects = DefenderFlankEffects()
        assert effects.melee_defence_value() == 0
        assert effects.range_defence_value() == 0
        assert effects.is_empty()

    def test_flank_constants_match_the_client(self):
        assert (Flank.LEFT, Flank.MIDDLE, Flank.RIGHT, Flank.YARD) == (0, 1, 2, 3)
