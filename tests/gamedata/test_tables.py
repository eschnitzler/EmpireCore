"""The typed rows of the tables the id enums name, read as the client reads them."""

import sys

from empire_core.enums import EquipmentSlot, Kingdom, MapItemType, WearerType
from empire_core.gamedata import (
    BuildingDef,
    DailyQuestDef,
    EquipmentGroupDef,
    EventDef,
    GameData,
    QuestCondition,
    QuestDef,
    ResearchDef,
    TitleDef,
    ids,
)


class TestBuildingDef:
    def test_a_bare_row_takes_the_client_defaults(self):
        building = BuildingDef.model_validate({"wodID": "171"})

        assert building.building_id is ids.Building.KEEP_L1
        assert (building.level, building.maximum_count, building.shop_category) == (-1, 1_000_000, "NOT_IN_SHOP")
        assert building.destructable and building.temp_server_destructable and not building.storeable
        assert building.sort_order == 1_000_000
        assert building.only_in_kingdoms == () and building.upgrade_building_id == 0

    def test_columns_read_as_the_client_reads_them(self):
        building = BuildingDef.model_validate(
            {
                "wodID": "171",
                "type": "-",
                "upgradeWodID": "172",
                "kIDs": "0,2,,x",
                "onlyInAreaTypes": "1,12",
                "destructable": "0",
                "storeable": "1",
                "sortOrder": "abc",
            }
        )

        # AVisualVO.parseXmlNode reads a "-" type as none; getBooleanAttribute is "0" != value
        assert building.building_type == "" and building.upgrade_building_id is ids.Building.KEEP_L2
        assert building.only_in_kingdoms == (Kingdom.GREEN, Kingdom.ICE)
        assert building.only_in_area_types == (MapItemType.CASTLE, MapItemType.KINGDOM_CASTLE)
        assert not building.destructable and building.storeable
        assert building.sort_order == sys.float_info.max


def test_a_research_keeps_only_prerequisites_above_zero():
    research = ResearchDef.model_validate({"researchID": "256", "prerequisiteIDs": "1,0,-1,", "groupID": "41"})

    assert research.prerequisite_ids == (ids.Research(1),)
    assert (research.group_id, research.level, research.min_research_tower_level) == (41, -1, 1)


def test_an_event_without_kingdoms_or_areas_runs_in_the_green_kingdom_and_main_castles():
    event = EventDef.model_validate({"eventID": "5", "eventType": "NomadInvasion"})

    assert event.event_id is ids.Event.NOMAD_INVASION
    assert (event.kingdoms, event.area_types, event.max_level) == ((Kingdom.GREEN,), (MapItemType.CASTLE,), 99)


def test_an_equipment_group_names_its_wearer_and_slot():
    group = EquipmentGroupDef.model_validate({"itemGroupID": "102", "wearerID": "2", "slotID": "6"})

    assert (group.wearer_id, group.slot_id) == (WearerType.COMMANDER, EquipmentSlot.HERO)


class TestQuests:
    def test_conditions_are_split_into_type_amount_and_data(self):
        quest = QuestDef.model_validate({"questID": "3047", "conditions": "buyRubies+1#killUnits+5+211|212#"})

        assert quest.conditions == (
            QuestCondition(condition_type="buyRubies", amount=1),
            QuestCondition(condition_type="killUnits", amount=5, raw_data="211|212"),
        )

    def test_a_negative_shown_kingdom_reads_as_the_green_kingdom(self):
        # CastleQuestVO.fillFromParamXML clamps shownKingdomID below 0 to 0, and keeps triggerKingdomID as sent
        quest = QuestDef.model_validate({"questID": "3047", "shownKingdomID": "-1", "triggerKingdomID": "-1"})

        assert (quest.shown_kingdom, quest.trigger_kingdom) == (Kingdom.GREEN, -1)
        assert (quest.required_quest_id, quest.event_id, quest.sort_priority) == (-1, 0, None)

    def test_a_daily_quest_reads_its_flags(self):
        quest = DailyQuestDef.model_validate(
            {"dailyQuestID": "1", "levelCalculated": "2", "isTempServerQuest": "2", "conditions": "login+1"}
        )

        # Boolean(parseInt(levelCalculated)) against 1 == parseInt(isTempServerQuest)
        assert quest.level_calculated and not quest.is_temp_server_quest
        assert quest.conditions == (QuestCondition(condition_type="login", amount=1),)


def test_a_title_reads_missing_numbers_as_minus_one():
    title = TitleDef.model_validate({"titleID": "1", "type": "FAME", "threshold": "100"})

    assert (title.threshold, title.top_x, title.previous_title_id, title.reward_id) == (100, -1, -1, -1)
    assert title.display_type == "-1"


def test_a_scaling_camp_gives_its_level():
    data = GameData.parse("786.03", {"eventAutoScalingCamps": [{"eventAutoScalingCampID": "7", "camplevel": "40"}]})

    assert data.scaling_camp_level(7) == 40
    assert data.scaling_camp_level(8) is None and data.scaling_camp_level(0) is None
    assert data.scaling_camps[7].shogun_points_needed_for_level_up == -1
    assert "eventAutoScalingCamps" not in data.raw_tables
