from enum import Enum


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
