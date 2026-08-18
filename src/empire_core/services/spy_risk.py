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


def spies_for_risk(
    guards: int,
    accuracy: int,
    max_risk: int,
    available: int,
    *,
    player_target: bool = True,
    dungeon: bool = False,
) -> int | None:
    """Fewest spies whose risk stays within *max_risk*, or None if unreachable.

    Risk falls monotonically as spies rise, so the first count that fits is the
    cheapest one. None means no affordable count reaches the budget — either the
    pool is too small or the budget is under the floor for this target.
    """
    for spies in range(1, available + 1):
        risk = spy_risk(spies, guards, accuracy, player_target=player_target, dungeon=dungeon)
        if risk <= max_risk:
            return spies
    return None


__all__ = [
    "MAX_ACCURACY",
    "MAX_RISK_SPY",
    "MIN_ACCURACY",
    "MIN_RISK_SPY_DUNGEON",
    "MIN_RISK_SPY_PLAYER",
    "spies_for_risk",
    "spy_risk",
]
