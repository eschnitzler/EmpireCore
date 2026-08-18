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
    """How a mission should be sent: the fewest spies at the best risk going."""

    spies: int
    risk: int


def plan_mission(
    guards: int,
    available: int,
    accuracy: int = MAX_ACCURACY,
    max_risk: int = MAX_RISK_SPY,
    *,
    player_target: bool = True,
    dungeon: bool = False,
) -> SpyPlan | None:
    """Cheapest way to run this mission at the lowest risk the pool allows.

    Risk falls monotonically with spies, so the best risk on offer is the one at
    the full pool — but several counts usually tie at that risk, and the
    smallest of them leaves the rest of the pool for other targets. Sending 46
    spies where 6 reach the same 5% buys nothing and strands 40.

    ``max_risk`` only decides whether to send at all: None is returned when even
    the whole pool cannot bring the risk down to it, which is a target to skip
    rather than a mission to run badly.
    """
    if available < 1:
        return None

    best_risk = spy_risk(available, guards, accuracy, player_target=player_target, dungeon=dungeon)
    if best_risk > max_risk:
        return None

    for spies in range(1, available + 1):
        risk = spy_risk(spies, guards, accuracy, player_target=player_target, dungeon=dungeon)
        if risk <= best_risk:
            return SpyPlan(spies=spies, risk=risk)
    return SpyPlan(spies=available, risk=best_risk)


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
