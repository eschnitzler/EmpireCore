"""
Typed rows of the items tables the generated id enums name: buildings, researches, events, loot boxes,
equipment groups, difficulty types, quests and daily quests, plus titles and difficulty scaling camps.

Each model reads the columns its client value object reads, with the same defaults; the costs and
rewards the client reads through its items collectable parsers (``CollectableParserX2CList`` and
``CollectableParserX2CRewards``, bundle lines 62874 and 62897) are not read yet.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from pydantic import Field, ValidationInfo, field_validator

from empire_core.enums import EquipmentSlot, Kingdom, MapItemType, WearerType
from empire_core.protocol.js import js_falsy, js_int, js_number_or_none, js_parse_int, js_string

from .lenient import GameDataId
from .models import READING_CACHE, EffectSpecRow, EffectValue, _parse_int_or_default, _Row

if TYPE_CHECKING:
    from .ids import (
        Building,
        DailyQuestId,
        DifficultyType,
        EquipmentGroup,
        Event,
        LootBox,
        LootBoxType,
        QuestId,
        Research,
    )


def _row_id(value: object) -> int:
    """The row's own id, ``parseInt`` of it; a row without one is skipped, as nothing can look it up."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
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
    hospital capacity, ...) are not read; ``fortifications`` has the walls, gates and moats.

    Client: ``AVisualVO.parseXmlNode`` (bundle line 17800), ``AShopVO.parseXmlNode`` (bundle lines
    31713-31715), ``ABasicBuildingVO.parseXmlNode``, ``parseEffects`` and
    ``parseAreaSpecificEffects`` (bundle lines 17842-17864)
    """

    building_id: GameDataId["Building"] = Field(alias="wodID", description="The building")
    name: str = Field(default="", description="Building name, shared across levels, e.g. Keep")
    group: str = Field(default="", description="Building group, e.g. Building, Tower or Moat")
    building_type: str = Field(alias="type", default="", description="Building type, e.g. Level1; empty for none")
    level: int = Field(default=-1, description="Upgrade level; -1 when the row has none")
    required_level: int = Field(alias="requiredLevel", default=0, description="Player level needed to build it")
    required_legend_level: int = Field(
        alias="requiredLegendLevel", default=0, description="Legend level needed to build it"
    )
    early_unlock_required_level: int = Field(
        alias="earlyUnlockRequiredLevel", default=0, description="Player level from which it can be unlocked early"
    )
    upgrade_building_id: GameDataId["Building"] = Field(
        alias="upgradeWodID", default=0, description="The building it upgrades to; 0 for none"
    )
    downgrade_building_id: GameDataId["Building"] = Field(
        alias="downgradeWodID", default=0, description="The building it downgrades to; 0 for none"
    )
    shop_category: str = Field(
        alias="shopCategory", default="NOT_IN_SHOP", description="Build menu category; NOT_IN_SHOP for none"
    )
    xp: int = Field(default=0, description="Experience for building it")
    might_value: int = Field(alias="mightValue", default=0, description="Might points it gives")
    storeable: bool = Field(default=False, description="It can be put into storage")
    maximum_count: int = Field(alias="maximumCount", default=1_000_000, description="How many a castle may have")
    destructable: bool = Field(default=True, description="It can be torn down")
    temp_server_destructable: bool = Field(
        alias="tempServerDestructable", default=True, description="It can be torn down on a temporary server"
    )
    is_battle_ground: bool = Field(alias="isBattleGround", default=False, description="Built on a battle ground only")
    is_not_battle_ground: bool = Field(
        alias="isNotBattleGround", default=False, description="Never built on a battle ground"
    )
    slum_level_needed: int = Field(alias="slumLevelNeeded", default=0, description="Slum level needed to build it")
    needs_construction_expert: bool = Field(
        alias="constructionExpert", default=False, description="Building it needs the construction expert"
    )
    sell_coins: int = Field(alias="sellC1", default=0, description="Coins for selling it")
    sort_order: float = Field(
        alias="sortOrder",
        default=1_000_000,
        description="Order in the build menu; a value that is no number sorts last",
    )
    only_in_area_types: tuple[GameDataId[MapItemType], ...] = Field(
        alias="onlyInAreaTypes", default=(), description="The castle types it may be built in; empty for any"
    )
    only_in_kingdoms: tuple[GameDataId[Kingdom], ...] = Field(
        alias="kIDs", default=(), description="The kingdoms it may be built in; empty for every kingdom"
    )
    only_in_event_ids: tuple[GameDataId["Event"], ...] = Field(
        alias="eventIDs", default=(), description="The events it may be built in; empty for none in particular"
    )
    effect_locked: bool = Field(alias="effectLocked", default=False, description="Its effects need unlocking")
    wall_bonus: int = Field(alias="wallBonus", default=0, description="Wall protection, in percent")
    moat_bonus: int = Field(alias="moatBonus", default=0, description="Moat protection, in percent")
    build_duration: int = Field(alias="buildDuration", default=0, description="Build time in seconds")
    building_ground_type: str = Field(
        alias="buildingGroundType", default="", description="The ground it stands on; empty for the default"
    )
    district_type_id: int = Field(alias="districtTypeID", default=0, description="The district type it belongs to")
    is_district: bool = Field(alias="isDistrict", default=False, description="It is a district")
    is_relic_building: bool = Field(alias="isRelicBuilding", default=False, description="It is a relic building")
    area_specific_effects: tuple[EffectValue, ...] = Field(
        alias="areaSpecificEffects",
        default=(),
        description="Bonuses that count only where their effect's conditions hold",
    )

    @field_validator("building_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _row_id(value)

    @field_validator(
        "level", "required_level", "required_legend_level", "early_unlock_required_level", "upgrade_building_id",
        "downgrade_building_id", "xp", "might_value", "maximum_count", "slum_level_needed", "sell_coins",
        "wall_bonus", "moat_bonus", "build_duration", "district_type_id", mode="before",
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


class ResearchDef(EffectSpecRow):
    """
    One level of a research.

    Client: ``AResearchVO.fillFromParamXML`` (bundle lines 61502-61516)
    """

    research_id: GameDataId["Research"] = Field(alias="researchID", description="The research")
    label: str = Field(
        alias="comment2", default="", description="Designer label the game does not read, e.g. recruitment speed"
    )
    group_id: int = Field(alias="groupID", default=-1, description="The group the research's levels share")
    level: int = Field(default=-1, description="Research level")
    prerequisite_ids: tuple[GameDataId["Research"], ...] = Field(
        alias="prerequisiteIDs", default=(), description="Researches it needs first"
    )
    min_research_tower_level: int = Field(
        alias="minResearchTowerLevel", default=1, description="Research tower level it needs"
    )
    required_level: int = Field(alias="requiredLevel", default=0, description="Player level it needs")
    required_legend_level: int = Field(alias="requiredLegendLevel", default=0, description="Legend level it needs")
    research_duration: int = Field(alias="researchDuration", default=0, description="Research time in seconds")
    temp_server_research_duration: int = Field(
        alias="globalServerResearchDuration", default=0, description="Research time on a temporary server"
    )
    only_with_research_expert: bool = Field(
        alias="onlyWithResearchExpert", default=False, description="It needs the research expert"
    )

    @field_validator("research_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _row_id(value)

    @field_validator(
        "group_id", "level", "min_research_tower_level", "required_level", "required_legend_level",
        "research_duration", "temp_server_research_duration", mode="before",
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

    event_id: GameDataId["Event"] = Field(alias="eventID", description="The event")
    event_type: str = Field(alias="eventType", default="", description="Event type, e.g. NomadInvasion")
    min_level: int = Field(alias="minLevel", default=0, description="Lowest player level that sees it")
    max_level: int = Field(alias="maxLevel", default=99, description="Highest player level that sees it")
    open_with_login: bool = Field(alias="openWithLogin", default=False, description="Its dialog opens on login")
    sort_order: int = Field(alias="sortOrder", default=0, description="Order among the events")
    crossplay_min_level: int = Field(
        alias="crossplayMinLevel", default=-1, description="Lowest level on a crossplay server; -1 for none"
    )
    extension_unlock: int = Field(alias="eventExtensionUnlock", default=0, description="Its extension unlock")
    kingdoms: tuple[GameDataId[Kingdom], ...] = Field(
        alias="kIDs", default=(Kingdom.GREEN,), description="The kingdoms it runs in"
    )
    area_types: tuple[GameDataId[MapItemType], ...] = Field(
        alias="areaTypes", default=(MapItemType.CASTLE,), description="The castle types it counts in"
    )

    @field_validator("event_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _row_id(value)

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

    loot_box_id: GameDataId["LootBox"] = Field(alias="lootBoxID", description="The loot box")
    name: str = Field(default="", description="Internal name, e.g. MysteryBoxBronze")
    loot_box_type_id: GameDataId["LootBoxType"] = Field(alias="lootBoxTypeID", default=0, description="Its type")
    tombola_id: int = Field(alias="lootBoxTombolaID", default=0, description="The tombola it draws from")
    key_tombola_id: int = Field(alias="lootBoxKeyTombolaID", default=0, description="The tombola its keys draw from")
    rarity: int = Field(default=0, description="Rarity")
    draws: int = Field(default=0, description="Draws per opening")
    sort_order: int = Field(alias="sortOrder", default=0, description="Order among the loot boxes")

    @field_validator("loot_box_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _row_id(value)

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

    loot_box_type_id: GameDataId["LootBoxType"] = Field(alias="lootBoxTypeID", description="The loot box type")
    theme: str = Field(alias="lootBoxTheme", default="", description="Its theme, e.g. MysteryBox")
    key_payout_threshold: int = Field(
        alias="lootBoxKeyPayoutThreshold", default=0, description="Keys that pay out a box"
    )

    @field_validator("loot_box_type_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _row_id(value)

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

    group_id: GameDataId["EquipmentGroup"] = Field(alias="itemGroupID", description="The item group")
    name: str = Field(default="", description="Internal name, e.g. AttackPVP")
    wearer_id: GameDataId[WearerType] = Field(alias="wearerID", default=-1, description="Who wears it; -1 for any")
    slot_id: GameDataId[EquipmentSlot] = Field(alias="slotID", default=-1, description="The slot it goes in")
    pic_id: int = Field(alias="picID", default=-1, description="Its picture")
    drop_rate: int = Field(alias="dropRate", default=-1, description="Its drop rate")

    @field_validator("group_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _row_id(value)

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

    difficulty_type_id: GameDataId["DifficultyType"] = Field(alias="difficultyTypeID", description="The type")
    name: str = Field(default="", description="Internal name, e.g. easyPlus")
    sort_order: int = Field(alias="sortOrder", default=0, description="Order among the types")

    @field_validator("difficulty_type_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _row_id(value)

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

    condition_type: str = Field(description="What it counts, e.g. buyRubies")
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

    quest_id: GameDataId["QuestId"] = Field(alias="questID", description="The quest")
    series_id: int = Field(alias="questSeriesID", default=-1, description="The quest series; -1 for none")
    series_number: int = Field(alias="questSeriesNumber", default=1, description="Its place in the series")
    quests_in_series: int = Field(alias="numberOfQuestsInSeries", default=0, description="Quests in the series")
    shown_kingdom: GameDataId[Kingdom] = Field(
        alias="shownKingdomID", default=Kingdom.GREEN, description="The kingdom it is shown in"
    )
    trigger_kingdom: GameDataId[Kingdom] = Field(
        alias="triggerKingdomID", default=Kingdom.GREEN, description="The kingdom it counts in, as the row has it"
    )
    hidden: bool = Field(default=False, description="It is not shown")
    map_id: int = Field(alias="mapID", default=-1, description="The map it belongs to; -1 for none")
    required_level: int = Field(alias="requiredLevel", default=0, description="Player level it needs")
    required_legend_level: int = Field(alias="requiredLegendLevel", default=0, description="Legend level it needs")
    required_quest_id: GameDataId["QuestId"] = Field(
        alias="requiredQuestID", default=-1, description="The quest it needs first; -1 for none"
    )
    quest_giver_id: int = Field(alias="questGiverID", default=0, description="The character who gives it")
    event_id: GameDataId["Event"] = Field(alias="eventID", default=0, description="The event it belongs to; 0 for none")
    duration: int = Field(default=-1, description="Seconds it runs; -1 for no limit")
    objective_type: int = Field(alias="objectiveType", default=0, description="Its objective type")
    auto_show: bool = Field(alias="autoShow", default=False, description="It opens on its own")
    sort_priority: int | None = Field(
        alias="sortPriority", default=None, description="Order in the quest book; None sorts last"
    )
    cost_rubies: int = Field(alias="c2Cost", default=0, description="Rubies to finish it at once")
    questbook_tab_id: int = Field(alias="questbookTabID", default=-1, description="Its quest book tab; -1 for none")
    conditions: tuple[QuestCondition, ...] = Field(default=(), description="What it counts")

    @field_validator("quest_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _row_id(value)

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

    quest_id: GameDataId["DailyQuestId"] = Field(alias="dailyQuestID", description="The daily quest")
    trigger_kingdom: GameDataId[Kingdom] = Field(
        alias="triggerKingdomID", default=Kingdom.GREEN, description="The kingdom it counts in; -1 for any"
    )
    is_temp_server_quest: bool = Field(
        alias="isTempServerQuest", default=False, description="It runs on temporary servers"
    )
    daily_task_points: int = Field(alias="addDailyDutyPoints", default=0, description="Daily task points it gives")
    level_calculated: bool = Field(
        alias="levelCalculated", default=False, description="Its amounts scale with the player's level"
    )
    conditions: tuple[QuestCondition, ...] = Field(default=(), description="What it counts")

    @field_validator("quest_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _row_id(value)

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

    Titles have no id enum: their rows have no name to make one of.

    Client: ``TitleVO.parseXml`` (bundle lines 62705-62713)
    """

    title_id: int = Field(alias="titleID", description="The title")
    title_system: str = Field(alias="type", default="-1", description="Its title system, a TitleSystem value")
    threshold: int = Field(default=-1, description="Points from which it is held; -1 for a top-X title")
    display_type: str = Field(alias="displayType", default="-1", description="How it is shown")
    forced: bool = Field(default=False, description="It is a forced title")
    decay: int = Field(default=-1, description="Its point decay")
    is_positive: bool = Field(alias="isPositive", default=False, description="It is a positive title")
    top_x: int = Field(alias="topX", default=-1, description="The top ranks that hold it; -1 or 0 for a points title")
    previous_title_id: int = Field(
        alias="previousTitleID", default=-1, description="The title below it in its system; -1 for the first"
    )
    reward_id: int = Field(alias="rewardID", default=-1, description="Its reward; -1 for none")
    might_value: int = Field(alias="mightValue", default=-1, description="Might points it gives")

    @field_validator("title_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _row_id(value)

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


class ScalingCampDef(_Row):
    """
    A camp of an event's difficulty scaling: the level and costs a chosen difficulty gives it.

    Client: ``DifficultyScalingCampXmlVO.parseXML`` (bundle line 145227), keyed by id in
    ``CastleEventDifficultyScalingData`` (bundle line 145211)
    """

    scaling_camp_id: int = Field(alias="eventAutoScalingCampID", description="The scaling camp, as map rows name it")
    rank: int = Field(default=0, description="Its rank")
    level: int = Field(alias="camplevel", default=0, description="The camp level it gives")
    cool_down: int = Field(alias="coolDown", default=0, description="Cooldown in seconds after an attack")
    event_id: GameDataId["Event"] = Field(alias="eventID", default=0, description="The event it belongs to")
    cooldown_increase: int = Field(alias="cooldownIncrease", default=0, description="Cooldown added per attack")
    cooldown_increase_cap: int = Field(alias="cooldownIncreaseCap", default=0, description="Most cooldown added")
    skip_cost: int = Field(alias="skipCosts", default=0, description="Cost to skip the cooldown")
    skip_cost_increase: int = Field(alias="skipCostIncrease", default=0, description="Skip cost added per attack")
    skip_cost_increase_cap: int = Field(alias="skipCostIncreaseCap", default=0, description="Most skip cost added")
    wall_bonus: int = Field(alias="wallBonus", default=0, description="Wall protection, in percent")
    gate_bonus: int = Field(alias="gateBonus", default=0, description="Gate protection, in percent")
    moat_bonus: int = Field(alias="moatBonus", default=0, description="Moat protection, in percent")
    unit_capacity: int = Field(alias="unitCapacity", default=0, description="Units it holds")
    shogun_points_needed_for_level_up: int = Field(
        alias="shogunPointsNeededForLevelUp", default=-1, description="Shogun points to the next level; -1 for none"
    )
    player_rage_cap: int = Field(
        alias="playerRageCap", default=-1, description="Most rage a player builds; -1 for none"
    )
    rage_needed_for_level_up: int = Field(
        alias="rageNeededForLevelUp", default=-1, description="Rage to the next level; -1 for none"
    )
    normal_def_strength_boost_min: int = Field(
        alias="normalDiffDefStrengthBoostMinDefense", default=0, description="Least defence boost, normal difficulty"
    )
    normal_def_strength_boost_max: int = Field(
        alias="normalDiffDefStrengthBoostMaxDefense", default=0, description="Most defence boost, normal difficulty"
    )
    premium_def_strength_boost_min: int = Field(
        alias="premiumDiffDefStrengthBoostMinDefense", default=0, description="Least defence boost, premium difficulty"
    )
    premium_def_strength_boost_max: int = Field(
        alias="premiumDiffDefStrengthBoostMaxDefense", default=0, description="Most defence boost, premium difficulty"
    )

    @field_validator("scaling_camp_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _row_id(value)

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


__all__ = [
    "BuildingDef",
    "DailyQuestDef",
    "DifficultyTypeDef",
    "EquipmentGroupDef",
    "EventDef",
    "LootBoxDef",
    "LootBoxTypeDef",
    "QuestCondition",
    "QuestDef",
    "ResearchDef",
    "ScalingCampDef",
    "TitleDef",
]
