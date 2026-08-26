"""Tool placement mechanics: slot matching, the strategy pool, and checkFlank."""

from empire_core.combat import Inventory, check_flank, fill_flank_with_tools
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
    """A strategy that offers each id in turn, then nothing."""
    remaining = list(wod_ids)

    def pick(inventory, game_data, *, free_items, attacker, defender):
        while remaining:
            tool = game_data.get_tool(remaining.pop(0))
            if tool is not None and inventory.available(tool.wod_id):
                return tool
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
