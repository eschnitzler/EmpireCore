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
    plan_mission,
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


class TestPlanMission:
    """Missions run at the best risk the pool allows, for the fewest spies."""

    def test_unguarded_castle_reaches_the_floor_without_draining_the_pool(self):
        plan = plan_mission(guards=0, available=46)

        assert plan is not None
        assert (plan.spies, plan.risk) == (6, MIN_RISK_SPY_PLAYER)

    def test_extra_spies_are_left_for_other_targets(self):
        # 46 spies and 6 spies buy exactly the same 5%.
        full_pool = plan_mission(guards=0, available=46)
        just_enough = plan_mission(guards=0, available=6)

        assert full_pool is not None and just_enough is not None
        assert full_pool.spies == just_enough.spies

    def test_a_guarded_target_costs_more_but_still_not_everything(self):
        plan = plan_mission(guards=60, available=46)

        assert plan is not None
        assert plan.risk == 7, "not the best risk this pool can reach"
        assert plan.spies < 46, "drained the pool for no reduction in risk"

    def test_a_thin_pool_settles_for_the_best_it_can_do(self):
        plan = plan_mission(guards=0, available=3)

        assert plan is not None
        assert (plan.spies, plan.risk) == (3, 22)

    def test_a_target_over_the_ceiling_is_skipped(self):
        # A single spy against a fully guarded castle stays above the ceiling at
        # every accuracy the game allows, so there is no mission to send.
        assert plan_mission(guards=180, available=1, max_risk=10) is None

    def test_the_ceiling_does_not_make_missions_riskier(self):
        # A loose ceiling must not buy a cheaper, riskier mission.
        plan = plan_mission(guards=0, available=46, max_risk=90)

        assert plan is not None
        assert plan.risk == MIN_RISK_SPY_PLAYER

    def test_accuracy_is_traded_down_to_meet_the_ceiling(self):
        """The game lowers accuracy rather than refusing the mission.

        A guarded castle sits at 7% with 46 spies at full accuracy, which a 5%
        ceiling rejects — but the same spies at lower accuracy reach 5%, which
        is the risk the game's own dialog shows.
        """
        plan = plan_mission(guards=60, available=46, max_risk=MIN_RISK_SPY_PLAYER)

        assert plan is not None, "refused a mission the game would allow"
        assert plan.risk <= MIN_RISK_SPY_PLAYER
        assert plan.accuracy < MAX_ACCURACY, "accuracy was never traded down"

    def test_full_accuracy_is_kept_when_it_already_fits(self):
        plan = plan_mission(guards=0, available=46, max_risk=MIN_RISK_SPY_PLAYER)

        assert plan is not None
        assert plan.accuracy == MAX_ACCURACY, "gave up report detail for nothing"

    def test_accuracy_never_drops_below_the_games_minimum(self):
        # Nothing can spy a fully guarded castle with two spies at 5%.
        plan = plan_mission(guards=180, available=2, max_risk=MIN_RISK_SPY_PLAYER)

        assert plan is None

    def test_the_most_accurate_report_within_budget_is_chosen(self):
        loose = plan_mission(guards=60, available=46, max_risk=40)
        tight = plan_mission(guards=60, available=46, max_risk=MIN_RISK_SPY_PLAYER)

        assert loose is not None and tight is not None
        assert loose.accuracy >= tight.accuracy, "a looser ceiling bought less detail"

    def test_an_empty_pool_has_no_plan(self):
        assert plan_mission(guards=0, available=0) is None
