"""
Travel time and carriage capacity, worked out as the game client works them out.

The server sends no travel time before a send: the client computes it from the
slowest troop, the distance, the horse and the speed bonuses, and so does this
module. Nothing here sends a request. Bonuses that come from the player's
effects (commander equipment, research, titles, global effects, alliance buffs)
are inputs, summed in percent the way the client's code for each action sums them.

Client: ``TravelConst`` (ggs.dll.js), ``CastleAttackInfoVO.calculateTravelTime``
(bundle line 160159), ``CastleTroopSupportVO.getBoostedTravelTime`` (bundle line 512667),
``CastleSupportDefenceVO.getBoostedTravelTime`` (bundle line 697495),
``CastlePostSendGoodsDialog.getBoostedTravelTime`` (bundle line 174648),
``CastlePostSpyDialog.getBoostedTravelTime`` (bundle line 201005),
``CastleTradeVO.getMaxCapacityForCurrentLevel`` (bundle line 698512)
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

from empire_core.enums import MapItemType, SpyType
from empire_core.gamedata import GameData, HorseStats, ToolStats, UnitOrTool, UnitStats, VipLevelDef
from empire_core.protocol.js import js_int32, js_round

BASIC_FIELD_TRAVEL_TIME = 600
HORSE_BOOST_FIELDS = 10
LOW_DISTANCE_BOOST_FIELDS = 100
TRAVEL_BOOST_TUTORIAL = 20
"""The speed factor of an attack on an NPC up to :data:`TUTORIAL_END_LEVEL`."""
TUTORIAL_END_LEVEL = 5
MAX_LEVEL_FOR_LOW_LEVEL_TRAVEL_BOOST = 25
CAPITAL_MIN_ATTACK_DISTANCE = 6
CAPITAL_MAX_ATTACK_DISTANCE = 144
METROPOLIS_MIN_ATTACK_DISTANCE = 6
METROPOLIS_MAX_ATTACK_DISTANCE = 144
ALLIANCE_RAID_PORTAL_TRAVEL_DISTANCE = 50
MARKET_TRAVEL_SPEED = 50
"""The speed of a trader's carriages (``MarketConst.MARKET_TRAVEL_SPEED``)."""
SPY_TRAVEL_SPEED = 450
"""The speed of spies (``SpyConst.TRAVELSPEED_SPY``)."""
SABOTAGE_TRAVEL_SPEED = 50
"""The speed of saboteurs (``SpyConst.TRAVELSPEED_SABOTAGE``)."""
RESOURCES_PER_CARRIAGE = 100
"""What a carriage carries before boosts (``MarketConst.RESOURCES_PER_CARRIAGE``)."""


def travel_time(speed: float, distance: float, speed_factor: float, area_bonus: float = 0) -> int:
    """
    Seconds to cover ``distance`` fields at ``speed`` without a horse.

    Client: ``TravelConst.getTravelTime`` and ``getTravelTimeAsFloat`` (ggs.dll.js)
    """
    fields_per_second = speed / 10 / BASIC_FIELD_TRAVEL_TIME * (speed_factor + area_bonus / 100)
    return _seconds(distance, fields_per_second)


def travel_time_with_horse(
    speed: float, distance: float, speed_factor: float, horse_boost: float = 0, area_bonus: float = 0
) -> int:
    """
    Seconds to cover ``distance`` fields at ``speed`` with a horse's boost in percent.

    Below :data:`LOW_DISTANCE_BOOST_FIELDS` the horse's boost grows with the
    log of the distance; from there it grows with the distance, and a horse
    saves the first 10 fields.

    Client: ``TravelConst.getTravelTimeWithHorse`` (ggs.dll.js); every call site passes
    the distance as both its second and its sixth argument
    """
    fields_per_second = speed / 10 / BASIC_FIELD_TRAVEL_TIME * (speed_factor + area_bonus / 100)
    if distance < LOW_DISTANCE_BOOST_FIELDS:
        horse = 1 + horse_boost / 100 / HORSE_BOOST_FIELDS * 60 * (math.log(distance / 2 + 1) / math.log(8))
    elif horse_boost > 0:
        horse = 1 + horse_boost / 100 / HORSE_BOOST_FIELDS * (distance - 10)
        distance -= 10
    else:
        horse = 1 + horse_boost / 100 / HORSE_BOOST_FIELDS * distance
    return _seconds(distance, fields_per_second * horse)


def _seconds(distance: float, fields_per_second: float) -> int:
    # 0 | Math.floor(x): NaN and the infinity of a zero speed read as 0
    try:
        seconds = distance / fields_per_second
    except ZeroDivisionError:
        return 0
    return js_int32(math.floor(seconds)) if math.isfinite(seconds) else 0


def low_level_boost(level: int, *, on_special_server: bool = False) -> float:
    """
    The speed factor a player below level 25 gets on top, in hundredths: 4 at level 1, 0 from 25 on.

    Client: ``TravelConst.calculateLowLevelBoost`` (ggs.dll.js)
    """
    if on_special_server or level >= MAX_LEVEL_FOR_LOW_LEVEL_TRAVEL_BOOST:
        return 0
    return js_int32(100 * max(0, -0.1667 * level + 4.167)) / 100


def corrected_attack_distance(distance: float, area_type: MapItemType) -> float:
    """
    The distance an attack travels: clamped to 6-144 fields for a capital or trading metropolis, 50 for a portal.

    Client: ``CastleAttackInfoVO.getCorrectedAttackDistance`` (bundle line 160226)
    """
    if area_type == MapItemType.CAPITAL:
        return min(max(distance, CAPITAL_MIN_ATTACK_DISTANCE), CAPITAL_MAX_ATTACK_DISTANCE)
    if area_type == MapItemType.TRADING_METROPOLIS:
        return min(max(distance, METROPOLIS_MIN_ATTACK_DISTANCE), METROPOLIS_MAX_ATTACK_DISTANCE)
    if area_type == MapItemType.ARE_PORTAL:
        return ALLIANCE_RAID_PORTAL_TRAVEL_DISTANCE
    return distance


def troop_speed(troop: UnitStats | ToolStats, *, research_bonus: int = 0, commander_boost: float = 0) -> int:
    """
    A unit's or tool's travel speed.

    ``research_bonus`` is the research ``UNIT_SPEED_BONUS`` for it, added to its
    speed; ``commander_boost`` the commander's ``SPEED_BOOST_UNIT`` for it, in percent.

    Client: ``BasicUnitVO.unitSpeed`` (bundle line 103194), ``CastleFightItemContainer.getLowestTravelSpeed``
    (bundle line 93268)
    """
    return math.ceil((troop.speed + research_bonus) * ((100 + commander_boost) / 100))


def lowest_travel_speed(
    troops: Iterable[UnitStats | ToolStats],
    *,
    research_bonuses: Mapping[UnitOrTool, int] | None = None,
    commander_boosts: Mapping[UnitOrTool, float] | None = None,
) -> int:
    """
    The speed of the slowest troop, which the whole army travels at.

    ``research_bonuses`` and ``commander_boosts`` hold :func:`troop_speed`'s bonuses by unit or tool.

    Raises:
        ValueError: no troops; the client gives an army without troops no travel time.

    Client: ``CastleFightItemContainer.getLowestTravelSpeed`` (bundle line 93268)
    """
    research_bonuses = research_bonuses or {}
    commander_boosts = commander_boosts or {}
    speeds = [
        troop_speed(
            troop,
            research_bonus=research_bonuses.get(troop.wod_id, 0),
            commander_boost=commander_boosts.get(troop.wod_id, 0),
        )
        for troop in troops
    ]
    if not speeds:
        raise ValueError("an army without troops has no travel speed")
    return min(speeds)


def attack_travel_time(
    speed: int,
    distance: float,
    target_area_type: MapItemType,
    *,
    player_level: int,
    horse: HorseStats | None = None,
    commander_bonus: int = 0,
    vip_level: VipLevelDef | None = None,
    target_is_npc: bool = False,
    legend_travel_boost: float = 0,
    on_special_server: bool = False,
    on_crusade_map: bool = False,
    outer_realms_rank_swap: bool = False,
) -> int:
    """
    Seconds an attack takes to reach its target.

    A conquest's army is slower still (``CastleConquerInfoVO.getLowestTravelSpeed``), which is not ported.

    Args:
        speed: the army's :func:`lowest_travel_speed`.
        distance: fields to the target as the client measures them (``MapHelper.getDistanceByMapobjects``,
            which gives some camps and towers fixed distances), before :func:`corrected_attack_distance`.
        target_area_type: the target's area type.
        player_level: the attacking player's level.
        horse: the horse sent along; its ``unit_boost`` counts.
        commander_bonus: the commander's equipment ``SPEED_BONUS`` and ``SPEED_BONUS_PVP`` in percent,
            each truncated to an int.
        vip_level: the active VIP level, None while VIP time does not run.
        target_is_npc: the target's owner is an NPC (player id below 0).
        legend_travel_boost: the legend skills' ``TRAVEL_ATTACK_BOOST`` in percent, given when the
            target's owner is a legend; 0 otherwise.
        on_special_server: the player is on a special server, which drops the low-level boost.
        on_crusade_map: the target is on a crusade treasure map, where the VIP bonus does not count.
        outer_realms_rank_swap: an Outer Realms rank swap attack, which drops the low-level boost.

    The King's Market return speed booster is left out: no call site in the client applies it.

    Client: ``CastleAttackInfoVO.calculateTravelTime`` (bundle line 160159),
    ``CastleFightScreenVO.getActionTravelTimeBonusForAreaType`` (bundle line 159369),
    ``CastlePostAttackDialog.getTravelBoost`` (bundle line 200671)
    """
    speed_factor: float = (
        TRAVEL_BOOST_TUTORIAL if player_level <= TUTORIAL_END_LEVEL and target_is_npc else 1
    ) + legend_travel_boost / 100
    area_bonus = commander_bonus
    if vip_level is not None and not on_crusade_map:
        area_bonus += vip_level.attack_speed_bonus
    if not outer_realms_rank_swap:
        speed_factor += low_level_boost(player_level, on_special_server=on_special_server)
    corrected = corrected_attack_distance(distance, target_area_type)
    return travel_time_with_horse(speed, corrected, speed_factor, horse.unit_boost if horse else 0, area_bonus)


def station_travel_time(
    speed: int,
    distance: float,
    *,
    player_level: int,
    horse: HorseStats | None = None,
    commander_bonus: int = 0,
    on_special_server: bool = False,
) -> int:
    """
    Seconds troops sent to one of the player's own castles take (``sti``).

    ``commander_bonus`` is the commander's equipment ``SPEED_BONUS`` plus ``STATIONING_SPEED_BONUS``, in percent.

    Client: ``CastleTroopSupportVO.getBoostedTravelTime`` (bundle line 512667)
    """
    speed_factor = low_level_boost(player_level, on_special_server=on_special_server) + 1
    return travel_time_with_horse(speed, distance, speed_factor, horse.unit_boost if horse else 0, commander_bonus)


def support_travel_time(
    speed: int,
    distance: float,
    target_area_type: MapItemType,
    *,
    horse: HorseStats | None = None,
    commander_bonus: int = 0,
) -> int:
    """
    Seconds a defence support (``sdi``) takes; 0 to a daimyo township without a horse.

    ``commander_bonus`` is the commander's equipment ``SPEED_BONUS`` plus ``SUPPORT_SPEED_BONUS``, in percent.
    With a horse the client takes the township's time from ``getBoostedTravelTime``, which has no
    township case.

    Client: ``CastleSupportDefenceVO.getTravelTime`` and ``getBoostedTravelTime`` (bundle lines 697490, 697495)
    """
    if horse is None and target_area_type == MapItemType.DAIMYO_TOWNSHIP:
        return 0
    return travel_time_with_horse(speed, distance, 1, horse.unit_boost if horse else 0, commander_bonus)


def trade_travel_time(
    distance: float,
    *,
    market_bonus: float = 0,
    subscription_bonus: float = 0,
    global_bonus: float = 0,
    area_bonus: float = 0,
    title_bonus: float = 0,
    horse: HorseStats | None = None,
) -> int:
    """
    Seconds a trader's carriages take.

    The bonuses are percents, added in the client's order: ``market_bonus`` the research
    ``MARKET_SPEED_BONUS`` to the player's own castle, or the alliance's market speed buff to
    another's; the subscription's ``MARKET_SPEED_BONUS``; the global ``SPEED_BONUS``; the trading
    castle's area ``MARKET_SPEED_BONUS``; the titles' ``MARKET_SPEED_BONUS`` and ``SPEED_BONUS``.

    Client: ``CastlePostSendGoodsDialog.getBoostedTravelTime`` (bundle line 174648),
    ``CastleSendGoodsDialog.getTravelTime`` (bundle line 142678)
    """
    speed_factor = 1 + market_bonus / 100
    for bonus in (subscription_bonus, global_bonus, area_bonus, title_bonus):
        speed_factor += bonus / 100
    return travel_time_with_horse(MARKET_TRAVEL_SPEED, distance, speed_factor, horse.market_boost if horse else 0)


def spy_travel_time(
    distance: float,
    spy_type: SpyType,
    *,
    research_bonus: float = 0,
    construction_bonus: float = 0,
    title_bonus: float = 0,
    global_bonus: float = 0,
    horse: HorseStats | None = None,
) -> int:
    """
    Seconds spies take: saboteurs travel at 50, other spies at 450.

    The bonuses are percents, added in the client's order: the research ``ESPIONAGE_SPEED_BOOST``,
    the construction items' espionage speed boost, the titles' ``SPEED_BONUS`` and the global ``SPEED_BONUS``.

    Client: ``CastlePostSpyDialog.getBoostedTravelTime`` (bundle line 201005),
    ``CastleStartSpyVO.getTravelTime`` (bundle line 697197)
    """
    speed = SABOTAGE_TRAVEL_SPEED if spy_type == SpyType.SABOTAGE else SPY_TRAVEL_SPEED
    speed_factor = 1 + research_bonus / 100
    for bonus in (construction_bonus, title_bonus, global_bonus):
        speed_factor += bonus / 100
    return travel_time_with_horse(speed, distance, speed_factor, horse.spy_boost if horse else 0)


def resources_per_carriage(
    caravan_overloader_level: int,
    *,
    capacity_boost: float = 0,
    capacity_bonus: float = 0,
    game_data: GameData | None = None,
) -> int:
    """
    What one carriage carries with the caravan overloader at ``caravan_overloader_level``.

    ``capacity_boost`` is the trading castle's area ``MARKET_CARRIAGE_CAPACITY_BOOST`` in percent;
    ``capacity_bonus`` its baron's and its area's ``MARKET_CARRIAGE_CAPACITY_BONUS``, added per carriage.

    Raises:
        KeyError: the items have no caravan overloader row for the level.

    Client: ``CastlePremiumBoostData.getResourcesTransportablePerCarriage`` (bundle line 81705),
    ``CastleTradeVO.getCapacityBoost`` and ``getCapacityBonus`` (bundle lines 698525, 698532)
    """
    game_data = game_data if game_data is not None else GameData.require()
    overloader = 1 + 0.01 * game_data.caravan_overloader_percent(caravan_overloader_level)
    carried = RESOURCES_PER_CARRIAGE * (0.01 * (100 + capacity_boost)) * overloader + capacity_bonus
    return 1 + js_round(js_round(carried * 10) / 10)


def trade_capacity(
    carriages: int,
    caravan_overloader_level: int,
    *,
    capacity_boost: float = 0,
    capacity_bonus: float = 0,
    game_data: GameData | None = None,
) -> int:
    """
    What ``carriages`` carriages carry together: :func:`resources_per_carriage` times their number.

    Client: ``CastleTradeVO.getMaxCapacityForCurrentLevel`` (bundle line 698512)
    """
    per_carriage = resources_per_carriage(
        caravan_overloader_level, capacity_boost=capacity_boost, capacity_bonus=capacity_bonus, game_data=game_data
    )
    return per_carriage * carriages


__all__ = [
    "ALLIANCE_RAID_PORTAL_TRAVEL_DISTANCE",
    "BASIC_FIELD_TRAVEL_TIME",
    "CAPITAL_MAX_ATTACK_DISTANCE",
    "CAPITAL_MIN_ATTACK_DISTANCE",
    "HORSE_BOOST_FIELDS",
    "LOW_DISTANCE_BOOST_FIELDS",
    "MARKET_TRAVEL_SPEED",
    "MAX_LEVEL_FOR_LOW_LEVEL_TRAVEL_BOOST",
    "METROPOLIS_MAX_ATTACK_DISTANCE",
    "METROPOLIS_MIN_ATTACK_DISTANCE",
    "RESOURCES_PER_CARRIAGE",
    "SABOTAGE_TRAVEL_SPEED",
    "SPY_TRAVEL_SPEED",
    "TRAVEL_BOOST_TUTORIAL",
    "TUTORIAL_END_LEVEL",
    "attack_travel_time",
    "corrected_attack_distance",
    "low_level_boost",
    "lowest_travel_speed",
    "resources_per_carriage",
    "spy_travel_time",
    "station_travel_time",
    "support_travel_time",
    "trade_capacity",
    "trade_travel_time",
    "travel_time",
    "travel_time_with_horse",
    "troop_speed",
]
