"""Equipment slots, wearers, origins and rarities."""

from enum import IntEnum


class EquipmentSlot(IntEnum):
    """Slot an equipment item occupies."""

    ARMOR = 1
    WEAPON = 2
    HELMET = 3
    ARTIFACT = 4
    SKIN = 5
    HERO = 6


class WearerType(IntEnum):
    """
    Who may wear an equipment item.

    The client treats any id but 1 and 2 as wearable by all
    (``BasicEquippableVO.getLordType``, bundle line 4837).

    Client: ``EquipmentConst.UNDEFINED_WEARER_ID``, ``BARON_WEARER_ID`` and
    ``COMMANDER_WEARER_ID`` (dll line 19249)
    """

    UNDEFINED = -1
    CASTELLAN = 1
    COMMANDER = 2


class EquipmentType(IntEnum):
    """
    Origin of an equipment item.

    Client: ``EquipmentConst.EQUIPMENT_TYPE_ID_*`` (dll line 19249)
    """

    GENERATED = 0
    UNIQUE = 1
    UNIQUE_TEMPORARY = 2
    RELIC = 3


class Rareness(IntEnum):
    """
    Rarity of an equipment item; hero items have their own range.

    Client: ``EquipmentConst.RARENESS_*`` (dll line 19249)
    """

    UNIQUE = 0
    COMMON = 1
    RARE = 2
    EPIC = 3
    LEGENDARY = 4
    RELIC = 5
    HERO_UNIQUE = 10
    HERO_BEGINN = 10
    HERO_COMMON = 11
    HERO_RARE = 12
    HERO_EPIC = 13
    HERO_LEGENDARY = 14
    HERO_RELIC = 15
