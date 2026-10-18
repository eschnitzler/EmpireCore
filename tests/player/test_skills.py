"""Spending and resetting legend skill points: skp and skr, applied to the kept skill list as the client does."""

import pytest

from empire_core.commanders import AddSkillPointRequest, AddSkillPointResponse, ResetSkillsRequest
from empire_core.enums import GGEError
from empire_core.exceptions import CommandError
from empire_core.gamedata import GameData, LegendSkill, LegendSkillDef
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

# Tree 0, group 1 (gateReduction) levels 1-3 of items 787.03
ROWS = [
    {"skillID": "1", "followingSkillID": "2", "level": "1", "skillTreeID": "0", "tier": "1", "skillGroupID": "1",
     "totalCostSkillPoints": "3", "costSkillPoints": "3", "effectType": "gateReduction"},
    {"skillID": "2", "requiredSkillID": "1", "followingSkillID": "3", "level": "2", "skillTreeID": "0", "tier": "1",
     "skillGroupID": "1", "totalCostSkillPoints": "6", "costSkillPoints": "3", "effectType": "gateReduction"},
    {"skillID": "3", "requiredSkillID": "2", "level": "3", "skillTreeID": "0", "tier": "1", "skillGroupID": "1",
     "totalCostSkillPoints": "9", "costSkillPoints": "3", "effectType": "gateReduction"},
]  # fmt: skip
L1, L2, L3 = (
    LegendSkill.GATE_REDUCTION_T0_G1_L1,
    LegendSkill.GATE_REDUCTION_T0_G1_L2,
    LegendSkill.GATE_REDUCTION_T0_G1_L3,
)


def _client(skl: dict, script: dict | None = None):
    client = make_client(script, state=logged_in_state(skl=skl))  # type: ignore[arg-type]
    conn(client).on_packet = client._on_packet
    client.game_data = GameData.parse("test", {"legendskills": ROWS})
    return client


class TestLegendSkillDef:
    """``CastleLegendSkillVO.parseXML`` (bundle line 48652)."""

    def test_a_level_names_its_neighbours_and_cost(self):
        first, second, last = (LegendSkillDef.model_validate(row) for row in ROWS)

        assert (first.cost_skill_points, first.required_skill_id, first.previous_skill_id) == (3, None, None)
        assert first.following_skill_id is L2 and not first.is_max_level
        assert second.required_skill_id is L1 and second.previous_skill_id is L1
        assert last.following_skill_id is None and last.is_max_level

    def test_an_explicit_previous_skill_wins_over_the_required_one(self):
        row = LegendSkillDef.model_validate({**ROWS[2], "previousSkillID": "1"})

        assert (row.required_skill_id, row.previous_skill_id) == (L2, L1)

    def test_zero_is_no_skill(self):
        row = LegendSkillDef.model_validate({**ROWS[1], "requiredSkillID": "0", "followingSkillID": "0"})

        assert (row.required_skill_id, row.previous_skill_id, row.following_skill_id) == (None, None, None)


class TestPoints:
    def test_available_points_are_the_total_less_the_held_levels_cost(self):
        client = _client({"SID": [2], "SP": 10, "RS": 0, "RC": 0})
        skills = client.player.skills
        assert skills is not None

        assert skills.spent_points(client.game_data) == 6
        assert skills.available_points(client.game_data) == 4


class TestAddSkillPoint:
    def test_the_wire_shapes(self):
        assert AddSkillPointRequest(skill=L2).to_payload() == {"ID": 2}
        assert AddSkillPointResponse.model_validate({"IDS": [2, "3"]}).skill_ids == (L2, L3)
        assert AddSkillPointResponse.model_validate({}).skill_ids == ()

    def test_the_next_level_replaces_the_one_before_it(self):
        client = _client({"SID": [1], "SP": 10, "RS": 0, "RC": 0}, {"skp": xt_packet("skp", {"IDS": [2]})})

        added = client.player.add_legend_skill_point(L2)

        assert conn(client).request_payloads == [("skp", {"ID": 2})]
        assert added.skill_ids == (L2,)
        skills = client.player.skills
        assert skills is not None and skills.legend_skill_ids == (L2,)
        assert skills.available_points(client.game_data) == 4

    def test_a_first_level_is_added(self):
        client = _client({"SID": [], "SP": 10, "RS": 0, "RC": 0}, {"skp": xt_packet("skp", {"IDS": [1]})})

        client.player.add_legend_skill_point(L1)

        skills = client.player.skills
        assert skills is not None and skills.legend_skill_ids == (L1,)

    def test_a_refusal_raises_and_keeps_the_list(self):
        refused = xt_packet("skp", {}, error_code=GGEError.ADD_LEGEND_SKILL_NOT_ENOUGH_SKILL_POINTS)
        client = _client({"SID": [1], "SP": 3, "RS": 0, "RC": 0}, {"skp": refused})

        with pytest.raises(CommandError) as raised:
            client.player.add_legend_skill_point(L2)

        assert raised.value.error is GGEError.ADD_LEGEND_SKILL_NOT_ENOUGH_SKILL_POINTS
        skills = client.player.skills
        assert skills is not None and skills.legend_skill_ids == (L1,)


class TestResetSkills:
    def test_the_request_has_no_fields(self):
        assert ResetSkillsRequest().to_payload() == {}

    def test_a_reset_off_cooldown_is_free_and_refreshes_the_list(self):
        held = xt_packet("skl", {"SID": [2], "SP": 10, "RS": 0, "RC": 1})
        cleared = xt_packet("skl", {"SID": [], "SP": 10, "RS": 1296000, "RC": 2})
        client = _client({"SID": [2], "SP": 10, "RS": 0, "RC": 1}, {"skl": [held, cleared]})

        skills = client.player.reset_skills()

        assert [command for command, _ in conn(client).request_payloads] == ["skl", "skr", "skl"]
        assert skills.legend_skill_ids == () and skills.reset_count == 2
        kept = client.player.skills
        assert kept is not None and kept.legend_skill_ids == ()

    def test_a_reset_on_cooldown_needs_consent_for_its_rubies(self):
        held = xt_packet("skl", {"SID": [2], "SP": 10, "RS": 600, "RC": 1})
        client = _client({"SID": [2], "SP": 10, "RS": 600, "RC": 1}, {"skl": held})

        # LegendSkillConst.resetSkipCostC2: 20 * 1**5 + (6 + 50) * 30
        with pytest.raises(ValueError, match="1700 rubies"):
            client.player.reset_skills()

        assert [command for command, _ in conn(client).request_payloads] == ["skl"]

    def test_the_price_grows_with_the_resets(self):
        held = xt_packet("skl", {"SID": [], "SP": 10, "RS": 600, "RC": 3})
        client = _client({"SID": [], "SP": 10, "RS": 600, "RC": 3}, {"skl": held})

        with pytest.raises(ValueError, match=f"{20 * 3**5 + 50 * 30} rubies"):
            client.player.reset_skills()

    def test_consent_skips_the_price_and_resets(self):
        cleared = xt_packet("skl", {"SID": [], "SP": 10, "RS": 1296000, "RC": 2})
        client = _client({"SID": [2], "SP": 10, "RS": 600, "RC": 1}, {"skl": cleared})

        client.player.reset_skills(spend_rubies=True)

        assert [command for command, _ in conn(client).request_payloads] == ["skr", "skl"]
