"""The castle-side tables: prebuilt castles and their special server selections, private villages, crafting,
the fusion forges, the citizen judgements and the construction item recipes, read as the client reads them."""

from empire_core.enums import CollectableKind, Kingdom
from empire_core.gamedata import (
    Building,
    ConstructionItem,
    ConstructionItemRecipeId,
    CraftingQueueId,
    CraftingRecipeId,
    Currency,
    CurrencyId,
    Effect,
    FusionForgeId,
    GameData,
    Judgement,
    PrebuiltCastle,
    PrivateVillageType,
    RewardId,
    StartResourcesId,
)
from tests.service_helpers import PREBUILT_CASTLE_ITEMS

ITEMS = {
    **PREBUILT_CASTLE_ITEMS,
    "startResources": [{"startResourceID": "1", "food": "2000", "wood": "3000", "stone": "3000", "currency1": "2000"}],
    "privateVillages": [
        {
            "villageID": "43",
            "type": "wood",
            "villageLevel": "3",
            "kID": "2",
            "costResourceVillageTokenLevel": "2",
            "costResourceVillageToken": "4",
            "effects": "600&6",
        }
    ],
    "craftingRecipes": [
        {
            "craftingRecipeId": "2",
            "recipeGroupID": "1",
            "researchGroupID": "141",
            "level": "2",
            "type": "Short",
            "queueTypeId": "1",
            "craftingDuration": "3600",
            "skipCostC2": "120",
            "costWood": "54400",
            "rewardIDs": "40002",
            "requiredCraftingBuildings": "171,172",
        }
    ],
    "craftingQueues": [
        {
            "craftingQueueId": "9",
            "queueTypeId": "3",
            "permanentProductionSlots": "1",
            "productionSlotUnlockCostC1": "5000000",
            "productionSlotUnlockDuration": "604800",
            "permanentQueueSlots": "1",
            "queueSlotUnlockCostC1": "500000,3000000,6500000",
            "queueSlotUnlockDuration": "604800",
        }
    ],
    "fusionSystems": [
        {
            "id": "1",
            "minLevel": 70,
            "energyRechargeIntervalInSeconds": "21600",
            "assembleCatalystEnergyCost": "900",
            "disassembleCatalystEnergyCost": "300",
            "baseBonusFusionXPChance": "10",
            "premiumBonusFusionXPChance": "100",
            "skipRechargeHardCurrencyCost": "500",
            "skipRechargeHardCurrencyCostFactor": "2.5",
        }
    ],
    "fusionForges": [{"forgeID": "1", "dustCurrencyID": "100000", "usableMinuteSkipsPerDay": "3"}],
    "judgements": [
        {
            "judgementID": "2",
            "visualName": "peasantRefugees",
            "spawnSpot": "resourceFood",
            "conditionTypeB": "wood#stone",
            "rewardTypeB": "currency1",
        }
    ],
    "constructionItemRecipes": [
        {"constructionItemRecipeID": "2", "blueprintID": "1", "constructionItemID": "2", "craftingDuration": "1"}
    ],
}


def game_data() -> GameData:
    return GameData.parse("test", ITEMS)


def kinds(costs) -> list[tuple[CollectableKind, int | float]]:
    return [(cost.kind, cost.amount) for cost in costs]


class TestPrebuiltCastles:
    def test_a_row_reads_its_spaces_level_and_non_zero_costs(self):
        castle = game_data().prebuilt_castles[PrebuiltCastle.ICE_SIMPLE_CASTLE]
        assert castle.prebuilt_castle_id is PrebuiltCastle.ICE_SIMPLE_CASTLE
        assert (castle.space_ids, castle.min_level, castle.kingdom) == ((2,), 25, Kingdom.ICE)
        assert kinds(castle.costs) == [
            (CollectableKind.WOOD, 7000),
            (CollectableKind.STONE, 7000),
            (CollectableKind.FOOD, 5000),
            (CollectableKind.COINS, 5000),
            (CollectableKind.RUBIES, 10000),
        ]
        assert not castle.is_premium and not castle.is_free and castle.cost_rubies == 10000
        assert CollectableKind.RUBIES not in [cost.kind for cost in castle.primary_costs]

    def test_a_castle_priced_only_in_rubies_is_premium(self):
        castle = game_data().prebuilt_castles[PrebuiltCastle.ICE_LORDLY_CASTLE]
        assert castle.is_premium and kinds(castle.primary_costs) == [(CollectableKind.RUBIES, 29000)]

    def test_zero_costs_make_a_free_castle_of_no_kingdom_but_the_green_one(self):
        castle = game_data().prebuilt_castles[PrebuiltCastle.OUTER_REALMS_PIONEERS_OUTPOST]
        assert castle.is_free and castle.kingdom is Kingdom.GREEN

    def test_a_season_camp_names_no_kingdom(self):
        castle = game_data().prebuilt_castles[PrebuiltCastle.BLADECOAST_SIMPLE_CAMP]
        assert castle.space_ids == (22, 27, 28) and castle.kingdom is None

    def test_the_main_castle_copy_flag(self):
        assert game_data().prebuilt_castles[PrebuiltCastle.OUTER_REALMS_CASTLE_TRANSPORTATION].is_main_castle_copy

    def test_names_come_from_the_game_s_text(self):
        assert PrebuiltCastle.STORM_TIDE_OUTPOST.text_id == "dialog_chooseCastle_preBuiltCastle_16"
        assert PrebuiltCastle.ICE_KNIGHTLY_CASTLE.text_id == "dialog_prebuiltCastle5_name"
        assert PrebuiltCastle.OUTER_REALMS_CASTLE_TRANSPORTATION.display_name() is None


class TestSpecialServerSelections:
    def test_a_row_reads_its_start_and_its_own_costs(self):
        data = game_data()
        row = data.outer_realms_prebuilt_castles[PrebuiltCastle.OUTER_REALMS_CASTLE_TRANSPORTATION]
        assert (row.start_level, row.start_legendary_level, row.start_resources_id) == (70, 800, 6)
        assert row.passage_token_package_id == 2358
        assert kinds(row.costs) == [(CollectableKind.CURRENCY, 1)]
        assert row.costs[0].item is Currency.CASTLE_PASSAGE_TOKEN

    def test_its_own_ruby_price_wins_over_the_castle_s(self):
        data = game_data()
        castle = PrebuiltCastle.OUTER_REALMS_ROYAL_KEEP_32
        row = data.outer_realms_prebuilt_castles[castle]
        assert row.cost_rubies(data.prebuilt_castles[castle]) == 19999
        assert row.is_ruby_castle(data.prebuilt_castles[castle])

    def test_a_free_castle_costs_0_rubies_and_still_counts_as_bought_with_them(self):
        data = game_data()
        castle = PrebuiltCastle.OUTER_REALMS_PIONEERS_OUTPOST
        row = data.outer_realms_prebuilt_castles[castle]
        assert kinds(row.selection_costs(data.prebuilt_castles[castle])) == [(CollectableKind.RUBIES, 0)]
        assert row.is_ruby_castle(data.prebuilt_castles[castle]) and row.cost_rubies(data.prebuilt_castles[castle]) == 0

    def test_with_no_costs_of_its_own_the_castle_s_primary_costs_count(self):
        data = game_data()
        castle = PrebuiltCastle.STORM_TIDE_OUTPOST
        row = data.storm_islands_prebuilt_castles[castle]
        assert kinds(row.selection_costs(data.prebuilt_castles[castle])) == [
            (CollectableKind.WOOD, 10000),
            (CollectableKind.COINS, 5000),
        ]
        assert not row.is_ruby_castle(data.prebuilt_castles[castle])

    def test_the_horizon_has_its_own_selection(self):
        data = game_data()
        assert set(data.horizon_prebuilt_castles) == {PrebuiltCastle.HORIZON_BATTALIONS_KEEP}

    def test_start_resources(self):
        resources = game_data().start_resources[StartResourcesId(1)].resources
        assert kinds(resources) == [
            (CollectableKind.FOOD, 2000),
            (CollectableKind.WOOD, 3000),
            (CollectableKind.STONE, 3000),
            (CollectableKind.COINS, 2000),
        ]


def test_a_private_village_row():
    village = game_data().private_villages[PrivateVillageType.ICE_PRIVATE_WOOD_VILLAGE_L3]
    assert (village.resource, village.level, village.kingdom) == ("wood", 3, Kingdom.ICE)
    assert (village.token_cost, village.total_token_cost) == (2, 4)
    assert village.effects[0].effect_id is Effect.WOOD_PRODUCTION_BOOST_ICE


def test_a_crafting_recipe_row():
    recipe = game_data().crafting_recipes[CraftingRecipeId(2)]
    assert (recipe.queue_id, recipe.recipe_group_id, recipe.research_group_id, recipe.level) == (1, 1, 141, 2)
    assert (recipe.recipe_type, recipe.crafting_seconds, recipe.skip_cost_rubies) == ("short", 3600, 120)
    assert kinds(recipe.costs) == [(CollectableKind.WOOD, 54400)]
    assert recipe.reward_ids == (RewardId(40002),)
    assert recipe.required_buildings == (Building.KEEP_L1, Building.KEEP_L2)


def test_crafting_queues_go_by_their_queue_type():
    queue = game_data().crafting_queues[CraftingQueueId(3)]
    assert (queue.permanent_production_slots, queue.production_slot_unlock_coins) == (1, (5000000,))
    assert queue.queue_slot_unlock_coins == (500000, 3000000, 6500000)
    assert (queue.production_slot_unlock_seconds, queue.queue_slot_unlock_seconds) == (604800, 604800)


def test_the_fusion_tables_share_the_forge_id():
    data = game_data()
    system = data.fusion_systems[FusionForgeId.DECORATIONS]
    assert (system.energy_recharge_seconds, system.assemble_catalyst_energy, system.disassemble_catalyst_energy) == (
        21600,
        900,
        300,
    )
    assert (system.refill_cost_rubies, system.refill_cost_factor) == (500, 2.5)
    forge = data.fusion_forges[FusionForgeId.DECORATIONS]
    assert forge.dust_currency_id is CurrencyId.DECORATION_DUST and forge.minute_skips_per_day == 3


def test_a_judgement_row():
    judgement = game_data().judgements[Judgement.REFUGEE_FARMERS]
    assert (judgement.visual_name, judgement.spawn_spot) == ("peasantRefugees", "resourceFood")
    assert judgement.option_a_requirements == () and judgement.option_b_requirements == ("wood", "stone")
    assert judgement.option_b_rewards == ("currency1",)
    assert Judgement.REFUGEE_FARMERS.text_id == "judgement_2_name"


def test_construction_item_recipes_go_by_their_typed_id():
    recipe = game_data().construction_item_recipes[ConstructionItemRecipeId(2)]
    assert recipe.recipe_id == 2 and recipe.construction_item_id is ConstructionItem(2)
