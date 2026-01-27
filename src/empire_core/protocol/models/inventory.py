from enum import Enum, IntEnum


class SCEItem(str, Enum):
    """
    String keys for Global Inventory Items (from 'sce' packet).
    These match the keys used in 'gpi'/'gbd'/'sce' payloads.
    """

    FEATHERS = "PTT"
    KHAN_TABLETS = "KT"
    KHAN_MEDALS = "KM"
    SAMURAI_TOKENS = "ST"
    SILVER_PIECES = "STO"
    REFINED_WOOD = "RL"
    REFINED_STONE = "RS"
    SCREWS = "CO1"
    BLACK_POWDER = "CO2"
    SAW = "CO3"
    DRILL = "CO4"
    CROWBAR = "CO5"
    LEATHER_STRIPS = "CO6"
    CHAINS = "CO7"
    METAL_PLATES = "CO8"
    SKIP_1_MIN = "MS1"


class ItemID(IntEnum):
    # Travel
    FEATHERS = 153

    # Event Currencies
    KHAN_TABLETS = 238
    KHAN_MEDALS = 216
    SAMURAI_TOKENS = 734

    # Resources/Materials
    SILVER_PIECES = 106
    REFINED_WOOD = 240
    REFINED_STONE = 152  # Tentative (159k vs 122k target)

    # Tools/Construction
    SCREWS = 202  # Match 13k vs 12.4k
    METAL_PLATES = 256  # Match 17k vs 12.7k (Tentative)
    BLACK_POWDER = 35
    SAW = 611
    DRILL = 635
    CROWBAR = 9
    LEATHER_STRIPS = 115
    CHAINS = 450

    # Skips
    SKIP_1_MIN = 653
    SKIP_5_MIN = 654
    SKIP_10_MIN = 648
    SKIP_30_MIN = 649
    SKIP_1_HR = 650
    SKIP_5_HRS = 651
    SKIP_24_HRS = 660

    # Unknown/Other high count items
    UNKNOWN_215 = 215
    UNKNOWN_227 = 227
