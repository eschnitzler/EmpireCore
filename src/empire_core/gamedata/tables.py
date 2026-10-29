"""
Typed rows of the items tables the generated id enums name: buildings, researches, events, loot boxes,
equipment groups, difficulty types, quests, daily quests, titles, achievements and alliance crest layouts
and colours, plus difficulty scaling camps and the rewards.

Each model reads the columns its client value object reads, with the same defaults. The ``rewards``
rows are read into collectables (``CollectableParserX2CRewards``, bundle line 62897); the costs and
other collectable columns the client reads with ``CollectableParserX2CList`` (bundle line 62874) from
other tables are not read yet.
"""

from __future__ import annotations

import math
import sys
from typing import TYPE_CHECKING, NewType

from pydantic import Field, ValidationInfo, field_validator, model_validator

from empire_core.enums import (
    BerimondLane,
    BerimondSpecialCampType,
    BuildingGroundType,
    BuildingGroup,
    CollectableKind,
    EquipmentSlot,
    Kingdom,
    MapItemType,
    QuestConditionType,
    RewardGrantType,
    TitleDisplayType,
    TitleSystem,
    TreasureMapType,
    WearerType,
)
from empire_core.protocol.js import js_falsy, js_int, js_number_or_none, js_parse_float, js_parse_int, js_string

from .collectables import _GOODS, _XML_COST_PREFIX, Collectable
from .lenient import GameDataId, GameDataKey
from .models import READING_CACHE, EffectSpecRow, EffectValue, _parse_int_or_default, _Row

if TYPE_CHECKING:
    from .data import GameData
    from .ids import (
        Achievement,
        AllianceCrestColor,
        AllianceCrestLayout,
        AllianceTowerEffect,
        BerimondSpecialCamp,
        Building,
        ConstructionItem,
        CurrencyId,
        DailyQuestId,
        DifficultyType,
        Effect,
        EquipmentGroup,
        Event,
        FusionForgeId,
        GemColor,
        GeneralRarity,
        GeneralsHubCharacter,
        Judgement,
        LeagueType,
        LootBox,
        LootBoxType,
        PrebuiltCastle,
        PrivateVillageType,
        QuestId,
        Research,
        SceatSkill,
        Title,
        TreasureMapId,
    )


RewardId = NewType("RewardId", int)
"""The id of a ``rewards`` row, whose collectables :meth:`GameData.reward_list` gives.

The rows have no name, so no generated enum names them; this type marks the id space instead.
"""


CoatOfArmsSymbolId = NewType("CoatOfArmsSymbolId", int)
"""The id of a ``crestsymbols`` row, a coat of arms symbol that :attr:`GameData.coat_of_arms_symbols` describes.

The rows have no name, so no generated enum names them; this type marks the id space instead.
"""

PackageId = NewType("PackageId", int)
"""The id of a ``packages`` row, an event package that :attr:`GameData.packages` describes.

The rows have no name the game shows, so no generated enum names them; this type marks the id space instead.
"""

ConstructionItemRecipeId = NewType("ConstructionItemRecipeId", int)
"""The id of a ``constructionItemRecipes`` row, a recipe that :attr:`GameData.construction_item_recipes` describes.

The rows have no name, so no generated enum names them; this type marks the id space instead.
"""

TreasureMapNodeId = NewType("TreasureMapNodeId", int)
"""The id of a ``tmapnodes`` row, a node of a treasure map that :attr:`GameData.treasure_map_nodes` describes.

The rows have no name, so no generated enum names them; this type marks the id space instead.
"""

CraftingRecipeId = NewType("CraftingRecipeId", int)
"""The id of a ``craftingRecipes`` row, a recipe that :attr:`GameData.crafting_recipes` describes.

The rows have no name, so no generated enum names them; this type marks the id space instead.
"""

CraftingQueueId = NewType("CraftingQueueId", int)
"""The ``queueTypeId`` of a ``craftingQueues`` row, the crafting queue :attr:`GameData.crafting_queues` describes.

The rows have no name, so no generated enum names them; this type marks the id space instead.
"""

StartResourcesId = NewType("StartResourcesId", int)
"""The id of a ``startResources`` row, the goods :attr:`GameData.start_resources` gives a special server's castle.

The rows have no name, so no generated enum names them; this type marks the id space instead.
"""

PartPayPriceId = NewType("PartPayPriceId", int)
"""The id of a ``partpayprices`` row, a price paid in parts that :attr:`GameData.part_pay_prices` describes."""

DonationItemId = NewType("DonationItemId", int)
"""The id of a ``donationItems`` row, what a donation event takes, that :attr:`GameData.donation_items` describes."""

DonationSettingId = NewType("DonationSettingId", int)
"""The id of a ``donationSettings`` row, a donation event's run settings, that :attr:`GameData.donation_settings`
describes."""

TrainingProgramId = NewType("TrainingProgramId", int)
"""The id of an ``officersSchoolEffects`` row, a training program that :attr:`GameData.training_programs` describes."""

EventDifficultyId = NewType("EventDifficultyId", int)
"""The id of an ``eventAutoScalingDifficulties`` row, an event difficulty that :attr:`GameData.event_difficulties`
describes."""

GachaId = NewType("GachaId", int)
"""The id of a ``gachaEvents`` row, a gacha level that :attr:`GameData.gachas` describes."""

WheelOfFortuneRewardSetId = NewType("WheelOfFortuneRewardSetId", int)
"""The id of a ``luckywheelrewardsets`` row, a Wheel of Fortune jackpot set that
:attr:`GameData.wheel_of_fortune_reward_sets` describes."""

WheelOfFortuneWinClassId = NewType("WheelOfFortuneWinClassId", int)
"""The id of a ``luckywheelclasses`` row, a Wheel of Fortune win class that
:attr:`GameData.wheel_of_fortune_win_classes` describes; the classes count up from 1."""

OuterRealmsSettingId = NewType("OuterRealmsSettingId", int)
"""The id of a ``tempServerSettings`` row, an Outer Realms run's settings that :attr:`GameData.outer_realms_settings`
describes."""

HorizonSettingId = NewType("HorizonSettingId", int)
"""The id of an ``allianceBattleGroundSettings`` row, a Beyond the Horizon run's settings that
:attr:`GameData.horizon_settings` describes."""

DaimyoContractId = NewType("DaimyoContractId", int)
"""The id of a daimyo alliance contract, a row of :attr:`GameData.daimyo_castle_contracts` or
:attr:`GameData.daimyo_township_contracts`: each table counts its own."""

ScalingCampId = NewType("ScalingCampId", int)
"""The id of an ``eventAutoScalingCamps`` row, a camp of an event's difficulty scaling that
:attr:`GameData.scaling_camps` describes."""

AllianceInvasionCampId = NewType("AllianceInvasionCampId", int)
"""The id of an ``allianceInvasionCamps`` row, an alliance invasion camp that :attr:`GameData.alliance_invasion_camps`
describes."""

RewardSetId = NewType("RewardSetId", int)
"""The reward set a league score event's ``RSID`` names: which :attr:`GameData.league_type_events` rows give its
leagues' rewards. Not a ``rewards`` row; 0 picks no set."""

LeagueTypeEventId = NewType("LeagueTypeEventId", int)
"""The id of a ``leaguetypeevents`` row, a league's rewards in one event that :attr:`GameData.league_type_events`
describes."""

LeaderboardRewardSetId = NewType("LeaderboardRewardSetId", int)
"""The reward set a score event's ``LRSI`` names: which :attr:`GameData.leaderboard_rewards` rows give its leaderboard's
rank rewards. Not a ``rewards`` row."""

LeaderboardRewardId = NewType("LeaderboardRewardId", int)
"""The id of a ``leaderboardRewards`` row, one rank band's rewards that :attr:`GameData.leaderboard_rewards`
describes."""


def row_id(value: object) -> int:
    """The row's own id, ``parseInt`` of it; a row without one is skipped, as nothing can look it up."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if type(value) is str and value.isascii() and value.isdigit():
        return int(value)
    parsed = None if js_falsy(value) else js_parse_int(value)
    if parsed is None:
        raise ValueError(f"row id {value!r} has no leading integer")
    return parsed


def _client_bool(value: object, default: bool) -> bool:
    """``CastleXMLUtils.getBooleanAttribute`` (bundle line 1033): anything but ``"0"`` is true."""
    if isinstance(value, bool):
        return value
    return default if js_falsy(value) else js_string(value) != "0"


def _is_one(value: object) -> bool:
    """``1 == parseInt(getValueOrDefault(key, row, "0"))``."""
    return value if isinstance(value, bool) else _parse_int_or_default(value, 0) == 1


def _int_list(value: object, default: str = "", separator: str = ",") -> list[int]:
    """
    ``CastleXMLUtils.createIntListFromString`` (bundle line 1038): ``parseInt`` of each non-empty ``,`` part.

    A part with no leading integer, which the client keeps as NaN, is left out.
    """
    if isinstance(value, list | tuple):
        return list(value)
    text = default if js_falsy(value) else js_string(value)
    return [number for part in text.split(separator) if part and (number := js_parse_int(part)) is not None]


def _text(value: object, default: str = "") -> str:
    """``getValueOrDefault`` of a text column: a missing or empty value reads as the default."""
    return default if js_falsy(value) else js_string(value)


class BuildingDef(EffectSpecRow):
    """
    A building: what every building, tower, gate, moat and decoration row has in common.

    The per-building columns the client's building subclasses read on top (storage, production,
    hospital capacity, ...) are not read; ``fortifications`` has the walls, gates and moats. Nor are the
    collectable lists ``AShopVO.parseXmlNode`` reads with its items parsers: the ``cost*`` columns
    (``costs``) other than ``costC2``, the ``sell*`` columns other than ``sellC1`` (the sell list) and
    ``tempServerCostWood`` and ``tempServerCostStone`` (Outer Realms repair costs).

    Client: ``AVisualVO.parseXmlNode`` (bundle line 17800), ``AShopVO.parseXmlNode`` (bundle lines
    31713-31715), ``ABasicBuildingVO.parseXmlNode``, ``parseEffects`` and
    ``parseAreaSpecificEffects`` (bundle lines 17842-17864)
    """

    building_id: GameDataId["Building"] = Field(validation_alias="wodID", description="The building")
    name: str = Field(default="", description="Building name, shared across levels, e.g. Keep")
    group: GameDataKey[BuildingGroup] = Field(default="", description="Building group, e.g. Building or Tower")
    building_type: str = Field(
        validation_alias="type",
        default="",
        description="Building type, e.g. Level1; empty for none",
    )
    level: int = Field(default=-1, description="Upgrade level; -1 when the row has none")
    required_level: int = Field(
        validation_alias="requiredLevel",
        default=0,
        description="Player level needed to build it",
    )
    required_legend_level: int = Field(
        validation_alias="requiredLegendLevel",
        default=0,
        description="Legend level needed to build it",
    )
    early_unlock_required_level: int = Field(
        validation_alias="earlyUnlockRequiredLevel",
        default=0,
        description="Player level from which it can be unlocked early",
    )
    upgrade_building_id: GameDataId["Building"] = Field(
        validation_alias="upgradeWodID",
        default=0,
        description="The building it upgrades to; 0 for none",
    )
    downgrade_building_id: GameDataId["Building"] = Field(
        validation_alias="downgradeWodID",
        default=0,
        description="The building it downgrades to; 0 for none",
    )
    shop_category: str = Field(
        validation_alias="shopCategory",
        default="NOT_IN_SHOP",
        description="Build menu category; NOT_IN_SHOP for none",
    )
    xp: int = Field(default=0, description="Experience for building it")
    might_value: int = Field(validation_alias="mightValue", default=0, description="Might points it gives")
    storeable: bool = Field(default=False, description="It can be put into storage")
    maximum_count: int = Field(
        validation_alias="maximumCount",
        default=1_000_000,
        description="How many a castle may have",
    )
    destructable: bool = Field(default=True, description="It can be torn down")
    outer_realms_destructable: bool = Field(
        validation_alias="tempServerDestructable",
        default=True,
        description="It can be torn down on the Outer Realms",
    )
    horizon_only: bool = Field(
        validation_alias="isBattleGround",
        default=False,
        description="Built on a battle ground only",
    )
    never_on_horizon: bool = Field(
        validation_alias="isNotBattleGround",
        default=False,
        description="Never built on a battle ground",
    )
    slum_level_needed: int = Field(
        validation_alias="slumLevelNeeded",
        default=0,
        description="Slum level needed to build it",
    )
    needs_construction_expert: bool = Field(
        validation_alias="constructionExpert",
        default=False,
        description="Building it needs the construction expert",
    )
    sell_coins: int = Field(validation_alias="sellC1", default=0, description="Coins for selling it")
    cost_rubies: int = Field(
        validation_alias="costC2",
        default=0,
        description="Rubies it costs to build or upgrade to",
    )
    sort_order: float = Field(
        validation_alias="sortOrder",
        default=1_000_000,
        description="Order in the build menu; a value that is no number sorts last",
    )
    only_in_area_types: tuple[GameDataId[MapItemType], ...] = Field(
        validation_alias="onlyInAreaTypes",
        default=(),
        description="The castle types it may be built in; empty for any",
    )
    only_in_kingdoms: tuple[GameDataId[Kingdom], ...] = Field(
        validation_alias="kIDs",
        default=(),
        description="The kingdoms it may be built in; empty for every kingdom",
    )
    only_in_event_ids: tuple[GameDataId["Event"], ...] = Field(
        validation_alias="eventIDs",
        default=(),
        description="The events it may be built in; empty for none in particular",
    )
    available_in_map_ids: tuple[GameDataId["TreasureMapId"], ...] = Field(
        validation_alias="mapIDs",
        default=(),
        description="The season event maps it may be built on; empty for any",
    )
    sceat_skill_id: GameDataId["SceatSkill"] = Field(
        validation_alias="sceatSkillLocked",
        default=0,
        description="The sceat skill that unlocks it; 0 for none",
    )
    construction_item_group_ids: tuple[int, ...] = Field(
        validation_alias="constructionItemGroupIDs",
        default=(),
        description="The construction item groups it takes",
    )
    low_level_build_durations: tuple[int, ...] = Field(
        validation_alias="lowLevelBuildDuration",
        default=(),
        description="Build times in seconds at the lowest player levels",
    )
    low_level_main_castle_cost_rubies: tuple[int, ...] = Field(
        validation_alias="lowLevelMainCastleCostC2",
        default=(),
        description="Ruby costs in the main castle at the lowest player levels",
    )
    effect_locked: bool = Field(
        validation_alias="effectLocked",
        default=False,
        description="Its effects need unlocking",
    )
    wall_bonus: int = Field(
        validation_alias="wallBonus",
        default=0,
        description="Wall protection, in percent",
    )
    moat_bonus: int = Field(
        validation_alias="moatBonus",
        default=0,
        description="Moat protection, in percent",
    )
    build_duration: int = Field(
        validation_alias="buildDuration",
        default=0,
        description="Build time in seconds",
    )
    building_ground_type: GameDataKey[BuildingGroundType] = Field(
        validation_alias="buildingGroundType",
        default=BuildingGroundType.NONE,
        description="The ground it stands on",
    )
    district_type_id: int = Field(
        validation_alias="districtTypeID",
        default=0,
        description="The district type it belongs to",
    )
    is_district: bool = Field(validation_alias="isDistrict", default=False, description="It is a district")
    is_relic_building: bool = Field(
        validation_alias="isRelicBuilding",
        default=False,
        description="It is a relic building",
    )
    area_specific_effects: tuple[EffectValue, ...] = Field(
        validation_alias="areaSpecificEffects",
        default=(),
        description="Bonuses that count only where their effect's conditions hold",
    )

    @field_validator("building_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "level", "required_level", "required_legend_level", "early_unlock_required_level", "upgrade_building_id",
        "downgrade_building_id", "xp", "might_value", "maximum_count", "slum_level_needed", "sell_coins",
        "cost_rubies", "wall_bonus", "moat_bonus", "build_duration", "district_type_id", mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object, info: ValidationInfo) -> int:
        return _parse_int_or_default(value, cls.model_fields[str(info.field_name)].default)

    @field_validator(
        "storeable", "destructable", "outer_realms_destructable", "horizon_only", "never_on_horizon",
        "needs_construction_expert", "effect_locked", "is_district", "is_relic_building", mode="before",
    )  # fmt: skip
    @classmethod
    def _bool_column(cls, value: object, info: ValidationInfo) -> bool:
        return _client_bool(value, cls.model_fields[str(info.field_name)].default)

    @field_validator("only_in_area_types", "only_in_kingdoms", "only_in_event_ids", mode="before")
    @classmethod
    def _list_column(cls, value: object) -> list[int]:
        return _int_list(value)

    @field_validator("available_in_map_ids", "low_level_build_durations", "low_level_main_castle_cost_rubies",
                     mode="before")  # fmt: skip
    @classmethod
    def _int_list_column(cls, value: object) -> list[int]:
        return _int_list(value)

    @field_validator("construction_item_group_ids", mode="before")
    @classmethod
    def _construction_item_groups(cls, value: object) -> list[int]:
        # ABasicBuildingVO.parseXmlNode keeps the ids above 0 (bundle lines 17843-17848)
        return [group_id for group_id in _int_list(value) if group_id > 0]

    @field_validator("sceat_skill_id", mode="before")
    @classmethod
    def _sceat_skill(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("sort_order", mode="before")
    @classmethod
    def _sort_order(cls, value: object) -> float:
        # getNumberAttribute("sortOrder", t, 1e6), NaN as Number.MAX_VALUE
        if READING_CACHE.get() and isinstance(value, float):
            return value
        if js_falsy(value):
            return 1_000_000
        number = js_number_or_none(value)
        return sys.float_info.max if number is None else number

    @field_validator("name", "group", "shop_category", "building_ground_type", mode="before")
    @classmethod
    def _text_column(cls, value: object, info: ValidationInfo) -> str:
        return _text(value, cls.model_fields[str(info.field_name)].default)

    @field_validator("area_specific_effects", mode="before")
    @classmethod
    def _area_effects(cls, value: object) -> object:
        # ABasicBuildingVO.parseAreaSpecificEffects (bundle line 17858)
        return EffectValue.parse_list(value)

    @field_validator("building_type", mode="before")
    @classmethod
    def _type(cls, value: object) -> str:
        text = _text(value)
        return "" if text == "-" else text

    def rubies_to_build(self, player_level: int | None) -> int:
        """
        The rubies it costs to build, before cost effects: ``low_level_main_castle_cost_rubies`` for the
        player's level when it names one, else ``cost_rubies``, and 0 at level 0. With the level unknown,
        the most either could be.

        Client: ``ABasicBuildingVO.costC2`` (bundle lines 17950-17953)
        """
        if player_level is None:
            return max((self.cost_rubies, *self.low_level_main_castle_cost_rubies))
        if player_level == 0:
            return 0
        if len(self.low_level_main_castle_cost_rubies) >= player_level:
            low_level = self.low_level_main_castle_cost_rubies[player_level - 1]
            if low_level > -1:
                return low_level
        return self.cost_rubies

    def seconds_to_build(self, player_level: int) -> int:
        """
        Its build time in seconds before boosts: ``low_level_build_durations`` for the player's level
        when that is above 0, else ``build_duration``.

        Client: ``ABasicBuildingVO.basicBuildDuration`` (bundle lines 17888-17890)
        """
        if 0 < player_level <= len(self.low_level_build_durations):
            low_level = self.low_level_build_durations[player_level - 1]
            if low_level > 0:
                return low_level
        return self.build_duration


_OUTER_REALMS_COST_PREFIX = "globalServerCost"
"""The prefix of a research's Outer Realms cost columns (``AResearchVO.fillFromParamXML``, bundle line 61509)."""


def is_research_cost_column(column: str) -> bool:
    """Whether a ``researches`` column is a cost: ``cost<name>`` or ``globalServerCost<name>``."""
    return column.startswith((_XML_COST_PREFIX, _OUTER_REALMS_COST_PREFIX))


class ResearchDef(EffectSpecRow):
    """
    One level of a research.

    ``costs`` and ``outer_realms_costs`` read every cost column of the row (see
    :meth:`Collectable.from_columns`), a currency named by its ``Name`` (``costLegendaryToken``) by the
    currency names GameData passes in as validation context (``currency_ids``).

    Client: ``AResearchVO.fillFromParamXML`` (bundle lines 61502-61516); ``getBaseCosts`` (bundle line
    61530) picks ``outer_realms_costs`` on the Outer Realms, and ``getFinalCosts`` (bundle line 61531)
    applies discounts to them
    """

    research_id: GameDataId["Research"] = Field(validation_alias="researchID", description="The research")
    label: str = Field(
        validation_alias="comment2",
        default="",
        description="Designer label the game does not read, e.g. recruitment speed",
    )
    group_id: int = Field(
        validation_alias="groupID",
        default=-1,
        description="The group the research's levels share",
    )
    level: int = Field(default=-1, description="Research level")
    prerequisite_ids: tuple[GameDataId["Research"], ...] = Field(
        validation_alias="prerequisiteIDs",
        default=(),
        description="Researches it needs first",
    )
    min_research_tower_level: int = Field(
        validation_alias="minResearchTowerLevel",
        default=1,
        description="Research tower level it needs",
    )
    required_level: int = Field(
        validation_alias="requiredLevel",
        default=0,
        description="Player level it needs",
    )
    required_legend_level: int = Field(
        validation_alias="requiredLegendLevel",
        default=0,
        description="Legend level it needs",
    )
    research_duration: int = Field(
        validation_alias="researchDuration",
        default=0,
        description="Research time in seconds",
    )
    outer_realms_research_duration: int = Field(
        validation_alias="globalServerResearchDuration",
        default=0,
        description="Research time on the Outer Realms",
    )
    only_with_research_expert: bool = Field(
        validation_alias="onlyWithResearchExpert",
        default=False,
        description="It needs the research expert",
    )
    cost_rubies: int = Field(validation_alias="costC2", default=0, description="Rubies it costs")
    costs: tuple[Collectable, ...] = Field(
        default=(), description="What it costs, in the items' order: resources, coins, rubies, tokens, ..."
    )
    outer_realms_costs: tuple[Collectable, ...] = Field(default=(), description="What it costs on the Outer Realms")

    @model_validator(mode="before")
    @classmethod
    def _read_costs(cls, row: object, info: ValidationInfo) -> object:
        if not isinstance(row, dict) or "costs" in row:
            return row
        currency_ids = (info.context or {}).get("currency_ids", {})
        return {
            **row,
            "costs": Collectable.from_columns(row, _XML_COST_PREFIX, currency_ids),
            "outer_realms_costs": Collectable.from_columns(row, _OUTER_REALMS_COST_PREFIX, currency_ids),
        }

    @field_validator("research_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "group_id", "level", "min_research_tower_level", "required_level", "required_legend_level",
        "research_duration", "outer_realms_research_duration", "cost_rubies", mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object, info: ValidationInfo) -> int:
        return _parse_int_or_default(value, cls.model_fields[str(info.field_name)].default)

    @field_validator("prerequisite_ids", mode="before")
    @classmethod
    def _prerequisites(cls, value: object) -> list[int]:
        # only ids above 0 count
        return [research_id for research_id in _int_list(value) if research_id > 0]

    @field_validator("only_with_research_expert", mode="before")
    @classmethod
    def _expert(cls, value: object) -> bool:
        return _is_one(value)

    @field_validator("label", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)


class EventDef(_Row):
    """
    An event: who sees it and where.

    Client: ``ASpecialEventVO.parseBasicsFromXmlNode`` (bundle lines 2959-2974); a season event's own map is the
    first of ``mapID`` (``ASeasonEventVO.parseEventXmlNode``, bundle line 31385)
    """

    event_id: GameDataId["Event"] = Field(validation_alias="eventID", description="The event")
    event_type: str = Field(
        validation_alias="eventType",
        default="",
        description="Event type, e.g. NomadInvasion",
    )
    min_level: int = Field(
        validation_alias="minLevel",
        default=0,
        description="Lowest player level that sees it",
    )
    max_level: int = Field(
        validation_alias="maxLevel",
        default=99,
        description="Highest player level that sees it",
    )
    open_with_login: bool = Field(
        validation_alias="openWithLogin",
        default=False,
        description="Its dialog opens on login",
    )
    sort_order: int = Field(validation_alias="sortOrder", default=0, description="Order among the events")
    crossplay_min_level: int = Field(
        validation_alias="crossplayMinLevel",
        default=-1,
        description="Lowest level on a crossplay server; -1 for none",
    )
    extension_unlock: int = Field(
        validation_alias="eventExtensionUnlock",
        default=0,
        description="Its extension unlock",
    )
    kingdoms: tuple[GameDataId[Kingdom], ...] = Field(
        validation_alias="kIDs",
        default=(Kingdom.GREEN,),
        description="The kingdoms it runs in",
    )
    area_types: tuple[GameDataId[MapItemType], ...] = Field(
        validation_alias="areaTypes",
        default=(MapItemType.CASTLE,),
        description="The castle types it counts in",
    )
    map_ids: tuple[GameDataId["TreasureMapId"], ...] = Field(
        validation_alias="mapID",
        default=(),
        description="The treasure maps it runs on, e.g. a season event's, whose first is its own map",
    )

    @field_validator("event_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "min_level", "max_level", "sort_order", "crossplay_min_level", "extension_unlock", mode="before"
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object, info: ValidationInfo) -> int:
        return _parse_int_or_default(value, cls.model_fields[str(info.field_name)].default)

    @field_validator("open_with_login", mode="before")
    @classmethod
    def _open_with_login(cls, value: object) -> bool:
        return _is_one(value)

    @field_validator("kingdoms", mode="before")
    @classmethod
    def _kingdoms(cls, value: object) -> list[int]:
        return _int_list(value, "0")

    @field_validator("area_types", mode="before")
    @classmethod
    def _area_types(cls, value: object) -> list[int]:
        return _int_list(value, "1")

    @field_validator("map_ids", mode="before")
    @classmethod
    def _map_ids(cls, value: object) -> list[int]:
        return _int_list(value)

    @field_validator("event_type", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)


class LootBoxDef(_Row):
    """
    A loot box.

    Client: ``LootBoxVO.parseXML`` (bundle line 112502)
    """

    loot_box_id: GameDataId["LootBox"] = Field(validation_alias="lootBoxID", description="The loot box")
    name: str = Field(default="", description="Internal name, e.g. MysteryBoxBronze")
    loot_box_type_id: GameDataId["LootBoxType"] = Field(
        validation_alias="lootBoxTypeID", default=0, description="Its type"
    )
    tombola_id: int = Field(
        validation_alias="lootBoxTombolaID",
        default=0,
        description="The tombola it draws from",
    )
    key_tombola_id: int = Field(
        validation_alias="lootBoxKeyTombolaID",
        default=0,
        description="The tombola its keys draw from",
    )
    rarity: int = Field(default=0, description="Rarity")
    draws: int = Field(default=0, description="Draws per opening")
    sort_order: int = Field(
        validation_alias="sortOrder",
        default=0,
        description="Order among the loot boxes",
    )

    @field_validator("loot_box_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("loot_box_type_id", "tombola_id", "key_tombola_id", "rarity", "draws", "sort_order", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("name", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)


class LootBoxTypeDef(_Row):
    """
    A loot box type, whose keys count toward a free box.

    Client: ``LootBoxTypeVO.parseXML`` (bundle line 58900)
    """

    loot_box_type_id: GameDataId["LootBoxType"] = Field(
        validation_alias="lootBoxTypeID", description="The loot box type"
    )
    theme: str = Field(
        validation_alias="lootBoxTheme",
        default="",
        description="Its theme, e.g. MysteryBox",
    )
    key_payout_threshold: int = Field(
        validation_alias="lootBoxKeyPayoutThreshold",
        default=0,
        description="Keys that pay out a box",
    )

    @field_validator("loot_box_type_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("key_payout_threshold", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("theme", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)


class GeneralRarityDef(_Row):
    """
    A general rarity: the shards that unlock a general of it and raise its stars, and the xp of each level.

    Client: ``GeneralRarityXmlVO.fillFromParamXml`` (bundle line 113254), keyed by ``generalRarityID`` in
    ``GeneralsData`` (bundle line 113035)
    """

    rarity_id: GameDataId["GeneralRarity"] = Field(validation_alias="generalRarityID", description="The rarity")
    name: str = Field(default="", description="Internal name, e.g. legendary")
    max_star_level: int = Field(validation_alias="maxStarLevel", default=0, description="The highest star level")
    unlock_cost: int = Field(validation_alias="unlockCosts", default=0, description="Shards that unlock a general")
    upgrade_costs: tuple[int, ...] = Field(
        validation_alias="upgradeCosts", default=(), description="Shards that raise a general from each star level"
    )
    xp_requirements: tuple[int, ...] = Field(
        validation_alias="xpRequirements", default=(), description="The total xp each level starts at"
    )
    universal_shards_per_hundred: int = Field(
        validation_alias="universalShardsPerHundred", default=0, description="Universal shards per hundred shards"
    )

    @field_validator("rarity_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("max_star_level", "unlock_cost", "universal_shards_per_hundred", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("upgrade_costs", "xp_requirements", mode="before")
    @classmethod
    def _int_lists(cls, value: object) -> list[int]:
        return _int_list(value)

    @field_validator("name", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)

    def star_upgrade_cost(self, star_level: int) -> int:
        """
        Shards that raise a general from ``star_level``; 0 past the last, where the client offers none.

        Client: ``GeneralRarityXmlVO.getRequiredShards`` (bundle line 113278)
        """
        return self.upgrade_costs[star_level] if 0 <= star_level < len(self.upgrade_costs) else 0

    def level_for_xp(self, xp: int) -> int:
        """
        The level a general of this rarity has at ``xp``; past the last requirement, the number of requirements.

        Client: ``GeneralRarityXmlVO.getLevelForXP`` (bundle line 113274)
        """
        level = 0
        while level < len(self.xp_requirements) - 1:
            if self.xp_requirements[level] <= xp < self.xp_requirements[level + 1]:
                return level + 1
            level += 1
        return level + 1


class GeneralsHubCharacterDef(_Row):
    """
    A character of the generals hub's inn, who spins a tombola for an offering.

    Client: ``GeneralsHubQuestVO.fillFromParamXml`` (bundle line 47005), keyed by ``characterID`` in
    ``GeneralsData`` (bundle line 113011)
    """

    character_id: GameDataId["GeneralsHubCharacter"] = Field(
        validation_alias="characterID", description="The character"
    )
    name: str = Field(default="", description="Internal name, e.g. fatKing")
    cooldown_seconds: int = Field(
        validation_alias="coolDownInSeconds", default=0, description="Seconds from the last free spin to the next"
    )
    max_free_openings: int = Field(
        validation_alias="maxFreeOpenings", default=0, description="Free spins that can wait at once"
    )
    offering_currency_ids: tuple[GameDataId["CurrencyId"], ...] = Field(
        validation_alias="tombolas", default=(), description="The offerings its tombolas take, one per tombola"
    )

    @field_validator("character_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("cooldown_seconds", "max_free_openings", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("offering_currency_ids", mode="before")
    @classmethod
    def _offerings(cls, value: object) -> object:
        # Each "#" part is offering+tombolaID (getTombolaOfferingCurrencyID, bundle line 47015)
        if not isinstance(value, str):
            return value if isinstance(value, list | tuple) else ()
        tombolas = (part.split("+") for part in value.split("#"))
        return [offering for parts in tombolas if (offering := js_parse_int(parts[0])) is not None]

    @field_validator("name", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)


class GemColorDef(_Row):
    """
    A gem colour, by which the auto-sell rules sell gems.

    Client: ``GemColorVO.parseXml`` (bundle line 144489), read by ``CastleGemData.parseGemColors`` (bundle line
    144298)
    """

    color_id: GameDataId["GemColor"] = Field(validation_alias="gemColorID", description="The gem colour")
    color_code: str = Field(validation_alias="colorCode", default="", description="Its colour, e.g. 0x29ABE2")

    @field_validator("color_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("color_code", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)


class EquipmentGroupDef(_Row):
    """
    An equipment item group, as equipment effects name them.

    Client: ``XmlEquipmentGroupVO.parseXml`` (bundle line 144187)
    """

    group_id: GameDataId["EquipmentGroup"] = Field(validation_alias="itemGroupID", description="The item group")
    name: str = Field(default="", description="Internal name, e.g. AttackPVP")
    wearer_id: GameDataId[WearerType] = Field(
        validation_alias="wearerID", default=-1, description="Who wears it; -1 for any"
    )
    slot_id: GameDataId[EquipmentSlot] = Field(validation_alias="slotID", default=-1, description="The slot it goes in")
    pic_id: int = Field(validation_alias="picID", default=-1, description="Its picture")
    drop_rate: int = Field(validation_alias="dropRate", default=-1, description="Its drop rate")

    @field_validator("group_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("wearer_id", "slot_id", "pic_id", "drop_rate", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)

    @field_validator("name", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)


class DifficultyTypeDef(_Row):
    """
    An event difficulty type, e.g. easyPlus.

    Client: ``EventAutoScalingDifficultyTypeVO.parseXML`` (bundle line 38258)
    """

    difficulty_type_id: GameDataId["DifficultyType"] = Field(
        validation_alias="difficultyTypeID", description="The type"
    )
    name: str = Field(default="", description="Internal name, e.g. easyPlus")
    sort_order: int = Field(validation_alias="sortOrder", default=0, description="Order among the types")

    @field_validator("difficulty_type_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("sort_order", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("name", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)


class QuestCondition(_Row):
    """
    One thing a quest counts: a ``type+amount+data`` part of its ``conditions``.

    Client: ``ABasicQuestConditionVO.loadFromParamArray`` (bundle line 52833)
    """

    condition_type: GameDataKey[QuestConditionType] = Field(description="What it counts, e.g. buyRubies")
    amount: int = Field(default=0, description="How many it needs")
    raw_data: str = Field(
        default="", description="Its |-separated parameters, which mean something different for each type"
    )

    @classmethod
    def parse_list(cls, value: object) -> list[QuestCondition] | object:
        """
        Each ``#``-separated condition of a ``conditions`` column; an empty part is left out.

        Client: ``CastleQuestVO.parseConditions`` (bundle line 52467), ``DailyQuestVO.fillFromParamXML`` (bundle
        line 134125)
        """
        if not isinstance(value, str):
            return value
        conditions = []
        for part in value.split("#"):
            if part:
                condition_type, _, rest = part.partition("+")
                amount, _, data = rest.partition("+")
                conditions.append(cls(condition_type=condition_type, amount=js_int(amount), raw_data=data))
        return conditions


class QuestDef(_Row):
    """
    A quest: where it shows, what unlocks it and what it counts.

    Client: ``CastleQuestVO.fillFromParamXML`` (bundle lines 52452-52454)
    """

    quest_id: GameDataId["QuestId"] = Field(validation_alias="questID", description="The quest")
    series_id: int = Field(
        validation_alias="questSeriesID",
        default=-1,
        description="The quest series; -1 for none",
    )
    series_number: int = Field(
        validation_alias="questSeriesNumber",
        default=1,
        description="Its place in the series",
    )
    quests_in_series: int = Field(
        validation_alias="numberOfQuestsInSeries",
        default=0,
        description="Quests in the series",
    )
    shown_kingdom: GameDataId[Kingdom] = Field(
        validation_alias="shownKingdomID",
        default=Kingdom.GREEN,
        description="The kingdom it is shown in",
    )
    trigger_kingdom: GameDataId[Kingdom] = Field(
        validation_alias="triggerKingdomID",
        default=Kingdom.GREEN,
        description="The kingdom it counts in, as the row has it",
    )
    hidden: bool = Field(default=False, description="It is not shown")
    map_id: GameDataId["TreasureMapId"] = Field(
        validation_alias="mapID",
        default=-1,
        description="The season event map it belongs to; -1 for none",
    )
    required_level: int = Field(
        validation_alias="requiredLevel",
        default=0,
        description="Player level it needs",
    )
    required_legend_level: int = Field(
        validation_alias="requiredLegendLevel",
        default=0,
        description="Legend level it needs",
    )
    required_quest_id: GameDataId["QuestId"] = Field(
        validation_alias="requiredQuestID",
        default=-1,
        description="The quest it needs first; -1 for none",
    )
    quest_giver_id: int = Field(
        validation_alias="questGiverID",
        default=0,
        description="The character who gives it",
    )
    event_id: GameDataId["Event"] = Field(
        validation_alias="eventID",
        default=0,
        description="The event it belongs to; 0 for none",
    )
    duration: int = Field(default=-1, description="Seconds it runs; -1 for no limit")
    objective_type: int = Field(
        validation_alias="objectiveType",
        default=0,
        description="Its objective type",
    )
    auto_show: bool = Field(validation_alias="autoShow", default=False, description="It opens on its own")
    sort_priority: int | None = Field(
        validation_alias="sortPriority",
        default=None,
        description="Order in the quest book; None sorts last",
    )
    cost_rubies: int = Field(validation_alias="c2Cost", default=0, description="Rubies to finish it at once")
    questbook_tab_id: int = Field(
        validation_alias="questbookTabID",
        default=-1,
        description="Its quest book tab; -1 for none",
    )
    conditions: tuple[QuestCondition, ...] = Field(default=(), description="What it counts")

    @field_validator("quest_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "series_id", "series_number", "quests_in_series", "trigger_kingdom", "map_id", "required_level",
        "required_legend_level", "required_quest_id", "quest_giver_id", "event_id", "duration", "objective_type",
        "cost_rubies", "questbook_tab_id", mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object, info: ValidationInfo) -> int:
        return _parse_int_or_default(value, cls.model_fields[str(info.field_name)].default)

    @field_validator("shown_kingdom", mode="before")
    @classmethod
    def _shown_kingdom(cls, value: object) -> int:
        return max(_parse_int_or_default(value, 0), 0)

    @field_validator("hidden", "auto_show", mode="before")
    @classmethod
    def _flag(cls, value: object) -> bool:
        return _is_one(value)

    @field_validator("sort_priority", mode="before")
    @classmethod
    def _sort_priority(cls, value: object) -> int | None:
        return None if value is None else js_int(value)

    @field_validator("conditions", mode="before")
    @classmethod
    def _conditions(cls, value: object) -> object:
        return QuestCondition.parse_list(value)


class DailyQuestDef(_Row):
    """
    A daily quest.

    Client: ``DailyQuestVO.fillFromParamXML`` (bundle lines 134124-134131)
    """

    quest_id: GameDataId["DailyQuestId"] = Field(validation_alias="dailyQuestID", description="The daily quest")
    trigger_kingdom: GameDataId[Kingdom] = Field(
        validation_alias="triggerKingdomID",
        default=Kingdom.GREEN,
        description="The kingdom it counts in; -1 for any",
    )
    is_outer_realms_quest: bool = Field(
        validation_alias="isTempServerQuest",
        default=False,
        description="It runs on the Outer Realms",
    )
    daily_task_points: int = Field(
        validation_alias="addDailyDutyPoints",
        default=0,
        description="Daily task points it gives",
    )
    level_calculated: bool = Field(
        validation_alias="levelCalculated",
        default=False,
        description="Its amounts scale with the player's level",
    )
    conditions: tuple[QuestCondition, ...] = Field(default=(), description="What it counts")

    @field_validator("quest_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("trigger_kingdom", "daily_task_points", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("is_outer_realms_quest", mode="before")
    @classmethod
    def _outer_realms(cls, value: object) -> bool:
        return _is_one(value)

    @field_validator("level_calculated", mode="before")
    @classmethod
    def _level_calculated(cls, value: object) -> bool:
        # Boolean(parseInt(getValueOrDefault("levelCalculated", e, "0")))
        return value if isinstance(value, bool) else _parse_int_or_default(value, 0) != 0

    @field_validator("conditions", mode="before")
    @classmethod
    def _conditions(cls, value: object) -> object:
        return QuestCondition.parse_list(value)


class TitleDef(EffectSpecRow):
    """
    A title of the glory, Berimond or Storm Islands title systems.

    Client: ``TitleVO.parseXml`` (bundle lines 62705-62713)
    """

    title_id: GameDataId["Title"] = Field(validation_alias="titleID", description="The title")
    title_system: GameDataKey[TitleSystem] = Field(
        validation_alias="type", default="-1", description="Its title system"
    )
    threshold: int = Field(default=-1, description="Points from which it is held; -1 for a top-X title")
    display_type: GameDataKey[TitleDisplayType] = Field(
        validation_alias="displayType",
        default="-1",
        description="Whether it goes before or after the name",
    )
    forced: bool = Field(default=False, description="It is a forced title")
    decay: int = Field(default=-1, description="Its point decay")
    is_positive: bool = Field(
        validation_alias="isPositive",
        default=False,
        description="It is a positive title",
    )
    top_x: int = Field(
        validation_alias="topX",
        default=-1,
        description="The top ranks that hold it; -1 or 0 for a points title",
    )
    previous_title_id: GameDataId["Title"] = Field(
        validation_alias="previousTitleID",
        default=-1,
        description="The title below it in its system; -1 for the first",
    )
    reward_id: RewardId = Field(
        validation_alias="rewardID",
        default=RewardId(-1),
        description="Its reward, whose collectables GameData.reward_list gives; -1 for none",
    )
    might_value: int = Field(validation_alias="mightValue", default=-1, description="Might points it gives")

    def rewards(self, *, game_data: GameData | None = None) -> tuple[Collectable, ...]:
        """
        What holding the title gives; nothing when it has no reward.

        Client: ``CastleTitleSystemHelper.getTitleRewardText`` reads ``getListById(rewardID)`` when it is
        above -1 (bundle line 4444)
        """
        from empire_core.gamedata.data import GameData

        data = game_data if game_data is not None else GameData.require()
        return data.reward_list((self.reward_id,))

    @field_validator("title_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "threshold", "decay", "top_x", "previous_title_id", "reward_id", "might_value", mode="before"
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)

    @field_validator("forced", "is_positive", mode="before")
    @classmethod
    def _flag(cls, value: object) -> bool:
        return _is_one(value)

    @field_validator("title_system", "display_type", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value, "-1")


class AchievementCondition(_Row):
    """
    One thing an achievement counts: a ``type+amount+params`` part of its ``conditions``.

    Client: ``AchievementConditionVO`` (bundle line 92956)
    """

    condition_type: str = Field(description="What it counts, e.g. achievementPoints")
    amount: int = Field(default=0, description="How many it needs")
    params: tuple[str, ...] = Field(default=(), description="Its further parameters, which differ for each type")

    @classmethod
    def parse_list(cls, value: object) -> list[AchievementCondition] | object:
        """
        Each ``#``-separated condition of a ``conditions`` column; an empty part is left out.

        Client: ``AchievementVO.fillFromParamXML`` (bundle lines 92883-92887)
        """
        if not isinstance(value, str):
            return value
        conditions = []
        for part in value.split("#"):
            if part:
                condition_type, _, rest = part.partition("+")
                amount, *params = rest.split("+")
                conditions.append(
                    cls(condition_type=condition_type, amount=_parse_int_or_default(amount, 0), params=tuple(params))
                )
        return conditions


class AchievementDef(_Row):
    """
    One step of an achievement series.

    Client: ``AchievementVO.fillFromParamXML`` (bundle lines 92882-92887) and
    ``AchievementSerieVO.fillFromParamXML`` (bundle line 92817), grouped by series in
    ``CastleAchievementData`` (bundle lines 29820-29827)
    """

    achievement_id: GameDataId["Achievement"] = Field(validation_alias="achievementID", description="The achievement")
    series_id: int = Field(
        validation_alias="achievementSeriesID",
        default=0,
        description="The series it is a step of",
    )
    series_number: int = Field(
        validation_alias="achievementSeriesNumber",
        default=0,
        description="Its step in the series",
    )
    achievements_in_series: int = Field(
        validation_alias="numberOfAchievementsInSeries",
        default=0,
        description="Steps in the series",
    )
    required_achievement_id: GameDataId["Achievement"] = Field(
        validation_alias="requiredAchievementID",
        default=0,
        description="The step before it; -1 or 0 for none",
    )
    achievement_points: int = Field(
        validation_alias="achievementPoints",
        default=0,
        description="Achievement points it gives",
    )
    category: str = Field(default="", description="The series' category, e.g. achievement or event")
    conditions: tuple[AchievementCondition, ...] = Field(default=(), description="What it counts")

    @field_validator("achievement_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "series_id", "series_number", "achievements_in_series", "required_achievement_id", "achievement_points",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("category", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)

    @field_validator("conditions", mode="before")
    @classmethod
    def _conditions(cls, value: object) -> object:
        return AchievementCondition.parse_list(value)


class AllianceCrestColorDef(_Row):
    """
    A colour an alliance crest can use.

    Client: ``AllianceCrestColorVO.parseXML`` (bundle line 111012), keyed by id in
    ``CastleAllianceCrestData.parseXML`` (bundle lines 110965-110970)
    """

    color_id: GameDataId["AllianceCrestColor"] = Field(validation_alias="allianceCoatColorID", description="The colour")
    color: str = Field(default="", description="The colour as hex text, e.g. 0xDBDACA")

    @field_validator("color_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("color", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)


class AllianceCrestLayoutDef(EffectSpecRow):
    """
    A layout an alliance crest can use, and the bonuses it grants.

    Client: ``AllianceCrestLayoutVO.parseXML`` and ``parseEffects`` (bundle lines 111024-111032), keyed by id
    in ``CastleAllianceCrestData.parseXML`` (bundle lines 110958-110963)
    """

    layout_id: GameDataId["AllianceCrestLayout"] = Field(
        validation_alias="allianceCoatLayoutID", description="The layout"
    )
    color_count: int = Field(validation_alias="noofColors", default=0, description="Colours it takes")
    event_id: GameDataId["Event"] = Field(
        validation_alias="eventID",
        default=0,
        description="The event that awards it; 0 for none",
    )
    max_duration: int = Field(
        validation_alias="maxDuration",
        default=0,
        description="Seconds it is held once won; 0 for a layout that does not expire",
    )
    effect_icon_id: int = Field(
        validation_alias="effectIconID",
        default=0,
        description="The icon its bonus shows",
    )
    label: str = Field(
        validation_alias="comment1",
        default="",
        description="Designer label the game does not read, e.g. nomad",
    )

    @field_validator("layout_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("color_count", "event_id", "max_duration", "effect_icon_id", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("label", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)


class ConstructionItemRecipeDef(_Row):
    """
    A recipe that crafts a construction item, one of a blueprint's.

    Client: ``ConstructionItemRecipeVO.parseFromXml`` (bundle line 141060), grouped into blueprints by
    ``ConstructionItemBlueprintData.parseFromXml`` (bundle line 141026)
    """

    recipe_id: ConstructionItemRecipeId = Field(
        validation_alias="constructionItemRecipeID",
        description="The recipe, as a research unlocks it",
    )
    blueprint_id: int = Field(
        validation_alias="blueprintID",
        default=0,
        description="The blueprint it belongs to",
    )
    construction_item_id: GameDataId["ConstructionItem"] = Field(
        validation_alias="constructionItemID",
        default=0,
        description="The construction item it crafts",
    )

    @field_validator("recipe_id", "blueprint_id", "construction_item_id", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)


_KINGDOM_IDS = frozenset(int(kingdom) for kingdom in Kingdom)
"""``WorldConst.WORLD_IDS`` (dll line 19996): the kingdoms' ids, the spaces a prebuilt castle unlocks a kingdom in."""

_NO_RUBIES = Collectable(kind=CollectableKind.RUBIES, key=CollectableKind.RUBIES.server_key, amount=0)


def _goods_costs(row: dict[str, object], currency_ids: dict[str, int]) -> tuple[Collectable, ...]:
    """
    The non-zero goods among a row's ``cost`` columns: resources, coins and rubies.

    Client: ``PrebuiltCastleItemVO.parseCosts`` (bundle line 142342) reads ``ClientConstCollectable.GROUP_LIST_GOODS``
    (bundle line 3073)
    """
    costs = Collectable.from_columns(row, _XML_COST_PREFIX, currency_ids)
    return tuple(cost for cost in costs if cost.kind in _GOODS and cost.amount)


def _rubies(costs: tuple[Collectable, ...]) -> int:
    return sum(int(cost.amount) for cost in costs if cost.kind is CollectableKind.RUBIES)


def is_cost_column(column: str) -> bool:
    """Whether an items column is a ``cost<name>`` column."""
    return column.startswith(_XML_COST_PREFIX)


class PrebuiltCastleDef(_Row):
    """
    A castle or camp you start a kingdom, a season event's map or a special server with, and its price.

    ``costs`` are its non-zero goods ``cost`` columns: resources, coins and rubies; the client reads no other.

    Client: ``PrebuiltCastleItemVO.parseXML`` and ``parseCosts`` (bundle lines 142341-142342), keyed by id
    and by space in ``PrebuiltCastleData.parsePreBuiltCastles`` (bundle line 142274)
    """

    prebuilt_castle_id: GameDataId["PrebuiltCastle"] = Field(
        validation_alias="preBuiltCastleID", description="The prebuilt castle"
    )
    space_ids: tuple[GameDataId[Kingdom, "TreasureMapId"], ...] = Field(
        validation_alias="spaceIDs",
        default=(),
        description="Where it is offered: a kingdom, or a season event's map; Kingdom.GREEN for a special server's",
    )
    min_level: int = Field(validation_alias="minLevel", default=0, description="Player level it needs")
    shown_discount: int = Field(
        validation_alias="shownDiscount", default=0, description="The discount in percent its offer shows"
    )
    is_main_castle_copy: bool = Field(
        validation_alias="isMainCastleCopy",
        default=False,
        description="It copies your main castle's buildings, as the Outer Realms castle transport does",
    )
    costs: tuple[Collectable, ...] = Field(default=(), description="What it costs; empty for a free one")
    area_label: str = Field(
        validation_alias="comment1", default="", description="Designer label the game does not read, e.g. Underworld"
    )
    label: str = Field(
        validation_alias="comment2", default="", description="Designer label the game does not read, e.g. C2Camp"
    )

    @model_validator(mode="before")
    @classmethod
    def _read_costs(cls, row: object, info: ValidationInfo) -> object:
        if not isinstance(row, dict) or "costs" in row:
            return row
        return {**row, "costs": _goods_costs(row, (info.context or {}).get("currency_ids", {}))}

    @field_validator("area_label", "label", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)

    @field_validator("prebuilt_castle_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("space_ids", mode="before")
    @classmethod
    def _spaces(cls, value: object) -> list[int]:
        return _int_list(value)

    @field_validator("min_level", "shown_discount", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("is_main_castle_copy", mode="before")
    @classmethod
    def _flag(cls, value: object) -> bool:
        return _is_one(value)

    @property
    def cost_rubies(self) -> int:
        """The rubies among its costs; 0 when it costs none."""
        return _rubies(self.costs)

    @property
    def is_free(self) -> bool:
        """Whether it costs nothing. Client: ``PrebuiltCastleItemVO.isFree`` (bundle line 142353)"""
        return not self.costs

    @property
    def is_premium(self) -> bool:
        """Whether rubies are its only price. Client: ``PrebuiltCastleItemVO.isPremium`` (bundle line 142354)"""
        return len(self.costs) == 1 and self.cost_rubies > 0

    @property
    def primary_costs(self) -> tuple[Collectable, ...]:
        """
        What it costs bought without its ruby price: all of a premium castle's costs, else those but the rubies.

        Client: ``PrebuiltCastleItemVO.primaryCosts`` (bundle line 142357)
        """
        if self.is_premium:
            return self.costs
        return tuple(cost for cost in self.costs if cost.kind is not CollectableKind.RUBIES)

    @property
    def kingdom(self) -> Kingdom | None:
        """
        The kingdom it starts, the first of its spaces that is one; None for a season camp.

        Client: ``AUnlockPrebuiltCastle.buyPrebuiltCastle`` (bundle line 55479) unlocks a kingdom for a castle
        with a space in ``WorldConst.WORLD_IDS``
        """
        return next((Kingdom(space) for space in self.space_ids if space in _KINGDOM_IDS), None)


class SpecialServerPrebuiltCastleDef(_Row):
    """
    A prebuilt castle as a special server's castle selection offers it: the Outer Realms, Beyond the Horizon or
    the Storm Islands, each with a table of its own.

    ``costs`` are its ``cost`` columns, rubies or castle passage tokens; :meth:`selection_costs` is what the
    selection charges. The ``questsToFinish`` column is not read: the client reads it nowhere.

    Client: ``SpecialServerPreBuiltCastleVO.parseXML`` (bundle line 40289), keyed by id in
    ``CastleTempServerData`` (bundle line 140201), ``CastleAllianceBattleGroundData`` (bundle line 144847)
    and ``CastleKingdomData`` (bundle line 134581)
    """

    prebuilt_castle_id: GameDataId["PrebuiltCastle"] = Field(
        validation_alias="preBuiltCastleID", description="The prebuilt castle"
    )
    start_resources_id: StartResourcesId = Field(
        validation_alias="startResourceID", default=StartResourcesId(0), description="The resources you start with"
    )
    start_level: int = Field(validation_alias="startPlayerLevel", default=0, description="Your level there")
    start_legendary_level: int = Field(
        validation_alias="startPlayerLegendLevel", default=0, description="Your legendary level there; 0 for none"
    )
    passage_token_package_id: PackageId = Field(
        validation_alias="castlePassageTokenPackageID",
        default=PackageId(0),
        description="The package that sells the castle passage tokens it costs; 0 for none",
    )
    costs: tuple[Collectable, ...] = Field(default=(), description="What it costs; empty when the row names none")

    @model_validator(mode="before")
    @classmethod
    def _read_costs(cls, row: object, info: ValidationInfo) -> object:
        if not isinstance(row, dict) or "costs" in row:
            return row
        currency_ids = (info.context or {}).get("currency_ids", {})
        return {**row, "costs": Collectable.from_columns(row, _XML_COST_PREFIX, currency_ids)}

    @field_validator("prebuilt_castle_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "start_resources_id", "start_level", "start_legendary_level", "passage_token_package_id", mode="before"
    )
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    def selection_costs(self, castle: PrebuiltCastleDef) -> tuple[Collectable, ...]:
        """
        What the castle selection charges for it: its own costs; with none, the castle's primary costs, or else
        0 rubies, which the client keeps as the price of a free castle.

        Client: ``SpecialServerPreBuiltCastleVO.parseXML`` (bundle line 40289) with
        ``CollectableParserX2CEventPackages.createCostList`` (bundle line 62852)
        """
        costs = self.costs or (_NO_RUBIES,)
        if len(costs) == 1 and costs[0].amount == 0 and castle.primary_costs:
            return castle.primary_costs
        return costs

    def is_ruby_castle(self, castle: PrebuiltCastleDef) -> bool:
        """
        Whether its selection is sent as bought with rubies (``OC2``): its selection costs hold rubies, even
        the 0 rubies of a free castle.

        Client: ``CastleSpecialServerPreBuildCastleSelectionDialog.onConfirmed`` (bundle line 27954),
        ``CollectableList.containsType`` (bundle line 1830)
        """
        return any(cost.kind is CollectableKind.RUBIES for cost in self.selection_costs(castle))

    def cost_rubies(self, castle: PrebuiltCastleDef) -> int:
        """The rubies its selection costs; 0 when it costs none."""
        return _rubies(self.selection_costs(castle))


class StartResourcesDef(_Row):
    """
    The goods a special server's prebuilt castle starts with.

    Client: ``StartResourcesVO.parseXML`` (bundle line 145059), keyed by id in
    ``CastleAllianceBattleGroundData`` (bundle line 144845)
    """

    start_resources_id: StartResourcesId = Field(validation_alias="startResourceID", description="The start resources")
    resources: tuple[Collectable, ...] = Field(default=(), description="What you start with")

    @model_validator(mode="before")
    @classmethod
    def _read_resources(cls, row: object, info: ValidationInfo) -> object:
        if not isinstance(row, dict) or "resources" in row:
            return row
        currency_ids = (info.context or {}).get("currency_ids", {})
        return {**row, "resources": Collectable.from_reward_row(row, currency_ids)}

    @field_validator("start_resources_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)


class PrivateVillageDef(EffectSpecRow):
    """
    One level of a private resource village, bought with resource village tokens.

    Client: ``PrivateResourceVillageInfoVO.fillFromParamXML`` (bundle line 143715), keyed by id in
    ``CastlePrivateResourceVillageData.parse`` (bundle line 143686)
    """

    village_type_id: GameDataId["PrivateVillageType"] = Field(
        validation_alias="villageID", description="The village type and level"
    )
    resource: str = Field(validation_alias="type", default="", description="What it produces: wood, stone or food")
    level: int = Field(validation_alias="villageLevel", default=0, description="Village level")
    kingdom: GameDataId[Kingdom] = Field(validation_alias="kID", default=Kingdom.GREEN, description="Its kingdom")
    token_cost: int = Field(
        validation_alias="costResourceVillageTokenLevel",
        default=0,
        description="Resource village tokens this level costs",
    )
    total_token_cost: int = Field(
        validation_alias="costResourceVillageToken",
        default=0,
        description="Resource village tokens it costs up to this level",
    )

    @field_validator("village_type_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("level", "kingdom", "token_cost", "total_token_cost", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("resource", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)


class CraftingRecipeDef(_Row):
    """
    A recipe a crafting queue crafts.

    The table keeps every row; the client, when it loads the table, drops a recipe whose rewards give nothing.

    Client: ``CraftingRecipeVO.fillFromParamXml`` (bundle line 111526), kept by id in ``CastleCraftingData``
    (bundle line 111386) only when its ``output`` is not empty
    """

    recipe_id: CraftingRecipeId = Field(validation_alias="craftingRecipeId", description="The recipe")
    queue_id: CraftingQueueId = Field(
        validation_alias="queueTypeId", default=CraftingQueueId(0), description="The crafting queue it is crafted in"
    )
    recipe_group_id: int = Field(
        validation_alias="recipeGroupID", default=0, description="The group the recipe's levels share"
    )
    research_group_id: int = Field(
        validation_alias="researchGroupID", default=0, description="The research group that unlocks it; 0 for none"
    )
    level: int = Field(default=0, description="Recipe level")
    recipe_type: str = Field(validation_alias="type", default="", description="short, long or ruby")
    crafting_seconds: int = Field(validation_alias="craftingDuration", default=0, description="Seconds it crafts")
    skip_cost_rubies: int = Field(validation_alias="skipCostC2", default=0, description="Rubies that finish it")
    costs: tuple[Collectable, ...] = Field(default=(), description="What it costs to start")
    reward_ids: tuple[RewardId, ...] = Field(validation_alias="rewardIDs", default=(), description="What it crafts")
    required_buildings: tuple[GameDataId["Building"], ...] = Field(
        validation_alias="requiredCraftingBuildings", default=(), description="The buildings it needs"
    )

    @model_validator(mode="before")
    @classmethod
    def _read_costs(cls, row: object, info: ValidationInfo) -> object:
        if not isinstance(row, dict) or "costs" in row:
            return row
        currency_ids = (info.context or {}).get("currency_ids", {})
        return {**row, "costs": Collectable.from_columns(row, _XML_COST_PREFIX, currency_ids)}

    @field_validator("recipe_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "queue_id", "recipe_group_id", "research_group_id", "level", "crafting_seconds", "skip_cost_rubies",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("recipe_type", mode="before")
    @classmethod
    def _type(cls, value: object) -> str:
        return _text(value).lower()

    @field_validator("reward_ids", "required_buildings", mode="before")
    @classmethod
    def _ids(cls, value: object) -> list[int]:
        return _int_list(value)


class CraftingQueueDef(_Row):
    """
    A crafting queue's slots: those it always has, and the temporary ones coins unlock for a while.

    Client: ``CraftingQueueXML.fillFromParamXml`` (bundle line 111498), keyed by ``queueTypeId`` in
    ``CastleCraftingData`` (bundle line 111381), the ``CQID`` a queue is sent with
    """

    queue_id: CraftingQueueId = Field(validation_alias="queueTypeId", description="The crafting queue")
    permanent_production_slots: int = Field(
        validation_alias="permanentProductionSlots", default=0, description="Slots that always craft"
    )
    production_slot_unlock_coins: tuple[int, ...] = Field(
        validation_alias="productionSlotUnlockCostC1",
        default=(),
        description="Coins each temporary crafting slot unlocks for, one per slot",
    )
    production_slot_unlock_seconds: int = Field(
        validation_alias="productionSlotUnlockDuration",
        default=0,
        description="Seconds a temporary crafting slot stays unlocked",
    )
    permanent_queue_slots: int = Field(
        validation_alias="permanentQueueSlots", default=0, description="Waiting slots it always has"
    )
    queue_slot_unlock_coins: tuple[int, ...] = Field(
        validation_alias="queueSlotUnlockCostC1",
        default=(),
        description="Coins each temporary waiting slot unlocks for, one per slot",
    )
    queue_slot_unlock_seconds: int = Field(
        validation_alias="queueSlotUnlockDuration",
        default=0,
        description="Seconds a temporary waiting slot stays unlocked",
    )

    @field_validator("queue_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "permanent_production_slots", "production_slot_unlock_seconds", "permanent_queue_slots",
        "queue_slot_unlock_seconds", mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("production_slot_unlock_coins", "queue_slot_unlock_coins", mode="before")
    @classmethod
    def _coins(cls, value: object) -> list[int]:
        return _int_list(value)


class FusionSystemDef(_Row):
    """
    A fusion forge's energy and fusion rules.

    The client builds one forge per row, with the row's id (``FusionForgeData.init``, bundle line 141977),
    and looks both tables up by that id (``FusionConst.DECORATION_FORGE_ID``, bundle lines 24974, 78008, 78074).

    Client: ``XmlFusionSystemVO.parseXml`` (bundle line 142170)
    """

    forge_id: GameDataId["FusionForgeId"] = Field(validation_alias="id", description="The fusion forge")
    energy_recharge_seconds: int = Field(
        validation_alias="energyRechargeIntervalInSeconds", default=0, description="Seconds between energy recharges"
    )
    assemble_catalyst_energy: int = Field(
        validation_alias="assembleCatalystEnergyCost", default=0, description="Energy one assembled catalyst takes"
    )
    disassemble_catalyst_energy: int = Field(
        validation_alias="disassembleCatalystEnergyCost",
        default=0,
        description="Energy one disassembled catalyst takes",
    )
    base_bonus_xp_chance: int = Field(
        validation_alias="baseBonusFusionXPChance", default=0, description="Percent chance of bonus fusion XP"
    )
    premium_bonus_xp_chance: int = Field(
        validation_alias="premiumBonusFusionXPChance",
        default=0,
        description="Percent chance of bonus fusion XP with a premium catalyst",
    )
    refill_cost_rubies: int = Field(
        validation_alias="skipRechargeHardCurrencyCost", default=0, description="Rubies the first energy refill costs"
    )
    refill_cost_factor: float = Field(
        validation_alias="skipRechargeHardCurrencyCostFactor",
        default=0.0,
        description="What each refill bought multiplies the next one's price by",
    )

    @field_validator("forge_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "energy_recharge_seconds", "assemble_catalyst_energy", "disassemble_catalyst_energy", "base_bonus_xp_chance",
        "premium_bonus_xp_chance", "refill_cost_rubies", mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("refill_cost_factor", mode="before")
    @classmethod
    def _factor(cls, value: object) -> float:
        return 0.0 if js_falsy(value) else js_parse_float(value)


class FusionForgeDef(_Row):
    """
    A fusion forge's dust and daily minute skips.

    Client: ``XmlFusionForgeVO.parseXml`` (bundle line 142155)
    """

    forge_id: GameDataId["FusionForgeId"] = Field(validation_alias="forgeID", description="The fusion forge")
    dust_currency_id: GameDataId["CurrencyId"] = Field(
        validation_alias="dustCurrencyID", default=0, description="The dust its fusions and level-ups spend"
    )
    minute_skips_per_day: int = Field(
        validation_alias="usableMinuteSkipsPerDay", default=0, description="Minute skips it takes a day"
    )

    @field_validator("forge_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("dust_currency_id", "minute_skips_per_day", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)


class JudgementDef(_Row):
    """
    A citizen judgement: where it appears, and what each verdict asks and gives.

    The requirements and rewards are the kinds of goods the client looks up, e.g. ``units`` or ``wood``.

    Client: ``JudgementVO.fillFromParamXML`` (bundle line 134514), keyed by id in ``CastleJudgementData``
    (bundle line 134451)
    """

    judgement_id: GameDataId["Judgement"] = Field(validation_alias="judgementID", description="The judgement")
    visual_name: str = Field(validation_alias="visualName", default="", description="The figure it shows, e.g. wolfs")
    spawn_spot: str = Field(validation_alias="spawnSpot", default="", description="Where it appears, e.g. keep")
    option_a_requirements: tuple[str, ...] = Field(
        validation_alias="conditionTypeA", default=(), description="What verdict A asks for"
    )
    option_b_requirements: tuple[str, ...] = Field(
        validation_alias="conditionTypeB", default=(), description="What verdict B asks for"
    )
    option_a_rewards: tuple[str, ...] = Field(
        validation_alias="rewardTypeA", default=(), description="What verdict A gives"
    )
    option_b_rewards: tuple[str, ...] = Field(
        validation_alias="rewardTypeB", default=(), description="What verdict B gives"
    )

    @field_validator("judgement_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("visual_name", "spawn_spot", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)

    @field_validator(
        "option_a_requirements", "option_b_requirements", "option_a_rewards", "option_b_rewards", mode="before"
    )
    @classmethod
    def _kinds(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, list | tuple):
            return tuple(value)
        return tuple(part for part in _text(value).split("#") if part)


class CoatOfArmsSymbolDef(_Row):
    """
    A symbol for a coat of arms. One with a required achievement is a premium symbol: that achievement
    earns it, and it is unlocked for its coin or ruby price.

    Client: ``CastleCrestSymbolData.parseXML`` (bundle line 111588), ``PremiumCrestSymbolVO.parseXML``
    (bundle line 111660)
    """

    symbol_id: CoatOfArmsSymbolId = Field(
        validation_alias="crestSymbolID", description="The symbol, as a coat of arms names it"
    )
    required_achievement_id: GameDataId["Achievement"] = Field(
        validation_alias="requiredAchievementID",
        default=0,
        description="The achievement that earns it; 0 for a standard symbol, free to use",
    )
    cost_coins: int = Field(validation_alias="costC1", default=0, description="Coins it is unlocked for")
    cost_rubies: int = Field(validation_alias="costC2", default=0, description="Rubies it is unlocked for")

    @field_validator("symbol_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("required_achievement_id", "cost_coins", "cost_rubies", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @property
    def is_premium(self) -> bool:
        """Whether an achievement earns it and it must be unlocked."""
        return self.required_achievement_id > 0


class PackageDef(_Row):
    """
    An event package: what a shop sells, and what a gift package holds. Only its id, type and gift flag are read.

    Client: ``EventPackageVO.fillFromParamXML`` (bundle line 34024), kept by id in ``CastleEventPackageData``
    (``getEventPackageByID``, bundle line 134408)
    """

    package_id: PackageId = Field(validation_alias="packageID", description="The package")
    package_type: str = Field(
        validation_alias="packageType", default="0", description="What it holds, e.g. tool, currency or item"
    )
    is_gift_package: bool = Field(
        validation_alias="isGiftPackage", default=False, description="Whether it is a gift package you may send"
    )

    @field_validator("package_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("package_type", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value, "0")

    @field_validator("is_gift_package", mode="before")
    @classmethod
    def _flag(cls, value: object) -> bool:
        return _is_one(value)


class PlayerNameChangeDef(_Row):
    """
    The ruby price of one of your player name changes, by its number.

    Client: ``ChangePlayerNameData.parseXml`` (bundle line 145454)
    """

    name_change_id: int = Field(
        validation_alias="nameChangeID", description="Which name change it prices: 1 for the first"
    )
    cost_rubies: int = Field(validation_alias="costC2", default=0, description="Rubies it costs")

    @field_validator("name_change_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("cost_rubies", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)


class ScalingCampDef(_Row):
    """
    A camp of an event's difficulty scaling: the level and costs a chosen difficulty gives it.

    Client: ``DifficultyScalingCampXmlVO.parseXML`` (bundle line 145227), keyed by id in
    ``CastleEventDifficultyScalingData`` (bundle line 145211)
    """

    scaling_camp_id: ScalingCampId = Field(
        validation_alias="eventAutoScalingCampID",
        description="The scaling camp, as map rows name it",
    )
    rank: int = Field(default=0, description="Its rank")
    level: int = Field(validation_alias="camplevel", default=0, description="The camp level it gives")
    cool_down: int = Field(
        validation_alias="coolDown",
        default=0,
        description="Cooldown in seconds after an attack",
    )
    event_id: GameDataId["Event"] = Field(validation_alias="eventID", default=0, description="The event it belongs to")
    cooldown_increase: int = Field(
        validation_alias="cooldownIncrease",
        default=0,
        description="Cooldown added per attack",
    )
    cooldown_increase_cap: int = Field(
        validation_alias="cooldownIncreaseCap",
        default=0,
        description="Most cooldown added",
    )
    skip_cost: int = Field(
        validation_alias="skipCosts",
        default=0,
        description="Cost to skip the cooldown",
    )
    skip_cost_increase: int = Field(
        validation_alias="skipCostIncrease",
        default=0,
        description="Skip cost added per attack",
    )
    skip_cost_increase_cap: int = Field(
        validation_alias="skipCostIncreaseCap",
        default=0,
        description="Most skip cost added",
    )
    wall_bonus: int = Field(
        validation_alias="wallBonus",
        default=0,
        description="Wall protection, in percent",
    )
    gate_bonus: int = Field(
        validation_alias="gateBonus",
        default=0,
        description="Gate protection, in percent",
    )
    moat_bonus: int = Field(
        validation_alias="moatBonus",
        default=0,
        description="Moat protection, in percent",
    )
    unit_capacity: int = Field(validation_alias="unitCapacity", default=0, description="Units it holds")
    shogun_points_needed_for_level_up: int = Field(
        validation_alias="shogunPointsNeededForLevelUp",
        default=-1,
        description="Shogun points to the next level; -1 for none",
    )
    player_rage_cap: int = Field(
        validation_alias="playerRageCap",
        default=-1,
        description="Most rage a player builds; -1 for none",
    )
    rage_needed_for_level_up: int = Field(
        validation_alias="rageNeededForLevelUp",
        default=-1,
        description="Rage to the next level; -1 for none",
    )
    normal_def_strength_boost_min: int = Field(
        validation_alias="normalDiffDefStrengthBoostMinDefense",
        default=0,
        description="Least defence boost, normal difficulty",
    )
    normal_def_strength_boost_max: int = Field(
        validation_alias="normalDiffDefStrengthBoostMaxDefense",
        default=0,
        description="Most defence boost, normal difficulty",
    )
    premium_def_strength_boost_min: int = Field(
        validation_alias="premiumDiffDefStrengthBoostMinDefense",
        default=0,
        description="Least defence boost, premium difficulty",
    )
    premium_def_strength_boost_max: int = Field(
        validation_alias="premiumDiffDefStrengthBoostMaxDefense",
        default=0,
        description="Most defence boost, premium difficulty",
    )

    @field_validator("scaling_camp_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "rank", "level", "cool_down", "event_id", "cooldown_increase", "cooldown_increase_cap", "skip_cost",
        "skip_cost_increase", "skip_cost_increase_cap", "wall_bonus", "gate_bonus", "moat_bonus", "unit_capacity",
        "shogun_points_needed_for_level_up", "player_rage_cap", "rage_needed_for_level_up",
        "normal_def_strength_boost_min", "normal_def_strength_boost_max", "premium_def_strength_boost_min",
        "premium_def_strength_boost_max", mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object, info: ValidationInfo) -> int:
        return _parse_int_or_default(value, cls.model_fields[str(info.field_name)].default)


class DaimyoContractDef(_Row):
    """
    An alliance contract of the daimyo event: one level of a contract rank.

    The contracts of one rank, in the table's order, are that rank's levels.

    Client: ``XmlSamuraiDaimyoContractVO.parseXml`` (bundle line 66377), keyed by id in
    ``SamuraiDaimyoDataXml.parseXml`` (bundle line 13914)
    """

    contract_id: DaimyoContractId = Field(validation_alias="id", description="The contract")
    rank: int = Field(default=-1, description="The contract rank it is a level of")
    enable_on_start: bool = Field(
        validation_alias="enableOnStart",
        default=False,
        description="Open from the event's start, not after another contract",
    )
    next_contract_id: DaimyoContractId = Field(
        validation_alias="nextContract",
        default=DaimyoContractId(-1),
        description="The contract after it; -1 for none",
    )
    shogun_points: int = Field(
        validation_alias="shogunPoints",
        default=-1,
        description="Shogun points it takes",
    )
    war_effort_points: int = Field(
        validation_alias="warEffortPoints",
        default=-1,
        description="War effort points it gives",
    )

    @field_validator("contract_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("rank", "next_contract_id", "shogun_points", "war_effort_points", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)

    @field_validator("enable_on_start", mode="before")
    @classmethod
    def _enabled(cls, value: object) -> bool:
        return _client_bool(value, False)


class RewardDef(_Row):
    """
    One reward of the items: what it gives, and to whom.

    ``collectables`` reads every collectable column of the row (see :meth:`Collectable.from_reward_row`),
    each ``add<currency name>`` column by the currency names GameData passes in as validation context
    (``currency_ids``); read without them, such a column is kept as ``OTHER``.

    Client: ``RewardVO.fillFromParamXml`` (bundle line 142368), read from the ``rewards`` table by
    ``CastleRewardData.parseXml`` (bundle line 142323)
    """

    reward_id: RewardId = Field(validation_alias="rewardID", description="The reward")
    grant_type: GameDataId[RewardGrantType] = Field(
        validation_alias="grantType",
        default=RewardGrantType.PLAYER,
        description="Who it goes to",
    )
    collectables: tuple[Collectable, ...] = Field(default=(), description="What it gives, in the client's order")

    @model_validator(mode="before")
    @classmethod
    def _read_collectables(cls, row: object, info: ValidationInfo) -> object:
        if not isinstance(row, dict) or "collectables" in row:
            return row
        currency_ids = (info.context or {}).get("currency_ids", {})
        return {**row, "collectables": Collectable.from_reward_row(row, currency_ids)}

    @field_validator("reward_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("grant_type", mode="before")
    @classmethod
    def _grant_type(cls, value: object) -> int:
        return _parse_int_or_default(value, RewardGrantType.PLAYER)


class TreasureMapDef(_Row):
    """
    A treasure map: a season event's map or one of the treasure hunt's, with its nodes and prices.

    Client: ``TreasureMapVO.fillFromParamXML`` (bundle line 140567), keyed by ``mapID`` in
    ``CastleTreasureMapData.parseTreasureMapXML`` (bundle line 140439)
    """

    map_id: GameDataId["TreasureMapId"] = Field(validation_alias="mapID", description="The map")
    label: str = Field(
        validation_alias="comment1", default="", description="Designer label the game does not read, e.g. hardmode"
    )
    note: str = Field(
        validation_alias="comment2", default="", description="Designer note the game does not read, e.g. Thornking"
    )
    node_ids: tuple[TreasureMapNodeId, ...] = Field(
        validation_alias="tmapnodeIDs", default=(), description="Its nodes, besides the start node"
    )
    end_node_id: TreasureMapNodeId = Field(
        validation_alias="endNodeID", default=TreasureMapNodeId(0), description="The node that ends the map"
    )
    map_type: GameDataId[TreasureMapType] = Field(
        validation_alias="maptype", default=TreasureMapType.SEASON, description="What the map is for"
    )
    kingdom: GameDataId[Kingdom] = Field(
        validation_alias="kID", default=Kingdom.GREEN, description="The kingdom a treasure hunt's map lies in"
    )
    total_pieces: int = Field(validation_alias="totalpieces", default=0, description="Pieces that make the map")
    piece_cost_rubies: int = Field(validation_alias="costpiece", default=0, description="Rubies a missing piece costs")
    travel_seconds: int = Field(
        validation_alias="travelTime", default=0, description="Seconds a transfer to a season map travels"
    )
    skip_cost_rubies: int = Field(
        validation_alias="skipCostC2", default=0, description="Rubies that skip a transfer to a season map"
    )
    package_ids: tuple[PackageId, ...] = Field(
        validation_alias="packages", default=(), description="The packages the map's shop sells"
    )

    @field_validator("map_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("label", "note", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)

    @field_validator("node_ids", "package_ids", mode="before")
    @classmethod
    def _ids(cls, value: object) -> list[int]:
        return _int_list(value, separator="+")

    @field_validator(
        "end_node_id", "map_type", "kingdom", "total_pieces", "piece_cost_rubies", "travel_seconds",
        "skip_cost_rubies", mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object, info: ValidationInfo) -> int:
        return _parse_int_or_default(value, cls.model_fields[str(info.field_name)].default)


class TreasureMapNodeDef(_Row):
    """
    A node of a treasure map: a camp, an obstacle or a port, and the nodes that unlock it.

    Client: ``TMapNodeVO.fillFromParamXML`` (bundle line 26934), keyed by ``tmapnodeID`` in
    ``CastleTreasureMapData.parseTreasureMapXML`` (bundle line 140431)
    """

    node_id: TreasureMapNodeId = Field(validation_alias="tmapnodeID", description="The node")
    node_type: str = Field(validation_alias="type", default="DUNGEON", description="What it is, e.g. DUNGEON or BRIDGE")
    unlocked_by_any: tuple[TreasureMapNodeId, ...] = Field(
        validation_alias="orUnlockIDs", default=(TreasureMapNodeId(0),), description="Any of these nodes unlocks it"
    )
    unlocked_by_all: tuple[TreasureMapNodeId, ...] = Field(
        validation_alias="andUnlockIDs", default=(TreasureMapNodeId(0),), description="All of these nodes unlock it"
    )
    count_victories: int = Field(
        validation_alias="countVictories", default=1, description="The victory count its camp is looked up by"
    )
    part_price_id: PartPayPriceId | None = Field(
        validation_alias="partPayPriceID",
        default=None,
        description="The price its obstacle is paid in parts; None for none",
    )
    position: int = Field(validation_alias="pos", default=0, description="Its place on the map")
    dungeon_level: int = Field(validation_alias="dungeonlevel", default=0, description="Its camp's level")
    cool_down: int = Field(validation_alias="coolDown", default=0, description="Seconds of cooldown after an attack")
    wall_bonus: int = Field(validation_alias="wallBonus", default=0, description="Wall protection, in percent")
    gate_bonus: int = Field(validation_alias="gateBonus", default=0, description="Gate protection, in percent")

    @field_validator("node_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("node_type", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value, "DUNGEON")

    @field_validator("unlocked_by_any", "unlocked_by_all", mode="before")
    @classmethod
    def _ids(cls, value: object) -> list[int]:
        return _int_list(value, "0", separator="+")

    @field_validator("part_price_id", mode="before")
    @classmethod
    def _price(cls, value: object) -> int | None:
        price = _parse_int_or_default(value, -1)
        return None if price < 0 else price

    @field_validator(
        "count_victories", "position", "dungeon_level", "cool_down", "wall_bonus", "gate_bonus", mode="before"
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object, info: ValidationInfo) -> int:
        return _parse_int_or_default(value, cls.model_fields[str(info.field_name)].default)


class PartPayPriceDef(_Row):
    """
    A price paid in parts: a season map's obstacle, a treasure map node's or a slum level's.

    ``costs`` reads the row's goods as a reward row's (see :meth:`Collectable.from_reward_row`).

    Client: ``PartpaypriceVO.fillFromParamXml`` (bundle line 142257)
    """

    part_price_id: PartPayPriceId = Field(validation_alias="partPayPriceID", description="The price")
    costs: tuple[Collectable, ...] = Field(default=(), description="What it costs, in the client's order")

    @model_validator(mode="before")
    @classmethod
    def _read_costs(cls, row: object, info: ValidationInfo) -> object:
        if not isinstance(row, dict) or "costs" in row:
            return row
        currency_ids = (info.context or {}).get("currency_ids", {})
        return {**row, "costs": Collectable.from_reward_row(row, currency_ids)}

    @field_validator("part_price_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)


class DonationItemDef(_Row):
    """
    What a donation event takes, and the points it gives. Its set, donation type and resource are not read.

    Client: ``DonationItemsVO.parseXmlNode`` (bundle line 111715), keyed by id in
    ``CastleDonationEventData.parseXml`` (bundle line 58843)
    """

    donation_item_id: DonationItemId = Field(validation_alias="donationItemID", description="The item")
    currency_id: GameDataId["CurrencyId"] = Field(
        validation_alias="currencyID", default=-1, description="The currency donated; -1 for a resource"
    )
    ratio: int = Field(default=-1, description="How many of it make a point")
    max_point_limit: int = Field(
        validation_alias="maxPointLimit", default=-1, description="Most points it gives; -1 for no limit"
    )

    @field_validator("donation_item_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("currency_id", "ratio", "max_point_limit", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)


class DonationSettingDef(_Row):
    """
    A donation event's run settings: which donation items it takes and which rewards it gives.

    The items and rewards are named by set: the ``donationItems`` rows and the ``donationRewards`` rows that
    share the set id.

    Client: ``DonationSettingVO.parseXmlNode`` (bundle line 111773), keyed by id in
    ``CastleDonationEventData.parseXml`` (bundle line 58833)
    """

    setting_id: DonationSettingId = Field(validation_alias="donationSettingID", description="The settings")
    item_set_id: int = Field(
        validation_alias="donationItemSetID", default=-1, description="The set of donation items it takes"
    )
    reward_set_id: int = Field(validation_alias="rewardSetID", default=-1, description="The set of rewards it gives")

    @field_validator("setting_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("item_set_id", "reward_set_id", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)


class TrainingProgramDef(_Row):
    """
    A training program of the officers' school: the bonus it gives against one event's targets, and its prices.

    Client: ``OfficersSchoolEffectVO.parseXml`` (bundle line 144770), keyed by id in ``OfficersSchoolData``
    (bundle line 144668)
    """

    program_id: TrainingProgramId = Field(validation_alias="id", description="The program")
    effect_id: GameDataId["Effect"] = Field(validation_alias="effectID", default=-1, description="The bonus it gives")
    event_id: GameDataId["Event"] = Field(validation_alias="eventID", default=-1, description="The event it is for")
    cost_coins: int = Field(validation_alias="c1Cost", default=-1, description="Coins its first slot costs")
    cost_rubies: int = Field(validation_alias="c2Cost", default=-1, description="Rubies its third slot costs")

    @field_validator("program_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("effect_id", "event_id", "cost_coins", "cost_rubies", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)


class EventDifficultyDef(_Row):
    """
    A difficulty an event offers, and what unlocking a locked one costs.

    Client: ``EventAutoScalingDifficultyVO.parseXML`` (bundle line 145390)
    """

    difficulty_id: EventDifficultyId = Field(validation_alias="difficultyID", description="The difficulty")
    event_id: GameDataId["Event"] = Field(validation_alias="eventID", default=0, description="The event it is for")
    difficulty_type: GameDataId["DifficultyType"] = Field(
        validation_alias="difficultyTypeID", default=0, description="Its type, e.g. easyPlus"
    )
    is_locked: bool = Field(validation_alias="isLocked", default=False, description="Whether it must be unlocked")
    unlock_rubies: int = Field(validation_alias="rentC2Cost", default=0, description="Rubies that unlock it")

    @field_validator("difficulty_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("event_id", "difficulty_type", "unlock_rubies", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("is_locked", mode="before")
    @classmethod
    def _flag(cls, value: object) -> bool:
        return _is_one(value)


class GachaDef(_Row):
    """
    A level of a gacha event: the pulls it covers and how many one buy may make.

    Client: ``GachaXmlVO.init`` (bundle line 113936), keyed by ``gachaID`` in ``GachaData.init`` (bundle line 113911)
    """

    gacha_id: GachaId = Field(validation_alias="gachaID", description="The gacha level")
    event_id: GameDataId["Event"] = Field(validation_alias="eventID", default=0, description="The gacha event")
    level: int = Field(validation_alias="gachaLevel", default=0, description="Its level in the event")
    min_pulls: int = Field(validation_alias="minPulls", default=0, description="Pulls made before it starts")
    max_pulls: int = Field(
        validation_alias="maxPulls", default=0, description="Pulls made when it ends; 0 when it never does"
    )
    multi_pull_max: int = Field(validation_alias="multiPullMax", default=0, description="Most pulls one buy makes")

    @field_validator("gacha_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("event_id", "level", "min_pulls", "max_pulls", "multi_pull_max", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)


class WheelOfFortuneRewardSetDef(_Row):
    """
    A Wheel of Fortune jackpot set: the rewards a jackpot spin can win.

    Client: ``LuckyWheelData.parseXml`` and ``createRewardItemsMappedToSetID`` (bundle lines 17571, 17583)
    """

    reward_set_id: WheelOfFortuneRewardSetId = Field(
        validation_alias="luckyWheelRewardSetID", description="The jackpot set"
    )
    reward_ids: tuple[RewardId, ...] = Field(validation_alias="rewardIDs", default=(), description="Its rewards")

    @field_validator("reward_set_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("reward_ids", mode="before")
    @classmethod
    def _ids(cls, value: object) -> list[int]:
        return _int_list(value)


class WheelOfFortuneWinClassDef(_Row):
    """
    A Wheel of Fortune win class: the spins to the next class, the rubies a skipped spin costs, and the previews.

    Client: ``LuckyWheelData.parseXml`` (bundle lines 17571-17576)
    """

    win_class_id: WheelOfFortuneWinClassId = Field(validation_alias="luckyWheelClassID", description="The win class")
    spins_to_next_class: int = Field(
        validation_alias="neededSpinsForNextClass", default=0, description="Spins that reach the next class"
    )
    rubies_per_skipped_spin: float = Field(
        validation_alias="C2PerSkippedSpin", default=0.0, description="Rubies each spin skipped to the next class costs"
    )
    preview_reward_ids: tuple[RewardId, ...] = Field(
        validation_alias="normalPreview", default=(), description="The rewards the wheel previews"
    )
    pro_mode_preview_reward_ids: tuple[RewardId, ...] = Field(
        validation_alias="hardcorePreview", default=(), description="The rewards the pro mode previews"
    )

    @field_validator("win_class_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("spins_to_next_class", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("rubies_per_skipped_spin", mode="before")
    @classmethod
    def _number(cls, value: object) -> float:
        number = js_number_or_none(_text(value, "0"))
        return 0.0 if number is None else float(number)

    @field_validator("preview_reward_ids", "pro_mode_preview_reward_ids", mode="before")
    @classmethod
    def _ids(cls, value: object) -> list[int]:
        return _int_list(value)


class OuterRealmsSettingDef(_Row):
    """
    An Outer Realms run's settings. Only some columns are read: the presets and rewards are not.

    Client: ``TempServerConfigurationVO.parseXML`` (bundle line 14448), keyed by ``settingID`` in
    ``CastleTempServerData`` (bundle line 140189)
    """

    setting_id: OuterRealmsSettingId = Field(validation_alias="settingID", description="The settings")
    peace_mode: bool = Field(validation_alias="peaceMode", default=False, description="Whether the run is peaceful")
    scoring_system: str = Field(validation_alias="scoringSystem", default="0", description="How it scores, e.g. might")
    start_currency_amount: int = Field(
        validation_alias="startCurrencyAmount", default=-1, description="The currency you start with; -1 for none"
    )
    currency_id: GameDataId["CurrencyId"] = Field(
        validation_alias="currencyID", default=0, description="The run's currency; 0 for none"
    )
    booster_package_id: PackageId = Field(
        validation_alias="boosterCurrencyPackageID",
        default=PackageId(0),
        description="The package that sells its booster currency; 0 for none",
    )

    @field_validator("setting_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("peace_mode", mode="before")
    @classmethod
    def _flag(cls, value: object) -> bool:
        return _is_one(value)

    @field_validator("scoring_system", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value, "0")

    @field_validator("start_currency_amount", "currency_id", "booster_package_id", mode="before")
    @classmethod
    def _int_column(cls, value: object, info: ValidationInfo) -> int:
        return _parse_int_or_default(value, cls.model_fields[str(info.field_name)].default)


class HorizonSettingDef(_Row):
    """
    A Beyond the Horizon run's settings. Only some columns are read: the presets, map and rewards are not.

    Client: ``AllianceBattleGroundConfigurationVO.parseXML`` (bundle line 145025), keyed by ``settingID`` in
    ``CastleAllianceBattleGroundData`` (bundle line 144859)
    """

    setting_id: HorizonSettingId = Field(validation_alias="settingID", description="The settings")
    max_alliance_size: int = Field(
        validation_alias="maxAllianceSize", default=0, description="Most members an alliance takes in"
    )
    currency_id: GameDataId["CurrencyId"] = Field(
        validation_alias="currencyID", default=0, description="The players' currency; 0 for none"
    )
    alliance_currency_id: GameDataId["CurrencyId"] = Field(
        validation_alias="allianceCurrencyID", default=0, description="The alliances' currency; 0 for none"
    )
    booster_package_id: PackageId = Field(
        validation_alias="boosterCurrencyPackageID",
        default=PackageId(0),
        description="The package that sells its booster currency; 0 for none",
    )
    tower_effects: tuple[GameDataId["AllianceTowerEffect"], ...] = Field(
        validation_alias="allianceTowerEffectIDs", default=(), description="The alliance tower effects on offer"
    )

    @field_validator("setting_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("max_alliance_size", "currency_id", "alliance_currency_id", "booster_package_id", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("tower_effects", mode="before")
    @classmethod
    def _ids(cls, value: object) -> list[int]:
        return _int_list(value)


class AllianceTowerEffectDef(_Row):
    """
    An alliance tower effect of Beyond the Horizon: the bonus it gives, and how its price and strength grow per level.

    Client: ``ABGAllianceTowerEffectXmlVO.parseXML`` (bundle line 145007)
    """

    tower_effect_id: GameDataId["AllianceTowerEffect"] = Field(
        validation_alias="allianceTowerEffectID", description="The tower effect"
    )
    effect_id: GameDataId["Effect"] = Field(validation_alias="effectID", default=0, description="The bonus it gives")
    base_price: int = Field(validation_alias="effectBasePrice", default=0, description="The price its levels grow from")
    max_level: int = Field(validation_alias="effectMaxLevel", default=0, description="Its highest level")
    start_value: float = Field(validation_alias="effectStartValue", default=0.0, description="Its strength at level 1")
    increase: float = Field(validation_alias="effectIncrease", default=0.0, description="Its strength's growth")

    @field_validator("tower_effect_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("effect_id", "base_price", "max_level", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("start_value", "increase", mode="before")
    @classmethod
    def _number(cls, value: object) -> float:
        number = js_parse_float(_text(value, "0"))
        return 0.0 if math.isnan(number) else number


class AllianceInvasionCampDef(_Row):
    """
    An alliance invasion camp, by the id an ``aic`` push names it with while its event scales no difficulty; with a
    difficulty chosen, that id is a scaling camp's (``GameData.scaling_camps``).

    The camp's defence, as the combat code reads it, is in ``GameData.camps["allianceInvasionCamps"]``.

    Client: ``CastleAllianceInvasionCampNodeVO.parseXML`` (bundle line 111195), keyed by id in
    ``CastleAllianceInvasionCampData`` (bundle line 111180), whose ``getAllianceCamp`` (bundle line 111182) looks up
    a scaling camp instead when the event's difficulty scaling is on (``AICCommand.executeCommand``, bundle line
    128192)
    """

    camp_id: AllianceInvasionCampId = Field(validation_alias="allianceInvasionCampID", description="The camp")
    event_id: GameDataId["Event"] = Field(validation_alias="eventID", default=0, description="The event it is for")
    dungeon_level: int = Field(validation_alias="dungeonlevel", default=0, description="Its level")
    rage_needed_for_level_up: int = Field(
        validation_alias="rageNeededForLevelUp", default=0, description="Alliance rage to its next level"
    )
    player_rage_cap: int = Field(validation_alias="playerRageCap", default=0, description="Most rage a player builds")
    wall_bonus: int = Field(validation_alias="wallBonus", default=0, description="Wall protection, in percent")
    gate_bonus: int = Field(validation_alias="gateBonus", default=0, description="Gate protection, in percent")
    count_victory: int = Field(validation_alias="countVictory", default=0, description="Its victory count")

    @field_validator("camp_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "event_id", "dungeon_level", "rage_needed_for_level_up", "player_rage_cap", "wall_bonus", "gate_bonus",
        "count_victory", mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)


def _reward_lists(value: object) -> list[list[int]]:
    """
    ``CollectableParser.createListsFromRewardIdsString`` (bundle line 40529): a list per ``,`` part, a part's ``#``
    pieces merged into one; a part with no reward id above 0 gives none.
    """
    if isinstance(value, list | tuple):
        return [list(part) for part in value]
    lists = [[i for i in _int_list(part, separator="#") if i > 0] for part in _text(value).split(",")]
    return [ids for ids in lists if ids]


class LeagueTypeEventDef(_Row):
    """
    One league's points thresholds and rewards in one event, for one reward set.

    A league score event takes the first row of its event, sub type and league whose set is its ``RSID``
    (any set while that is 0 or less).

    Client: ``ALeagueTypeScoreEventVO.parseAdditionalXmlFromRoot`` and ``parseLeagueTypeEventElement`` (bundle lines
    10268-10289); ``FactionEventVO.parseData`` (bundle line 7352) reads Berimond's rows by league and set
    """

    league_type_event_id: LeagueTypeEventId = Field(validation_alias="leaguetypeEventsID", description="The row")
    event_id: GameDataId["Event"] = Field(validation_alias="eventID", default=0, description="The event it is for")
    league_type_id: GameDataId["LeagueType"] = Field(
        validation_alias="leaguetypeID", default=0, description="The league it rewards"
    )
    sub_type: int = Field(validation_alias="subType", default=0, description="The event's sub type")
    reward_set_id: RewardSetId = Field(
        validation_alias="rewardSetID", default=RewardSetId(0), description="The reward set it belongs to"
    )
    needed_points: tuple[int, ...] = Field(
        validation_alias="neededPointsForRewards",
        default=(),
        description="The points each reward tier needs, before the event's point scale",
    )
    reward_ids: tuple[tuple[RewardId, ...], ...] = Field(
        validation_alias="rewardIDs",
        default=(),
        description="One reward list per ``,`` part, in the row's order",
    )
    top_x: tuple[int, ...] = Field(
        validation_alias="topXValue", default=(), description="The ranks the top-rank rewards go to"
    )
    hard_mode_start: int = Field(
        validation_alias="hardModeStart",
        default=0,
        description="Points above which the tiers are hard mode's; 0 for none",
    )
    alliance_reward_threshold_points: int = Field(
        validation_alias="allianceRewardThresholdPoints",
        default=0,
        description="Points a player needs for the alliance rewards",
    )

    @field_validator("league_type_event_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "event_id", "league_type_id", "sub_type", "reward_set_id", "hard_mode_start",
        "alliance_reward_threshold_points", mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("needed_points", "top_x", mode="before")
    @classmethod
    def _ints(cls, value: object) -> list[int]:
        return _int_list(value)

    @field_validator("reward_ids", mode="before")
    @classmethod
    def _rewards(cls, value: object) -> list[list[int]]:
        return _reward_lists(value)

    def rewards(self, *, game_data: GameData | None = None) -> tuple[tuple[Collectable, ...], ...]:
        """
        What each tier gives, in the order of :attr:`reward_ids`.

        Client: ``createListsFromRewardIdsString`` (bundle line 40529) builds each list with
        ``rewardData.getListById``
        """
        from empire_core.gamedata.data import GameData

        data = game_data if game_data is not None else GameData.require()
        return tuple(data.reward_list(ids) for ids in self.reward_ids)


class LeaderboardRewardDef(_Row):
    """
    The rewards of one rank band of an event's leaderboard, in one reward set.

    Client: ``LeaderboardRewardVO.fillFromParamXML`` (bundle line 112034), keyed by id in
    ``CastleLeaderBoardRewardsData`` (bundle line 112005)
    """

    leaderboard_reward_id: LeaderboardRewardId = Field(validation_alias="leaderboardRewardID", description="The row")
    event_id: GameDataId["Event"] = Field(validation_alias="eventTypeID", default=0, description="The event it is for")
    reward_set_id: LeaderboardRewardSetId = Field(
        validation_alias="leaderboardRewardSetID",
        default=LeaderboardRewardSetId(0),
        description="The reward set it belongs to",
    )
    max_rank: int = Field(validation_alias="maxRank", default=0, description="The lowest rank the band reaches")
    reward_ids: tuple[RewardId, ...] = Field(validation_alias="rewardIDs", default=(), description="Its rewards")
    league_type_id: GameDataId["LeagueType"] = Field(
        validation_alias="leagueID", default=-1, description="The league it is for; -1 for every league"
    )

    @field_validator("leaderboard_reward_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("event_id", "reward_set_id", "max_rank", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("league_type_id", mode="before")
    @classmethod
    def _league(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)

    @field_validator("reward_ids", mode="before")
    @classmethod
    def _ids(cls, value: object) -> list[int]:
        return _int_list(value)

    def rewards(self, *, game_data: GameData | None = None) -> tuple[Collectable, ...]:
        """
        What the band gives.

        Client: ``rewardData.getListByIdArray(rewardIDs)`` (``CastleLeaderBoardRewardsData.getRewardListForDialogList``,
        bundle line 112017)
        """
        from empire_core.gamedata.data import GameData

        data = game_data if game_data is not None else GameData.require()
        return data.reward_list(self.reward_ids)


class BerimondSpecialCampDef(_Row):
    """
    A Battle for Berimond special camp: a watchtower, a capital or the resource village, by the id map rows and the
    ``afd`` targets name it with.

    Client: ``FactionEventVO.parseAdditionalXmlFromRoot`` (bundle line 7398) reads ``specialcampID``, ``type`` and
    ``distance``, ``FactionTowerInfoVO.parseXML`` and ``FactionCapitalInfoVO.parseXML`` (bundle lines 88030, 88004)
    the lane, position, villages and unlocks. The level, attacks and loot columns are the server's: the client never
    reads them.
    """

    special_camp_id: GameDataId["BerimondSpecialCamp"] = Field(validation_alias="specialcampID", description="The camp")
    camp_type: GameDataKey[BerimondSpecialCampType] = Field(
        validation_alias="type", default="", description="What it is; empty for none"
    )
    distance: int = Field(default=0, description="Its distance")
    lane_id: GameDataId[BerimondLane] = Field(
        validation_alias="laneID", default=0, description="The lane it stands on; 0 for the resource village"
    )
    village_count: int = Field(validation_alias="villageCount", default=0, description="A watchtower's villages")
    sector_x: int = Field(validation_alias="CampPosX", default=0, description="Its x in the event's sector")
    sector_y: int = Field(validation_alias="CampPosY", default=0, description="Its y in the event's sector")
    unlock_ids: tuple[GameDataId["BerimondSpecialCamp"], ...] = Field(
        validation_alias="unlockIDs", default=(), description="A capital's camps, as the client lists them"
    )
    level: int = Field(validation_alias="dungeonlevel", default=0, description="Its level")
    attacks_until_destroyed: int = Field(
        validation_alias="attacksUntilDestroyed", default=0, description="The attacks that destroy it; 0 for none"
    )
    loot_coins: int = Field(validation_alias="lootc1", default=0, description="The coins it lists as loot")
    loot_rubies: int = Field(validation_alias="lootc2", default=0, description="The rubies it lists as loot")
    loot_wood: int = Field(validation_alias="lootWood", default=0, description="The wood it lists as loot")
    loot_stone: int = Field(validation_alias="lootStone", default=0, description="The stone it lists as loot")
    loot_food: int = Field(validation_alias="lootFood", default=0, description="The food it lists as loot")
    loot_mead: int = Field(validation_alias="lootMead", default=0, description="The mead it lists as loot")
    loot_beef: int = Field(validation_alias="lootBeef", default=0, description="The beef it lists as loot")

    @field_validator("special_camp_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "distance",
        "lane_id",
        "village_count",
        "sector_x",
        "sector_y",
        "level",
        "attacks_until_destroyed",
        "loot_coins",
        "loot_rubies",
        "loot_wood",
        "loot_stone",
        "loot_food",
        "loot_mead",
        "loot_beef",
        mode="before",
    )
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("camp_type", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)

    @field_validator("unlock_ids", mode="before")
    @classmethod
    def _ids(cls, value: object) -> list[int]:
        return _int_list(value)


__all__ = [
    "BerimondSpecialCampDef",
    "LeaderboardRewardDef",
    "LeaderboardRewardId",
    "LeaderboardRewardSetId",
    "LeagueTypeEventDef",
    "LeagueTypeEventId",
    "RewardSetId",
    "row_id",
    "is_cost_column",
    "ConstructionItemRecipeId",
    "CraftingQueueDef",
    "CraftingQueueId",
    "CraftingRecipeDef",
    "CraftingRecipeId",
    "FusionForgeDef",
    "FusionSystemDef",
    "JudgementDef",
    "PrebuiltCastleDef",
    "PrivateVillageDef",
    "SpecialServerPrebuiltCastleDef",
    "StartResourcesDef",
    "StartResourcesId",
    "AllianceInvasionCampDef",
    "AllianceInvasionCampId",
    "AllianceTowerEffectDef",
    "DaimyoContractId",
    "DonationItemDef",
    "DonationItemId",
    "DonationSettingDef",
    "DonationSettingId",
    "EventDifficultyDef",
    "EventDifficultyId",
    "GachaDef",
    "GachaId",
    "HorizonSettingDef",
    "HorizonSettingId",
    "OuterRealmsSettingDef",
    "OuterRealmsSettingId",
    "PartPayPriceDef",
    "PartPayPriceId",
    "ScalingCampId",
    "TrainingProgramDef",
    "TrainingProgramId",
    "TreasureMapDef",
    "TreasureMapNodeDef",
    "TreasureMapNodeId",
    "WheelOfFortuneRewardSetDef",
    "WheelOfFortuneRewardSetId",
    "WheelOfFortuneWinClassDef",
    "WheelOfFortuneWinClassId",
    "CoatOfArmsSymbolDef",
    "CoatOfArmsSymbolId",
    "PackageDef",
    "PackageId",
    "PlayerNameChangeDef",
    "RewardDef",
    "RewardId",
    "AchievementCondition",
    "AchievementDef",
    "AllianceCrestColorDef",
    "AllianceCrestLayoutDef",
    "BuildingDef",
    "DailyQuestDef",
    "DaimyoContractDef",
    "DifficultyTypeDef",
    "EquipmentGroupDef",
    "EventDef",
    "LootBoxDef",
    "LootBoxTypeDef",
    "GeneralRarityDef",
    "GeneralsHubCharacterDef",
    "GemColorDef",
    "QuestCondition",
    "QuestDef",
    "ResearchDef",
    "ConstructionItemRecipeDef",
    "ScalingCampDef",
    "TitleDef",
]
