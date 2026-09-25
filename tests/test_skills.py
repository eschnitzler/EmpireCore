"""Generals and player skills: the gie and skl payloads, as the client reads them."""

import pytest

from empire_core.gamedata import GeneralDef
from empire_core.protocol.models import General, GetGeneralsResponse, GetSkillsResponse

# The generals row for general 103 in items v786.03.
GENERAL_103 = GeneralDef.model_validate(
    {
        "generalID": "103",
        "attackSlots": "101032,101031,101033",
        "defenseSlots": "101037,101036,101038",
        "generalRarityID": "4",
        "maxLevel": "100",
        "maxStarLevel": "10",
    }
)


class TestGenerals:
    """``GeneralsData.parse_GIE`` and ``GeneralVO.parseData``."""

    LIVE = {
        "G": [
            # GASAIDS arrives as [slot, ability] pairs; a live payload rejected
            # a list[int] model outright.
            {
                "GID": 101,
                "XP": 2520,
                "ST": 2,
                "SIDS": [10317, 10311, 10314],
                "GASAIDS": [[101031, 10073], [101033, 10303], [101032, 10263]],
                "W": 40,
                "D": 3,
            },
            {"GID": 102, "XP": 3360, "ST": 6, "SIDS": [], "W": 2, "D": 0},
        ]
    }

    def test_the_skills_of_one_general(self):
        response = GetGeneralsResponse.model_validate(self.LIVE)

        assert [g.general_id for g in response.generals] == [101, 102]
        assert response.skill_ids(101) == [10317, 10311, 10314]

    def test_the_selected_abilities_are_pairs(self):
        general = GetGeneralsResponse.model_validate(self.LIVE).generals[0]

        assert general.ability_ids == [10073, 10303, 10263]
        assert (general.selected_abilities[0].slot_id, general.selected_abilities[0].ability_id) == (101031, 10073)

    def test_an_empty_slot_is_not_a_selected_ability(self):
        general = GetGeneralsResponse.model_validate(
            {"G": [{"GID": 101, "GASAIDS": [[101031, -1], [101033, 10303]]}]}
        ).generals[0]

        assert len(general.selected_abilities) == 2
        assert general.ability_ids == [10303]

    def test_a_malformed_slot_is_skipped(self):
        general = GetGeneralsResponse.model_validate(
            {"G": [{"GID": 101, "GASAIDS": [10073, [101031], ["x", "y"], [101033, 10303]]}]}
        ).generals[0]

        assert general.ability_ids == [10303]

    def test_a_general_with_nothing_unlocked(self):
        assert GetGeneralsResponse.model_validate(self.LIVE).skill_ids(102) == []

    def test_an_unknown_general_is_not_an_error(self):
        # Sizing a wave must not fail because a general is missing.
        assert GetGeneralsResponse.model_validate(self.LIVE).skill_ids(999) == []

    def test_an_empty_payload(self):
        assert GetGeneralsResponse.model_validate({}).generals == []

    # Expected values below come from running GeneralVO.parseData and
    # getSelectedAbilities from the client bundle in node.

    def test_the_abilities_of_each_side(self):
        general = General.model_validate(
            {
                "GID": 103,
                "GASAIDS": [
                    [101031, 10073],
                    [101033, -1],
                    [101037, 10303],
                    [101036, 0],
                    [101011, 10263],
                    [101032, 10111],
                ],
            }
        )

        assert general.attack_ability_ids(GENERAL_103) == [10073, 10111]
        assert general.defense_ability_ids(GENERAL_103) == [10303]
        assert general.ability_ids == [10073, 10303, 10263, 10111]

    @pytest.mark.parametrize(
        ("data", "star_level", "fixed_level"),
        [
            ({"L": 20}, 1, 20),
            ({"L": 30, "ST": 0}, 2, 30),
            ({"L": 30, "ST": 4}, 4, 30),
            ({"L": 0}, 0, -1),
            ({}, 0, -1),
        ],
    )
    def test_the_star_level_falls_back_on_the_fixed_level(self, data, star_level, fixed_level):
        general = General.model_validate({"GID": 103, **data})

        assert (general.star_level, general.fixed_level) == (star_level, fixed_level)

    def test_no_star_level_from_a_fixed_level_the_client_reads_as_nan(self):
        # The client's other branch reads a getter-less property and gets NaN.
        assert General.model_validate({"GID": 103, "L": 15}).star_level == 0

    def test_the_flags_and_the_old_xp(self):
        general = General.model_validate({"GID": 103, "IN": 1, "LU": "1", "OXP": 2400})

        assert (general.is_new, general.has_level_up, general.old_experience) == (True, True, 2400)

    def test_a_flag_other_than_1_is_off(self):
        general = General.model_validate({"GID": 103, "IN": 0, "LU": 2})

        assert (general.is_new, general.has_level_up, general.old_experience) == (False, False, 0)


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
