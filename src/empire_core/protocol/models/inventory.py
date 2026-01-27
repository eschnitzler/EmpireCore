from enum import Enum


class SCEItem(str, Enum):
    """
    String keys for Global Inventory Items (from 'sce' packet).
    These match the keys used in 'gpi'/'gbd'/'sce' payloads.
    """

    # Travel & Speed
    FEATHERS = "PTT"

    # Skips (Time Skips)
    SKIP_1_MIN = "MS1"
    SKIP_5_MIN = "MS2"
    SKIP_10_MIN = "MS3"
    SKIP_30_MIN = "MS4"
    SKIP_1_HR = "MS5"
    SKIP_5_HRS = "MS6"
    SKIP_24_HRS = "MS7"

    # Event Currencies
    KHAN_TABLETS = "KT"
    KHAN_MEDALS = "KM"
    SAMURAI_TOKENS = "ST"
    SAMURAI_MEDALS = "SM"
    SCEATS = "STP"
    TICKETS = "LWT"
    AFFLUENCE_TICKETS = "SLWT"
    FUSION_COINS = "FC"
    VILLAGE_TOKENS = "RVT"
    CONSTRUCTION_TOKENS = "LT"
    UPGRADE_TOKENS = "LM"
    RELIC_SHARDS = "RF"
    FLORA_TOKENS = "FT"
    ALLIANCE_COINS = "AC"
    RIFT_COINS = "RC"
    PEARLS = "PR"
    PASSAGE_TOKENS = "CPT"

    # Standard Currencies/Materials
    SILVER_PIECES = "STO"
    GOLD_PIECES = "GTO"
    IMPERIAL_DUCATS = "IDCT"

    # Construction Materials (Kingdom Resources)
    REFINED_WOOD = "RL"
    REFINED_STONE = "RS"
    PLASTER = "PL"
    DRAGON_SCALE_TILES = "DST"
    DRAGON_SCALE_SPLINTERS = "DSS"
    DRAGON_CHARMS = "DC"

    # Tools (Construction/Upgrade)
    SCREWS = "CO1"
    BLACK_POWDER = "CO2"
    SAW = "CO3"
    DRILL = "CO4"
    CROWBAR = "CO5"
    LEATHER_STRIPS = "CO6"
    CHAINS = "CO7"
    METAL_PLATES = "CO8"

    # Boosters
    BUILD_BOOSTER_RARE = "BC1"
    BUILD_BOOSTER_EPIC = "BC2"
    BUILD_BOOSTER_LEGENDARY = "BC3"

    # Consumables
    SOLDIER_BISCUIT = "SB"
    GENERAL_SKILL_RESET = "GRT"
    GENERAL_XP_5K = "GXP5"
    GENERAL_XP_10K = "GXP7"
    GENERAL_XP_15K = "GXP9"

    # Offerings
    OFFERING_LUDWIG = "FKT"
    OFFERING_ULRICH = "KTK"
    OFFERING_BEATRICE = "PTK"
    OFFERING_SASAKI = "STK"
    OFFERING_TIZI = "TTK"
    OFFERING_HASAN = "HAT"
    OFFERING_DIANA = "DAT"
    OFFERING_ASHIRA = "AST"
    OFFERING_KAELRITH = "KLT"
    OFFERING_BARIN = "BRN"
    OFFERING_EDRIC = "EDR"

    # General Shards
    SHARD_TORIL = "STL"
    SHARD_LEO = "SLE"
    SHARD_ALYSSA = "SAL"
    SHARD_HORATIO = "SHT"
    SHARD_SASAKI = "SSK"
    SHARD_DIANA = "SDN"
    SHARD_TOM = "SOM"
    SHARD_TIZI = "STT"
    SHARD_HASAN = "SHS"
    SHARD_GARRIK = "SGA"
    SHARD_KAELRITH = "SKL"
