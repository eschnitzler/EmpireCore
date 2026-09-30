"""Espionage risk model, ported from the game client's SpyConst.

Constants and formulas are taken verbatim from ``SpyConst`` (dll lines
19738-19757), so a mission can be costed before it is sent. ``getSpyRisk``
reads:

    ratioGuardSpy = MAX_GUARD / MAX_SPY
    ratioAccuracy = 50 - (MAX_ACCURACY + MIN_ACCURACY) / 2
    r = clamp(-(ratioGuardSpy * spies - guards) + ratioAccuracy + accuracy, floor, MAX_RISK_SPY)
    o = clamp(floor(guards / spies / ratioGuardSpy * (ratioAccuracy + accuracy)), floor, MAX_RISK_SPY)
    risk = round((r + o) / 2)

The floor is MIN_RISK_SPY_PLAYER unless the target is a dungeon or not a
player's, then MIN_RISK_SPY_DUNGEON; see :func:`risk_target_flags`.
``getSabotageRisk`` is the same with the damage for the accuracy, its own
ratio and the fixed MIN_RISK_SABOTAGE..MAX_RISK_SABOTAGE range.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from empire_core.combat import is_npc_pvp_player, owner_id_from_row
from empire_core.enums import MapItemType
from empire_core.messages.models import SPY_VALIDITY
from empire_core.protocol.js import js_int

MAX_GUARD = 180
MAX_SPY = 15
MIN_RISK_SPY_PLAYER = 5
MIN_RISK_SPY_DUNGEON = 0
MAX_RISK_SPY = 95
MIN_ACCURACY = 50
MAX_ACCURACY = 100
MIN_RISK_SABOTAGE = 10
MAX_RISK_SABOTAGE = 90
MIN_DAMAGE = 10
MAX_DAMAGE = 50
DAMAGE_PER_BUILDING = 10
MAX_SABOTAGE_COOLDOWN = 43200
SABOTAGE_PROTECTION_WINDOW = 345600
TRAVELSPEED_SPY = 450
TRAVELSPEED_SABOTAGE = 50
DAMAGE_PER_SPY = 0.02
SABOTAGE_PROTECTION_THRESHOLD = 12
"""``SpyConst.SABTOAGE_PROTECTION_THRESHOLD``, spelled that way in the client."""
MAX_DEPLOYABLE_PLAGUEMONKS = 20
MAX_OWNABLE_PLAGUEMONKS = 200

RATIO_GUARD_SPY = MAX_GUARD / MAX_SPY
RATIO_ACCURACY = 50 - (MAX_ACCURACY + MIN_ACCURACY) / 2
RATIO_DAMAGE = 50 - (MAX_DAMAGE + MIN_DAMAGE) / 2

OUTPOST_AREA_TYPES = frozenset({int(MapItemType.OUTPOST), int(MapItemType.CAPITAL), int(MapItemType.METROPOL)})
"""
Area types built as an ``OutpostMapobjectVO``: the outpost and its capital and
metropolis subclasses (``WorldmapObjectFactory.mapObjectVOs``, bundle line 5357;
``CapitalMapobjectVO`` bundle line 18760, ``MetropolMapobjectVO`` 21637).
"""

_NPC_OWNED_AREA_TYPES = frozenset(
    {
        int(MapItemType.DUNGEON),
        int(MapItemType.BOSS_DUNGEON),
        int(MapItemType.EVENT_DUNGEON),
        int(MapItemType.ISLE_DUNGEON),
        int(MapItemType.DAIMYO_CASTLE),
        int(MapItemType.WOLF_KING),
    }
)
"""
Area types whose map object always gets an NPC owner below 0 that the game
does not fight like a player:

- ``DUNGEON``: ``DungeonConst.DUNGEON_PLAYER_ID`` (-202) minus 0-12, or
  ``KINGDOM_DUNGEON_PLAYER_ID`` (-220) minus the kingdom
  (``WorldmapObjectFactory.initDungeonByXY``, bundle lines 5349-5354)
- ``BOSS_DUNGEON``: ``KINGDOM_BOSS_DUNGEON_PLAYER_ID`` (-230) minus the kingdom
  (``BossdungeonMapobjectVO.parseAreaInfo``, bundle line 34441)
- ``EVENT_DUNGEON``: the running dungeon event's owner, -500 to -503 or
  ``DungeonConst.INVALID`` (-1) (``EventdungeonMapobjectVO.parseAreaInfo``,
  bundle lines 34488-34490; ``getEventDungeonOwnerIDBySkinID``, dll line 19123)
- ``ISLE_DUNGEON``: ``NPC_ID_EILAND_DUNGEON``, -220 minus the storm islands
  (``DungeonIsleMapobjectVO``, bundle lines 76287-76288)
- ``DAIMYO_CASTLE``: ``BASIC_DAIMYO_CASTLE_PLAYER_ID`` (-811) (bundle line 19651)
- ``WOLF_KING``: ``BASIC_WOLF_KING_PLAYER_ID`` (-1201) (bundle line 34409)

Ids from ``DungeonConst`` (dll line 19157).
"""

_NPC_CAMP_OWNERS = {
    int(MapItemType.NOMAD_CAMP): -601,
    int(MapItemType.SAMURAI_CAMP): -651,
    int(MapItemType.ALLIANCE_NOMAD_CAMP): -801,
}
"""
``DungeonConst.BASIC_NOMAD_CAMP_PLAYER_ID``, ``BASIC_SAMURAI_CAMP_PLAYER_ID`` and
``BASIC_ALLIANCE_NOMAD_CAMP_PLAYER_ID`` (dll line 19157): the owners
``NomadCampMapObjectVO.parseAreaInfo``, ``SamuraiCampMapObjectVO.parseAreaInfo`` and
``NomadKhanCampMapObjectVO.parseData`` set for a row of more than three fields
(bundle lines 76379, 76493, 76434 through 47391).
"""

_FACTION_INVASION_OWNER_FIELD = 7
"""``FactionInvasionCampMapObjectVO.parseAreaInfo`` (bundle line 76324) owns the camp by ``int(e[7])``."""


def _clamp(value: float, low: float, high: float) -> float:
    return max(min(value, high), low)


def _js_round(value: float) -> int:
    # Math.round rounds halves up; Python's round() is banker's rounding
    return math.floor(value + 0.5)


def spy_risk(
    spies: int,
    guards: int,
    accuracy: int | float = MAX_ACCURACY,
    *,
    player_target: bool = True,
    dungeon: bool = False,
) -> int:
    """
    The percentage chance of a military or economy mission being caught, as the client shows it.

    Args:
        spies: Spies sent, at least 1
        guards: Guards at the target, ``SpyScreenInfoResponse.guard_count``
        accuracy: Accuracy percent, 50-100
        player_target: The client's ``isPlayer``; see :func:`risk_target_flags`
        dungeon: The client's ``isDungeon``; see :func:`risk_target_flags`

    Client: ``SpyConst.getSpyRisk`` (dll lines 19745-19748)
    """
    if spies < 1:
        raise ValueError("a spy mission needs at least one spy")

    floor = MIN_RISK_SPY_PLAYER if (player_target and not dungeon) else MIN_RISK_SPY_DUNGEON

    direct = _clamp(-(RATIO_GUARD_SPY * spies - guards) + RATIO_ACCURACY + accuracy, floor, MAX_RISK_SPY)
    ratio = _clamp(
        math.floor(guards / spies / RATIO_GUARD_SPY * (RATIO_ACCURACY + accuracy)),
        floor,
        MAX_RISK_SPY,
    )
    return _js_round((direct + ratio) / 2)


def sabotage_risk(spies: int, guards: int, damage: int | float) -> int:
    """
    The percentage chance of a sabotage mission being caught, as the client shows it.

    The client costs a plague monk mission with the same formula.

    Args:
        spies: Spies sent, at least 1
        guards: Guards at the target, ``SpyScreenInfoResponse.guard_count``
        damage: Damage percent, 10-50

    Client: ``SpyConst.getSabotageRisk`` (dll line 19749), ``CastleStartSpyVO.setSabotageValues``
    and ``setPlagueValues`` (bundle lines 140006-140007)
    """
    if spies < 1:
        raise ValueError("a sabotage mission needs at least one spy")

    direct = _clamp(-(RATIO_GUARD_SPY * spies - guards) + RATIO_DAMAGE + damage, MIN_RISK_SABOTAGE, MAX_RISK_SABOTAGE)
    ratio = _clamp(
        math.floor(guards / spies / RATIO_GUARD_SPY * (RATIO_DAMAGE + damage)),
        MIN_RISK_SABOTAGE,
        MAX_RISK_SABOTAGE,
    )
    return _js_round((direct + ratio) / 2)


def max_damaged_buildings(owner_level: int) -> int:
    """
    How many buildings a sabotage of an owner at this level can damage.

    Client: ``CombatConst.getMaxDamagedBuildings`` (dll line 18896)
    """
    return _js_round(0.179 * math.exp(0.199 * (owner_level - 4)))


def max_sabotage_damage(owner_level: int) -> int:
    """
    The most damage the client lets a sabotage of an owner at this level do, 0 when it offers no sabotage.

    The damage slider runs from MIN_DAMAGE to MAX_DAMAGE and stops at ten
    per building the target can lose; the sabotage tab is disabled when that
    is no building.

    Args:
        owner_level: The target owner's level

    Client: ``ACastleSpyDialogState.updateSliderForDamage`` (bundle line 34360),
    the sabotage tab check (bundle line 34338)
    """
    buildings = max_damaged_buildings(owner_level)
    if buildings < 1:
        return 0
    return min(MAX_DAMAGE, buildings * DAMAGE_PER_BUILDING)


def risk_target_flags(owner_id: int, area_type: int | None) -> tuple[bool, bool]:
    """
    The client's ``(isDungeon, isPlayer)`` for a target, in the order :func:`spy_risk` takes them.

    ``isDungeon`` is an owner below 0 that is no alien invasion or collector;
    ``isPlayer`` is anything but an outpost, or an outpost a player owns.
    Pass them as ``spy_risk(..., dungeon=..., player_target=...)``.

    Args:
        owner_id: The target owner's player id, e.g. ``MapObject.owner_id`` or a map row's owner
        area_type: The target's area type

    Client: ``CastleStartSpyVO.setSpyValues`` (bundle line 140004),
    ``PlayerHelper.isNpcPvpPlayer`` (bundle line 4689)
    """
    dungeon = owner_id < 0 and not is_npc_pvp_player(owner_id)
    player_target = area_type not in OUTPOST_AREA_TYPES or owner_id > 0
    return dungeon, player_target


def row_risk_flags(row: list | None) -> tuple[bool, bool] | None:
    """
    The client's ``(isDungeon, isPlayer)`` for a target's map row, or None where its owner is not traced here.

    NPC dungeons and camps have fixed owners below 0 that the game does not
    fight like players; a faction invasion camp names its owner in the row;
    alien camps and the areas whose row names the owner are read with
    :func:`~empire_core.combat.owner_id_from_row`. Not traced: treasure
    dungeons and camps, shadow areas (whose owner may be a collector) and any
    other type; a samurai alien camp has no map object in the client.

    Args:
        row: The target's raw map row, e.g. ``SpyScreenInfoResponse.target_row().raw_data``

    Client: ``WorldmapObjectFactory.parseWorldMapArea`` (bundle line 5343) and the
    ``parseAreaInfo`` of each map object
    """
    if not row:
        return None
    try:
        area_type = int(row[0])
        if area_type in _NPC_OWNED_AREA_TYPES:
            return True, True
        if area_type in _NPC_CAMP_OWNERS:
            owner_id = _NPC_CAMP_OWNERS[area_type] if len(row) > 3 else None
        elif area_type == MapItemType.FACTION_INVASION_CAMP:
            owner_id = js_int(row[_FACTION_INVASION_OWNER_FIELD]) if len(row) > _FACTION_INVASION_OWNER_FIELD else None
        else:
            owner_id = owner_id_from_row(row)
    except (TypeError, ValueError):
        return None
    if owner_id is None:
        return None
    return risk_target_flags(owner_id, area_type)


@dataclass(frozen=True)
class SpyPlan:
    """How a mission should be sent: spies, the risk it buys, and at what detail."""

    spies: int
    risk: int
    accuracy: int = MAX_ACCURACY


def plan_mission(
    guards: int,
    available: int,
    accuracy: int = MAX_ACCURACY,
    max_risk: int = MAX_RISK_SPY,
    *,
    player_target: bool = True,
    dungeon: bool = False,
) -> SpyPlan | None:
    """
    The library's cheapest military or economy mission inside the risk ceiling.

    Risk falls as accuracy falls, so accuracy is walked down from ``accuracy``
    to MIN_ACCURACY until the whole pool's risk fits the ceiling. The most
    detailed report that fits is chosen, then the fewest spies that reach the
    same risk, leaving the rest of the pool for other targets. This search is
    the library's own: the client's dialog lets the player pick both values and
    only colours its slider by risk (``ACastleSpyDialogState.getAccuracyByRisk``,
    bundle line 34363).

    None means even the least accurate mission with every spy available stays
    above the ceiling: a target to skip rather than spy badly.
    """
    if available < 1:
        return None

    for candidate in range(min(accuracy, MAX_ACCURACY), MIN_ACCURACY - 1, -1):
        best_risk = spy_risk(available, guards, candidate, player_target=player_target, dungeon=dungeon)
        if best_risk > max_risk:
            continue
        for spies in range(1, available + 1):
            risk = spy_risk(spies, guards, candidate, player_target=player_target, dungeon=dungeon)
            if risk <= best_risk:
                return SpyPlan(spies=spies, risk=risk, accuracy=candidate)
        return SpyPlan(spies=available, risk=best_risk, accuracy=candidate)
    return None


@dataclass(frozen=True)
class SabotagePlan:
    """How a sabotage should be sent: spies, the risk it buys, and the damage."""

    spies: int
    risk: int
    damage: int


def plan_sabotage(guards: int, available: int, damage: int, max_risk: int = MAX_RISK_SABOTAGE) -> SabotagePlan | None:
    """
    The library's cheapest sabotage at this damage inside the risk ceiling.

    The damage is kept as asked; the fewest spies that reach the whole pool's
    risk are sent. None when even the whole pool stays above the ceiling.

    Args:
        guards: Guards at the target
        available: Spies at hand
        damage: Damage percent, MIN_DAMAGE up to :func:`max_sabotage_damage` of the target's owner
        max_risk: Ceiling on the risk, percent
    """
    if available < 1:
        return None
    if not MIN_DAMAGE <= damage <= MAX_DAMAGE:
        raise ValueError(f"sabotage damage must be {MIN_DAMAGE}-{MAX_DAMAGE}, got {damage}")
    best_risk = sabotage_risk(available, guards, damage)
    if best_risk > max_risk:
        return None
    for spies in range(1, available + 1):
        risk = sabotage_risk(spies, guards, damage)
        if risk <= best_risk:
            return SabotagePlan(spies=spies, risk=risk, damage=damage)
    return SabotagePlan(spies=available, risk=best_risk, damage=damage)


__all__ = [
    "DAMAGE_PER_BUILDING",
    "DAMAGE_PER_SPY",
    "MAX_ACCURACY",
    "MAX_DAMAGE",
    "MAX_DEPLOYABLE_PLAGUEMONKS",
    "MAX_OWNABLE_PLAGUEMONKS",
    "MAX_GUARD",
    "MAX_RISK_SABOTAGE",
    "MAX_RISK_SPY",
    "MAX_SABOTAGE_COOLDOWN",
    "MAX_SPY",
    "MIN_ACCURACY",
    "MIN_DAMAGE",
    "MIN_RISK_SABOTAGE",
    "MIN_RISK_SPY_DUNGEON",
    "MIN_RISK_SPY_PLAYER",
    "OUTPOST_AREA_TYPES",
    "SABOTAGE_PROTECTION_THRESHOLD",
    "SABOTAGE_PROTECTION_WINDOW",
    "SPY_VALIDITY",
    "TRAVELSPEED_SABOTAGE",
    "TRAVELSPEED_SPY",
    "SabotagePlan",
    "SpyPlan",
    "max_damaged_buildings",
    "max_sabotage_damage",
    "plan_mission",
    "plan_sabotage",
    "risk_target_flags",
    "row_risk_flags",
    "sabotage_risk",
    "spy_risk",
]
