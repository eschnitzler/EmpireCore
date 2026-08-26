"""Generals and player skills: the gie and skl payloads, as the client reads them."""

from empire_core.protocol.models import GetGeneralsResponse, GetSkillsResponse


class TestGenerals:
    """``GeneralsData.parse_GIE`` and ``GeneralVO.parseData``."""

    LIVE = {
        "G": [
            {"GID": 101, "XP": 2520, "ST": 2, "SIDS": [10317, 10311, 10314], "GASAIDS": [1], "W": 40, "D": 3},
            {"GID": 102, "XP": 3360, "ST": 6, "SIDS": [], "W": 2, "D": 0},
        ]
    }

    def test_the_skills_of_one_general(self):
        response = GetGeneralsResponse.model_validate(self.LIVE)

        assert [g.general_id for g in response.generals] == [101, 102]
        assert response.skill_ids(101) == [10317, 10311, 10314]

    def test_a_general_with_nothing_unlocked(self):
        assert GetGeneralsResponse.model_validate(self.LIVE).skill_ids(102) == []

    def test_an_unknown_general_is_not_an_error(self):
        # Sizing a wave must not fail because a general is missing.
        assert GetGeneralsResponse.model_validate(self.LIVE).skill_ids(999) == []

    def test_an_empty_payload(self):
        assert GetGeneralsResponse.model_validate({}).generals == []


class TestPlayerSkills:
    """``LegendSkillData.parse_SKL``: SID is legend, SIDS is sceat."""

    def test_the_two_lists_are_kept_apart(self):
        response = GetSkillsResponse.model_validate({"SID": [3, 4, 5], "SIDS": [90, 91], "SP": 40, "RS": 7200})

        assert response.legend_skill_ids == [3, 4, 5]
        assert response.sceat_skill_ids == [90, 91]
        assert response.total_points == 40
        assert response.seconds_until_reset == 7200

    def test_a_player_with_no_skills(self):
        response = GetSkillsResponse.model_validate({"SP": 0})

        assert response.legend_skill_ids == []
        assert response.sceat_skill_ids == []
