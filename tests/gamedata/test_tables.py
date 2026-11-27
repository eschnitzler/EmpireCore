"""The typed rows of the tables the id enums name, read as the client reads them."""

import logging
import sys

from empire_core.combat import Bonus, effect_value_bonuses
from empire_core.enums import (
    AllianceQuestType,
    BerimondFaction,
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
    SceatSkillTab,
    TitleDisplayType,
    TitleSystem,
    TreasureMapType,
    WearerType,
)
from empire_core.events import GrandTournamentQuestSlot
from empire_core.gamedata import (
    AllianceInvasionCampId,
    AllianceQuestId,
    BuildingDef,
    CitadelLevelId,
    DailyQuestDef,
    DonationItemId,
    DonationSettingId,
    Effect,
    EffectDef,
    EffectValue,
    EquipmentEffectValue,
    EquipmentGroupDef,
    EquipmentSetDef,
    EventDef,
    EventDifficultyId,
    GachaId,
    GameData,
    HorizonSettingId,
    OasisSettlementId,
    OasisTradeId,
    OuterRealmsSettingId,
    PartPayPriceId,
    QuestCondition,
    QuestDef,
    RelicEffectDef,
    ResearchDef,
    ScalingCampId,
    TitleDef,
    TrainingProgramId,
    TreasureMapNodeId,
    WheelOfFortuneRewardSetId,
    WheelOfFortuneWinClassId,
    ids,
)


class TestBuildingDef:
    def test_a_bare_row_takes_the_client_defaults(self):
        building = BuildingDef.model_validate({"wodID": "171"})

        assert building.building_id is ids.Building.KEEP_L1
        assert (building.level, building.maximum_count, building.shop_category) == (-1, 1_000_000, "NOT_IN_SHOP")
        assert building.destructable and building.outer_realms_destructable and not building.storeable
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

    assert event.event_id is ids.Event.NOMAD_INVASION_5
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
        assert quest.level_calculated and not quest.is_outer_realms_quest
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
        assert [(c.kind, c.amount) for c in title.rewards(game_data=data)] == [(CollectableKind.COINS, 100)]
        assert TitleDef.model_validate({"titleID": "2", "type": "FAME"}).rewards(game_data=data) == ()

    def test_the_cache_keeps_the_collectable_columns_only(self, tmp_path):
        GameData.parse("786.03", self.ITEMS)._write_cache(tmp_path / "cache.json")

        again = GameData._read_cache(tmp_path / "cache.json", "786.03")

        assert again is not None and again.reward_list([170, 40054]) == GameData.parse(
            "786.03", self.ITEMS
        ).reward_list([170, 40054])
        assert again._table_rows["rewards"][170] == {"rewardID": "170", "units": "722+5"}


def test_a_scaling_camp_gives_its_level():
    data = GameData.parse("786.03", {"eventAutoScalingCamps": [{"eventAutoScalingCampID": "7", "camplevel": "40"}]})

    assert data.scaling_camp_level(ScalingCampId(7)) == 40
    assert data.scaling_camp_level(ScalingCampId(8)) is None and data.scaling_camp_level(ScalingCampId(0)) is None
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

        assert (title.title_system, title.display_type) == (TitleSystem.STORM_ISLANDS, TitleDisplayType.PREFIX)

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
        "dungeons": [{"countVictories": "0", "kID": "2", "lordID": "-14"}],
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
        assert data.default_commanders[-14].wearer_id is WearerType.CASTELLAN
        assert data.dungeons[0].kingdom_id is Kingdom.ICE
        assert data.dungeons[0].commander == data.default_commanders[-14]
        assert data.league_brackets[0].event_id is ids.Event.NOMAD_INVASION_5
        assert type(data.fortifications[501].wod_id) is ids.Building
        assert data.tools[1].slot_types == (1, 9)

    def test_they_survive_the_cache(self, tmp_path):
        data = GameData.parse("786.03", self.PAYLOAD)
        data._write_cache(tmp_path / "cache.json")

        again = GameData._read_cache(tmp_path / "cache.json", "786.03")

        assert again is not None and again == data
        assert again.equipment_effects[9].item_group_ids == (ids.EquipmentGroup.ATTACK_PVP, 4711)
        assert again.dungeons[0].kingdom_id is Kingdom.ICE
        assert again.dungeons[0].commander == data.default_commanders[-14]


class TestEventTables:
    ITEMS = {
        "tmaps": [
            {
                "mapID": "25",
                "comment1": "hardmode",
                "comment2": "Thornking",
                "tmapnodeIDs": "122+123",
                "kID": "-1",
                "maptype": "0",
                "endNodeID": "123",
                "packages": "213+214",
                "travelTime": "7200",
                "skipCostC2": "240",
            },
            {"mapID": "9", "tmapnodeIDs": "65", "kID": "1", "totalpieces": "13", "costpiece": "1590", "maptype": "1"},
        ],
        "tmapnodes": [
            {"tmapnodeID": "122", "type": "DUNGEON", "countVictories": "-20", "pos": "1", "dungeonlevel": "5"},
            {"tmapnodeID": "71", "orUnlockIDs": "69+70", "partPayPriceID": "164", "type": "BRIDGE"},
        ],
        "partpayprices": [
            {"partPayPriceID": "164", "wood": "160", "stone": "160", "food": "0", "currency2": "68", "mode": "fixed"}
        ],
        "donationItems": [{"donationItemID": "2", "donationItemSetID": "1", "currencyID": "15", "ratio": "1"}],
        "donationSettings": [{"donationSettingID": "3", "donationItemSetID": "3", "rewardSetID": "4"}],
        "officersSchoolEffects": [{"id": "1", "effectID": "276", "eventID": "72", "c1Cost": "80000", "c2Cost": "700"}],
        "eventAutoScalingDifficulties": [
            {"difficultyID": "311", "eventID": "72", "difficultyTypeID": "2", "isLocked": "1", "rentC2Cost": "55000"}
        ],
        "gachaEvents": [{"gachaID": "1", "eventID": "126", "gachaLevel": "1", "maxPulls": "9", "multiPullMax": "10"}],
        "luckywheelrewardsets": [{"luckyWheelRewardSetID": "1", "rewardIDs": "170,130,233"}],
        "luckywheelclasses": [
            {
                "luckyWheelClassID": "1",
                "neededSpinsForNextClass": "3",
                "C2PerSkippedSpin": "300",
                "normalPreview": "245",
            }
        ],
        "tempServerSettings": [
            {"settingID": "8", "scoringSystem": "might", "startCurrencyAmount": "-1", "boosterCurrencyPackageID": "7"}
        ],
        "allianceBattleGroundSettings": [
            {"settingID": "15", "maxAllianceSize": "65", "currencyID": "115", "allianceTowerEffectIDs": "1,2,9"}
        ],
        "allianceTowerEffects": [
            {"allianceTowerEffectID": "1", "effectID": "141", "effectStartValue": "1", "effectIncrease": "2.5"}
        ],
        "currencies": [
            {"currencyID": "126", "Name": "JadeBlades"},
            {"currencyID": "93", "Name": "AncientJadeStatuette"},
        ],
        "tradingCamps": [
            {
                "tradingCampID": "100",
                "tradingCampTypeID": "1",
                "level": "1",
                "tradeGroupID": "1",
                "speedMultiplier": "x",
            }
        ],
        "trades": [
            {
                "tradeID": "10",
                "tradeGroupID": "1",
                "mainRewardID": "7",
                "costJadeBlades": "20",
                "lootCapacityCost": "200",
            }
        ],
        "allianceCitadels": [
            {"allianceCitadelID": "1", "level": "1", "radius": "10", "costAncientJadeStatuette": "0"},
            {
                "allianceCitadelID": "2",
                "level": "2",
                "radius": "15",
                "costAncientJadeStatuette": "25000",
                "scatterWeights": "15,5",
            },
        ],
        "allianceInvasionCamps": [
            {"allianceInvasionCampID": "85", "eventID": "72", "dungeonlevel": "105", "rageNeededForLevelUp": "18500"}
        ],
    }

    def test_treasure_maps_and_their_nodes(self):
        data = GameData.parse("788.02", self.ITEMS)

        season = data.treasure_maps[ids.TreasureMapId.THORN_KING_HARDMODE]
        assert season.map_id is ids.TreasureMapId.THORN_KING_HARDMODE
        assert (season.node_ids, season.end_node_id, season.package_ids) == ((122, 123), 123, (213, 214))
        assert (season.map_type, season.kingdom) == (TreasureMapType.SEASON, -1)
        assert (season.travel_seconds, season.skip_cost_rubies) == (7200, 240)
        hunt = data.treasure_maps[9]
        assert (hunt.map_type, hunt.kingdom, hunt.total_pieces, hunt.piece_cost_rubies) == (
            TreasureMapType.TREASURE_HUNT,
            Kingdom.SANDS,
            13,
            1590,
        )

        dungeon = data.treasure_map_nodes[TreasureMapNodeId(122)]
        assert (dungeon.node_type, dungeon.count_victories, dungeon.position, dungeon.dungeon_level) == (
            "DUNGEON",
            -20,
            1,
            5,
        )
        assert (dungeon.unlocked_by_any, dungeon.part_price_id) == ((0,), None)
        bridge = data.treasure_map_nodes[TreasureMapNodeId(71)]
        assert (bridge.unlocked_by_any, bridge.part_price_id) == ((69, 70), 164)
        price = data.part_pay_prices[PartPayPriceId(164)]
        assert [(c.kind, c.amount) for c in price.costs if c.amount] == [
            (CollectableKind.WOOD, 160),
            (CollectableKind.STONE, 160),
            (CollectableKind.RUBIES, 68),
        ]

    def test_event_minigame_and_difficulty_rows(self):
        data = GameData.parse("788.02", self.ITEMS)

        assert data.donation_items[DonationItemId(2)].currency_id == 15
        setting = data.donation_settings[DonationSettingId(3)]
        assert (setting.item_set_id, setting.reward_set_id) == (3, 4)
        program = data.training_programs[TrainingProgramId(1)]
        assert (program.event_id, program.cost_coins, program.cost_rubies) == (ids.Event.NOMAD_INVASION_72, 80000, 700)
        difficulty = data.event_difficulties[EventDifficultyId(311)]
        assert (difficulty.event_id, difficulty.difficulty_type) == (ids.Event.NOMAD_INVASION_72, 2)
        assert difficulty.is_locked and difficulty.unlock_rubies == 55000
        gacha = data.gachas[GachaId(1)]
        assert (gacha.event_id, gacha.level, gacha.max_pulls, gacha.multi_pull_max) == (126, 1, 9, 10)
        assert data.wheel_of_fortune_reward_sets[WheelOfFortuneRewardSetId(1)].reward_ids == (170, 130, 233)
        win_class = data.wheel_of_fortune_win_classes[WheelOfFortuneWinClassId(1)]
        assert (win_class.spins_to_next_class, win_class.rubies_per_skipped_spin) == (3, 300.0)
        assert win_class.preview_reward_ids == (245,) and win_class.pro_mode_preview_reward_ids == ()

    def test_special_server_settings_and_alliance_tower_effects(self):
        data = GameData.parse("788.02", self.ITEMS)

        outer_realms = data.outer_realms_settings[OuterRealmsSettingId(8)]
        assert (outer_realms.scoring_system, outer_realms.start_currency_amount) == ("might", -1)
        assert outer_realms.booster_package_id == 7 and not outer_realms.peace_mode
        horizon = data.horizon_settings[HorizonSettingId(15)]
        assert (horizon.max_alliance_size, horizon.currency_id) == (65, 115)
        assert horizon.tower_effects == (
            ids.AllianceTowerEffect.SHRINE_WALL_BOOST,
            ids.AllianceTowerEffect.SHRINE_GATE_BOOST,
            9,
        )
        effect = data.alliance_tower_effects[ids.AllianceTowerEffect.SHRINE_WALL_BOOST]
        assert (effect.effect_id, effect.start_value, effect.increase) == (141, 1.0, 2.5)

    def test_jade_desert_settlements_trades_and_citadel_levels(self):
        data = GameData.parse("790.02", self.ITEMS)

        settlement = data.oasis_settlements[OasisSettlementId(100)]
        assert (settlement.level, settlement.trade_group_id, settlement.cooldown_seconds) == (1, 1, 0)
        assert (settlement.speed_multiplier, settlement.travel_cost_multiplier) == (1.0, 1.0)
        trade = data.oasis_trades[OasisTradeId(10)]
        assert (trade.trade_group_id, trade.main_reward_id, trade.loot_capacity_cost) == (1, 7, 200)
        assert [(cost.item, cost.amount) for cost in trade.costs] == [(ids.Currency.JADE_BLADES, 20)]
        assert data.citadel_levels[CitadelLevelId(1)].costs == ()
        level_2 = data.citadel_levels[CitadelLevelId(2)]
        assert (level_2.radius, level_2.scatter_weights) == (15, (15, 5))
        assert [(cost.item, cost.amount) for cost in level_2.costs] == [(ids.Currency.ANCIENT_JADE_STATUETTE, 25000)]

    def test_alliance_invasion_camps_by_id(self):
        data = GameData.parse("788.02", self.ITEMS)

        camp = data.alliance_invasion_camps[AllianceInvasionCampId(85)]
        assert (camp.event_id, camp.dungeon_level, camp.rage_needed_for_level_up) == (
            ids.Event.NOMAD_INVASION_72,
            105,
            18500,
        )
        assert [row.dungeon_level for row in data.camps["allianceInvasionCamps"]] == [105]

    def test_they_survive_the_cache(self, tmp_path):
        GameData.parse("788.02", self.ITEMS)._write_cache(tmp_path / "cache.json")

        again = GameData._read_cache(tmp_path / "cache.json", "788.02")

        assert again is not None
        assert again.treasure_maps[25].node_ids == (122, 123)
        assert (
            again.part_pay_prices[PartPayPriceId(164)]
            == GameData.parse("788.02", self.ITEMS).part_pay_prices[PartPayPriceId(164)]
        )
        assert again.alliance_invasion_camps[AllianceInvasionCampId(85)].event_id == ids.Event.NOMAD_INVASION_72


def test_quests_and_buildings_name_their_season_maps():
    quest = QuestDef.model_validate({"questID": "1", "mapID": "25"})
    building = BuildingDef.model_validate({"wodID": "171", "mapIDs": "21,30"})

    assert quest.map_id is ids.TreasureMapId.THORN_KING_HARDMODE
    assert QuestDef.model_validate({"questID": "2"}).map_id == -1
    assert building.available_in_map_ids == (
        ids.TreasureMapId.THORN_KING_NORMAL,
        ids.TreasureMapId.UNDERWORLD_LOW_LEVEL,
    )


def test_berimond_invasion_camp_rows_name_their_faction():
    data = GameData.parse(
        "788.02",
        {
            "factioninvasioncamps": [
                {"countVictory": "3", "factionID": "0", "wallBonus": "10"},
                {"countVictory": "3", "factionID": "1", "wallBonus": "20"},
            ]
        },
    )

    blue = data.berimond_invasion_camp(3, BerimondFaction.URSIDAE)
    red = data.berimond_invasion_camp(3, BerimondFaction.GERBRANDT)
    assert blue is not None and blue.faction_id is BerimondFaction.URSIDAE and blue.wall_bonus == 10
    assert red is not None and red.faction_id is BerimondFaction.GERBRANDT and red.wall_bonus == 20


class TestFeastsAndSceatSkillTrees:
    ITEMS = {
        "feasts": [
            {
                "feastID": "0",
                "productionBoost": "80",
                "duration": "3600",
                "costFood": "4000",
                "minLevel": 10,
                "maxLevel": "69",
                "type": "small",
                "sortOrder": "1",
            },
            {"feastID": "4", "productionBoost": "500", "costC2": "1750", "type": "ruby", "sortOrder": "2"},
        ],
        "sceatSkillTrees": [{"skillTreeID": "3", "tabID": "1"}, {"skillTreeID": "4", "tabID": "2"}, {"tabID": "1"}],
    }

    def test_a_feast_reads_its_price_bonus_and_levels(self):
        data = GameData.parse("790.02", self.ITEMS)

        food = data.feasts[ids.Feast.COUNTRY_FEAST]
        assert (food.cost_food, food.cost_rubies, food.is_ruby_priced) == (4000, 0, False)
        assert (food.recruitment_speed_bonus, food.duration_seconds, food.sort_order) == (80, 3600, 0)
        assert food.offered_at(10) and food.offered_at(69) and not food.offered_at(70)
        assert food.text_id == "dialog_festival_smallEvent" == ids.Feast.COUNTRY_FEAST.text_id
        ruby = data.feasts[ids.Feast.IMPERIAL_BANQUET]
        assert (ruby.cost_rubies, ruby.is_ruby_priced, ruby.sort_order) == (1750, True, 1)

    def test_sceat_skill_trees_name_their_tab_and_a_row_without_a_tree_is_left_out(self):
        data = GameData.parse("790.02", self.ITEMS)

        assert {tree: row.tab_id for tree, row in data.sceat_skill_trees.items()} == {
            3: SceatSkillTab.BUILDINGS,
            4: SceatSkillTab.UNITS,
        }

    def test_they_survive_the_cache(self, tmp_path):
        GameData.parse("790.02", self.ITEMS)._write_cache(tmp_path / "cache.json")

        again = GameData._read_cache(tmp_path / "cache.json", "790.02")

        assert again is not None
        banquet = again.feasts[ids.Feast.IMPERIAL_BANQUET]
        assert (banquet.cost_rubies, banquet.sort_order) == (1750, 1)
        assert again.sceat_skill_trees[4].tab_id is SceatSkillTab.UNITS


class TestAllianceQuests:
    ITEMS = {
        "allianceQuests": [
            {
                "allianceQuestID": "2",
                "comment1": "AME",
                "comment4": "countDungeons+10+10",
                "questID": "3601",
                "questType": "defeatTarget",
                "chance": "1",
                "duration": "3600",
                "rewardPoints": "60",
                "cancelCostC2": "199",
            },
            {
                "allianceQuestID": "178",
                "questID": "3777",
                "questType": "bloodcrowInvasion",
                "chance": "2",
                "duration": "43200",
                "rewardPoints": "380",
                "cancelCostC2": "149",
                "eventID": "103",
            },
            {"allianceQuestID": "5", "questType": "upgrade"},
        ],
        "quests": [
            {"questID": "3601", "eventID": "129", "conditions": "countDungeons+10+10", "hidden": "1"},
            {"questID": "3777", "eventID": "129", "conditions": "alienFame+550000000", "hidden": "1"},
        ],
    }

    def test_a_row_reads_its_points_type_duration_and_costs(self):
        data = GameData.parse("790.06", self.ITEMS)

        quest = data.alliance_quests[AllianceQuestId(178)]
        # questType[0].toUpperCase() + questType.slice(1)
        assert quest.quest_type is AllianceQuestType.BLOODCROW_INVASION
        assert (quest.reward_points, quest.duration, quest.cancel_cost_rubies, quest.chance) == (380, 43200, 149, 2)
        assert quest.event_id is ids.Event.BLOODCROW_INVASION
        assert data.alliance_quests[AllianceQuestId(2)].quest_type is AllianceQuestType.DEFEAT_TARGET

    def test_missing_columns_take_the_client_defaults(self):
        quest = GameData.parse("790.06", self.ITEMS).alliance_quests[AllianceQuestId(5)]

        assert quest.quest_type is AllianceQuestType.UPGRADE
        assert (quest.quest_id, quest.event_id, quest.cancel_cost_rubies) == (-1, -1, 199)
        assert (quest.reward_points, quest.duration, quest.chance) == (0, 0, 0)

    def test_its_quest_id_is_the_quests_row_with_the_conditions(self):
        data = GameData.parse("790.06", self.ITEMS)

        quest = data.quests[data.alliance_quests[AllianceQuestId(2)].quest_id]
        assert quest.conditions == (
            QuestCondition(condition_type=QuestConditionType.COUNT_DUNGEONS, amount=10, raw_data="10"),
        )

    def test_a_quest_slot_looks_up_its_definition_and_quest(self):
        data = GameData.parse("790.06", self.ITEMS)
        slot = GrandTournamentQuestSlot(slot_id=0, alliance_quest_id=178, player_id=-1, remaining_seconds=0)
        unknown = slot.model_copy(update={"alliance_quest_id": 999})
        no_quest = slot.model_copy(update={"alliance_quest_id": 5})

        definition = slot.definition(game_data=data)
        assert definition is not None and definition.reward_points == 380
        quest = slot.quest(game_data=data)
        assert quest is not None
        assert quest.conditions == (QuestCondition(condition_type="alienFame", amount=550000000),)
        assert unknown.definition(game_data=data) is None and unknown.quest(game_data=data) is None
        assert no_quest.definition(game_data=data) is not None and no_quest.quest(game_data=data) is None

    def test_they_survive_the_cache(self, tmp_path):
        GameData.parse("790.06", self.ITEMS)._write_cache(tmp_path / "cache.json")

        again = GameData._read_cache(tmp_path / "cache.json", "790.06")

        assert again is not None
        quest = again.alliance_quests[AllianceQuestId(178)]
        assert (quest.quest_type, quest.reward_points, quest.event_id) == (
            AllianceQuestType.BLOODCROW_INVASION,
            380,
            103,
        )
        assert again.quests[quest.quest_id].conditions[0].amount == 550000000
