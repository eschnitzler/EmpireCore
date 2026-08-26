"""Flank effect maths, ported from the client's combat helpers."""

import pytest

from empire_core.combat import (
    AttackerFlankEffects,
    DefenderFlankEffects,
    FillOptions,
    Flank,
    Inventory,
    WaveCapacity,
    boost_to_modifier,
    defender_flank_effects,
    event_camp_defence,
    fill_flank_with_soldiers,
    fill_wave,
    fill_waves,
    fill_yard_wave,
    is_legendary_fight,
    max_attackers,
    max_wave_count,
    minimum_owner_level,
    npc_camp_defence,
    pick_soldier_stack,
    wave_level,
    wave_limit_violations,
    yard_capacity,
)
from empire_core.gamedata import GameData, UnitStats
from empire_core.protocol.models import AttackWave, WaveFlank
from empire_core.protocol.models.map import MapItemType

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

    def test_a_defending_tool_raises_the_fortification(self):
        # 646 is a moat tool worth 80%. The client adds a defending tool's
        # bonus once per stack, whatever the stack holds, so two of them are
        # still one 80%.
        effects = defender_flank_effects([(646, 2)], data(), moat_bonus=0.5)

        assert effects.moat_bonus == pytest.approx(1.3)

    def test_only_the_middle_meets_the_gate(self):
        stacks = [(601, 10)]
        kwargs = {"wall_bonus": 0.3, "gate_bonus": 0.3, "moat_bonus": 0.3}

        middle = defender_flank_effects(stacks, data(), flank=Flank.MIDDLE, **kwargs)
        left = defender_flank_effects(stacks, data(), flank=Flank.LEFT, **kwargs)

        assert middle.gate_bonus == 0.3
        assert left.gate_bonus == 0.0
        # Only the gate is flank-specific.
        assert left.wall_bonus == 0.3
        assert left.moat_bonus == 0.3

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


class TestYardCapacity:
    """The courtyard / final-assault wave."""

    def test_matches_four_captured_dialogs(self):
        # One account, attacker level 70, four targets. The implied bonus is
        # identical across all four, which is what confirms the formula.
        for target_level, expected in ((1, 3109), (13, 3349), (45, 3989), (70, 4489)):
            assert yard_capacity(70, target_level, bonus=2872) == expected

    def test_it_grows_with_both_levels(self):
        # Unlike a flank, the attacker's own level counts here too.
        assert yard_capacity(70, 10) > yard_capacity(10, 10)
        assert yard_capacity(70, 70) > yard_capacity(70, 10)

    def test_the_bonus_is_absolute_not_a_percentage(self):
        plain = yard_capacity(70, 13)
        assert yard_capacity(70, 13, bonus=100) == plain + 100

    def test_the_boost_is_a_multiplier_applied_last(self):
        import math

        plain = yard_capacity(70, 13, bonus=2872)
        # The client rounds once, at the end, so doubling the *rounded* result
        # is not the same answer: 3349.33 x 2 rounds to 6699, not 6698.
        unrounded = 20 * math.sqrt(70) + 50 + 20 * 13 + 2872

        assert boost_to_modifier(0) == 1.0
        assert yard_capacity(70, 13, bonus=2872, boost=0) == plain
        assert yard_capacity(70, 13, bonus=2872, boost=100) == round(unrounded * 2.0)

    def test_a_negative_boost_cannot_go_below_zero(self):
        assert boost_to_modifier(-500) == 0.0
        assert yard_capacity(70, 13, bonus=2872, boost=-500) == 0


class TestWaveWithTools:
    """A wave now carries tools, and the client's ordering is observable."""

    PAYLOAD = dict(
        SOLVER_PAYLOAD,
        units=[
            *SOLVER_PAYLOAD["units"],
            {
                "wodID": 611,
                "name": "Workshop",
                "type": "Ram",
                "typ": "Attack",
                "slotTypes": "1,2,9",
                "gateBonus": "10",
                "fightType": "1",
            },
        ],
    )

    def data(self):
        return GameData.parse("test", self.PAYLOAD)

    def capacity(self):
        return WaveCapacity(
            level=70,
            flank_soldiers=10,
            middle_soldiers=10,
            flank_tools=5,
            middle_tools=5,
            flank_unit_slots=1,
            middle_unit_slots=1,
            flank_tool_slots=1,
            middle_tool_slots=1,
        )

    def test_tools_are_placed_alongside_units(self):
        game = self.data()
        inv = Inventory({601: 100, 611: 100})
        defence = {
            f: DefenderFlankEffects(gate_bonus=0.30, melee_units_melee_strength=50)
            for f in (Flank.LEFT, Flank.MIDDLE, Flank.RIGHT)
        }

        wave = fill_wave(inv, game, self.capacity(), defence=defence)

        payload = wave.model_dump(by_alias=True)
        assert payload["L"]["T"] == [[611, 3]]  # 30 gate / 10 per ram
        assert payload["L"]["U"] == [[601, 10]]

    def test_tools_are_returned_when_a_flank_gets_no_units(self):
        game = self.data()
        # Rams but no soldiers: the tools must come back rather than be sent.
        inv = Inventory({611: 100})
        defence = {Flank.LEFT: DefenderFlankEffects(gate_bonus=0.30)}

        wave = fill_wave(inv, game, self.capacity(), defence=defence)

        payload = wave.model_dump(by_alias=True)
        assert payload["L"]["T"] == []
        assert inv.available(611) == 100

    def test_a_unit_only_wave_is_still_available(self):
        game = self.data()
        inv = Inventory({601: 100, 611: 100})
        defence = {Flank.LEFT: DefenderFlankEffects(gate_bonus=0.30)}

        wave = fill_wave(inv, game, self.capacity(), defence=defence, strategies=[])

        assert wave.model_dump(by_alias=True)["L"]["T"] == []
        assert inv.available(611) == 100


class TestYardWave:
    def test_units_only_and_capped_by_capacity(self):
        game = GameData.parse("test", SOLVER_PAYLOAD)
        inv = Inventory({601: 10_000})

        yard = fill_yard_wave(inv, game, 3349)

        assert yard == [[601, 3349]] + [[-1, 0]] * 7
        assert inv.available(601) == 10_000 - 3349

    def test_every_slot_goes_out_even_when_empty(self):
        game = GameData.parse("test", SOLVER_PAYLOAD)
        assert fill_yard_wave(Inventory({}), game, 3349) == [[-1, 0]] * 8


class TestYardRounding:
    def test_a_half_unit_rounds_up_not_to_even(self):
        # base 50, boost 1 -> 50.5. JS Math.round gives 51; Python's round gives 50.
        assert yard_capacity(0, 0, boost=1) == 51


class TestWhichLevelDrivesWhat:
    """Two different levels, and mixing them up changes every number."""

    def test_flanks_tools_and_slots_follow_the_target(self):
        small = WaveCapacity.for_level(13)
        large = WaveCapacity.for_level(70)

        assert small.flank_soldiers < large.flank_soldiers
        assert small.flank_tools < large.flank_tools
        assert small.middle_unit_slots < large.middle_unit_slots

    def test_wave_count_follows_the_attacker(self):
        # A level 70 attacker gets four waves whether the target is level 1 or
        # level 70; the target only decides how big each one is.
        assert max_wave_count(70) == 4
        assert max_wave_count(13) == 2

    def test_the_courtyard_grows_with_both(self):
        assert yard_capacity(70, 13) != yard_capacity(13, 70)


class TestAreaTypeLevelFloor:
    """``CastleAttackWaveVO`` opens with ``e = int(max(e, t))``."""

    def test_a_landmark_defends_at_its_own_level(self):
        # A level 12 owner's monument is still built for level 70.
        assert wave_level(12, MapItemType.MONUMENT) == 70
        assert wave_level(12, MapItemType.KINGS_TOWER) == 70
        assert wave_level(12, MapItemType.LABORATORY) == 70

    def test_an_ordinary_target_keeps_its_owners_level(self):
        for area_type in (MapItemType.CASTLE, MapItemType.OUTPOST, MapItemType.DUNGEON):
            assert wave_level(12, area_type) == 12
        assert wave_level(12, None) == 12

    def test_the_floor_never_lowers_the_level(self):
        assert wave_level(70, MapItemType.MONUMENT) == 70
        assert wave_level(80, MapItemType.MONUMENT) == 80

    def test_a_capital_reads_its_landmark(self):
        # The client takes this from the landmark at runtime, so it is supplied.
        assert wave_level(12, MapItemType.CAPITAL, landmark_min_level=55) == 55
        assert minimum_owner_level(12, MapItemType.CAPITAL, landmark_min_level=55) == 55
        # Without it there is no floor to apply.
        assert wave_level(12, MapItemType.CAPITAL) == 12

    def test_the_floor_changes_what_a_flank_holds(self):
        assert WaveCapacity.for_level(wave_level(12, MapItemType.MONUMENT)).flank_soldiers > (
            WaveCapacity.for_level(12).flank_soldiers
        )


class TestWaveLimitViolations:
    def test_a_legal_attack_reports_nothing(self):
        capacity = WaveCapacity.for_level(70)
        wave = AttackWave(L=WaveFlank(U=[[601, capacity.flank_soldiers]]))

        assert wave_limit_violations([wave], capacity) == []

    def test_an_overfull_flank_is_named(self):
        capacity = WaveCapacity.for_level(70)
        wave = AttackWave(L=WaveFlank(U=[[601, capacity.flank_soldiers + 1]]))

        problems = wave_limit_violations([wave], capacity)

        assert len(problems) == 1
        assert "wave 0 L" in problems[0]

    def test_an_overfull_courtyard_is_named(self):
        capacity = WaveCapacity.for_level(70)
        yard = [[601, 5000]] + [[-1, 0]] * 7

        problems = wave_limit_violations([], capacity, yard=yard, yard_capacity=4489)

        assert problems == ["courtyard: 5000 units, limit 4489"]

    def test_empty_courtyard_slots_do_not_count(self):
        capacity = WaveCapacity.for_level(70)

        assert wave_limit_violations([], capacity, yard=[[-1, 0]] * 8, yard_capacity=0) == []


class TestCastellanDefence:
    """The defending castellan, from a live aci capture and its effects panel."""

    PAYLOAD = {
        "effecttypes": [
            {"effectTypeID": "6", "name": "wallBonus"},
            {"effectTypeID": "7", "name": "gateBonus"},
            {"effectTypeID": "8", "name": "moatBonus"},
            {"effectTypeID": "9", "name": "meleeBonus"},
            {"effectTypeID": "10", "name": "rangeBonus"},
            {"effectTypeID": "31", "name": "defenseBonus"},
            {"effectTypeID": "32", "name": "defenseBoostYard"},
        ],
        "effects": [
            {"effectID": "515", "name": "newDefenseWallBonusPVP", "effectTypeID": "6", "capID": "2100"},
            {"effectID": "524", "name": "newDefenseGateBonusPVP", "effectTypeID": "7", "capID": "2105"},
            {"effectID": "529", "name": "newDefenseMoatBonusPVP", "effectTypeID": "8", "capID": "2110"},
            {"effectID": "518", "name": "newDefenseMeleeBonusPVP", "effectTypeID": "9", "capID": "2103"},
            {"effectID": "527", "name": "newDefenseRangeBonusPVP", "effectTypeID": "10", "capID": "2108"},
            {"effectID": "533", "name": "newDefenseBonusPVP", "effectTypeID": "31", "capID": "2113"},
            {"effectID": "532", "name": "newDefenseBoostYardPVP", "effectTypeID": "32", "capID": "2112"},
        ],
        "effectCaps": [
            {"capID": "2100", "maxTotalBonus": "420"},
            {"capID": "2103", "maxTotalBonus": "324"},
            {"capID": "2105", "maxTotalBonus": "420"},
            {"capID": "2108", "maxTotalBonus": "324"},
            {"capID": "2110", "maxTotalBonus": "270"},
            {"capID": "2112", "maxTotalBonus": "298"},
            {"capID": "2113", "maxTotalBonus": "38"},
        ],
    }

    # Three items each granting wall/gate/moat, and three each granting
    # melee/range/courtyard. Verbatim from the capture's B block.
    CASTELLAN = {
        "ID": 1,
        "WID": 1,
        "EQ": [],
        "AE": [],
        "E": [
            [515, [140.0], "EQ"],
            [524, [140.0], "EQ"],
            [529, [90.0], "EQ"],
            [515, [140.0], "EQ"],
            [524, [140.0], "EQ"],
            [529, [90.0], "EQ"],
            [533, [5.0], "EQ"],
            [518, [120.0], "EQ"],
            [527, [120.0], "EQ"],
            [532, [110.0], "EQ"],
            [518, [120.0], "EQ"],
            [527, [120.0], "EQ"],
            [532, [110.0], "EQ"],
            [518, [120.0], "EQ"],
            [527, [120.0], "EQ"],
            [532, [110.0], "EQ"],
        ],
    }

    def parts(self):
        from empire_core.combat import EffectResolver, commander_bonuses
        from empire_core.protocol.models import Commander

        game = GameData.parse("test", self.PAYLOAD)
        return EffectResolver(game), commander_bonuses(Commander.model_validate(self.CASTELLAN))

    def test_the_fortification_matches_the_effects_panel(self):
        from empire_core.combat import castellan_fortification

        resolver, bonuses = self.parts()

        # The panel reads +280% wall, +280% gate, +180% moat.
        assert castellan_fortification(resolver, bonuses, area_type=1) == pytest.approx((2.8, 2.8, 1.8))

    def test_a_flank_multiplier_is_capped(self):
        from empire_core.combat import castellan_defence_multiplier

        resolver, bonuses = self.parts()

        # 3 x 120% of melee unit strength is capped at 324%, plus the 5%
        # all-flank defence bonus. The panel reads "+360% (max: 324%)".
        assert castellan_defence_multiplier(
            resolver, bonuses, flank=Flank.LEFT, melee=True, area_type=1
        ) == pytest.approx(3.29)

    def test_the_middle_also_takes_the_courtyard_boost(self):
        from empire_core.combat import castellan_defence_multiplier

        resolver, bonuses = self.parts()

        # 3 x 110% capped at 298%, added on the middle flank - which is where
        # the client adds it, not on the courtyard.
        assert castellan_defence_multiplier(
            resolver, bonuses, flank=Flank.MIDDLE, melee=True, area_type=1
        ) == pytest.approx(6.27)

    def test_the_courtyard_does_not_take_its_own_boost(self):
        from empire_core.combat import castellan_defence_multiplier

        resolver, bonuses = self.parts()

        assert castellan_defence_multiplier(
            resolver, bonuses, flank=Flank.YARD, melee=True, area_type=1
        ) == pytest.approx(3.29)
