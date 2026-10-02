"""The titles you hold, from your points and top-X ranks."""

import pytest

from empire_core.enums import TitleSystem
from empire_core.gamedata import GameData
from empire_core.player import FactionPointsResponse, GloryPointsResponse, TitleRanksResponse
from empire_core.player.titles import held_titles, player_title_ids, titles_in_order

_FAME_THRESHOLDS = [
    0, 4444, 7778, 10000, 71111, 230429, 283903, 349788, 430962, 530973, 654195, 806011, 993059, 1223515, 1507451,
    1844454, 1857280, 2288292, 2819328, 3473599, 4279705, 5272880, 6496539, 8004167, 9861664, 12150225, 14969884,
    18443890, 22724097, 34494489,
]  # fmt: skip
_FACTION_THRESHOLDS = [250, 750, 1500, 2500, 10000, 15000, 25000, 35000, 37500, 40000, 45000, 95000, 145000, 195000]


def _chain(type_: str, first: int, thresholds: list[int], top_x: list[int]) -> list[dict]:
    rows = []
    for index, value in enumerate([*[("threshold", t) for t in thresholds], *[("topX", x) for x in top_x]]):
        row = {"titleID": str(first + index), "type": type_, value[0]: str(value[1])}
        if index:
            row["previousTitleID"] = str(first + index - 1)
        rows.append(row)
    return rows


# The FAME and FACTION titles of items 786.03, and its Storm Islands chain (54 lowest, 50 highest)
TITLES = [
    *_chain("FAME", 0, _FAME_THRESHOLDS, [100, 50, 10, 1]),
    *_chain("FACTION", 100, _FACTION_THRESHOLDS, [100, 50, 20, 1]),
    {"titleID": "50", "previousTitleID": "51", "type": "ISLE", "topX": "1"},
    {"titleID": "51", "previousTitleID": "52", "type": "ISLE", "topX": "2"},
    {"titleID": "52", "previousTitleID": "53", "type": "ISLE", "topX": "3"},
    {"titleID": "53", "previousTitleID": "54", "type": "ISLE", "topX": "4"},
    {"titleID": "54", "type": "ISLE", "topX": "10"},
]


@pytest.fixture
def game_data() -> GameData:
    return GameData.parse("test", {"titles": TITLES})


class TestHeldTitles:
    def test_each_system_in_chain_order(self, game_data):
        assert titles_in_order(game_data, TitleSystem.GLORY) == list(range(34))
        assert titles_in_order(game_data, TitleSystem.FACTION) == list(range(100, 118))
        assert titles_in_order(game_data, TitleSystem.ISLAND) == [54, 53, 52, 51, 50]

    # Expected values from CastleTitleData.setupThisUsersTitlesinSystem (bundle line 21048) run in node
    @pytest.mark.parametrize(
        ("system", "points", "rank", "expected"),
        [
            (TitleSystem.GLORY, 71107, -1, list(range(4))),
            (TitleSystem.GLORY, 71111, 0, list(range(5))),
            (TitleSystem.GLORY, 34494489, 100, list(range(31))),
            (TitleSystem.GLORY, 34494489, 101, list(range(30))),
            (TitleSystem.GLORY, 0, 1, [0]),
            (TitleSystem.GLORY, 99999999, 10, list(range(33))),
            (TitleSystem.FACTION, 4999, -1, list(range(100, 104))),
            (TitleSystem.FACTION, 195000, 20, list(range(100, 117))),
            (TitleSystem.FACTION, None, 5, []),
        ],
    )
    def test_as_the_client_works_them_out(self, game_data, system, points, rank, expected):
        assert held_titles(game_data, system, points, rank) == expected

    def test_every_title_you_hold(self, game_data):
        glory = GloryPointsResponse.model_validate({"CF": "10000", "HF": 20000})
        faction = FactionPointsResponse.model_validate({"CFP": 800, "HFP": 900})
        ranks = TitleRanksResponse.model_validate(
            {"FTM": {"CTXT": -1}, "BTM": {"CTXT": -1}, "ITM": {"TID": 53}, "PFX": "FAME", "SFX": "FACTION"}
        )
        assert player_title_ids(game_data, glory, faction, ranks) == [0, 1, 2, 3, 100, 101, 54, 53]
        assert player_title_ids(game_data, None, None, None) == []
