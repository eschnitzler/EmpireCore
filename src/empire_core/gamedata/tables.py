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

import sys
from typing import TYPE_CHECKING, NewType

from pydantic import Field, ValidationInfo, field_validator, model_validator

from empire_core.enums import (
    BuildingGroundType,
    BuildingGroup,
    EquipmentSlot,
    Kingdom,
    MapItemType,
    QuestConditionType,
    RewardGrantType,
    TitleDisplayType,
    TitleSystem,
    WearerType,
)
from empire_core.protocol.js import js_falsy, js_int, js_number_or_none, js_parse_int, js_string

from .collectables import _XML_COST_PREFIX, Collectable
from .lenient import GameDataId, GameDataKey
from .models import READING_CACHE, EffectSpecRow, EffectValue, _parse_int_or_default, _Row

if TYPE_CHECKING:
    from .data import GameData
    from .ids import (
        Achievement,
        AllianceCrestColor,
        AllianceCrestLayout,
        Building,
        ConstructionItem,
        DailyQuestId,
        DifficultyType,
        EquipmentGroup,
        Event,
        LootBox,
        LootBoxType,
        QuestId,
        Research,
        SceatSkill,
        Title,
    )


RewardId = NewType("RewardId", int)
"""The id of a ``rewards`` row, whose collectables :meth:`GameData.reward_list` gives.

The rows have no name, so no generated enum names them; this type marks the id space instead.
"""


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


def _int_list(value: object, default: str = "") -> list[int]:
    """
    ``CastleXMLUtils.createIntListFromString`` (bundle line 1038): ``parseInt`` of each non-empty ``,`` part.

    A part with no leading integer, which the client keeps as NaN, is left out.
    """
    if isinstance(value, list | tuple):
        return list(value)
    text = default if js_falsy(value) else js_string(value)
    return [number for part in text.split(",") if part and (number := js_parse_int(part)) is not None]


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
    ``tempServerCostWood`` and ``tempServerCostStone`` (temporary server repair costs).

    Client: ``AVisualVO.parseXmlNode`` (bundle line 17800), ``AShopVO.parseXmlNode`` (bundle lines
    31713-31715), ``ABasicBuildingVO.parseXmlNode``, ``parseEffects`` and
    ``parseAreaSpecificEffects`` (bundle lines 17842-17864)
    """

    building_id: GameDataId["Building"] = Field(
        validation_alias="wodID", serialization_alias="wodID", description="The building"
    )
    name: str = Field(default="", description="Building name, shared across levels, e.g. Keep")
    group: GameDataKey[BuildingGroup] = Field(default="", description="Building group, e.g. Building or Tower")
    building_type: str = Field(
        validation_alias="type",
        serialization_alias="type",
        default="",
        description="Building type, e.g. Level1; empty for none",
    )
    level: int = Field(default=-1, description="Upgrade level; -1 when the row has none")
    required_level: int = Field(
        validation_alias="requiredLevel",
        serialization_alias="requiredLevel",
        default=0,
        description="Player level needed to build it",
    )
    required_legend_level: int = Field(
        validation_alias="requiredLegendLevel",
        serialization_alias="requiredLegendLevel",
        default=0,
        description="Legend level needed to build it",
    )
    early_unlock_required_level: int = Field(
        validation_alias="earlyUnlockRequiredLevel",
        serialization_alias="earlyUnlockRequiredLevel",
        default=0,
        description="Player level from which it can be unlocked early",
    )
    upgrade_building_id: GameDataId["Building"] = Field(
        validation_alias="upgradeWodID",
        serialization_alias="upgradeWodID",
        default=0,
        description="The building it upgrades to; 0 for none",
    )
    downgrade_building_id: GameDataId["Building"] = Field(
        validation_alias="downgradeWodID",
        serialization_alias="downgradeWodID",
        default=0,
        description="The building it downgrades to; 0 for none",
    )
    shop_category: str = Field(
        validation_alias="shopCategory",
        serialization_alias="shopCategory",
        default="NOT_IN_SHOP",
        description="Build menu category; NOT_IN_SHOP for none",
    )
    xp: int = Field(default=0, description="Experience for building it")
    might_value: int = Field(
        validation_alias="mightValue", serialization_alias="mightValue", default=0, description="Might points it gives"
    )
    storeable: bool = Field(default=False, description="It can be put into storage")
    maximum_count: int = Field(
        validation_alias="maximumCount",
        serialization_alias="maximumCount",
        default=1_000_000,
        description="How many a castle may have",
    )
    destructable: bool = Field(default=True, description="It can be torn down")
    temp_server_destructable: bool = Field(
        validation_alias="tempServerDestructable",
        serialization_alias="tempServerDestructable",
        default=True,
        description="It can be torn down on a temporary server",
    )
    is_battle_ground: bool = Field(
        validation_alias="isBattleGround",
        serialization_alias="isBattleGround",
        default=False,
        description="Built on a battle ground only",
    )
    is_not_battle_ground: bool = Field(
        validation_alias="isNotBattleGround",
        serialization_alias="isNotBattleGround",
        default=False,
        description="Never built on a battle ground",
    )
    slum_level_needed: int = Field(
        validation_alias="slumLevelNeeded",
        serialization_alias="slumLevelNeeded",
        default=0,
        description="Slum level needed to build it",
    )
    needs_construction_expert: bool = Field(
        validation_alias="constructionExpert",
        serialization_alias="constructionExpert",
        default=False,
        description="Building it needs the construction expert",
    )
    sell_coins: int = Field(
        validation_alias="sellC1", serialization_alias="sellC1", default=0, description="Coins for selling it"
    )
    cost_rubies: int = Field(
        validation_alias="costC2",
        serialization_alias="costC2",
        default=0,
        description="Rubies it costs to build or upgrade to",
    )
    sort_order: float = Field(
        validation_alias="sortOrder",
        serialization_alias="sortOrder",
        default=1_000_000,
        description="Order in the build menu; a value that is no number sorts last",
    )
    only_in_area_types: tuple[GameDataId[MapItemType], ...] = Field(
        validation_alias="onlyInAreaTypes",
        serialization_alias="onlyInAreaTypes",
        default=(),
        description="The castle types it may be built in; empty for any",
    )
    only_in_kingdoms: tuple[GameDataId[Kingdom], ...] = Field(
        validation_alias="kIDs",
        serialization_alias="kIDs",
        default=(),
        description="The kingdoms it may be built in; empty for every kingdom",
    )
    only_in_event_ids: tuple[GameDataId["Event"], ...] = Field(
        validation_alias="eventIDs",
        serialization_alias="eventIDs",
        default=(),
        description="The events it may be built in; empty for none in particular",
    )
    available_in_map_ids: tuple[int, ...] = Field(
        validation_alias="mapIDs",
        serialization_alias="mapIDs",
        default=(),
        description="The maps it may be built on; empty for any",
    )
    sceat_skill_id: GameDataId["SceatSkill"] = Field(
        validation_alias="sceatSkillLocked",
        serialization_alias="sceatSkillLocked",
        default=0,
        description="The sceat skill that unlocks it; 0 for none",
    )
    construction_item_group_ids: tuple[int, ...] = Field(
        validation_alias="constructionItemGroupIDs",
        serialization_alias="constructionItemGroupIDs",
        default=(),
        description="The construction item groups it takes",
    )
    low_level_build_durations: tuple[int, ...] = Field(
        validation_alias="lowLevelBuildDuration",
        serialization_alias="lowLevelBuildDuration",
        default=(),
        description="Build times in seconds at the lowest player levels",
    )
    low_level_main_castle_cost_rubies: tuple[int, ...] = Field(
        validation_alias="lowLevelMainCastleCostC2",
        serialization_alias="lowLevelMainCastleCostC2",
        default=(),
        description="Ruby costs in the main castle at the lowest player levels",
    )
    effect_locked: bool = Field(
        validation_alias="effectLocked",
        serialization_alias="effectLocked",
        default=False,
        description="Its effects need unlocking",
    )
    wall_bonus: int = Field(
        validation_alias="wallBonus",
        serialization_alias="wallBonus",
        default=0,
        description="Wall protection, in percent",
    )
    moat_bonus: int = Field(
        validation_alias="moatBonus",
        serialization_alias="moatBonus",
        default=0,
        description="Moat protection, in percent",
    )
    build_duration: int = Field(
        validation_alias="buildDuration",
        serialization_alias="buildDuration",
        default=0,
        description="Build time in seconds",
    )
    building_ground_type: GameDataKey[BuildingGroundType] = Field(
        validation_alias="buildingGroundType",
        serialization_alias="buildingGroundType",
        default=BuildingGroundType.NONE,
        description="The ground it stands on",
    )
    district_type_id: int = Field(
        validation_alias="districtTypeID",
        serialization_alias="districtTypeID",
        default=0,
        description="The district type it belongs to",
    )
    is_district: bool = Field(
        validation_alias="isDistrict", serialization_alias="isDistrict", default=False, description="It is a district"
    )
    is_relic_building: bool = Field(
        validation_alias="isRelicBuilding",
        serialization_alias="isRelicBuilding",
        default=False,
        description="It is a relic building",
    )
    area_specific_effects: tuple[EffectValue, ...] = Field(
        validation_alias="areaSpecificEffects",
        serialization_alias="areaSpecificEffects",
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
        "storeable", "destructable", "temp_server_destructable", "is_battle_ground", "is_not_battle_ground",
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


_TEMP_SERVER_COST_PREFIX = "globalServerCost"
"""The prefix of a research's temporary server cost columns (``AResearchVO.fillFromParamXML``, bundle line 61509)."""


def is_research_cost_column(column: str) -> bool:
    """Whether a ``researches`` column is a cost: ``cost<name>`` or ``globalServerCost<name>``."""
    return column.startswith((_XML_COST_PREFIX, _TEMP_SERVER_COST_PREFIX))


class ResearchDef(EffectSpecRow):
    """
    One level of a research.

    ``costs`` and ``temp_server_costs`` read every cost column of the row (see
    :meth:`Collectable.from_columns`), a currency named by its ``Name`` (``costLegendaryToken``) by the
    currency names GameData passes in as validation context (``currency_ids``).

    Client: ``AResearchVO.fillFromParamXML`` (bundle lines 61502-61516); ``getBaseCosts`` (bundle line
    61530) picks ``temp_server_costs`` on a temporary server, and ``getFinalCosts`` (bundle line 61531)
    applies discounts to them
    """

    research_id: GameDataId["Research"] = Field(
        validation_alias="researchID", serialization_alias="researchID", description="The research"
    )
    label: str = Field(
        validation_alias="comment2",
        serialization_alias="comment2",
        default="",
        description="Designer label the game does not read, e.g. recruitment speed",
    )
    group_id: int = Field(
        validation_alias="groupID",
        serialization_alias="groupID",
        default=-1,
        description="The group the research's levels share",
    )
    level: int = Field(default=-1, description="Research level")
    prerequisite_ids: tuple[GameDataId["Research"], ...] = Field(
        validation_alias="prerequisiteIDs",
        serialization_alias="prerequisiteIDs",
        default=(),
        description="Researches it needs first",
    )
    min_research_tower_level: int = Field(
        validation_alias="minResearchTowerLevel",
        serialization_alias="minResearchTowerLevel",
        default=1,
        description="Research tower level it needs",
    )
    required_level: int = Field(
        validation_alias="requiredLevel",
        serialization_alias="requiredLevel",
        default=0,
        description="Player level it needs",
    )
    required_legend_level: int = Field(
        validation_alias="requiredLegendLevel",
        serialization_alias="requiredLegendLevel",
        default=0,
        description="Legend level it needs",
    )
    research_duration: int = Field(
        validation_alias="researchDuration",
        serialization_alias="researchDuration",
        default=0,
        description="Research time in seconds",
    )
    temp_server_research_duration: int = Field(
        validation_alias="globalServerResearchDuration",
        serialization_alias="globalServerResearchDuration",
        default=0,
        description="Research time on a temporary server",
    )
    only_with_research_expert: bool = Field(
        validation_alias="onlyWithResearchExpert",
        serialization_alias="onlyWithResearchExpert",
        default=False,
        description="It needs the research expert",
    )
    cost_rubies: int = Field(
        validation_alias="costC2", serialization_alias="costC2", default=0, description="Rubies it costs"
    )
    costs: tuple[Collectable, ...] = Field(
        default=(), description="What it costs, in the items' order: resources, coins, rubies, tokens, ..."
    )
    temp_server_costs: tuple[Collectable, ...] = Field(default=(), description="What it costs on a temporary server")

    @model_validator(mode="before")
    @classmethod
    def _read_costs(cls, row: object, info: ValidationInfo) -> object:
        if not isinstance(row, dict) or "costs" in row:
            return row
        currency_ids = (info.context or {}).get("currency_ids", {})
        return {
            **row,
            "costs": Collectable.from_columns(row, _XML_COST_PREFIX, currency_ids),
            "temp_server_costs": Collectable.from_columns(row, _TEMP_SERVER_COST_PREFIX, currency_ids),
        }

    @field_validator("research_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "group_id", "level", "min_research_tower_level", "required_level", "required_legend_level",
        "research_duration", "temp_server_research_duration", "cost_rubies", mode="before",
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

    Client: ``ASpecialEventVO.parseBasicsFromXmlNode`` (bundle lines 2959-2974)
    """

    event_id: GameDataId["Event"] = Field(
        validation_alias="eventID", serialization_alias="eventID", description="The event"
    )
    event_type: str = Field(
        validation_alias="eventType",
        serialization_alias="eventType",
        default="",
        description="Event type, e.g. NomadInvasion",
    )
    min_level: int = Field(
        validation_alias="minLevel",
        serialization_alias="minLevel",
        default=0,
        description="Lowest player level that sees it",
    )
    max_level: int = Field(
        validation_alias="maxLevel",
        serialization_alias="maxLevel",
        default=99,
        description="Highest player level that sees it",
    )
    open_with_login: bool = Field(
        validation_alias="openWithLogin",
        serialization_alias="openWithLogin",
        default=False,
        description="Its dialog opens on login",
    )
    sort_order: int = Field(
        validation_alias="sortOrder", serialization_alias="sortOrder", default=0, description="Order among the events"
    )
    crossplay_min_level: int = Field(
        validation_alias="crossplayMinLevel",
        serialization_alias="crossplayMinLevel",
        default=-1,
        description="Lowest level on a crossplay server; -1 for none",
    )
    extension_unlock: int = Field(
        validation_alias="eventExtensionUnlock",
        serialization_alias="eventExtensionUnlock",
        default=0,
        description="Its extension unlock",
    )
    kingdoms: tuple[GameDataId[Kingdom], ...] = Field(
        validation_alias="kIDs",
        serialization_alias="kIDs",
        default=(Kingdom.GREEN,),
        description="The kingdoms it runs in",
    )
    area_types: tuple[GameDataId[MapItemType], ...] = Field(
        validation_alias="areaTypes",
        serialization_alias="areaTypes",
        default=(MapItemType.CASTLE,),
        description="The castle types it counts in",
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

    @field_validator("event_type", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)


class LootBoxDef(_Row):
    """
    A loot box.

    Client: ``LootBoxVO.parseXML`` (bundle line 112502)
    """

    loot_box_id: GameDataId["LootBox"] = Field(
        validation_alias="lootBoxID", serialization_alias="lootBoxID", description="The loot box"
    )
    name: str = Field(default="", description="Internal name, e.g. MysteryBoxBronze")
    loot_box_type_id: GameDataId["LootBoxType"] = Field(
        validation_alias="lootBoxTypeID", serialization_alias="lootBoxTypeID", default=0, description="Its type"
    )
    tombola_id: int = Field(
        validation_alias="lootBoxTombolaID",
        serialization_alias="lootBoxTombolaID",
        default=0,
        description="The tombola it draws from",
    )
    key_tombola_id: int = Field(
        validation_alias="lootBoxKeyTombolaID",
        serialization_alias="lootBoxKeyTombolaID",
        default=0,
        description="The tombola its keys draw from",
    )
    rarity: int = Field(default=0, description="Rarity")
    draws: int = Field(default=0, description="Draws per opening")
    sort_order: int = Field(
        validation_alias="sortOrder",
        serialization_alias="sortOrder",
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
        validation_alias="lootBoxTypeID", serialization_alias="lootBoxTypeID", description="The loot box type"
    )
    theme: str = Field(
        validation_alias="lootBoxTheme",
        serialization_alias="lootBoxTheme",
        default="",
        description="Its theme, e.g. MysteryBox",
    )
    key_payout_threshold: int = Field(
        validation_alias="lootBoxKeyPayoutThreshold",
        serialization_alias="lootBoxKeyPayoutThreshold",
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


class EquipmentGroupDef(_Row):
    """
    An equipment item group, as equipment effects name them.

    Client: ``XmlEquipmentGroupVO.parseXml`` (bundle line 144187)
    """

    group_id: GameDataId["EquipmentGroup"] = Field(
        validation_alias="itemGroupID", serialization_alias="itemGroupID", description="The item group"
    )
    name: str = Field(default="", description="Internal name, e.g. AttackPVP")
    wearer_id: GameDataId[WearerType] = Field(
        validation_alias="wearerID", serialization_alias="wearerID", default=-1, description="Who wears it; -1 for any"
    )
    slot_id: GameDataId[EquipmentSlot] = Field(
        validation_alias="slotID", serialization_alias="slotID", default=-1, description="The slot it goes in"
    )
    pic_id: int = Field(validation_alias="picID", serialization_alias="picID", default=-1, description="Its picture")
    drop_rate: int = Field(
        validation_alias="dropRate", serialization_alias="dropRate", default=-1, description="Its drop rate"
    )

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
        validation_alias="difficultyTypeID", serialization_alias="difficultyTypeID", description="The type"
    )
    name: str = Field(default="", description="Internal name, e.g. easyPlus")
    sort_order: int = Field(
        validation_alias="sortOrder", serialization_alias="sortOrder", default=0, description="Order among the types"
    )

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

    quest_id: GameDataId["QuestId"] = Field(
        validation_alias="questID", serialization_alias="questID", description="The quest"
    )
    series_id: int = Field(
        validation_alias="questSeriesID",
        serialization_alias="questSeriesID",
        default=-1,
        description="The quest series; -1 for none",
    )
    series_number: int = Field(
        validation_alias="questSeriesNumber",
        serialization_alias="questSeriesNumber",
        default=1,
        description="Its place in the series",
    )
    quests_in_series: int = Field(
        validation_alias="numberOfQuestsInSeries",
        serialization_alias="numberOfQuestsInSeries",
        default=0,
        description="Quests in the series",
    )
    shown_kingdom: GameDataId[Kingdom] = Field(
        validation_alias="shownKingdomID",
        serialization_alias="shownKingdomID",
        default=Kingdom.GREEN,
        description="The kingdom it is shown in",
    )
    trigger_kingdom: GameDataId[Kingdom] = Field(
        validation_alias="triggerKingdomID",
        serialization_alias="triggerKingdomID",
        default=Kingdom.GREEN,
        description="The kingdom it counts in, as the row has it",
    )
    hidden: bool = Field(default=False, description="It is not shown")
    map_id: int = Field(
        validation_alias="mapID",
        serialization_alias="mapID",
        default=-1,
        description="The map it belongs to; -1 for none",
    )
    required_level: int = Field(
        validation_alias="requiredLevel",
        serialization_alias="requiredLevel",
        default=0,
        description="Player level it needs",
    )
    required_legend_level: int = Field(
        validation_alias="requiredLegendLevel",
        serialization_alias="requiredLegendLevel",
        default=0,
        description="Legend level it needs",
    )
    required_quest_id: GameDataId["QuestId"] = Field(
        validation_alias="requiredQuestID",
        serialization_alias="requiredQuestID",
        default=-1,
        description="The quest it needs first; -1 for none",
    )
    quest_giver_id: int = Field(
        validation_alias="questGiverID",
        serialization_alias="questGiverID",
        default=0,
        description="The character who gives it",
    )
    event_id: GameDataId["Event"] = Field(
        validation_alias="eventID",
        serialization_alias="eventID",
        default=0,
        description="The event it belongs to; 0 for none",
    )
    duration: int = Field(default=-1, description="Seconds it runs; -1 for no limit")
    objective_type: int = Field(
        validation_alias="objectiveType",
        serialization_alias="objectiveType",
        default=0,
        description="Its objective type",
    )
    auto_show: bool = Field(
        validation_alias="autoShow", serialization_alias="autoShow", default=False, description="It opens on its own"
    )
    sort_priority: int | None = Field(
        validation_alias="sortPriority",
        serialization_alias="sortPriority",
        default=None,
        description="Order in the quest book; None sorts last",
    )
    cost_rubies: int = Field(
        validation_alias="c2Cost", serialization_alias="c2Cost", default=0, description="Rubies to finish it at once"
    )
    questbook_tab_id: int = Field(
        validation_alias="questbookTabID",
        serialization_alias="questbookTabID",
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

    quest_id: GameDataId["DailyQuestId"] = Field(
        validation_alias="dailyQuestID", serialization_alias="dailyQuestID", description="The daily quest"
    )
    trigger_kingdom: GameDataId[Kingdom] = Field(
        validation_alias="triggerKingdomID",
        serialization_alias="triggerKingdomID",
        default=Kingdom.GREEN,
        description="The kingdom it counts in; -1 for any",
    )
    is_temp_server_quest: bool = Field(
        validation_alias="isTempServerQuest",
        serialization_alias="isTempServerQuest",
        default=False,
        description="It runs on temporary servers",
    )
    daily_task_points: int = Field(
        validation_alias="addDailyDutyPoints",
        serialization_alias="addDailyDutyPoints",
        default=0,
        description="Daily task points it gives",
    )
    level_calculated: bool = Field(
        validation_alias="levelCalculated",
        serialization_alias="levelCalculated",
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

    @field_validator("is_temp_server_quest", mode="before")
    @classmethod
    def _temp_server(cls, value: object) -> bool:
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

    title_id: GameDataId["Title"] = Field(
        validation_alias="titleID", serialization_alias="titleID", description="The title"
    )
    title_system: GameDataKey[TitleSystem] = Field(
        validation_alias="type", serialization_alias="type", default="-1", description="Its title system"
    )
    threshold: int = Field(default=-1, description="Points from which it is held; -1 for a top-X title")
    display_type: GameDataKey[TitleDisplayType] = Field(
        validation_alias="displayType",
        serialization_alias="displayType",
        default="-1",
        description="Whether it goes before or after the name",
    )
    forced: bool = Field(default=False, description="It is a forced title")
    decay: int = Field(default=-1, description="Its point decay")
    is_positive: bool = Field(
        validation_alias="isPositive",
        serialization_alias="isPositive",
        default=False,
        description="It is a positive title",
    )
    top_x: int = Field(
        validation_alias="topX",
        serialization_alias="topX",
        default=-1,
        description="The top ranks that hold it; -1 or 0 for a points title",
    )
    previous_title_id: GameDataId["Title"] = Field(
        validation_alias="previousTitleID",
        serialization_alias="previousTitleID",
        default=-1,
        description="The title below it in its system; -1 for the first",
    )
    reward_id: RewardId = Field(
        validation_alias="rewardID",
        serialization_alias="rewardID",
        default=RewardId(-1),
        description="Its reward, whose collectables GameData.reward_list gives; -1 for none",
    )
    might_value: int = Field(
        validation_alias="mightValue", serialization_alias="mightValue", default=-1, description="Might points it gives"
    )

    def rewards(self, data: GameData) -> tuple[Collectable, ...]:
        """
        What holding the title gives; nothing when it has no reward.

        Client: ``CastleTitleSystemHelper.getTitleRewardText`` reads ``getListById(rewardID)`` when it is
        above -1 (bundle line 4444)
        """
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

    achievement_id: GameDataId["Achievement"] = Field(
        validation_alias="achievementID", serialization_alias="achievementID", description="The achievement"
    )
    series_id: int = Field(
        validation_alias="achievementSeriesID",
        serialization_alias="achievementSeriesID",
        default=0,
        description="The series it is a step of",
    )
    series_number: int = Field(
        validation_alias="achievementSeriesNumber",
        serialization_alias="achievementSeriesNumber",
        default=0,
        description="Its step in the series",
    )
    achievements_in_series: int = Field(
        validation_alias="numberOfAchievementsInSeries",
        serialization_alias="numberOfAchievementsInSeries",
        default=0,
        description="Steps in the series",
    )
    required_achievement_id: GameDataId["Achievement"] = Field(
        validation_alias="requiredAchievementID",
        serialization_alias="requiredAchievementID",
        default=0,
        description="The step before it; -1 or 0 for none",
    )
    achievement_points: int = Field(
        validation_alias="achievementPoints",
        serialization_alias="achievementPoints",
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

    color_id: GameDataId["AllianceCrestColor"] = Field(
        validation_alias="allianceCoatColorID", serialization_alias="allianceCoatColorID", description="The colour"
    )
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
        validation_alias="allianceCoatLayoutID", serialization_alias="allianceCoatLayoutID", description="The layout"
    )
    color_count: int = Field(
        validation_alias="noofColors", serialization_alias="noofColors", default=0, description="Colours it takes"
    )
    event_id: GameDataId["Event"] = Field(
        validation_alias="eventID",
        serialization_alias="eventID",
        default=0,
        description="The event that awards it; 0 for none",
    )
    max_duration: int = Field(
        validation_alias="maxDuration",
        serialization_alias="maxDuration",
        default=0,
        description="Seconds it is held once won; 0 for a layout that does not expire",
    )
    effect_icon_id: int = Field(
        validation_alias="effectIconID",
        serialization_alias="effectIconID",
        default=0,
        description="The icon its bonus shows",
    )
    label: str = Field(
        validation_alias="comment1",
        serialization_alias="comment1",
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

    recipe_id: int = Field(
        validation_alias="constructionItemRecipeID",
        serialization_alias="constructionItemRecipeID",
        description="The recipe, as a research unlocks it",
    )
    blueprint_id: int = Field(
        validation_alias="blueprintID",
        serialization_alias="blueprintID",
        default=0,
        description="The blueprint it belongs to",
    )
    construction_item_id: GameDataId["ConstructionItem"] = Field(
        validation_alias="constructionItemID",
        serialization_alias="constructionItemID",
        default=0,
        description="The construction item it crafts",
    )

    @field_validator("recipe_id", "blueprint_id", "construction_item_id", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)


class ScalingCampDef(_Row):
    """
    A camp of an event's difficulty scaling: the level and costs a chosen difficulty gives it.

    Client: ``DifficultyScalingCampXmlVO.parseXML`` (bundle line 145227), keyed by id in
    ``CastleEventDifficultyScalingData`` (bundle line 145211)
    """

    scaling_camp_id: int = Field(
        validation_alias="eventAutoScalingCampID",
        serialization_alias="eventAutoScalingCampID",
        description="The scaling camp, as map rows name it",
    )
    rank: int = Field(default=0, description="Its rank")
    level: int = Field(
        validation_alias="camplevel", serialization_alias="camplevel", default=0, description="The camp level it gives"
    )
    cool_down: int = Field(
        validation_alias="coolDown",
        serialization_alias="coolDown",
        default=0,
        description="Cooldown in seconds after an attack",
    )
    event_id: GameDataId["Event"] = Field(
        validation_alias="eventID", serialization_alias="eventID", default=0, description="The event it belongs to"
    )
    cooldown_increase: int = Field(
        validation_alias="cooldownIncrease",
        serialization_alias="cooldownIncrease",
        default=0,
        description="Cooldown added per attack",
    )
    cooldown_increase_cap: int = Field(
        validation_alias="cooldownIncreaseCap",
        serialization_alias="cooldownIncreaseCap",
        default=0,
        description="Most cooldown added",
    )
    skip_cost: int = Field(
        validation_alias="skipCosts",
        serialization_alias="skipCosts",
        default=0,
        description="Cost to skip the cooldown",
    )
    skip_cost_increase: int = Field(
        validation_alias="skipCostIncrease",
        serialization_alias="skipCostIncrease",
        default=0,
        description="Skip cost added per attack",
    )
    skip_cost_increase_cap: int = Field(
        validation_alias="skipCostIncreaseCap",
        serialization_alias="skipCostIncreaseCap",
        default=0,
        description="Most skip cost added",
    )
    wall_bonus: int = Field(
        validation_alias="wallBonus",
        serialization_alias="wallBonus",
        default=0,
        description="Wall protection, in percent",
    )
    gate_bonus: int = Field(
        validation_alias="gateBonus",
        serialization_alias="gateBonus",
        default=0,
        description="Gate protection, in percent",
    )
    moat_bonus: int = Field(
        validation_alias="moatBonus",
        serialization_alias="moatBonus",
        default=0,
        description="Moat protection, in percent",
    )
    unit_capacity: int = Field(
        validation_alias="unitCapacity", serialization_alias="unitCapacity", default=0, description="Units it holds"
    )
    shogun_points_needed_for_level_up: int = Field(
        validation_alias="shogunPointsNeededForLevelUp",
        serialization_alias="shogunPointsNeededForLevelUp",
        default=-1,
        description="Shogun points to the next level; -1 for none",
    )
    player_rage_cap: int = Field(
        validation_alias="playerRageCap",
        serialization_alias="playerRageCap",
        default=-1,
        description="Most rage a player builds; -1 for none",
    )
    rage_needed_for_level_up: int = Field(
        validation_alias="rageNeededForLevelUp",
        serialization_alias="rageNeededForLevelUp",
        default=-1,
        description="Rage to the next level; -1 for none",
    )
    normal_def_strength_boost_min: int = Field(
        validation_alias="normalDiffDefStrengthBoostMinDefense",
        serialization_alias="normalDiffDefStrengthBoostMinDefense",
        default=0,
        description="Least defence boost, normal difficulty",
    )
    normal_def_strength_boost_max: int = Field(
        validation_alias="normalDiffDefStrengthBoostMaxDefense",
        serialization_alias="normalDiffDefStrengthBoostMaxDefense",
        default=0,
        description="Most defence boost, normal difficulty",
    )
    premium_def_strength_boost_min: int = Field(
        validation_alias="premiumDiffDefStrengthBoostMinDefense",
        serialization_alias="premiumDiffDefStrengthBoostMinDefense",
        default=0,
        description="Least defence boost, premium difficulty",
    )
    premium_def_strength_boost_max: int = Field(
        validation_alias="premiumDiffDefStrengthBoostMaxDefense",
        serialization_alias="premiumDiffDefStrengthBoostMaxDefense",
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

    contract_id: int = Field(validation_alias="id", serialization_alias="id", description="The contract")
    rank: int = Field(default=-1, description="The contract rank it is a level of")
    enable_on_start: bool = Field(
        validation_alias="enableOnStart",
        serialization_alias="enableOnStart",
        default=False,
        description="Open from the event's start, not after another contract",
    )
    next_contract_id: int = Field(
        validation_alias="nextContract",
        serialization_alias="nextContract",
        default=-1,
        description="The contract after it; -1 for none",
    )
    shogun_points: int = Field(
        validation_alias="shogunPoints",
        serialization_alias="shogunPoints",
        default=-1,
        description="Shogun points it takes",
    )
    war_effort_points: int = Field(
        validation_alias="warEffortPoints",
        serialization_alias="warEffortPoints",
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

    reward_id: RewardId = Field(validation_alias="rewardID", serialization_alias="rewardID", description="The reward")
    grant_type: GameDataId[RewardGrantType] = Field(
        validation_alias="grantType",
        serialization_alias="grantType",
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


__all__ = [
    "row_id",
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
    "QuestCondition",
    "QuestDef",
    "ResearchDef",
    "ConstructionItemRecipeDef",
    "ScalingCampDef",
    "TitleDef",
]
