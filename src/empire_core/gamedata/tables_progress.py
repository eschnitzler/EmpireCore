"""
Typed rows of the commander and progression tables: the generals' ability slots, skill tiers, xp items and ability
effects, the sceat skill tiers, the level-up rewards and prices, the might ranks and the weekly honour rewards.

Each model reads the columns its client value object reads, with the same defaults.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, NewType

from pydantic import Field, field_validator, model_validator

from empire_core.protocol.js import js_int, js_int32, js_loose_equals, js_parse_int, js_round, js_truthy

from .lenient import GameDataId
from .models import (
    EffectSpecRow,
    GeneralAbilityEffectId,
    GeneralSlotId,
    _id_list,
    _landmark_int,
    _parse_int_or_default,
    _Row,
    parse_ids,
)
from .tables import RewardId

if TYPE_CHECKING:
    from .ids import Building, CurrencyId, General, LeagueType, SceatSkill, Tool, Unit


GeneralSkillTierId = NewType("GeneralSkillTierId", int)
"""The id of a ``generalSkillTiers`` row, which :attr:`GameData.general_skill_tiers` describes.

The client finds a tier by its general and tier number (:meth:`GameData.general_skill_tier`); this type marks the
row's own id.
"""

SceatSkillTierId = NewType("SceatSkillTierId", int)
"""The id of a ``sceatSkillTiers`` row, which :attr:`GameData.sceat_skill_tiers` describes.

The client finds a tier by its tree and tier number (:meth:`GameData.sceat_skill_tier`); this type marks the row's
own id.
"""

LevelUpPriceId = NewType("LevelUpPriceId", int)
"""The id of a ``levelUpPrices`` row, which :attr:`GameData.level_up_prices` describes.

The client finds a price by its levels (:meth:`GameData.level_up_cost`); this type marks the row's own id.
"""

MightRankId = NewType("MightRankId", int)
"""The id of a ``mightranks`` row, a might rank that :attr:`GameData.might_ranks` describes.

The rows have no name, so no generated enum names them; this type marks the id space instead.
"""

SKIP_GROUP = "inSkipGroup"
"""The ``abTest`` of a level-up row for the split-run skip group.

Client: ``SplitRunConst.SKIP_GROUP_PARAM`` (dll line 237)
"""


def _int_or_zero(value: object) -> int:
    return _parse_int_or_default(value, 0)


def _int_or_minus_one(value: object) -> int:
    return _parse_int_or_default(value, -1)


def _int_or_nan(value: object) -> int | None:
    """``parseInt(value || "")``: None where the client reads NaN."""
    return _landmark_int(value, "")


class GeneralSlotDef(_Row):
    """
    A general's ability slot and the ability groups it offers.

    A general's ``attack_slots`` and ``defense_slots`` name these rows; :meth:`GameData.general_slot_abilities` gives a
    slot's abilities.

    Client: ``GeneralGeneralSlotXmlVO.fillFromParamXml`` (split.js line 581073), keyed by ``slotID`` in
    ``GeneralsData.init`` (split.js line 580426)
    """

    slot_id: GeneralSlotId = Field(validation_alias="slotID", default=GeneralSlotId(0), description="The slot")
    ability_group_ids: tuple[int, ...] = Field(
        validation_alias="abilityGroupIDs",
        default=(),
        description="The ability groups it offers, each a GeneralAbilityDef.ability_group_id",
    )

    _slot_id = field_validator("slot_id", mode="before")(_int_or_zero)

    @field_validator("ability_group_ids", mode="before")
    @classmethod
    def _groups(cls, value: object) -> object:
        return _id_list(value)


class GeneralSkillTierDef(_Row):
    """
    A tier of a general's skill tree and the skill points and star level that unlock it.

    Client: ``GeneralsData.init`` (split.js line 580466) reads the rows without their ``tierID`` and adds the
    requirement to the general's tier when :attr:`has_requirement`;
    ``GeneralUnlockRequirementSpentPointsInTier.isUnlocked`` (split.js line 581781) compares the points with
    ``GeneralsData.getSkillPointsSpent``, every point the general's unlocked skills cost
    """

    tier_id: GeneralSkillTierId = Field(validation_alias="tierID", description="The row")
    general_id: GameDataId["General"] = Field(
        validation_alias="generalID", default=-1, description="The general whose tree it is; -1 for none"
    )
    tier: int = Field(default=-1, description="The tier, from 1; -1 for none")
    is_hidden: bool = Field(
        validation_alias="hidden",
        default=False,
        description="The tier is hidden, which marks the general's tree as incomplete",
    )
    required_skill_points: int = Field(
        validation_alias="previousTierRequiredSkillPoints",
        default=-1,
        description="Skill points spent on the general's skills that unlock it; -1 for none",
    )
    min_star_level: int | None = Field(
        validation_alias="minGeneralStarTier",
        default=-1,
        description="The star level the general needs as well; -1 for none, None when unreadable, which no star "
        "level reaches",
    )

    _general_id = field_validator("general_id", mode="before")(_int_or_minus_one)
    _ints = field_validator("tier", "required_skill_points", mode="before")(_int_or_minus_one)

    @field_validator("min_star_level", mode="before")
    @classmethod
    def _min_star_level(cls, value: object) -> int | None:
        return _landmark_int(value, "-1")

    @field_validator("is_hidden", mode="before")
    @classmethod
    def _hidden(cls, value: object) -> bool:
        return value if isinstance(value, bool) else _parse_int_or_default(value, 0) == 1

    @property
    def has_requirement(self) -> bool:
        """Whether the client gates the tier on the points spent before it: a general, a tier and points above 0."""
        return self.general_id >= 0 and self.tier > 0 and self.required_skill_points > 0


class GeneralXpItemDef(_Row):
    """
    A general xp item: a currency that gives a general experience.

    Client: ``GeneralsXPItemVO.fillFromParamXml`` (split.js line 581234), keyed by ``currencyID`` in
    ``GeneralsData.init`` (split.js line 580447); ``GeneralsLevelUpDialogListItem.isXPCurrency`` (split.js line
    385083) offers a currency as xp only when it is one
    """

    currency_id: GameDataId["CurrencyId"] = Field(
        validation_alias="currencyID", default=0, description="The xp item's currency"
    )
    xp: int = Field(validation_alias="xpAmount", default=0, description="Experience one of it gives")

    _ints = field_validator("currency_id", "xp", mode="before")(_int_or_zero)


def is_single_effect_column(column: str) -> bool:
    """Whether a ``generalAbilityEffects`` column is ``effect``, which the client reads before ``effects``."""
    return column == "effect"


class GeneralAbilityEffectDef(EffectSpecRow):
    """
    The bonuses a general's ability grants while attacking or defending.

    A general ability names these rows by its ``ability_attack_effect_id`` and ``ability_defense_effect_id``.

    Client: ``GeneralAbilityEffectXmlVO.fillFromParamXml`` and ``parseBoni`` (split.js lines 580811-580840), which read
    ``effect``, else ``effects``, with ``BonusVO.parseFromValueString``; keyed by ``abilityEffectID`` in
    ``GeneralsData.init`` (split.js line 580433)
    """

    ability_effect_id: GeneralAbilityEffectId = Field(
        validation_alias="abilityEffectID", default=GeneralAbilityEffectId(0), description="The row"
    )
    priority: int = Field(default=0, description="The row's priority value")

    _ints = field_validator("ability_effect_id", "priority", mode="before")(_int_or_zero)

    @model_validator(mode="before")
    @classmethod
    def _effect_column(cls, data: object) -> object:
        if isinstance(data, Mapping) and js_truthy(data.get("effect")):
            return {**data, "effects": data["effect"]}
        return data


class SceatSkillTierDef(_Row):
    """
    A tier of a Hall of Legends sceat skill tree and what unlocks it.

    Client: ``CastleLegendSkillData.parseXML`` (split.js line 576514) reads the rows without their ``tierID``, for a
    tree from 0 and a tier from 1; ``TreeNodeUnlockRequirementsCreator.createUnlockRequirements`` (split.js line
    251357) reads the buildings, skills and legendary level
    """

    tier_id: SceatSkillTierId = Field(validation_alias="tierID", description="The row")
    skill_tree_id: int = Field(
        validation_alias="skillTreeID", default=-1, description="The tree, a sceat_skill_trees key; -1 for none"
    )
    tier: int = Field(default=-1, description="The tier, from 1; -1 for none")
    requires_previous_tier: bool = Field(
        validation_alias="requirePreviousTierUnlocked",
        default=True,
        description="The tier before must be unlocked, and each of its skills active",
    )
    required_buildings: tuple[GameDataId["Building"], ...] = Field(
        validation_alias="requiredBuildings", default=(), description="The buildings that unlock it, at their level"
    )
    any_required_building: bool = Field(
        validation_alias="requiredBuildingsCondition",
        default=False,
        description="Any one of required_buildings unlocks it; otherwise each is needed",
    )
    required_skills: tuple[GameDataId["SceatSkill"], ...] = Field(
        validation_alias="requiredSkillIDs", default=(), description="The sceat skill levels that must be active"
    )
    required_legendary_level: int = Field(
        validation_alias="requiredLegendLevel", default=0, description="The legendary level it needs; 0 for none"
    )

    _ints = field_validator("skill_tree_id", "tier", mode="before")(_int_or_minus_one)
    _legendary_level = field_validator("required_legendary_level", mode="before")(_int_or_zero)

    @field_validator("requires_previous_tier", mode="before")
    @classmethod
    def _previous_tier(cls, value: object) -> bool:
        return value if isinstance(value, bool) else _landmark_int(value, "1") == 1

    @field_validator("required_buildings", mode="before")
    @classmethod
    def _buildings(cls, value: object) -> object:
        # a building id that is not above 0 adds no requirement
        return [wod_id for wod_id in parse_ids(value) if wod_id > 0] if isinstance(value, str) else value

    @field_validator("required_skills", mode="before")
    @classmethod
    def _skills(cls, value: object) -> object:
        return _id_list(value)

    @field_validator("any_required_building", mode="before")
    @classmethod
    def _any(cls, value: object) -> bool:
        return value if isinstance(value, bool) else value == "or"


class LevelUpDef(_Row):
    """
    The rewards for reaching a range of levels, or of legendary levels.

    Client: ``LevelUpVO.parseXML`` (split.js line 581945); ``LevelUpData.getLevelUp`` (split.js line 581906) takes the
    first row whose range holds the level
    """

    is_legendary: bool = Field(
        validation_alias="isLegend", default=False, description="It rewards legendary levels rather than levels"
    )
    min_level: int | None = Field(
        validation_alias="minLevel", default=None, description="The first level it rewards; None when unreadable"
    )
    max_level: int | None = Field(
        validation_alias="maxLevel", default=None, description="The last level it rewards; None when unreadable"
    )
    reward_id: RewardId | None = Field(
        validation_alias="rewardID", default=None, description="The reward; None when unreadable"
    )
    in_skip_group: bool = Field(
        validation_alias="abTest", default=False, description="It is for players in the split-run skip group"
    )

    _ints = field_validator("min_level", "max_level", "reward_id", mode="before")(_int_or_nan)

    @field_validator("is_legendary", mode="before")
    @classmethod
    def _legendary(cls, value: object) -> bool:
        # "1" == getValueOrDefault("isLegend", row, "0")
        if isinstance(value, bool):
            return value
        return value == "1" if isinstance(value, str) else js_truthy(value) and js_loose_equals(value, 1)

    @field_validator("in_skip_group", mode="before")
    @classmethod
    def _skip_group(cls, value: object) -> bool:
        return value if isinstance(value, bool) else value == SKIP_GROUP

    def holds(self, level: int, *, legendary: bool = False) -> bool:
        """
        Whether it rewards ``level``, a legendary level when ``legendary``.

        Client: ``LevelUpVO.checkLevelRange`` (split.js line 581939)
        """
        return (
            legendary == self.is_legendary
            and self.min_level is not None
            and self.max_level is not None
            and self.min_level <= level <= self.max_level
        )


class LevelUpPriceDef(_Row):
    """
    What buying a level costs in rubies.

    Client: ``LevelUpPriceVO.parseXML`` (split.js line 573894); ``CastleBuyLevelData.getLevelUpCost`` (split.js line
    573872) takes the first row of the two levels
    """

    level_up_price_id: LevelUpPriceId = Field(validation_alias="levelUpPriceID", description="The row")
    from_level: int | None = Field(
        validation_alias="fromLevel", default=None, description="The level bought from; None when unreadable"
    )
    to_level: int | None = Field(
        validation_alias="toLevel", default=None, description="The level bought; None when unreadable"
    )
    cost_rubies: int | None = Field(
        validation_alias="c2Cost", default=None, description="Rubies it costs; None when unreadable"
    )

    _ints = field_validator("from_level", "to_level", "cost_rubies", mode="before")(_int_or_nan)


class MightRankDef(_Row):
    """
    A might rank: the might points that reach it and its reward.

    Client: ``MightRankVO.parseXML`` (split.js line 582107), keyed by ``mightID`` (``CastleXmlData.parseXML``)
    """

    might_rank_id: MightRankId = Field(validation_alias="mightID", default=MightRankId(0), description="The rank")
    threshold: int | None = Field(
        default=0, description="The might points past which the rank is reached; None when unreadable"
    )
    reward_id: RewardId = Field(validation_alias="rewardID", default=RewardId(0), description="Its reward")

    _id = field_validator("might_rank_id", "reward_id", mode="before")(_int_or_zero)

    @field_validator("threshold", mode="before")
    @classmethod
    def _threshold(cls, value: object) -> int | None:
        return _landmark_int(value, "0")


class HighscoreUnitReward(_Row):
    """
    One unit of a weekly honour reward and its base amount, a ``wodID+amount`` part of ``unitReward``.

    Client: ``HighscoreBonusVO`` (split.js line 576226) keeps a part whose ``parseInt`` id is above 0
    """

    unit: GameDataId["Unit"] = Field(description="The unit")
    amount: int | None = Field(description="Its base amount, before the rank; None when unreadable")

    @classmethod
    def parse_list(cls, value: object) -> object:
        """The ``#``-separated ``wodID+amount`` parts whose id is above 0."""
        if not isinstance(value, str):
            return () if value is None else value
        rewards = []
        for part in value.split("#"):
            wod_id, *rest = part.split("+")
            unit = js_parse_int(wod_id)
            if unit is not None and unit > 0:
                rewards.append({"unit": unit, "amount": js_parse_int(rest[0]) if rest else None})
        return rewards


class HighscoreBonusDef(_Row):
    """
    A weekly honour reward for a league's band of ranks: coins, or units and a tool.

    Client: ``CastleHighscoreData`` (split.js line 576071) reads the rows into ``HighscoreBonusVO`` (split.js line
    576226); ``CastleWeeklyHighscoreRewardDialog.setReward`` (split.js line 234995) prices them with
    ``HighscoreBonusConst`` (dll line 237)
    """

    league_type_id: GameDataId["LeagueType"] = Field(
        validation_alias="leaguetypeID", default=-1, description="The league; -1 for none"
    )
    highest_rank: int | None = Field(
        validation_alias="highestRank", default=0, description="The band's best rank; None when unreadable"
    )
    lowest_rank: int = Field(
        validation_alias="lowestRank", default=0, description="The band's worst rank; 0 for every rank below"
    )
    coins: int = Field(validation_alias="c1Reward", default=0, description="Coins at the band's best rank; 0 for none")
    units: tuple[HighscoreUnitReward, ...] = Field(
        validation_alias="unitReward", default=(), description="The units it gives"
    )
    tool: GameDataId["Tool"] | None = Field(
        validation_alias="toolReward", default=None, description="The tool it gives; None for none"
    )
    min_amount: int = Field(
        validation_alias="minAmount", default=0, description="The fewest coins or units of each kind it gives"
    )
    tool_offset: int = Field(
        validation_alias="toolOffset", default=0, description="The rank the tool amount counts down to"
    )
    tool_min_amount: int = Field(validation_alias="toolMinAmount", default=0, description="The fewest tools it gives")

    _ints = field_validator("coins", "min_amount", "tool_offset", "tool_min_amount", mode="before")(_int_or_zero)
    _league = field_validator("league_type_id", mode="before")(_int_or_minus_one)

    @field_validator("highest_rank", mode="before")
    @classmethod
    def _highest_rank(cls, value: object) -> int | None:
        return _landmark_int(value, "0")

    @field_validator("lowest_rank", mode="before")
    @classmethod
    def _lowest_rank(cls, value: object) -> int:
        return js_int(value)

    @field_validator("units", mode="before")
    @classmethod
    def _units(cls, value: object) -> object:
        return HighscoreUnitReward.parse_list(value)

    @field_validator("tool", mode="before")
    @classmethod
    def _tool(cls, value: object) -> object:
        if value is None:
            return None
        tool = value if isinstance(value, int) and not isinstance(value, bool) else _parse_int_or_default(value, 0)
        return tool if tool > 0 else None

    def holds(self, rank: int) -> bool:
        """Whether ``rank`` is in the band; never for an unreadable best rank."""
        return self.highest_rank is not None and self.highest_rank <= rank <= (
            self.lowest_rank if self.lowest_rank > 0 else math.inf
        )

    def coins_at(self, rank: int, level: int) -> int:
        """
        The coins it gives at ``rank`` to a player of ``level``, without legendary levels; 0 for an unreadable best
        rank.

        Client: ``HighscoreBonusConst.calcHighscoreBonusForC1`` (dll line 237), which
        ``CastleWeeklyHighscoreRewardDialog.setReward`` (split.js line 235013) passes ``userData.userLevel``
        """
        if self.highest_rank is None:
            return 0
        by_rank = max(self.min_amount, self.coins - 10 * (rank - self.highest_rank))
        # Math.pow of a negative level is NaN, which `| 0` reads as 0
        by_level = 10 * js_int32(js_round(level**1.1)) if level >= 0 else 0
        return max(by_rank, by_level)

    def unit_amount(self, unit: HighscoreUnitReward, rank: int) -> int:
        """
        How many of ``unit`` it gives at ``rank``.

        Client: ``HighscoreBonusConst.calcHighscoreBonusForUnits`` (dll line 237)
        """
        if unit.amount is None or self.highest_rank is None:
            return 0  # Math.max with NaN is NaN, which `| 0` reads as 0
        return js_int32(js_round(max(self.min_amount, (1 - (rank - self.highest_rank + 1) / 100 + 0.01) * unit.amount)))

    def tool_amount(self, rank: int) -> int:
        """
        How many of the tool it gives at ``rank``.

        Client: ``HighscoreBonusConst.calcHighscoreBonusForTools`` (dll line 237)
        """
        return max(self.tool_min_amount, js_int32(math.floor(0.5 * (self.tool_offset - rank))))


__all__ = [
    "SKIP_GROUP",
    "GeneralAbilityEffectDef",
    "GeneralSkillTierDef",
    "GeneralSkillTierId",
    "GeneralSlotDef",
    "GeneralXpItemDef",
    "HighscoreBonusDef",
    "HighscoreUnitReward",
    "LevelUpDef",
    "LevelUpPriceDef",
    "LevelUpPriceId",
    "MightRankDef",
    "MightRankId",
    "SceatSkillTierDef",
    "SceatSkillTierId",
    "is_single_effect_column",
]
