"""Flank effect maths, ported from the client's combat helpers."""

from empire_core.combat import (
    AttackerFlankEffects,
    DefenderFlankEffects,
    FillOptions,
    Flank,
    Inventory,
    defender_flank_effects,
    fill_flank_with_soldiers,
    fill_wave,
    npc_camp_defence,
    pick_soldier_stack,
)
from empire_core.gamedata import GameData, UnitStats

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

    def test_a_roleless_unit_has_no_stack_value(self):
        # Tools are not units at all, and a unit with no role matches neither
        # bonus, so it can never be picked as a stack.
        assert data().get_unit(646) is None

        roleless = UnitStats.model_validate({"wodID": 1, "meleeAttack": "500"})
        assert AttackerFlankEffects().soldier_stack_attack_value(roleless, 10, 10) == 0

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


# =============================================================================
# Solver: soldier fill
# =============================================================================

SOLVER_PAYLOAD = {
    "units": [
        # Melee: 100 attack. Ranged: 270 attack. A ruby-healed and a mead unit
        # for the filters, and a pure defender that must never be picked.
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
            "wodID": 211,
            "name": "Barracks",
            "type": "MeadRanger",
            "role": "ranged",
            "rangeAttack": "270",
            "meleeDefence": "25",
            "rangeDefence": "42",
            "meadSupply": "2",
        },
        {
            "wodID": 700,
            "name": "Barracks",
            "type": "RubyKnight",
            "role": "melee",
            "meleeAttack": "500",
            "healingCostC2": "10",
        },
        {"wodID": 800, "name": "Barracks", "type": "Wall", "role": "melee", "meleeDefence": "900"},
    ],
}


def solver_data() -> GameData:
    return GameData.parse("test", SOLVER_PAYLOAD)


class TestInventory:
    def test_deduct_caps_at_stock_and_removes_empty_kinds(self):
        inv = Inventory({601: 5})

        assert inv.deduct(601, 10) == 5
        assert inv.available(601) == 0
        assert 601 not in inv.counts

    def test_deduct_leaves_the_remainder(self):
        inv = Inventory({601: 10})
        assert inv.deduct(601, 4) == 4
        assert inv.available(601) == 6

    def test_soldier_count_ignores_non_units(self):
        inv = Inventory({601: 5, 999999: 100})
        assert inv.soldier_count(solver_data()) == 5

    def test_non_positive_stacks_are_dropped(self):
        assert Inventory({601: 0, 211: -2}).counts == {}


class TestPickSoldierStack:
    def test_strongest_stack_wins_without_defender_info(self):
        game = solver_data()
        inv = Inventory({601: 100, 211: 100})

        pick = pick_soldier_stack(10, inv, game)

        # 270 > 100 per unit, so the ranged unit is chosen and deducted.
        assert pick == (211, 10)
        assert inv.available(211) == 90

    def test_melee_is_chosen_against_a_ranged_heavy_defence(self):
        game = solver_data()
        # A defence made only of ranged-defence strength: melee attack counters.
        defender = DefenderFlankEffects(range_units_range_strength=1000)

        pick = pick_soldier_stack(10, Inventory({601: 100, 211: 100}), game, defender=defender)

        assert pick[0] == 601

    def test_ranged_is_chosen_against_a_melee_heavy_defence(self):
        game = solver_data()
        defender = DefenderFlankEffects(melee_units_melee_strength=1000)

        pick = pick_soldier_stack(10, Inventory({601: 100, 211: 100}), game, defender=defender)

        assert pick[0] == 211

    def test_pure_defenders_are_never_picked(self):
        pick = pick_soldier_stack(10, Inventory({800: 100}), solver_data())
        assert pick is None

    def test_ruby_filter_excludes_the_expensive_unit(self):
        game = solver_data()
        inv = Inventory({601: 100, 700: 100})

        allowed = pick_soldier_stack(10, Inventory(inv.counts), game)
        blocked = pick_soldier_stack(10, Inventory(inv.counts), game, options=FillOptions(allow_c2_cost=False))

        assert allowed[0] == 700
        assert blocked[0] == 601

    def test_mead_filter_excludes_the_mead_unit(self):
        game = solver_data()
        pick = pick_soldier_stack(10, Inventory({211: 100, 601: 100}), game, options=FillOptions(allow_mead=False))
        assert pick[0] == 601

    def test_role_filters_restrict_the_pool(self):
        game = solver_data()

        melee_only = pick_soldier_stack(10, Inventory({601: 50, 211: 50}), game, options=FillOptions(use_ranged=False))
        assert melee_only[0] == 601

        assert pick_soldier_stack(10, Inventory({211: 50}), game, options=FillOptions(use_ranged=False)) is None

    def test_no_capacity_picks_nothing(self):
        assert pick_soldier_stack(0, Inventory({601: 10}), solver_data()) is None

    def test_stack_is_capped_by_remaining_capacity(self):
        inv = Inventory({601: 1000})
        assert pick_soldier_stack(7, inv, solver_data()) == (601, 7)
        assert inv.available(601) == 993


class TestFillFlank:
    def test_slots_are_filled_until_capacity_runs_out(self):
        game = solver_data()
        inv = Inventory({601: 10, 211: 10})

        placed = fill_flank_with_soldiers(15, 4, inv, game)

        # First slot takes 10 ranged (all of it), second the 5 melee that fit.
        assert placed == [(211, 10), (601, 5)]
        assert sum(count for _wod, count in placed) == 15

    def test_fill_stops_when_the_pool_is_empty(self):
        placed = fill_flank_with_soldiers(100, 5, Inventory({601: 3}), solver_data())
        assert placed == [(601, 3)]

    def test_no_slots_places_nothing(self):
        inv = Inventory({601: 10})
        assert fill_flank_with_soldiers(100, 0, inv, solver_data()) == []
        assert inv.available(601) == 10

    def test_empty_pool_places_nothing(self):
        assert fill_flank_with_soldiers(100, 3, Inventory({}), solver_data()) == []


class TestFillWave:
    def test_wave_is_ready_to_send(self):
        game = solver_data()
        inv = Inventory({601: 30})

        wave = fill_wave(inv, game, flank_capacity=10, flank_slots=1)

        assert wave.is_complete()
        payload = wave.model_dump(by_alias=True)
        assert payload["L"]["U"] == [[601, 10]]
        assert payload["M"]["U"] == [[601, 10]]
        assert payload["R"]["U"] == [[601, 10]]
        assert payload["L"]["T"] == []
        assert inv.available(601) == 0

    def test_inventory_is_shared_across_flanks(self):
        game = solver_data()
        inv = Inventory({601: 15})

        wave = fill_wave(inv, game, flank_capacity=10, flank_slots=1)

        payload = wave.model_dump(by_alias=True)
        assert payload["L"]["U"] == [[601, 10]]
        assert payload["M"]["U"] == [[601, 5]]
        assert payload["R"]["U"] == []

    def test_disabled_flanks_stay_empty(self):
        game = solver_data()
        inv = Inventory({601: 100})

        wave = fill_wave(
            inv,
            game,
            flank_capacity=10,
            flank_slots=1,
            options=FillOptions(fill_left=False, fill_right=False),
        )

        payload = wave.model_dump(by_alias=True)
        assert payload["L"]["U"] == []
        assert payload["M"]["U"] == [[601, 10]]
        assert payload["R"]["U"] == []

    def test_an_unfillable_wave_is_incomplete_not_an_error(self):
        wave = fill_wave(Inventory({}), solver_data(), flank_capacity=10, flank_slots=2)

        assert not wave.is_complete()
        assert wave.unit_count() == 0

    def test_per_flank_defence_steers_each_flank(self):
        game = solver_data()
        inv = Inventory({601: 100, 211: 100})

        wave = fill_wave(
            inv,
            game,
            flank_capacity=10,
            flank_slots=1,
            defence={
                Flank.LEFT: DefenderFlankEffects(melee_units_melee_strength=1000),
                Flank.RIGHT: DefenderFlankEffects(range_units_range_strength=1000),
            },
        )

        payload = wave.model_dump(by_alias=True)
        assert payload["L"]["U"][0][0] == 211  # melee-heavy defence -> ranged attack
        assert payload["R"]["U"][0][0] == 601  # ranged-heavy defence -> melee attack
