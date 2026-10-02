"""The spy count: gms plus research, legend skill and title boosts, and the spies at home."""

from __future__ import annotations

import pytest

from empire_core.enums import MovementType
from empire_core.exceptions import GameDataNotLoadedError
from empire_core.gamedata import GameData
from empire_core.movements.models import MovementSpy
from empire_core.movements.tracked import Movement
from empire_core.spy.pool import (
    island_title_chain,
    legend_spy_bonus,
    research_spy_bonus,
    title_spy_percent,
    total_spies,
)
from empire_core.state.manager import GameState
from tests.service_helpers import StubState, make_client

# Rows as items 786.03 has them
ITEMS = {
    "effects": [
        {"effectID": "48", "name": "attackBonus", "effectTypeID": "36", "capID": "99"},
        {"effectID": "69", "name": "spyCountBoost", "effectTypeID": "73", "capID": "99"},
        {"effectID": "93", "name": "amountSpiesBonus", "effectTypeID": "98", "capID": "99"},
    ],
    "effectCaps": [{"capID": "99"}],
    "researches": [
        {"researchID": str(research_id), "groupID": "21", "level": str(research_id - 170), "effects": "93&1"}
        for research_id in range(171, 178)
    ]
    + [{"researchID": "1", "groupID": "1", "level": "1", "effects": "48&5"}],
    "titles": [
        {"titleID": "50", "previousTitleID": "51", "type": "ISLE", "topX": "1", "effects": "48&20"},
        {"titleID": "51", "previousTitleID": "52", "type": "ISLE", "topX": "2", "effects": "299&25,67&25"},
        {"titleID": "52", "previousTitleID": "53", "type": "ISLE", "topX": "3", "effects": "300&25"},
        {"titleID": "53", "previousTitleID": "54", "type": "ISLE", "topX": "4", "effects": "80&100"},
        {"titleID": "54", "type": "ISLE", "topX": "10", "effects": "69&100"},
    ],
    "legendskills": [
        {
            "skillID": str(skill_id),
            "level": str(skill_id - 50),
            "skillTreeID": "0",
            "tier": "2",
            "skillGroupID": "5",
            "effectType": "spyAmountBonus",
            "totalEffectValue": str(skill_id - 50),
            "effectValue": "1",
        }
        for skill_id in (51, 52, 53)
    ],
}
ALL_SPY_RESEARCH = list(range(171, 178))


@pytest.fixture
def game_data() -> GameData:
    return GameData.parse("test", ITEMS)


def spy_movement(
    mid: int, spies: int, *, mine: bool = True, movement_type: int = MovementType.SPY, returning: bool = False
) -> Movement:
    spy = MovementSpy.model_validate({"ST": 0, "SA": 100, "SC": spies, "SR": 26})
    owner = 1001 if mine else 2002
    return Movement(MID=mid, T=movement_type, D=int(returning), OID=owner, local_player_id=1001, spy=spy)


class TestTotalSpies:
    # Expected values from CastleSpyData.getNumAllSpies run in node with these inputs
    @pytest.mark.parametrize(
        ("max_spies", "research", "legend", "title", "expected"),
        [
            (10, 0, 0, 0, 10),
            (10, 7, 3, 100, 40),
            (10, 7, 0, 100, 34),
            (13, 2, 0, 33, 19),
        ],
    )
    def test_the_client_formula(self, max_spies, research, legend, title, expected):
        assert total_spies(max_spies, research_bonus=research, legend_bonus=legend, title_percent=title) == expected

    def test_research_and_legend_are_truncated_before_the_title(self):
        assert total_spies(10, research_bonus=1.9, legend_bonus=0.9, title_percent=50) == 16


class TestBoosts:
    def test_research_adds_one_spy_per_level(self, game_data):
        assert research_spy_bonus(game_data, ALL_SPY_RESEARCH) == 7
        assert research_spy_bonus(game_data, [171, 1, 999]) == 1
        assert research_spy_bonus(game_data, []) == 0

    def test_legend_skills_count_their_total_value(self, game_data):
        assert legend_spy_bonus(game_data, [53]) == 3
        assert legend_spy_bonus(game_data, []) == 0

    def test_an_island_title_holds_every_title_below_it(self, game_data):
        assert island_title_chain(game_data, 50) == [54, 53, 52, 51, 50]
        assert island_title_chain(game_data, 54) == [54]
        assert island_title_chain(game_data, -1) == []
        assert island_title_chain(game_data, 999) == []

    def test_only_the_lowest_island_title_boosts_spies(self, game_data):
        assert title_spy_percent(game_data, island_title_chain(game_data, 50)) == 100
        assert title_spy_percent(game_data, [50, 51, 52, 53]) == 0


class TestSpyService:
    def client(self, *, gms: dict | None = None, movements: list[Movement] | None = None, game_data=None):
        client = make_client()
        state = GameState()
        if gms is not None:
            state.update_from_packet("gbd", {"gms": gms})
        state.get_all_movements = lambda: list(movements or [])  # ty: ignore[invalid-assignment]
        client.state = state
        client.game_data = game_data
        return client

    def test_none_before_gms(self):
        client = self.client()
        assert client.spy.total_spies() is None
        assert client.spy.available_spies() is None

    def test_without_boosts_needs_no_game_data(self):
        client = self.client(gms={"MS": 12, "BS": 0}, movements=[spy_movement(1, 5)])
        assert client.spy.total_spies() == 12
        assert client.spy.available_spies() == 7

    def test_boosts_from_game_data(self, game_data):
        client = self.client(gms={"MS": 10, "BS": 0}, movements=[spy_movement(1, 4)], game_data=game_data)
        kwargs = {"research_ids": ALL_SPY_RESEARCH, "legend_skill_ids": [53], "island_title_id": 50}

        assert client.spy.total_spies(**kwargs, legend_target=True) == 40
        assert client.spy.available_spies(**kwargs, legend_target=True) == 36
        assert client.spy.total_spies(**kwargs) == 34

    def test_legend_skills_alone_need_a_legend_target(self):
        client = self.client(gms={"MS": 10})
        assert client.spy.total_spies(legend_skill_ids=[53]) == 10

    def test_boosts_need_game_data(self):
        client = self.client(gms={"MS": 10})
        with pytest.raises(GameDataNotLoadedError):
            client.spy.total_spies(research_ids=[171])

    def test_available_can_go_negative_as_in_the_client(self):
        client = self.client(gms={"MS": 7}, movements=[spy_movement(1, 5), spy_movement(2, 4)])
        assert client.spy.available_spies() == -2


class TestSpiesInUse:
    def test_only_your_own_spy_movements_count(self):
        movements = [
            spy_movement(1, 4),
            spy_movement(2, 4, mine=False),
            spy_movement(3, 9, movement_type=MovementType.PLAGUEMONK),
            Movement(MID=4, T=MovementType.SPY, OID=1001, local_player_id=1001),
            spy_movement(5, 3, returning=True),
        ]
        client = make_client(state=StubState(movements=movements))

        assert client.spy.spies_in_use() == 7
