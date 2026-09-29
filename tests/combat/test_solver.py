"""Tests for the solver's soldier fill."""

from empire_core.combat import (
    DefenderFlankEffects,
    FillOptions,
    Flank,
    Inventory,
    WaveCapacity,
    fill_flank_with_soldiers,
    fill_wave,
    pick_soldier_stack,
)
from tests.combat.combat_helpers import placed, solver_data, unit_of


def stack_of(pick: tuple[int, int] | None) -> tuple[int, int]:
    """The chosen stack, insisting one was chosen."""
    assert pick is not None, "no stack was picked"
    return pick


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

    def test_melee_is_chosen_against_a_ranged_heavy_defense(self):
        game = solver_data()
        # A defense made only of ranged-defense strength: melee attack counters.
        defender = DefenderFlankEffects(range_units_range_strength=1000)

        pick = pick_soldier_stack(10, Inventory({601: 100, 211: 100}), game, defender=defender)

        assert stack_of(pick)[0] == 601

    def test_ranged_is_chosen_against_a_melee_heavy_defense(self):
        game = solver_data()
        defender = DefenderFlankEffects(melee_units_melee_strength=1000)

        pick = pick_soldier_stack(10, Inventory({601: 100, 211: 100}), game, defender=defender)

        assert stack_of(pick)[0] == 211

    def test_pure_defenders_are_never_picked(self):
        pick = pick_soldier_stack(10, Inventory({800: 100}), solver_data())
        assert pick is None

    def test_defensive_units_are_not_candidates_even_with_attack_value(self):
        # 604 is a halberdier: attack 17, but fightType 1. A large stack of it
        # would outscore a real attacker if the flag were ignored.
        game = solver_data()

        assert not unit_of(game, 604).is_offensive
        assert pick_soldier_stack(1000, Inventory({604: 5000}), game) is None

        pick = pick_soldier_stack(1000, Inventory({604: 5000, 601: 50}), game)
        assert pick == (601, 50)

    def test_ruby_filter_excludes_the_expensive_unit(self):
        game = solver_data()
        inv = Inventory({601: 100, 700: 100})

        allowed = pick_soldier_stack(10, Inventory(inv.counts), game)
        blocked = pick_soldier_stack(10, Inventory(inv.counts), game, options=FillOptions(allow_ruby_cost=False))

        assert stack_of(allowed)[0] == 700
        assert stack_of(blocked)[0] == 601

    def test_mead_filter_excludes_the_mead_unit(self):
        game = solver_data()
        pick = pick_soldier_stack(10, Inventory({211: 100, 601: 100}), game, options=FillOptions(allow_mead=False))
        assert stack_of(pick)[0] == 601

    def test_role_filters_restrict_the_pool(self):
        game = solver_data()

        melee_only = pick_soldier_stack(10, Inventory({601: 50, 211: 50}), game, options=FillOptions(use_ranged=False))
        assert stack_of(melee_only)[0] == 601

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
        # One pair per slot, locked slots included, as getSlotList sends them
        assert payload["L"] == {"T": [[-1, 0], [-1, 0]], "U": [[601, 10], [-1, 0]]}
        assert payload["R"] == {"T": [[-1, 0], [-1, 0]], "U": [[601, 10], [-1, 0]]}
        assert payload["M"] == {"T": [[-1, 0]] * 3, "U": [[601, 10]] + [[-1, 0]] * 5}
        assert list(payload) == ["L", "R", "M"]
        assert inv.available(601) == 0

    def test_inventory_is_shared_across_flanks_in_the_clients_order(self):
        # fillWave fills left, then right, then middle, and the flanks share one
        # inventory - so a pool that runs out shows the order.
        game = solver_data()
        inv = Inventory({601: 15})

        wave = fill_wave(inv, game, _capacity(10, 1))

        payload = wave.model_dump(by_alias=True)
        assert placed(payload["L"]["U"]) == [[601, 10]]
        assert placed(payload["R"]["U"]) == [[601, 5]]
        assert placed(payload["M"]["U"]) == []

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
        assert placed(payload["L"]["U"]) == []
        assert placed(payload["M"]["U"]) == [[601, 10]]
        assert placed(payload["R"]["U"]) == []

    def test_an_unfillable_wave_is_incomplete_not_an_error(self):
        wave = fill_wave(Inventory({}), solver_data(), _capacity(10, 2))

        assert not wave.is_complete()
        assert wave.unit_count() == 0

    def test_per_flank_defense_steers_each_flank(self):
        game = solver_data()
        inv = Inventory({601: 100, 211: 100})

        wave = fill_wave(
            inv,
            game,
            _capacity(10, 1),
            defense={
                Flank.LEFT: DefenderFlankEffects(melee_units_melee_strength=1000),
                Flank.RIGHT: DefenderFlankEffects(range_units_range_strength=1000),
            },
        )

        payload = wave.model_dump(by_alias=True)
        assert payload["L"]["U"][0][0] == 211  # melee-heavy defense -> ranged attack
        assert payload["R"]["U"][0][0] == 601  # ranged-heavy defense -> melee attack
