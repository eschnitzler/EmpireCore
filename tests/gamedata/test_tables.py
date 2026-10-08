"""The typed rows of the tables the id enums name, read as the client reads them."""

import logging
import sys

from empire_core.combat import Bonus, effect_value_bonuses
from empire_core.enums import (
    BuildingGroundType,
    BuildingGroup,
    CollectableKind,
    EquipmentSlot,
    Kingdom,
    MapItemType,
    PlayerRelation,
    QuestConditionType,
    RelicEffectType,
    RewardGrantType,
    TitleDisplayType,
    TitleSystem,
    WearerType,
)
from empire_core.gamedata import (
    BuildingDef,
    DailyQuestDef,
    Effect,
    EffectDef,
    EffectValue,
    EquipmentEffectValue,
    EquipmentGroupDef,
    EquipmentSetDef,
    EventDef,
    GameData,
    QuestCondition,
    QuestDef,
    RelicEffectDef,
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


class TestRewards:
    ITEMS = {
        "currencies": [{"currencyID": "29", "Name": "LegendaryMaterial", "JSONKey": "LM"}],
        "rewards": [
            {"rewardID": "170", "comment1": "x", "units": "722+5", "hiddenFood": "200"},
            {"rewardID": "9314", "addC1": "100", "grantType": "2"},
            {"rewardID": "40054", "addLegendaryMaterial": "540", "currency1": "5"},
        ],
        "titles": [{"titleID": "1", "type": "FAME", "rewardID": "9314"}],
    }

    def test_a_reward_reads_its_collectables_and_grant_type(self):
        data = GameData.parse("786.03", self.ITEMS)

        assert [(c.kind, c.item, c.amount) for c in data.rewards[170].collectables] == [
            (CollectableKind.UNITS, ids.Unit.ARROWTHROWER, 5)
        ]
        assert (data.rewards[170].grant_type, data.rewards[9314].grant_type) == (
            RewardGrantType.PLAYER,
            RewardGrantType.ALLIANCE_MEMBER,
        )

    def test_an_add_column_names_a_currency_of_the_currencies_table(self):
        data = GameData.parse("786.03", self.ITEMS)

        assert [(c.kind, c.item, c.amount) for c in data.rewards[40054].collectables] == [
            (CollectableKind.COINS, None, 5),
            (CollectableKind.CURRENCY, ids.Currency.UPGRADE_TOKEN, 540),
        ]

    def test_reward_list_gives_the_rewards_in_order_and_skips_unknown_ids(self):
        data = GameData.parse("786.03", self.ITEMS)

        rewards = data.reward_list([40054, -1, 170, 9314])

        assert [(c.kind, c.amount) for c in rewards] == [
            (CollectableKind.COINS, 5),
            (CollectableKind.CURRENCY, 540),
            (CollectableKind.UNITS, 5),
            (CollectableKind.COINS, 100),
        ]
        assert [(c.kind, c.amount) for c in data.reward_list([40054, 9314], combine=True)][0] == (
            CollectableKind.COINS,
            105,
        )

    def test_a_title_s_reward(self):
        data = GameData.parse("786.03", self.ITEMS)

        title = data.titles[1]

        assert title.reward_id == 9314
        assert [(c.kind, c.amount) for c in data.reward_list([title.reward_id])] == [(CollectableKind.COINS, 100)]

    def test_the_cache_keeps_the_collectable_columns_only(self, tmp_path):
        GameData.parse("786.03", self.ITEMS)._write_cache(tmp_path / "cache.json")

        again = GameData._read_cache(tmp_path / "cache.json", "786.03")

        assert again is not None and again.reward_list([170, 40054]) == GameData.parse(
            "786.03", self.ITEMS
        ).reward_list([170, 40054])
        assert again._table_rows["rewards"][170] == {"rewardID": "170", "units": "722+5"}


def test_a_scaling_camp_gives_its_level():
    data = GameData.parse("786.03", {"eventAutoScalingCamps": [{"eventAutoScalingCampID": "7", "camplevel": "40"}]})

    assert data.scaling_camp_level(7) == 40
    assert data.scaling_camp_level(8) is None and data.scaling_camp_level(0) is None
    assert data.scaling_camps[7].shogun_points_needed_for_level_up == -1
    assert "eventAutoScalingCamps" not in data.raw_tables


class TestEffects:
    def test_an_effects_column_keeps_each_value_s_structure(self):
        building = BuildingDef.model_validate(
            {"wodID": "171", "effects": "428&10,373&3+5,113&426#427,507&686+30#687+30", "areaSpecificEffects": "107&-5"}
        )

        assert [(e.effect_id, e.values) for e in building.effects] == [
            (Effect.SIGHT_RADIUS_BONUS, ((10,),)),
            (Effect.CRAFTING_QUEUE_PRODUCTION_BOOST, ((3, 5),)),
            (Effect.ENABLE_CONSTRUCTION_ITEM_RECIPES, ((426,), (427,))),
            (Effect.DEFENSE_SUPPORT_UNITS_WEAK, ((686, 30), (687, 30))),
        ]
        assert building.area_specific_effects == (
            EffectValue(effect_id=Effect.RECRUITMENT_TIME_BONUS, values=((-5,),)),
        )

    def test_a_value_reads_as_the_client_splits_it(self):
        # BonusVO callers take split("&")[1]; a piece that is no number is the client's NaN
        effects = ResearchDef.model_validate({"researchID": "1", "effects": "1&2&3,5&5+,7&x+4"}).effects

        assert [(e.effect_id, e.values) for e in effects] == [(1, ((2,),)), (5, ((5, None),)), (7, ((None, 4),))]
        assert effect_value_bonuses(effects) == [
            Bonus(effect_id=1, value=2),
            Bonus(effect_id=5, value=5, raw_values=(5.0, 0.0)),
        ]

    def test_an_entry_without_a_value_is_kept_and_one_without_an_id_left_out(self):
        effects = ResearchDef.model_validate({"researchID": "1", "effects": "12&,x&3,,99,5&1.5"}).effects

        assert [(e.effect_id, e.values, e.value) for e in effects] == [
            (12, (), None),
            (99, (), None),
            (5, ((1.5,),), 1.5),
        ]

    def test_equipment_sets_name_equipment_effects(self):
        row = EquipmentSetDef.model_validate({"setID": "3", "effects": "422&513+5#514+5"})

        assert row.effects == (EquipmentEffectValue(equipment_effect_id=422, values=((513, 5), (514, 5))),)

    def test_effects_survive_the_cache(self, tmp_path):
        data = GameData.parse("786.03", {"titles": [{"titleID": "1", "effects": "504&20,22001&602+13#608+13"}]})
        data._write_cache(tmp_path / "cache.json")

        again = GameData._read_cache(tmp_path / "cache.json", "786.03")

        assert again is not None and again.titles[1].effects == data.titles[1].effects


class TestFixedTextColumns:
    def test_a_building_s_group_and_ground_are_enums(self):
        building = BuildingDef.model_validate({"wodID": "1", "group": "Tower", "buildingGroundType": "MILITARY"})

        assert (building.group, building.building_ground_type) == (BuildingGroup.TOWER, BuildingGroundType.MILITARY)
        assert BuildingDef.model_validate({"wodID": "1"}).building_ground_type is BuildingGroundType.NONE

    def test_a_value_the_client_does_not_name_is_kept_as_text_without_a_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            building = BuildingDef.model_validate({"wodID": "1", "group": "Ground"})
            quest = QuestDef.model_validate({"questID": "1", "conditions": "buyRubies+1#login+1"})

        assert building.group == "Ground" and type(building.group) is str
        assert [c.condition_type for c in quest.conditions] == [QuestConditionType.BUY_RUBIES, "login"]
        assert not caplog.records

    def test_a_title_s_system_and_display_type_are_enums(self):
        title = TitleDef.model_validate({"titleID": "1", "type": "ISLE", "displayType": "prefix"})

        assert (title.title_system, title.display_type) == (TitleSystem.ISLAND, TitleDisplayType.PREFIX)

    def test_effect_relations_and_relic_effect_types_are_enums(self):
        effect = EffectDef.model_validate({"effectID": "1", "playerRelation": "sameAlliance"})
        relic = RelicEffectDef.model_validate({"id": "4", "relicEffectType": "unitTool"})

        assert effect.player_relation is PlayerRelation.SAME_ALLIANCE
        assert effect.applies_to_relation(PlayerRelation.SAME_ALLIANCE)
        assert not effect.applies_to_relation(PlayerRelation.SAME_PLAYER)
        assert relic.relic_effect_type is RelicEffectType.UNIT_TOOL


class TestReferencedIds:
    PAYLOAD = {
        "effects": [
            {"effectID": "1", "effectTypeID": "0", "areaTypeID": "1,12", "spaceIDs": "0,2", "raidBossID": "1,x"}
        ],
        "equipment_effects": [{"equipmentEffectID": "9", "effectID": "1", "wearerID": "2", "itemGroupID": "102,4711"}],
        "relicEffects": [{"id": "4", "effectID": "1"}],
        "generalSkills": [{"skillID": "10110201", "generalID": "101"}],
        "lords": [{"lordID": "-14", "wearerID": "1"}],
        "dungeons": [{"countVictories": "0", "kID": "2"}],
        "leaguetypes": [{"leaguetypeID": "1", "eventID": "5"}],
        "buildings": [{"wodID": "501", "name": "Castlewall", "wallBonus": "30"}],
        "units": [{"wodID": "1", "slotTypes": "1,9"}],
    }

    def test_ids_rows_reference_are_their_enums(self):
        data = GameData.parse("786.03", self.PAYLOAD)

        effect = data.effects[1]
        assert effect.effect_type_id is ids.EffectType(0)
        assert effect.area_type_ids == (MapItemType.CASTLE, MapItemType.KINGDOM_CASTLE)
        assert effect.space_ids == (Kingdom.GREEN, Kingdom.ICE)
        assert effect.raid_boss_ids == (ids.RaidBoss.NECROMANCER,)
        equipment = data.equipment_effects[9]
        assert (equipment.effect_id, equipment.wearer_id) == (ids.Effect(1), WearerType.COMMANDER)
        assert equipment.item_group_ids == (ids.EquipmentGroup.ATTACK_PVP, 4711)
        assert data.relic_effects[4].effect_id is ids.Effect(1)
        assert data.general_skills[10110201].general_id is ids.General.TORIL
        assert data.default_lords[-14].wearer_id is WearerType.CASTELLAN
        assert data.dungeons[0].kingdom_id is Kingdom.ICE
        assert data.league_brackets[0].event_id is ids.Event.NOMAD_INVASION
        assert type(data.fortifications[501].wod_id) is ids.Building
        assert data.tools[1].slot_types == (1, 9)

    def test_they_survive_the_cache(self, tmp_path):
        data = GameData.parse("786.03", self.PAYLOAD)
        data._write_cache(tmp_path / "cache.json")

        again = GameData._read_cache(tmp_path / "cache.json", "786.03")

        assert again is not None and again == data
        assert again.equipment_effects[9].item_group_ids == (ids.EquipmentGroup.ATTACK_PVP, 4711)
        assert again.dungeons[0].kingdom_id is Kingdom.ICE
