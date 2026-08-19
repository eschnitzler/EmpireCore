"""Espionage risk model, ported from the game client's SpyConst.

Constants and both formulas are taken verbatim from ``SpyConst`` in the live
client bundle, so a spy mission can be costed before it is sent instead of
sending the whole spy pool and hoping. ``getSpyRisk`` there reads:

    ratioGuardSpy = MAX_GUARD / MAX_SPY
    ratioAccuracy = 50 - (MAX_ACCURACY + MIN_ACCURACY) / 2
    r = clamp(-(ratioGuardSpy * spies - guards) + ratioAccuracy + accuracy, floor, MAX_RISK_SPY)
    o = clamp(floor(guards / spies / ratioGuardSpy * (ratioAccuracy + accuracy)), floor, MAX_RISK_SPY)
    risk = round((r + o) / 2)

The floor is MIN_RISK_SPY_PLAYER for a player's castle or owned outpost and
MIN_RISK_SPY_DUNGEON otherwise: spying a player is never risk-free.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MAX_GUARD = 180
MAX_SPY = 15
MIN_RISK_SPY_PLAYER = 5
MIN_RISK_SPY_DUNGEON = 0
MAX_RISK_SPY = 95
MIN_ACCURACY = 50
MAX_ACCURACY = 100

RATIO_GUARD_SPY = MAX_GUARD / MAX_SPY
RATIO_ACCURACY = 50 - (MAX_ACCURACY + MIN_ACCURACY) / 2


def _clamp(value: float, low: float, high: float) -> float:
    return max(min(value, high), low)


def spy_risk(
    spies: int,
    guards: int,
    accuracy: int = MAX_ACCURACY,
    *,
    player_target: bool = True,
    dungeon: bool = False,
) -> int:
    """The percentage chance of being caught, as the client would show it."""
    if spies < 1:
        raise ValueError("a spy mission needs at least one spy")

    floor = MIN_RISK_SPY_PLAYER if (player_target and not dungeon) else MIN_RISK_SPY_DUNGEON

    direct = _clamp(-(RATIO_GUARD_SPY * spies - guards) + RATIO_ACCURACY + accuracy, floor, MAX_RISK_SPY)
    ratio = _clamp(
        math.floor(guards / spies / RATIO_GUARD_SPY * (RATIO_ACCURACY + accuracy)),
        floor,
        MAX_RISK_SPY,
    )
    # Math.round in the client rounds halves up; Python's round() is
    # banker's rounding, which disagrees on every .5 (a 6.5 risk is 7 there
    # and 6 here) and would silently pick a different spy count.
    return math.floor((direct + ratio) / 2 + 0.5)


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
    """Cheapest way to run this mission inside the risk ceiling.

    Accuracy is a lever, not a constant. Risk falls as accuracy falls, so the
    client's own dialog walks accuracy down until the risk fits rather than
    refusing the mission — a guarded castle that sits at 7% with a full pool at
    accuracy 100 reaches the 5% floor at a lower accuracy. The most detailed
    report that fits is chosen, then the fewest spies that achieve it, leaving
    the rest of the pool for other targets.

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


__all__ = [
    "MAX_ACCURACY",
    "MAX_RISK_SPY",
    "MIN_ACCURACY",
    "MIN_RISK_SPY_DUNGEON",
    "MIN_RISK_SPY_PLAYER",
    "SpyPlan",
    "plan_mission",
    "spy_risk",
]
