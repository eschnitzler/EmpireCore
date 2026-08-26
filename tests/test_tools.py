"""Tool placement mechanics: slot matching, the strategy pool, and checkFlank."""

import pytest

from empire_core.combat import (
    MELEE_DEFENCE_MALUS_TYPE,
    RANGE_DEFENCE_MALUS_TYPE,
    AttackerFlankEffects,
    DefenderFlankEffects,
    Inventory,
    check_flank,
    conditioned_effect_bonus,
    default_tool_strategies,
    fill_flank_with_tools,
)
from empire_core.gamedata import GameData

# slotTypes 2 = flank tool slot, 1 = middle. 646 fits neither (4,9).
PAYLOAD = {
    "units": [
        {"wodID": 301, "name": "Workshop", "type": "Ladder", "typ": "Attack", "slotTypes": "1,2,9", "fightType": "1"},
        {"wodID": 302, "name": "Workshop", "type": "Ram", "typ": "Attack", "slotTypes": "1,9", "fightType": "1"},
        {"wodID": 646, "name": "Dworkshop", "type": "Stakes", "typ": "Defence", "slotTypes": "4,9", "fightType": "1"},
    ]
}


def data() -> GameData:
    return GameData.parse("test", PAYLOAD)


def strategy_for(*wod_ids):
    """A strategy that offers each id in turn, taking whatever fits."""
    remaining = list(wod_ids)

    def pick(inventory, game_data, *, free_items, attacker, defender, area_type=None):
        while remaining:
            tool = game_data.get_tool(remaining.pop(0))
            if tool is not None and inventory.available(tool.wod_id):
                return tool, free_items
        return None

    return pick


class TestToolFill:
    def test_a_tool_that_fits_is_placed(self):
        inv = Inventory({301: 100})

        placed = fill_flank_with_tools(40, 2, 2, inv, data(), [strategy_for(301)])

        assert placed == [(301, 40)]
        assert inv.available(301) == 60

    def test_a_tool_that_does_not_fit_retires_its_strategy(self):
        # 646 fits slot types 4 and 9, not 2, so its strategy is popped and the
        # next one supplies a ladder.
        inv = Inventory({646: 10, 301: 10})

        placed = fill_flank_with_tools(40, 2, 2, inv, data(), [strategy_for(301), strategy_for(646)])

        assert placed == [(301, 10)]
        assert inv.available(646) == 10

    def test_an_empty_pool_stops_filling(self):
        inv = Inventory({301: 100})

        assert fill_flank_with_tools(40, 2, 2, inv, data(), []) == []
        assert inv.available(301) == 100

    def test_the_same_tool_merges_rather_than_taking_two_slots(self):
        inv = Inventory({301: 100})

        placed = fill_flank_with_tools(40, 2, 2, inv, data(), [strategy_for(301, 301)])

        assert placed == [(301, 40)]

    def test_capacity_bounds_the_total(self):
        inv = Inventory({301: 5, 302: 100})

        placed = fill_flank_with_tools(40, 3, 1, inv, data(), [strategy_for(302), strategy_for(301)])

        assert sum(count for _wod, count in placed) <= 40

    def test_no_slots_places_nothing(self):
        inv = Inventory({301: 10})
        assert fill_flank_with_tools(40, 0, 2, inv, data(), [strategy_for(301)]) == []
        assert inv.available(301) == 10


class TestCheckFlank:
    def test_a_flank_with_units_stands(self):
        tools = [(301, 10)]
        inv = Inventory({})

        assert check_flank(tools, [(601, 5)], inv) is True
        assert tools == [(301, 10)]

    def test_tools_without_units_go_back(self):
        tools = [(301, 10), (302, 4)]
        inv = Inventory({301: 1})

        assert check_flank(tools, [], inv) is False
        assert tools == []
        assert inv.available(301) == 11
        assert inv.available(302) == 4

    def test_zero_count_units_do_not_save_a_flank(self):
        tools = [(301, 10)]
        inv = Inventory({})

        assert check_flank(tools, [(601, 0)], inv) is False
        assert inv.available(301) == 10


# =============================================================================
# The five strategies
# =============================================================================

STRATEGY_PAYLOAD = {
    "units": [
        # Rams cancel gate protection; a bigger one cancels it in fewer units.
        {
            "wodID": 611,
            "name": "Workshop",
            "type": "Ram",
            "typ": "Attack",
            "slotTypes": "1,9",
            "gateBonus": "10",
            "fightType": "1",
        },
        {
            "wodID": 648,
            "name": "Workshop",
            "type": "Eliteram",
            "typ": "Attack",
            "slotTypes": "1,9",
            "gateBonus": "20",
            "fightType": "1",
        },
        # A ladder for walls, and a defensive tool that must never be picked.
        {
            "wodID": 301,
            "name": "Workshop",
            "type": "Ladder",
            "typ": "Attack",
            "slotTypes": "1,9",
            "wallBonus": "15",
            "fightType": "1",
        },
        {
            "wodID": 646,
            "name": "Dworkshop",
            "type": "Stakes",
            "typ": "Defence",
            "slotTypes": "1,9",
            "moatBonus": "80",
            "fightType": "1",
        },
        # Limited to two per wave.
        {
            "wodID": 700,
            "name": "Workshop",
            "type": "Bigram",
            "typ": "Attack",
            "slotTypes": "1,9",
            "gateBonus": "50",
            "amountPerWave": "2",
            "fightType": "1",
        },
    ]
}


def strategy_data() -> GameData:
    return GameData.parse("test", STRATEGY_PAYLOAD)


def by_name(name):
    return next(s for s in default_tool_strategies() if s.name == name)


def defender(**kwargs) -> DefenderFlankEffects:
    """Defender effects. Bonuses are fractions, as the tool columns are."""
    return DefenderFlankEffects(**kwargs)


class TestReduceDefenceBonusStrategy:
    def test_pool_order_matches_the_client(self):
        # Pushed moat, range, melee, gate, wall and popped from the end.
        assert [s.name for s in default_tool_strategies()] == [
            "moat",
            "range",
            "melee",
            "gate",
            "wall",
        ]

    def test_nothing_to_cancel_means_no_tool(self):
        game = strategy_data()
        picked = by_name("gate")(
            Inventory({611: 100}),
            game,
            free_items=40,
            attacker=AttackerFlankEffects(),
            defender=defender(gate_bonus=0.0),
        )
        assert picked is None

    def test_already_out_reduced_defence_needs_no_tool(self):
        game = strategy_data()
        picked = by_name("gate")(
            Inventory({611: 100}),
            game,
            free_items=40,
            attacker=AttackerFlankEffects(gate_reduction=0.5),
            defender=defender(gate_bonus=0.4),
        )
        assert picked is None

    def test_the_tool_that_cancels_in_fewest_units_wins(self):
        game = strategy_data()
        # 40% gate protection: the elite ram cancels it in 2, the plain one
        # would need 4, so the elite wins.
        picked = by_name("gate")(
            Inventory({611: 100, 648: 100}),
            game,
            free_items=40,
            attacker=AttackerFlankEffects(),
            defender=defender(gate_bonus=0.40),
        )
        assert picked is not None
        tool, count = picked
        assert tool.wod_id == 648
        assert count == 2

    def test_defensive_tools_are_never_picked(self):
        game = strategy_data()
        picked = by_name("moat")(
            Inventory({646: 100}),
            game,
            free_items=40,
            attacker=AttackerFlankEffects(),
            defender=defender(moat_bonus=0.80),
        )
        assert picked is None

    def test_when_nothing_cancels_it_takes_the_biggest_dent(self):
        game = strategy_data()
        # 500% gate protection with only 3 rams: nothing cancels it, so the
        # strategy falls back to whatever removes most.
        picked = by_name("gate")(
            Inventory({611: 3, 648: 3}),
            game,
            free_items=40,
            attacker=AttackerFlankEffects(),
            defender=defender(gate_bonus=5.0),
        )
        tool, count = picked
        assert tool.wod_id == 648
        assert count == 3

    def test_amount_per_wave_caps_a_tool(self):
        game = strategy_data()
        # The big ram would cancel 500% in 10, but only 2 fit per wave, so it
        # can only dent it - 2 x 0.50 beats 3 x 0.20 from the elite rams.
        picked = by_name("gate")(
            Inventory({700: 100, 648: 3}),
            game,
            free_items=40,
            attacker=AttackerFlankEffects(),
            defender=defender(gate_bonus=5.0),
        )
        tool, count = picked
        assert (tool.wod_id, count) == (700, 2)

    def test_range_and_melee_stand_down_without_such_defenders(self):
        game = strategy_data()
        inv = Inventory({611: 100})

        no_defenders = defender(range_bonus=1.0, melee_bonus=1.0)
        assert (
            by_name("range")(inv, game, free_items=40, attacker=AttackerFlankEffects(), defender=no_defenders) is None
        )
        assert (
            by_name("melee")(inv, game, free_items=40, attacker=AttackerFlankEffects(), defender=no_defenders) is None
        )

    def test_no_defender_information_means_no_tool(self):
        game = strategy_data()
        assert (
            by_name("wall")(Inventory({301: 10}), game, free_items=40, attacker=AttackerFlankEffects(), defender=None)
            is None
        )

    def test_fill_uses_the_pool_end_first(self):
        game = strategy_data()
        inv = Inventory({301: 100, 611: 100})
        # Wall is last in the pool so it is tried first; a wall defence is
        # present, so a ladder lands rather than a ram.
        placed = fill_flank_with_tools(
            40,
            2,
            1,
            inv,
            game,
            default_tool_strategies(),
            defender=defender(wall_bonus=0.30, gate_bonus=0.30),
        )
        assert placed[0][0] == 301


class TestToolFeedback:
    """Each placed tool dents the defence the next pick is measured against."""

    def test_a_tool_reduces_what_the_next_one_must_cancel(self):
        game = strategy_data()
        effects = AttackerFlankEffects()
        ram = game.get_tool(611)  # gate bonus 0.10

        updated = effects.apply_tool(ram, 3)

        assert updated.gate_reduction == pytest.approx(0.30)
        # The original is untouched.
        assert effects.gate_reduction == 0.0

    def test_defence_reductions_accumulate_per_unit_placed(self):
        game = strategy_data()
        stakes = game.get_tool(646)  # a defensive tool, moat 0.80

        updated = AttackerFlankEffects().apply_tool(stakes, 2)

        assert updated.moat_reduction == pytest.approx(1.60)

    def test_filling_stops_once_the_defence_is_cancelled(self):
        game = strategy_data()
        inv = Inventory({611: 100})
        # 0.30 of gate protection and three slots: the first slot cancels it,
        # so the rest stay empty rather than wasting rams.
        placed = fill_flank_with_tools(
            40,
            3,
            1,
            inv,
            game,
            default_tool_strategies(),
            defender=DefenderFlankEffects(gate_bonus=0.30),
        )

        assert placed == [(611, 3)]
        assert inv.available(611) == 97


class TestFortificationAlreadyBeaten:
    """A defence the attacker already out-reduces needs no tool."""

    def test_strategies_retire_when_reductions_exceed_the_defence(self):
        game = strategy_data()
        # A commander with -116% wall protection against a camp with 70%: the
        # wall is already gone, so no ladder is worth a slot.
        picked = by_name("wall")(
            Inventory({301: 500}),
            game,
            free_items=20,
            attacker=AttackerFlankEffects(wall_reduction=1.161),
            defender=DefenderFlankEffects(wall_bonus=0.70),
        )

        assert picked is None

    def test_the_pool_falls_through_to_the_next_defence(self):
        game = strategy_data()
        inv = Inventory({611: 500})
        # Gate is out-reduced but the defenders themselves are not, so filling
        # moves past the fortification strategies rather than stopping.
        placed = fill_flank_with_tools(
            20,
            2,
            1,
            inv,
            game,
            default_tool_strategies(),
            attacker=AttackerFlankEffects(wall_reduction=2.0, gate_reduction=2.0, moat_reduction=2.0),
            defender=DefenderFlankEffects(wall_bonus=0.70, gate_bonus=0.70, melee_units_melee_strength=100),
        )

        # 611 only carries a gate bonus, and gate is already beaten, so nothing
        # in this inventory is worth placing.
        assert placed == []
        assert inv.available(611) == 500


class TestConditionedEffectBonus:
    """Some tools weaken a defender through their effects, not their columns."""

    PAYLOAD = {
        "units": [
            # A live shape: a weakening tool with no defence columns at all.
            {
                "wodID": 811,
                "name": "Workshop",
                "type": "DragonWeakeningRanged",
                "typ": "Attack",
                "slotTypes": "1,2,9",
                "effects": "491&250",
                "fightType": "1",
            },
        ],
        "effecttypes": [{"effectTypeID": "217", "name": "rangeDefenseMalus"}],
        "effects": [{"effectID": "491", "name": "rangeMalus", "effectTypeID": "217", "capID": "99"}],
    }

    def data(self):
        return GameData.parse("test", self.PAYLOAD)

    def test_a_tool_with_no_columns_still_counts(self):
        game = self.data()
        tool = game.get_tool(811)

        assert tool.def_range_bonus == 0.0
        assert conditioned_effect_bonus(game, tool, RANGE_DEFENCE_MALUS_TYPE) == 2.5

    def test_the_range_strategy_now_sees_it(self):
        game = self.data()

        picked = by_name("range")(
            Inventory({811: 100}),
            game,
            free_items=20,
            attacker=AttackerFlankEffects(),
            defender=DefenderFlankEffects(range_bonus=1.0, range_units_range_strength=100),
        )

        assert picked is not None
        tool, count = picked
        # 2.5 per tool against a 1.0 defence: one is enough.
        assert (tool.wod_id, count) == (811, 1)

    def test_effects_of_another_type_do_not_count(self):
        game = self.data()
        assert conditioned_effect_bonus(game, game.get_tool(811), MELEE_DEFENCE_MALUS_TYPE) == 0.0
