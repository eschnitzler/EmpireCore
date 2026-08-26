"""Flank effect maths, ported from the client's combat helpers."""

from empire_core.combat import (
    AttackerFlankEffects,
    DefenderFlankEffects,
    FillOptions,
    Flank,
    Inventory,
    WaveCapacity,
    defender_flank_effects,
    event_camp_defence,
    fill_flank_with_soldiers,
    fill_wave,
    fill_waves,
    is_legendary_fight,
    max_attackers,
    max_wave_count,
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


class TestEventCampDefence:
    PAYLOAD = dict(
        PAYLOAD,
        nomadCamps=[
            {
                "countVictory": "48",
                "defStrength": "8800",
                "defenceUnits": "601,211",
                "defenceTools": "646",
                "wallBonus": "30",
                "gateBonus": "30",
                "lordID": "-21",
            }
        ],
    )

    def data(self):
        return GameData.parse("test", self.PAYLOAD)

    def test_wall_and_gate_are_read_as_fractions(self):
        effects = event_camp_defence(self.data(), "nomadCamps", 48)

        assert effects is not None
        middle = effects[Flank.MIDDLE]
        assert (middle.wall_bonus, middle.gate_bonus) == (0.3, 0.3)

    def test_every_flank_is_defended(self):
        effects = event_camp_defence(self.data(), "nomadCamps", 48)

        # These tables list one defending force rather than a per-flank split.
        assert all(not e.is_empty() for e in effects.values())

    def test_unknown_camp_or_table(self):
        assert event_camp_defence(self.data(), "nomadCamps", 999) is None
        assert event_camp_defence(self.data(), "notATable", 48) is None


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
        # A defensive unit with a real attack value: fightType decides, not the
        # attack number, so this must never be picked.
        {
            "wodID": 604,
            "name": "Barracks",
            "type": "Halberd",
            "role": "melee",
            "meleeAttack": "17",
            "meleeDefence": "135",
            "rangeDefence": "50",
            "fightType": "1",
        },
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


def _capacity(units_per_flank: int, slots: int) -> WaveCapacity:
    """A hand-built capacity, so fill tests stay independent of the level maths."""
    return WaveCapacity(
        level=0,
        flank_soldiers=units_per_flank,
        middle_soldiers=units_per_flank,
        flank_tools=0,
        middle_tools=0,
        flank_unit_slots=slots,
        middle_unit_slots=slots,
        flank_tool_slots=0,
        middle_tool_slots=0,
    )


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

    def test_defensive_units_are_not_candidates_even_with_attack_value(self):
        # 604 is a halberdier: attack 17, but fightType 1. A large stack of it
        # would outscore a real attacker if the flag were ignored.
        game = solver_data()

        assert not game.get_unit(604).is_offensive
        assert pick_soldier_stack(1000, Inventory({604: 5000}), game) is None

        pick = pick_soldier_stack(1000, Inventory({604: 5000, 601: 50}), game)
        assert pick == (601, 50)

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

        wave = fill_wave(inv, game, _capacity(10, 1))

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

        wave = fill_wave(inv, game, _capacity(10, 1))

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
            _capacity(10, 1),
            options=FillOptions(fill_left=False, fill_right=False),
        )

        payload = wave.model_dump(by_alias=True)
        assert payload["L"]["U"] == []
        assert payload["M"]["U"] == [[601, 10]]
        assert payload["R"]["U"] == []

    def test_an_unfillable_wave_is_incomplete_not_an_error(self):
        wave = fill_wave(Inventory({}), solver_data(), _capacity(10, 2))

        assert not wave.is_complete()
        assert wave.unit_count() == 0

    def test_per_flank_defence_steers_each_flank(self):
        game = solver_data()
        inv = Inventory({601: 100, 211: 100})

        wave = fill_wave(
            inv,
            game,
            _capacity(10, 1),
            defence={
                Flank.LEFT: DefenderFlankEffects(melee_units_melee_strength=1000),
                Flank.RIGHT: DefenderFlankEffects(range_units_range_strength=1000),
            },
        )

        payload = wave.model_dump(by_alias=True)
        assert payload["L"]["U"][0][0] == 211  # melee-heavy defence -> ranged attack
        assert payload["R"]["U"][0][0] == 601  # ranged-heavy defence -> melee attack


# =============================================================================
# Wave capacity
# =============================================================================


class TestWaveCapacity:
    def test_capacity_follows_the_target_not_the_attacker(self):
        # Live samples, all made by the same level 70 attacker: a wave against
        # a level 13 castle holds far less than one against a level 70 castle.
        assert WaveCapacity.for_level(13).flank_soldiers == 15
        assert WaveCapacity.for_level(28).flank_soldiers == 30
        assert WaveCapacity.for_level(70).flank_soldiers == 64
        assert WaveCapacity.for_level(1).flank_soldiers == 3

    def test_flanks_and_middle_add_up_to_the_wave_total(self):
        # The middle takes what the two flanks leave, so the three must sum to
        # getMaxAttackers exactly at every level.
        for level in (1, 5, 12, 13, 26, 36, 50, 68, 69, 70, 100):
            capacity = WaveCapacity.for_level(level)
            assert capacity.total_soldiers() == max_attackers(level), f"level {level}"

    def test_attacker_count_caps_at_level_69(self):
        assert max_attackers(69) == 260
        assert max_attackers(70) == 320
        assert max_attackers(200) == 320

    def test_low_level_capacity_follows_the_linear_rule(self):
        # 5*level + 8, capped at 260.
        assert max_attackers(5) == 33
        assert max_attackers(12) == 68

    def test_level_70_matches_the_client(self):
        capacity = WaveCapacity.for_level(70)

        assert (capacity.flank_soldiers, capacity.middle_soldiers) == (64, 192)
        assert (capacity.flank_tools, capacity.middle_tools) == (40, 50)
        assert (capacity.flank_unit_slots, capacity.middle_unit_slots) == (2, 6)
        assert (capacity.flank_tool_slots, capacity.middle_tool_slots) == (2, 3)

    def test_slots_unlock_with_level(self):
        # Unit slots: flank [0, 13], middle [0, 0, 13, 13, 26, 26].
        assert WaveCapacity.for_level(12).flank_unit_slots == 1
        assert WaveCapacity.for_level(13).flank_unit_slots == 2
        assert WaveCapacity.for_level(12).middle_unit_slots == 2
        assert WaveCapacity.for_level(26).middle_unit_slots == 6
        # Tool slots: flank [0, 37], middle [0, 11, 37].
        assert WaveCapacity.for_level(36).flank_tool_slots == 1
        assert WaveCapacity.for_level(37).flank_tool_slots == 2
        assert WaveCapacity.for_level(10).middle_tool_slots == 1

    def test_flank_and_front_bonuses_are_independent(self):
        # The client resizes the sides and the middle from two different
        # effects, so one must not move the other.
        flank_only = WaveCapacity.for_level(70, flank_bonus_percent=50)
        front_only = WaveCapacity.for_level(70, front_bonus_percent=50)

        assert (flank_only.flank_soldiers, flank_only.middle_soldiers) == (96, 192)
        assert (front_only.flank_soldiers, front_only.middle_soldiers) == (64, 288)

    def test_matches_the_attack_dialog_across_targets(self):
        """Five targets captured from one level 70 attacker.

        Flank capacity matches exactly. The middle is within one unit on three
        of them because the game's effects panel rounds its percentages to one
        decimal, and the bonuses here are read off that panel.
        """
        castle = (57.8 + 60, 67.4 + 6.5)  # equipment + general
        camp = (46 + 60, 41 + 6.5)  # fewer effects apply to a camp
        legend = (30, 25)  # only in a legendary fight

        samples = [
            # target level, bonuses, legendary, expected flank, expected middle
            (13, castle, False, 32, 75),
            (28, castle, False, 65, 154),
            (70, castle, True, 159, 382),
            (1, camp, False, 6, 11),
            (45, camp, False, 96, 206),
        ]
        for level, (flank_bonus, front_bonus), legendary, want_flank, want_middle in samples:
            capacity = WaveCapacity.for_level(
                level,
                flank_bonus_percent=flank_bonus + (legend[0] if legendary else 0),
                front_bonus_percent=front_bonus + (legend[1] if legendary else 0),
            )
            assert capacity.flank_soldiers == want_flank, f"flank at level {level}"
            assert capacity.middle_soldiers == want_middle, f"middle at level {level}"

    def test_a_legendary_fight_needs_two_capped_players(self):
        assert is_legendary_fight(70, 70, target_is_player=True)
        assert not is_legendary_fight(70, 70, target_is_player=False)
        assert not is_legendary_fight(70, 45, target_is_player=True)
        assert not is_legendary_fight(60, 70, target_is_player=True)

    def test_bonuses_are_not_clamped(self):
        # An earlier version clamped these at 50%, which reproduced one target
        # and broke every other. Nothing in the tables caps them.
        assert WaveCapacity.for_level(70, flank_bonus_percent=60).flank_soldiers == 103
        assert WaveCapacity.for_level(70, flank_bonus_percent=117.8).flank_soldiers == 140

    def test_wave_count_unlocks_and_conquest_adds_two(self):
        assert max_wave_count(12) == 1
        assert max_wave_count(13) == 2
        assert max_wave_count(26) == 3
        assert max_wave_count(51) == 4
        assert max_wave_count(70, conquer=True) == 6
        assert max_wave_count(70, bonus=1) == 5

    def test_per_flank_lookups(self):
        capacity = WaveCapacity.for_level(70)

        assert capacity.soldier_capacity(Flank.MIDDLE) == 192
        assert capacity.soldier_capacity(Flank.LEFT) == 64
        assert capacity.soldier_capacity(Flank.RIGHT) == 64
        assert capacity.tool_slot_type(Flank.MIDDLE) == 1
        assert capacity.tool_slot_type(Flank.LEFT) == 2


class TestFillWaves:
    def test_waves_are_sized_and_counted_from_the_level(self):
        game = solver_data()
        # Level 13: 73 attackers, so 15 per flank and 43 in the middle.
        inventory = Inventory({601: 10_000})

        waves = fill_waves(inventory, game, level=13)

        assert len(waves) == 2
        first = waves[0].model_dump(by_alias=True)
        assert first["L"]["U"] == [[601, 15]]
        assert first["M"]["U"] == [[601, 43]]
        assert waves[0].unit_count() == max_attackers(13)

    def test_filling_stops_when_the_pool_runs_dry(self):
        game = solver_data()
        # Enough for the first wave and a little of the second.
        waves = fill_waves(Inventory({601: 80}), game, level=13)

        assert len(waves) == 2
        assert waves[0].unit_count() == 73
        assert waves[1].unit_count() == 7

    def test_no_units_means_no_waves(self):
        assert fill_waves(Inventory({}), solver_data(), level=70) == []

    def test_conquest_attacks_get_more_waves(self):
        game = solver_data()
        pool = {601: 10_000}

        normal = fill_waves(Inventory(pool), game, level=70)
        conquest = fill_waves(Inventory(pool), game, level=70, conquer=True)

        assert len(normal) == 4
        assert len(conquest) == 6

    def test_a_level_70_wave_maxes_out(self):
        waves = fill_waves(Inventory({601: 10_000}), solver_data(), level=70)

        assert waves[0].unit_count() == 320
