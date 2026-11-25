"""Travel time and carriage capacity against the client's own code, run in node (tests/data/travel_client.json)."""

import json
from pathlib import Path

import pytest

from empire_core.enums import Kingdom, MapItemType, SpyType
from empire_core.gamedata import GameData, HorseStats, ToolStats, UnitStats, VipLevelDef
from empire_core.map.models.items import MapAreaItem
from empire_core.movements import (
    attack_travel_time,
    conquest_travel_speed,
    corrected_attack_distance,
    low_level_boost,
    lowest_travel_speed,
    resources_per_carriage,
    spy_travel_time,
    station_travel_time,
    support_travel_time,
    trade_capacity,
    trade_travel_time,
    travel_distance,
    travel_time,
    travel_time_with_horse,
    troop_speed,
)

CLIENT = json.loads((Path(__file__).parents[1] / "data" / "travel_client.json").read_text())

# The caravan overloader rows of v790.02's levelBoosters table
CARAVAN_PERCENTS = [0, 7, 14, 21, 28, 35, 42, 49, 56, 63, 70, 77, 84, 91, 98, 105, 112, 119, 126, 133, 140, 147]
GAME_DATA = GameData.parse(
    "790.02",
    {
        "levelBoosters": [
            {"boosterType": "11", "level": str(level), "costC2": "0", "boostPercentage": str(percent)}
            for level, percent in enumerate(CARAVAN_PERCENTS)
        ],
        "specialcamps": [
            {"specialcampID": camp, "type": "DUNGEON", "distance": str(distance)}
            for camp, distance in CLIENT["distance_camps"].items()
        ],
    },
)


def _horse(unit_boost: int = 0, market_boost: int = 0, spy_boost: int = 0) -> HorseStats | None:
    if not (unit_boost or market_boost or spy_boost):
        return None
    return HorseStats(wod_id=1001, unit_boost=unit_boost, market_boost=market_boost, spy_boost=spy_boost)


def test_travel_time_with_horse_matches_the_client():
    for speed, distance, factor, horse, area, expected in CLIENT["with_horse"] + CLIENT["edge"]:
        assert travel_time_with_horse(speed, distance, factor, horse, area) == expected, (speed, distance, horse)


def test_travel_time_without_horse_matches_the_client():
    for speed, distance, factor, area, expected in CLIENT["plain"]:
        assert travel_time(speed, distance, factor, area) == expected


def test_a_long_trip_wraps_as_the_client_s_int32_does():
    assert travel_time_with_horse(1, 1e9, 1) == -69312513


def test_a_zero_speed_takes_no_time_as_in_the_client():
    assert travel_time_with_horse(0, 50, 1) == 0


def test_low_level_boost_matches_the_client():
    for level, special, expected in CLIENT["low_level"]:
        assert low_level_boost(level, on_special_server=special) == expected


@pytest.mark.parametrize(
    ("area_type", "distance", "corrected"),
    [
        (MapItemType.CAPITAL, 2.5, 6),
        (MapItemType.CAPITAL, 200, 144),
        (MapItemType.CAPITAL, 50.3, 50.3),
        (MapItemType.TRADING_METROPOLIS, 1, 6),
        (MapItemType.TRADING_METROPOLIS, 145, 144),
        (MapItemType.ARE_PORTAL, 3, 50),
        (MapItemType.CASTLE, 300.7, 300.7),
    ],
)
def test_corrected_attack_distance(area_type, distance, corrected):
    assert corrected_attack_distance(distance, area_type) == corrected


def test_troop_speed_matches_the_client():
    for speed, research, boost, expected in CLIENT["troop_speed"]:
        unit = UnitStats(wod_id=601, speed=speed)
        assert troop_speed(unit, research_bonus=research, commander_boost=boost) == expected


def test_the_slowest_troop_sets_the_speed():
    swordman, archer, ram = (
        UnitStats(wod_id=601, speed=18),
        UnitStats(wod_id=602, speed=20),
        ToolStats(wod_id=611, speed=12),
    )

    assert lowest_travel_speed([swordman, archer]) == 18
    assert lowest_travel_speed([swordman, archer, ram]) == 12
    assert lowest_travel_speed([swordman, archer], research_bonuses={601: 3}, commander_boosts={602: 10}) == 21


def test_an_army_without_troops_has_no_speed():
    with pytest.raises(ValueError):
        lowest_travel_speed([])


def test_attack_travel_time_matches_the_client():
    for row in CLIENT["attack"]:
        area_type, distance, level, npc, legend, vip, crusade, special, rank_swap, horse, commander, expected = row
        time = attack_travel_time(
            20,
            distance,
            MapItemType(area_type),
            player_level=level,
            horse=_horse(unit_boost=horse),
            commander_bonus=commander,
            vip_level=VipLevelDef(vip_level_id=5, attack_speed_bonus=vip) if vip is not None else None,
            target_is_npc=npc,
            legend_travel_boost=legend,
            on_special_server=special,
            on_crusade_map=crusade,
            outer_realms_rank_swap=rank_swap,
        )
        assert time == expected, row


def test_station_travel_time_matches_the_client():
    for distance, level, special, horse, commander, expected in CLIENT["station"]:
        time = station_travel_time(
            12,
            distance,
            player_level=level,
            horse=_horse(unit_boost=horse),
            commander_bonus=commander,
            on_special_server=special,
        )
        assert time == expected


def test_support_travel_time_matches_the_client():
    for distance, area_type, horse, commander, expected in CLIENT["support"]:
        time = support_travel_time(
            12, distance, MapItemType(area_type), horse=_horse(unit_boost=horse), commander_bonus=commander
        )
        assert time == expected


def test_trade_travel_time_matches_the_client():
    for distance, market, subscription, global_, area, title, horse, expected in CLIENT["trade"]:
        time = trade_travel_time(
            distance,
            market_bonus=market,
            subscription_bonus=subscription,
            global_bonus=global_,
            area_bonus=area,
            title_bonus=title,
            horse=_horse(market_boost=horse),
        )
        assert time == expected, (distance, market, subscription, global_, area, title, horse)


def test_spy_travel_time_matches_the_client():
    for distance, spy_type, research, construction, title, global_, horse, expected in CLIENT["spy"]:
        time = spy_travel_time(
            distance,
            SpyType(spy_type),
            research_bonus=research,
            construction_bonus=construction,
            title_bonus=title,
            global_bonus=global_,
            horse=_horse(spy_boost=horse),
        )
        assert time == expected, (distance, spy_type, research, construction, title, global_, horse)


def test_resources_per_carriage_matches_the_client():
    for level, boost, bonus, expected in CLIENT["carriage"]:
        carried = resources_per_carriage(level, capacity_boost=boost, capacity_bonus=bonus, game_data=GAME_DATA)
        assert carried == expected, (level, boost, bonus)


def test_trade_capacity_is_per_carriage_times_carriages():
    assert trade_capacity(30, 21, game_data=GAME_DATA) == 30 * resources_per_carriage(21, game_data=GAME_DATA)


def test_an_unknown_caravan_overloader_level_raises():
    with pytest.raises(KeyError):
        resources_per_carriage(22, game_data=GAME_DATA)


def test_travel_distance_matches_the_client():
    for row in CLIENT["distance"]:
        source_type, sx, sy, target_type, tx, ty, kingdom, camp, width, collector, berimond, rank_swap, expected = row
        target_kind = MapItemType(target_type)
        source = MapAreaItem(item_type=MapItemType(source_type), x=sx, y=sy, kingdom=Kingdom(kingdom))
        target = MapAreaItem(
            item_type=target_kind,
            x=tx,
            y=ty,
            kingdom=Kingdom(kingdom),
            special_camp_id=camp
            if target_kind in (MapItemType.BERIMOND_WATCHTOWER, MapItemType.BERIMOND_CAPITAL)
            else None,
        )
        distance = travel_distance(
            source,
            target,
            width,
            collector_attack=collector,
            outer_realms_rank_swap=rank_swap,
            berimond_event_running=berimond,
            game_data=GAME_DATA,
        )
        assert distance == expected, row


def test_a_berimond_camp_without_a_distance_raises():
    source = MapAreaItem(item_type=MapItemType.BERIMOND_CAMP, x=3, y=4)
    tower = MapAreaItem(item_type=MapItemType.BERIMOND_WATCHTOWER, x=9, y=9, special_camp_id=91)

    with pytest.raises(KeyError):
        travel_distance(source, tower, 650, game_data=GAME_DATA)


@pytest.mark.parametrize(
    ("kind", "area_type"),
    [
        ("capital", MapItemType.CAPITAL),
        ("metropolis", MapItemType.TRADING_METROPOLIS),
        ("outpost", MapItemType.OUTPOST),
        ("outpost", MapItemType.BERIMOND_CAMP),
    ],
)
def test_conquest_travel_speed_matches_the_client(kind, area_type):
    rows = [row for row in CLIENT["conquest_speed"] if row[0] == kind]
    assert rows
    for _, lowest, expected in rows:
        assert conquest_travel_speed(lowest, area_type) == expected
