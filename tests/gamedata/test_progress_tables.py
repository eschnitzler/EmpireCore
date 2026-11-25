"""The commander and progression tables, read as the client reads them: whole real tables and edge cases."""

import json
import logging
from pathlib import Path

import pytest

from empire_core.exceptions import AmbiguousLookupError
from empire_core.gamedata import (
    Building,
    CurrencyId,
    Effect,
    GameData,
    General,
    GeneralAbility,
    GeneralAbilityEffectDef,
    GeneralSkillTierDef,
    GeneralSlotDef,
    GeneralSlotId,
    GeneralXpItemDef,
    HighscoreBonusDef,
    LeagueType,
    LevelUpDef,
    LevelUpPriceDef,
    MightRankDef,
    MightRankId,
    RewardId,
    SceatSkill,
    SceatSkillTierDef,
    Tool,
    Unit,
)

REAL = json.loads((Path(__file__).parents[1] / "data" / "progress_tables.json").read_text())
"""The tables as items v790.06 has them, with the generalAbilities they name."""

TABLES = {
    "general_slots": "generalSlots",
    "general_skill_tiers": "generalSkillTiers",
    "general_xp_items": "generalXpItems",
    "general_ability_effects": "generalAbilityEffects",
    "sceat_skill_tiers": "sceatSkillTiers",
    "level_up_prices": "levelUpPrices",
    "might_ranks": "mightranks",
}


@pytest.fixture(scope="module")
def real() -> GameData:
    return GameData.parse(REAL["version"], REAL)


class TestRealTables:
    @pytest.mark.parametrize(("table", "items_table"), TABLES.items())
    def test_every_row_reads(self, table, items_table, caplog):
        data = GameData.parse(REAL["version"], REAL)
        with caplog.at_level(logging.WARNING):
            rows = list(getattr(data, table).values())

        assert len(rows) == len(REAL[items_table])
        assert not caplog.records

    def test_the_listed_tables_keep_every_row(self, real):
        assert len(real.level_ups) == len(REAL["levelups"]) == 10
        assert len(real.highscore_bonuses) == len(REAL["highscoreboni"]) == 30

    def test_every_ability_names_its_bonuses_and_every_slot_its_abilities(self, real):
        named = {
            effect_id
            for a in real.general_abilities.values()
            for effect_id in (a.ability_attack_effect_id, a.ability_defense_effect_id)
            if effect_id
        }

        assert named == set(real.general_ability_effects)
        assert all(real.general_slot_abilities(slot) for slot in real.general_slots)

    def test_a_slot_offers_its_ability_groups_in_order(self, real):
        groups = real.general_slot_abilities(GeneralSlotId(101012))

        assert [group[0].ability_group_id for group in groups] == [1034, 1038]
        assert groups[1][0].ability_id is GeneralAbility.EXHALTED_L1

    def test_an_xp_item_by_its_currency(self, real):
        assert real.general_xp_items[CurrencyId.GENERALS_XP_250].xp == 250
        assert real.general_xp_items[CurrencyId.GENERALS_XP_15000].xp == 15000

    def test_an_ability_effect_with_two_bonuses(self, real):
        row = real.general_ability_effects[101910]

        assert [(e.effect_id, e.value) for e in row.effects] == [
            (Effect.MIND_CLARITY_EVEN_WAVE, 50),
            (Effect.MIND_CLARITY_ODD_WAVE, 50),
        ]
        assert row.priority == 19

    def test_a_general_skill_tier(self, real):
        tier = real.general_skill_tier(General.HORATIO, 5)

        assert tier is not None
        assert (tier.tier_id, tier.required_skill_points, tier.min_star_level) == (17, 90, 10)
        assert tier.has_requirement and not tier.is_hidden

    def test_a_sceat_skill_tier(self, real):
        tier = real.sceat_skill_tier(3, 3)

        assert tier is not None
        assert tier.required_buildings == (Building.RELIC_BEEKEEPER_L1, Building.STOREHOUSE_L8_1943, 1959)
        assert tier.requires_previous_tier and not tier.any_required_building

    def test_the_level_up_rewards(self, real):
        assert real.level_up(9) == LevelUpDef(min_level=1, max_level=70, reward_id=RewardId(447))
        skip_group = real.level_up(9, skip_group=True)
        assert skip_group is not None and skip_group.reward_id == 765
        legendary = real.level_up(950, legendary=True)
        assert legendary is not None and legendary.is_legendary
        assert real.level_up(71) is None

    def test_the_level_prices(self, real):
        assert real.level_up_cost(10, 11) == 490
        assert real.level_up_cost(10, 12) == 0

    def test_the_might_ranks(self, real):
        assert real.might_rank(500) is None
        rank = real.might_rank(501)
        assert rank is not None and (rank.might_rank_id, rank.reward_id) == (1, 8512)
        upcoming = real.next_might_rank(500)
        assert upcoming is not None and upcoming.threshold == 1000
        assert real.next_might_rank(20_000_000) is None

    def test_a_weekly_honour_reward(self, real):
        bonus = real.highscore_bonus(LeagueType.LEVELS_1_19, 120)

        assert bonus is not None
        assert [(u.unit, u.amount) for u in bonus.units] == [
            (Unit.ELITE_RANKREWARDMELEE, 50),
            (Unit.ELITE_RANKREWARDRANGE, 50),
        ]
        assert bonus.tool is Tool.ELITESHIELDS
        bottom = real.highscore_bonus(LeagueType.LEVELS_1_19, 100_000)
        assert bottom is not None and (bottom.coins, bottom.lowest_rank) == (7500, 0)

    def test_the_listed_tables_survive_the_cache(self, real, tmp_path):
        real._write_cache(tmp_path / "cache.json")

        again = GameData._read_cache(tmp_path / "cache.json", REAL["version"])

        assert again is not None
        assert again.level_ups == real.level_ups
        assert again.highscore_bonuses == real.highscore_bonuses
        assert again.might_ranks == real.might_ranks


class TestGeneralRows:
    def test_a_slot_without_columns(self):
        assert GeneralSlotDef.model_validate({}) == GeneralSlotDef(slot_id=GeneralSlotId(0), ability_group_ids=())

    def test_a_group_without_abilities_is_left_out(self):
        data = GameData.parse(
            "test",
            {
                "generalSlots": [{"slotID": "5", "abilityGroupIDs": "7,,x,8"}],
                "generalAbilities": [{"abilityID": "70", "abilityGroupID": "7", "level": "1"}],
            },
        )

        assert data.general_slots[5].ability_group_ids == (7, 8)
        assert [[a.ability_id for a in group] for group in data.general_slot_abilities(GeneralSlotId(5))] == [[70]]
        assert data.general_slot_abilities(GeneralSlotId(6)) == ()

    def test_a_skill_tier_reads_the_client_defaults(self):
        tier = GeneralSkillTierDef.model_validate({"tierID": "1"})

        assert (tier.general_id, tier.tier, tier.required_skill_points, tier.min_star_level) == (-1, -1, -1, -1)
        assert not tier.is_hidden and not tier.has_requirement

    @pytest.mark.parametrize(("hidden", "expected"), [("1", True), ("01", True), ("2", False), ("x", False)])
    def test_a_hidden_tier_is_parse_int_one(self, hidden, expected):
        assert GeneralSkillTierDef.model_validate({"tierID": "1", "hidden": hidden}).is_hidden is expected

    def test_an_unreadable_star_level_is_none(self):
        assert GeneralSkillTierDef.model_validate({"tierID": "1", "minGeneralStarTier": "x"}).min_star_level is None

    def test_a_tier_without_points_has_no_requirement(self):
        row = {"tierID": "1", "generalID": "101", "tier": "2", "previousTierRequiredSkillPoints": "0"}

        assert not GeneralSkillTierDef.model_validate(row).has_requirement

    def test_two_rows_for_one_tier_are_ambiguous(self):
        row = {"generalID": "101", "tier": "2"}
        data = GameData.parse("test", {"generalSkillTiers": [{"tierID": "1", **row}, {"tierID": "2", **row}]})

        with pytest.raises(AmbiguousLookupError):
            data.general_skill_tier(General.TORIL, 2)

    def test_an_xp_item_without_columns(self):
        assert GeneralXpItemDef.model_validate({}) == GeneralXpItemDef(currency_id=0, xp=0)

    def test_the_effect_column_comes_before_effects(self):
        data = GameData.parse(
            "test",
            {
                "generalAbilityEffects": [
                    {"abilityEffectID": "1", "effect": "21019&5", "effects": "21040&9"},
                    {"abilityEffectID": "2", "effect": "", "effects": "21040&9"},
                ]
            },
        )

        assert [e.effect_id for e in data.general_ability_effects[1].effects] == [Effect.MIND_CLARITY_EVEN_WAVE]
        assert [e.effect_id for e in data.general_ability_effects[2].effects] == [Effect.MIND_CLARITY_ODD_WAVE]

    def test_an_ability_effect_without_columns(self):
        row = GeneralAbilityEffectDef.model_validate({})

        assert (row.ability_effect_id, row.priority, row.effects) == (0, 0, ())


class TestSceatSkillTiers:
    def test_the_client_defaults(self):
        tier = SceatSkillTierDef.model_validate({"tierID": "9"})

        assert (tier.skill_tree_id, tier.tier, tier.required_legendary_level) == (-1, -1, 0)
        assert tier.requires_previous_tier
        assert tier.required_buildings == tier.required_skills == ()

    @pytest.mark.parametrize(("value", "expected"), [("0", False), ("1", True), ("x", False), ("", True)])
    def test_the_previous_tier_is_required_unless_told(self, value, expected):
        row = {"tierID": "9", "requirePreviousTierUnlocked": value}

        assert SceatSkillTierDef.model_validate(row).requires_previous_tier is expected

    def test_the_requirements(self):
        tier = SceatSkillTierDef.model_validate(
            {
                "tierID": "9",
                "requiredBuildings": "0,1942,,-3",
                "requiredBuildingsCondition": "or",
                "requiredSkillIDs": "91,92",
                "requiredLegendLevel": "20",
            }
        )

        assert tier.required_buildings == (1942,)
        assert tier.any_required_building
        assert tier.required_skills == (SceatSkill(91), SceatSkill(92))
        assert tier.required_legendary_level == 20


class TestLevelUps:
    @pytest.mark.parametrize(("value", "expected"), [("1", True), ("01", False), ("0", False), (1, True)])
    def test_legendary_is_the_text_one(self, value, expected):
        assert LevelUpDef.model_validate({"isLegend": value}).is_legendary is expected

    def test_unreadable_levels_hold_nothing(self):
        row = LevelUpDef.model_validate({"minLevel": "x", "rewardID": "7"})

        assert (row.min_level, row.max_level, row.reward_id) == (None, None, 7)
        assert not row.holds(1)

    def test_the_first_row_that_holds_the_level(self):
        data = GameData.parse(
            "test",
            {
                "levelups": [
                    {"minLevel": 1, "maxLevel": "10", "rewardID": "1"},
                    {"minLevel": 5, "maxLevel": "10", "rewardID": "2"},
                    {"minLevel": 1, "maxLevel": "10", "rewardID": "3", "abTest": "other"},
                ]
            },
        )

        assert [data.level_up(level) for level in (5, 11)] == [data.level_ups[0], None]
        assert data.level_up(5, skip_group=True) is None

    def test_a_price_without_a_cost_is_unreadable(self):
        data = GameData.parse("test", {"levelUpPrices": [{"levelUpPriceID": "1", "fromLevel": "9", "toLevel": "10"}]})

        assert data.level_up_cost(9, 10) is None
        assert LevelUpPriceDef.model_validate({"levelUpPriceID": "1"}).cost_rubies is None


class TestMightRanks:
    def test_the_thresholds_are_strict(self):
        data = GameData.parse(
            "test",
            {
                "mightranks": [
                    {"mightID": "2", "threshold": "200"},
                    {"mightID": "1", "threshold": "100"},
                    {"mightID": "3", "threshold": "x"},
                ]
            },
        )

        assert data.might_rank(100) is None
        assert [data.might_rank(m) for m in (101, 201)] == [data.might_ranks[1], data.might_ranks[2]]
        assert [data.next_might_rank(m) for m in (99, 100)] == [data.might_ranks[1], data.might_ranks[2]]

    def test_a_rank_without_columns(self):
        assert MightRankDef.model_validate({}) == MightRankDef(
            might_rank_id=MightRankId(0), threshold=0, reward_id=RewardId(0)
        )


class TestHighscoreBonuses:
    def test_an_unbounded_band(self):
        bonus = HighscoreBonusDef.model_validate({"leaguetypeID": "1", "highestRank": "201", "c1Reward": "7500"})

        assert bonus.lowest_rank == 0
        assert bonus.holds(10**9) and not bonus.holds(200)

    def test_units_need_an_id_above_zero_and_a_tool_too(self):
        bonus = HighscoreBonusDef.model_validate({"unitReward": "0+5#9+x#10+7", "toolReward": "0"})

        assert [(u.unit, u.amount) for u in bonus.units] == [(9, None), (10, 7)]
        assert bonus.tool is None

    def test_a_row_without_columns(self):
        bonus = HighscoreBonusDef.model_validate({})

        assert (bonus.league_type_id, bonus.highest_rank, bonus.lowest_rank) == (-1, 0, 0)

    def test_an_unreadable_best_rank_holds_nothing_and_prices_nothing(self):
        bonus = HighscoreBonusDef.model_validate(
            {"highestRank": "x", "c1Reward": "7500", "minAmount": "10", "unitReward": "9+50"}
        )

        assert bonus.highest_rank is None
        assert not bonus.holds(1)
        assert bonus.coins_at(1, 30) == bonus.unit_amount(bonus.units[0], 1) == 0

    # Expected amounts from HighscoreBonusConst (dll line 237) run in node.
    @pytest.mark.parametrize(
        ("rank", "level", "expected"), [(500, 30, 4510), (201, 70, 7500), (1200, 5, 60), (5000, 1, 10)]
    )
    def test_the_coins(self, rank, level, expected):
        bonus = HighscoreBonusDef.model_validate({"highestRank": "201", "c1Reward": "7500", "minAmount": "10"})

        assert bonus.coins_at(rank, level) == expected

    @pytest.mark.parametrize(
        ("amount", "highest", "rank", "minimum", "expected"),
        [(50, 101, 120, 260, 260), (500, 1, 1, 10, 500), (500, 1, 50, 10, 255), (125, 1, 2, 10, 124)],
    )
    def test_the_units(self, amount, highest, rank, minimum, expected):
        bonus = HighscoreBonusDef.model_validate(
            {"highestRank": str(highest), "minAmount": str(minimum), "unitReward": f"9+{amount}"}
        )

        assert bonus.unit_amount(bonus.units[0], rank) == expected

    @pytest.mark.parametrize(
        ("minimum", "offset", "rank", "expected"),
        [(50, 151, 120, 50), (5, 1, 1, 5), (5, 401, 100, 150), (5, 402, 100, 151)],
    )
    def test_the_tools(self, minimum, offset, rank, expected):
        bonus = HighscoreBonusDef.model_validate({"toolMinAmount": str(minimum), "toolOffset": str(offset)})

        assert bonus.tool_amount(rank) == expected

    def test_nan_amounts_read_as_zero(self):
        bonus = HighscoreBonusDef.model_validate({"unitReward": "9+x", "minAmount": "10", "c1Reward": "0"})

        assert bonus.unit_amount(bonus.units[0], 1) == 0
        assert bonus.coins_at(1, -5) == 10

    def test_the_first_band_of_the_league(self):
        data = GameData.parse(
            "test",
            {
                "highscoreboni": [
                    {"leaguetypeID": "2", "highestRank": "1", "lowestRank": "50"},
                    {"leaguetypeID": "1", "highestRank": "1", "lowestRank": "50", "c1Reward": "1"},
                    {"leaguetypeID": "1", "highestRank": "1", "c1Reward": "2"},
                ]
            },
        )

        assert [data.highscore_bonus(1, rank) for rank in (10, 60)] == data.highscore_bonuses[1:]
        assert data.highscore_bonus(3, 1) is None
