"""The fixed values of the items tables' text columns, as the client compares them."""

from enum import Enum


class UnitRole(str, Enum):
    """
    A soldier's role, the ``role`` column of a unit.

    Client: ``SoldierUnitVO.ROLE_MELEE`` and ``ROLE_RANGE`` (bundle line 12590)
    """

    MELEE = "melee"
    RANGED = "ranged"


class ToolSide(str, Enum):
    """
    Whether a tool is used in attack or in defence, the ``typ`` column of a tool.

    Client: ``ClientConstCastle.ATTACK_TOOL`` and ``DEFENSE_TOOL`` (bundle line 1004)
    """

    ATTACK = "Attack"
    DEFENCE = "Defence"


class ToolCategory(str, Enum):
    """
    A tool's category, the ``toolCategory`` column in lower case.

    Client: ``AttackDialogWaveInfoHelper.TOOL_CATEGORIES`` (bundle line 13361)
    """

    BASIC = "basic"
    PREMIUM = "premium"
    ELITE = "elite"
    EVENT = "event"
    COMBO = "combo"


class BuildingGroup(str, Enum):
    """
    The ``group`` column of a building, tower, gate or moat.

    Client: ``ClientConstCastle.GROUP_*`` (bundle line 1004)
    """

    EXPANSION = "Expansion"
    TOWER = "Tower"
    BACKGROUND = "Background"
    RESOURCES = "Resources"
    CASTLEWALL = "Castlewall"
    GATE = "Gate"
    TOWERBASE = "Towerbase"
    BUILDING = "Building"
    MAPOBJECT = "Mapobject"
    MAPMOVEMENT = "Mapmovement"
    UNIT = "Unit"
    DEFENCE = "Defence"
    SURROUNDINGS = "Surroundings"
    FIXED_POSITION_BUILDING = "FixedPositionBuilding"
    TRAVELBOOSTER = "Travelbooster"
    MOAT = "Moat"
    EVENT = "Event"
    MOVING = "Moving"


class BuildingGroundType(str, Enum):
    """
    The ground a building stands on, its ``buildingGroundType`` column.

    Client: ``ClientConstCastle.BUILDINGGROUND_TYPE_*`` (bundle line 1004)
    """

    NONE = ""
    DECO = "DECO"
    MILITARY = "MILITARY"
    DEFENCE = "DEFENCE"
    CIVIL = "CIVIL"


class QuestConditionType(str, Enum):
    """
    What a quest condition counts, the first part of each ``conditions`` entry.

    The client names only these; quests count more types, which only the server reads.

    Client: ``ClientConstQuestCondition.QUESTTYPE_*`` (bundle line 9773)
    """

    STARTER = "starter"
    BUILDINGS = "buildings"
    UNITS = "units"
    TOOLS = "tools"
    TOOL_START = "toolStart"
    DECOS = "decos"
    STORAGE = "storage"
    EXPANSIONS = "expansions"
    INSTANTBUILD = "instantBuild"
    COLLECT_TAX = "collectTax"
    BRIBE_TAXCOLLECTOR = "bribeTaxCollector"
    DONATE_STONE = "donateStone"
    DONATE_FOOD = "donateFood"
    DONATE_WOOD = "donateWood"
    DONATE_C1 = "donateCurrency1"
    DONATE_COAL = "donateCoal"
    DONATE_OIL = "donateOil"
    DONATE_GLASS = "donateGlass"
    DONATE_IRON = "donateIron"
    DONATE_KHAN_MEDALS = "donateKhanMedals"
    DONATE_SAMURAI_TOKENS = "donateSamuraiTokens"
    COUNT_BATTLES = "countBattles"
    COUNT_DUNGEONS = "countDungeons"
    COUNT_POPULATION = "population"
    LOOTRESOURCE = "lootResource"
    SPY = "spy"
    OUTPOSTS = "outposts"
    START_TREASUREMAP = "startTreasureMap"
    TREASURE_NODE = "treasureNode"
    FINISHTREASUREDUNGEONS = "finishTreasureDungeons"
    JOIN_ALLIANCE = "alliance"
    START_KINGDOM = "startKingdom"
    CONQUER_VILLAGES = "villages"
    COUNT_BOSSDUNGEONS = "bossDungeon"
    TREASURE_VILLAGES = "treasureVillages"
    COLLECT_SILVER_RUNES = "collectSilverRunes"
    FIND_EQUIPMENT = "findEquipment"
    OFF_UNITS = "offUnits"
    DEF_UNITS = "defUnits"
    CONQUER_FACTIONCAMPS = "conquerFactionCamp"
    CONQUER_FACTIONVILLAGE = "conquerFactionVillage"
    DEFEATED_FACTIONCAPITAL = "defeatedFactionCapitalOnMap"
    DEFEATED_FACTIONCAMP = "defeatFactionCamp"
    FINISH_UNLOCKABLE = "finishUnlockable"
    JOIN_AREA = "joinArea"
    REPAIR_TREASURE_BRIDGES = "repairedTreasureBridges"
    COLLECT_KHAN_TABLETS = "collectKhanTablets"
    COLLECT_SAMURAI_TOKENS = "collectSamuraiTokens"
    SPEND_SAMURAI_TOKENS = "spendSamuraiTokens"
    LAW_AND_ORDER = "lawAndOrder"
    LOOT_PVP_AQUAMARINE = "lootAquamarineInPVP"
    LOOT_NPC_AQUAMARINE = "lootAquamarineFromNPC"
    CONQUER_RESOURCE_ISLE = "conquerResourceIsle"
    BUY_RUBIES = "buyRubies"
    COLLECT_FAME = "collectFame"
    HEAL_SOLDIERS = "healSoldiers"
    RESEARCH = "research"
    SPEND_KHAN_TABLETS = "spendKhanTablets"
    WISHING_WELL = "wishingWell"
    MINUTESKIP = "useMinuteSkip"
    INVITE_A_FRIEND = "inviteFriend"
    CONSTRUCTION_ALLIANCE_HELP = "requestAllianceHelpBuilding"
    BUY_PACKAGE = "buyPackage"
    WIN_FAME_FIGHT = "winFameFight"
    SPEND_RUBIES = "spendC2"
    WRITE_ALLIANCECHAT = "writeInAllianceChat"
    SEND_RESOURCES_PLAYER = "resourceToPlayer"
    SABOTAGE = "sabotageDamage"
    USE_FORGE_ALLIANCE = "useAllianceForge"
    USE_FORGE = "craftEquipment"
    COLLECT_CITIZEN = "collectFromCitizen"
    RECRUIT_UNITS = "recruitUnits"
    PRODUCE_TOOLS = "produceTools"
    REQUEST_ALLIANCE_HELP = "requestAllianceHelp"
    COMPLETE_MERCENARY_MISSION = "completeMercenaryMission"
    COLLECT_FROM_CARRIAGE = "collectFromCarriage"
    CREATE_EMBLEM = "createEmblem"
    ASSIGN_CONSTRUCTIONITEM = "assignConstructionItem"
    GAIN_FACTION_POINTS = "gainFactionPoints"
    DEFEAT_ALIENS_WITH_MIN_FAME = "defeatAliensWithMinFame"
    LOOT_RESOURCES_POINT_EVENT = "lootResourcesPointEvent"
    CONNECT_TO_FACEBOOK = "connectToFacebook"
    RECRUIT_ATTACK_UNITS = "recruitedAttackUnitsWithMinStrength"
    RECRUIT_DEFENDER_UNITS = "recruitedDefenderUnitsWithMinStrength"
    LOOT_RESOURCES_PVP = "lootResourcesPvP"
    DEFEAT_FACTION_TOWERS_ON_MAP = "defeatedFactionTowersOnMap"
    DEFEAT_FACTION_TOWERS = "defeatedFactionTowers"
    DEFEAT_KHAN_CAMPS = "defeatKhanCamps"
    DEFEND_KHAN_ATTACKS = "defendKhanAttacks"
    COLLECT_RAGE = "collectRage"
    SPEND_KHAN_MEDALS = "spendKhanMedals"
    COLLECT_PEARL_RELICS = "collectPearlRelics"
    DEFEAT_NOMAD_CAMPS = "defeatNomads"
    DEFEAT_SAMURAI_CAMPS = "defeatSamuraiCamps"
    GAIN_LTPE_POINTS = "gainLTPEPoints"
    JOIN_TEMP_SERVER = "joinTempServer"
    VISIT_SHOP = "visitShop"
    BUY_MIN_AMOUNT_OF_RUBIES = "buyMinAmountOfRubies"
    OPEN_SAMURAI_EVENT_DIALOG = "clientOnly_openSamuraiEventDialog"
    OPTIN_NEWSLETTER = "optinNewsletter"
    VISIT_GENERALS_INN = "visitGeneralsInn"
    GENERAL_ASSIGN_TO_BARON = "assignGeneralToBaron"
    GENERAL_ASSIGN_TO_COMMANDER = "assignGeneralToCommander"
    DEFEND_WOLFKING = "defendWolfKing"
    DEFEAT_WOLFKING = "defeatWolfKing"
    GACHA_DRAW = "performGacha"
    VISIT_GENERALS_OVERVIEW = "visitGeneralsOverview"


class TitleDisplayType(str, Enum):
    """
    Whether a title goes before or after the name, a title's ``displayType`` column.

    Client: ``ClientConstTitle.DISPLAYTYPE_PREFIX`` and ``DISPLAYTYPE_SUFFIX`` (bundle line 6767)
    """

    PREFIX = "prefix"
    SUFFIX = "suffix"


class PlayerRelation(str, Enum):
    """
    The relationship to the target an effect is limited to, an effect's ``playerRelation`` column.

    Client: ``EffectVO.RELATION_*`` (bundle line 41739)
    """

    SAME_ALLIANCE = "sameAlliance"
    ALLIANCE_IN_WAR = "allianceInWar"
    SAME_PLAYER = "samePlayer"


class RelicEffectType(str, Enum):
    """
    A relic effect's kind, its ``relicEffectType`` column.

    Client: ``XmlRelicEffectVO.EFFECT_TYPE_NORMAL``, ``EFFECT_TYPE_UNIT_TOOL`` and the ``"economy"`` of
    ``EFFECT_TYPE_SORT_ORDER`` (bundle line 18417)
    """

    NORMAL = "normal"
    UNIT_TOOL = "unitTool"
    ECONOMY = "economy"


class CastleEffect(str, Enum):
    """
    A construction item's fixed bonus, one column of its row named after the bonus, e.g. ``recruitCostReduction``.

    Members are in the client's order, the order a construction item lists them in.

    Client: ``CastleEffectEnum`` (bundle line 3770), read by ``CastleEffectVO.createFromXML`` (bundle line 79059)
    """

    WOODPRODUCTION = "Woodproduction"
    STONEPRODUCTION = "Stoneproduction"
    FOODPRODUCTION = "Foodproduction"
    COALPRODUCTION = "Coalproduction"
    OILPRODUCTION = "Oilproduction"
    GLASSPRODUCTION = "Glassproduction"
    IRONPRODUCTION = "Ironproduction"
    WOODBOOST = "Woodboost"
    STONEBOOST = "Stoneboost"
    FOODBOOST = "Foodboost"
    ALLI_FOOD_PRODUCTION_BONUS = "alliFoodProductionBonus"
    COALBOOST = "Coalboost"
    OILBOOST = "Oilboost"
    GLASSBOOST = "Glassboost"
    IRONBOOST = "Ironboost"
    FOODREDUCTION = "Foodreduction"
    HIDEOUT = "Hideout"
    DECO_POINTS = "decoPoints"
    POPULATION = "Population"
    WOOD_STORAGE = "woodStorage"
    STONE_STORAGE = "stoneStorage"
    FOOD_STORAGE = "foodStorage"
    COAL_STORAGE = "coalStorage"
    OIL_STORAGE = "oilStorage"
    GLASS_STORAGE = "glassStorage"
    IRON_STORAGE = "ironStorage"
    HONEY_STORAGE = "honeyStorage"
    MEAD_STORAGE = "meadStorage"
    BEEF_STORAGE = "beefStorage"
    MARKET_CARRIAGES = "marketCarriages"
    SIGHT_RADIUS_BONUS = "sightRadiusBonus"
    COMMANDER_SIZE = "commanderSize"
    GUARD_SIZE = "guardSize"
    SPY_SIZE = "spySize"
    BUILDING_COST_REDUCTION = "buildingCostReduction"
    SHOWN_TRAVEL_BONUS = "shownTravelBonus"
    ISLAND_ALLIANCE_POINTS = "islandAlliancePoints"
    BUILD_SPEED_BOOST = "buildSpeedBoost"
    SURVIVE_BOOST = "surviveBoost"
    HOSPITAL_CAPACITY = "hospitalCapacity"
    HOSPITAL_SLOTS = "hospitalSlots"
    RECRUIT_COST_REDUCTION = "recruitCostReduction"
    STACK_SIZE = "stackSize"
    HEAL_SPEED = "healSpeed"
    RECRUIT_SPEED_BOOST = "recruitSpeedBoost"
    UNIT_WALL_COUNT = "unitWallCount"
    UNBOOSTED_FOOD_PRODUCTION = "unboostedFoodProduction"
    UNBOOSTED_WOOD_PRODUCTION = "unboostedWoodProduction"
    UNBOOSTED_STONE_PRODUCTION = "unboostedStoneProduction"
    ESPIONAGE_TRAVEL_BOOST = "espionageTravelBoost"
    DEFENSIVE_TOOLS_COSTS_REDUCTION = "defensiveToolsCostsReduction"
    DEFENSIVE_TOOLS_SPEED_BOOST = "defensiveToolsSpeedBoost"
    FEAST_COSTS_REDUCTION = "feastCostsReduction"
    OFFENSIVE_TOOLS_COSTS_REDUCTION = "offensiveToolsCostsReduction"
    OFFENSIVE_TOOLS_SPEED_BOOST = "offensiveToolsSpeedBoost"
    REDUCE_RESEARCH_RESOURCE_COSTS = "ReduceResearchResourceCosts"
    XP_BOOST_BUILD_BUILDINGS = "XPBoostBuildBuildings"
    DISTRICT_SLOTS = "districtSlots"
    MEADREDUCTION = "Meadreduction"
    BEEFREDUCTION = "Beefreduction"
