"""The Battle for Berimond's lanes and special camps, read as the client reads them."""

from empire_core.enums import BerimondLane
from empire_core.gamedata import GameData

DATA = GameData.parse(
    "test",
    {
        "specialcamps": [
            {"specialcampID": "1", "type": "VILLAGES"},
            {"specialcampID": "2", "type": "CAPITAL", "laneID": "4", "unlockIDs": "5,6"},
            {"specialcampID": "6", "type": "DUNGEON", "laneID": "1"},
            {
                "specialcampID": "4",
                "type": "DUNGEON",
                "laneID": "1",
                "dungeonlevel": "50",
                "attacksUntilDestroyed": "92",
                "lootc1": "22782",
                "lootc2": "5",
                "lootWood": "100",
                "lootStone": "200",
                "lootFood": "300",
                "lootMead": "6408",
                "lootBeef": "6407",
            },
            {"specialcampID": "5", "type": "DUNGEON", "laneID": "2"},
        ]
    },
)


class TestLanes:
    def test_a_capital_has_its_factions_three_lanes(self):
        assert BerimondLane.GERBRANDT_CAPITAL.tower_lanes == (
            BerimondLane.GERBRANDT_MIDDLE,
            BerimondLane.GERBRANDT_TOP,
            BerimondLane.GERBRANDT_BOTTOM,
        )
        assert BerimondLane.URSIDAE_CAPITAL.tower_lanes == (
            BerimondLane.URSIDAE_MIDDLE,
            BerimondLane.URSIDAE_TOP,
            BerimondLane.URSIDAE_BOTTOM,
        )

    def test_a_watchtower_lane_has_none(self):
        assert BerimondLane.GERBRANDT_TOP.tower_lanes == ()

    def test_a_lanes_towers_are_its_watchtowers_by_id(self):
        towers = DATA.berimond_lane_towers(BerimondLane.GERBRANDT_MIDDLE)
        assert [tower.special_camp_id for tower in towers] == [4, 6]

    def test_a_capitals_lane_has_no_towers(self):
        assert DATA.berimond_lane_towers(BerimondLane.GERBRANDT_CAPITAL) == []


class TestSpecialCamps:
    def test_a_watchtower_reads_its_level_attacks_and_loot(self):
        tower = DATA.berimond_special_camps[4]
        assert (tower.level, tower.attacks_until_destroyed) == (50, 92)
        assert (tower.loot_coins, tower.loot_rubies) == (22782, 5)
        assert (tower.loot_wood, tower.loot_stone, tower.loot_food) == (100, 200, 300)
        assert (tower.loot_mead, tower.loot_beef) == (6408, 6407)

    def test_a_camp_without_them_reads_zero(self):
        village = DATA.berimond_special_camps[1]
        assert (village.level, village.attacks_until_destroyed, village.loot_rubies, village.loot_mead) == (0, 0, 0, 0)
