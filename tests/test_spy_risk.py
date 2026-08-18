"""The client-side espionage risk model, ported from the game's own code.

Constants and formula are lifted verbatim from SpyConst in the live client
bundle (ggs.dll), so these tests pin our port against it rather than against
anything invented here.
"""

import pytest

from empire_core.services.spy_risk import (
    MAX_ACCURACY,
    MAX_RISK_SPY,
    MIN_ACCURACY,
    MIN_RISK_SPY_PLAYER,
    spies_for_risk,
    spy_risk,
)


class TestSpyRiskMatchesTheClient:
    @pytest.mark.parametrize(
        "spies,expected",
        [(1, 34), (3, 22), (6, 5), (46, 5)],
    )
    def test_unguarded_castle_at_full_accuracy(self, spies, expected):
        assert spy_risk(spies, guards=0, accuracy=100) == expected

    def test_risk_never_drops_below_the_player_floor(self):
        assert spy_risk(1000, guards=0, accuracy=100) == MIN_RISK_SPY_PLAYER

    def test_a_dungeon_has_no_player_floor(self):
        assert spy_risk(1000, guards=0, accuracy=100, dungeon=True) == 0

    def test_risk_is_capped(self):
        assert spy_risk(1, guards=180, accuracy=100) == MAX_RISK_SPY

    def test_guards_raise_risk(self):
        unguarded = spy_risk(6, guards=0, accuracy=100)
        guarded = spy_risk(6, guards=60, accuracy=100)
        assert guarded > unguarded

    def test_lower_accuracy_lowers_risk(self):
        assert spy_risk(2, guards=0, accuracy=MIN_ACCURACY) < spy_risk(2, guards=0, accuracy=MAX_ACCURACY)

    def test_halves_round_up_like_the_client(self):
        # 46 spies against 60 guards at full accuracy averages 5 and 8 -> 6.5.
        # Math.round gives 7; Python's round() would give 6.
        assert spy_risk(46, guards=60, accuracy=100) == 7

    def test_risk_falls_as_spies_rise(self):
        risks = [spy_risk(n, guards=30, accuracy=100) for n in range(1, 20)]
        assert risks == sorted(risks, reverse=True)


class TestSpiesForRisk:
    def test_picks_the_cheapest_count_meeting_the_budget(self):
        assert spies_for_risk(guards=0, accuracy=100, max_risk=5, available=46) == 6

    def test_a_loose_budget_costs_fewer_spies(self):
        assert spies_for_risk(guards=0, accuracy=100, max_risk=34, available=46) == 1

    def test_returns_none_when_the_budget_is_unreachable(self):
        # 5% is the floor for a player castle, so 4% cannot be bought at any count.
        assert spies_for_risk(guards=0, accuracy=100, max_risk=4, available=46) is None

    def test_never_exceeds_what_is_available(self):
        chosen = spies_for_risk(guards=0, accuracy=100, max_risk=5, available=3)
        assert chosen is None, "claimed a risk budget it could not afford"

    def test_a_guarded_target_needs_more_spies(self):
        assert spies_for_risk(guards=60, accuracy=100, max_risk=20, available=200) > spies_for_risk(
            guards=0, accuracy=100, max_risk=20, available=200
        )
