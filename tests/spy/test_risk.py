"""The client-side espionage risk model, ported from the game's own code.

Constants and formula are lifted verbatim from SpyConst in the live client
bundle (ggs.dll), so these tests pin our port against it rather than against
anything invented here.
"""

import pytest

from empire_core.spy.risk import (
    MAX_ACCURACY,
    MAX_RISK_SPY,
    MIN_ACCURACY,
    MIN_RISK_SPY_PLAYER,
    max_damaged_buildings,
    max_sabotage_damage,
    plan_mission,
    plan_sabotage,
    risk_target_flags,
    row_risk_flags,
    sabotage_risk,
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


class TestTheLiveCampRisk:
    def test_the_server_costed_the_live_camp_without_the_player_floor(self):
        # The live csm reply for 2 spies at accuracy 100 against an unguarded camp said SR 26:
        # getSpyRisk gives 26 with the dungeon floor and 28 with the player floor.
        assert spy_risk(2, guards=0, accuracy=100, dungeon=True) == 26
        assert spy_risk(2, guards=0, accuracy=100) == 28

    @pytest.mark.parametrize(
        "spies,dungeon_risk,player_risk",
        # SpyConst.getSpyRisk(s, 0, 100, isDungeon, true) run in node
        [(1, 32, 34), (3, 20, 22), (5, 8, 10), (6, 2, 5), (7, 0, 5), (10, 0, 5)],
    )
    def test_both_floors_match_the_client(self, spies, dungeon_risk, player_risk):
        assert spy_risk(spies, 0, 100, dungeon=True) == dungeon_risk
        assert spy_risk(spies, 0, 100) == player_risk

    def test_a_non_player_target_has_no_floor(self):
        # SpyConst.getSpyRisk(6, 0, 100, false, false) == 2
        assert spy_risk(6, 0, 100, player_target=False) == 2


class TestRiskTargetFlags:
    """CastleStartSpyVO.setSpyValues: (isDungeon, isPlayer)."""

    @pytest.mark.parametrize(
        "owner_id,area_type,flags",
        [
            (1001, 1, (False, True)),  # a player's castle
            (1001, 4, (False, True)),  # a player's outpost
            (-300, 4, (True, False)),  # an unclaimed outpost
            (-300, 3, (True, False)),  # capitals are outposts
            (-300, 22, (True, False)),  # and so are metropolises
            (-212, 2, (True, True)),  # a robber baron
            (-1000, 21, (False, True)),  # an alien invasion fights like a player
            (-1002, 34, (False, True)),
            (-1103, 2, (False, True)),  # a collector
            (-1108, 2, (True, True)),  # a collector isCollectorPlayer leaves out
        ],
    )
    def test_flags(self, owner_id, area_type, flags):
        assert risk_target_flags(owner_id, area_type) == flags

    @pytest.mark.parametrize(
        "row,flags",
        [
            ([2, 1, 2, -1, 0, -1, 0], (True, True)),  # robber baron: a dungeon NPC
            ([21, 1, 2, -1, 0, -1, 0], (False, True)),  # alien camp: -1000
            ([27, 1, 2, 0, 3, 0, 0, 0, 1, 0, 0, 0], (True, True)),  # nomad camp: -601
            ([29, 1, 2, 0, 3, 0, 0, 0, 1, 0, 0, 0], (True, True)),  # samurai camp: -651
            ([1, 1, 2, 2001, 1001, 2, 2, 2, 1, 0, "Keep"], (False, True)),
            ([4, 1, 2, -300, -300, 1, 1, 1, 0, 0, ""], (True, False)),
        ],
    )
    def test_row_flags(self, row, flags):
        assert row_risk_flags(row) == flags

    @pytest.mark.parametrize("row", [None, [], [8, 1, 2, 0, 0], [27, 1, 2], ["x", 1, 2, 0]])
    def test_an_owner_not_traced_is_none(self, row):
        assert row_risk_flags(row) is None


class TestSabotageRisk:
    @pytest.mark.parametrize(
        "spies,guards,damage,expected",
        # SpyConst.getSabotageRisk run in node
        [
            (1, 0, 10, 14),
            (1, 0, 50, 34),
            (5, 0, 10, 10),
            (5, 60, 30, 50),
            (10, 180, 50, 90),
            (15, 180, 10, 30),
            (3, 24, 20, 27),
            (20, 0, 50, 10),
            (2, 13, 25, 29),
        ],
    )
    def test_matches_the_client(self, spies, guards, damage, expected):
        assert sabotage_risk(spies, guards, damage) == expected

    def test_needs_a_spy(self):
        with pytest.raises(ValueError):
            sabotage_risk(0, 0, 10)

    @pytest.mark.parametrize(
        "level,buildings",
        # CombatConst.getMaxDamagedBuildings run in node
        [(0, 0), (9, 0), (10, 1), (14, 1), (15, 2), (18, 3), (19, 4), (21, 5), (30, 32), (40, 231)],
    )
    def test_damaged_buildings_match_the_client(self, level, buildings):
        assert max_damaged_buildings(level) == buildings

    @pytest.mark.parametrize("level,damage", [(9, 0), (10, 10), (15, 20), (18, 30), (20, 40), (21, 50), (70, 50)])
    def test_the_damage_cap(self, level, damage):
        assert max_sabotage_damage(level) == damage


class TestPlanSabotage:
    def test_fewest_spies_for_the_pools_risk(self):
        # getSabotageRisk(s, 30, 30) is 11 at 10 and 11 spies and 10 at 12
        plan = plan_sabotage(guards=30, available=12, damage=30)

        assert plan is not None
        assert (plan.spies, plan.risk, plan.damage) == (12, 10, 30)

    def test_extra_spies_are_left(self):
        plan = plan_sabotage(guards=30, available=11, damage=30)

        assert plan is not None
        assert (plan.spies, plan.risk) == (10, 11)

    def test_over_the_ceiling_is_none(self):
        assert plan_sabotage(guards=30, available=3, damage=30, max_risk=20) is None

    @pytest.mark.parametrize("damage", [9, 51])
    def test_damage_outside_the_slider_is_refused(self, damage):
        with pytest.raises(ValueError):
            plan_sabotage(guards=0, available=5, damage=damage)
