"""What a reward, a cost or a list of goods can hold."""

from __future__ import annotations

from enum import Enum, IntEnum


class CollectableKind(str, Enum):
    """
    The kind of a collectable: the client's ``CollectableEnum`` types a server key can name.

    The value is the client's type name, ``server_key`` the key the server sends it under. A
    currency (``CURRENCY``) has no key of its own: it comes under the currency's key. ``OTHER``
    stands for a key the client has no type for; the client drops such an entry.

    Client: ``CollectableEnum.__initialize_static_members`` (bundle lines 419-551); each item
    class's ``SERVER_KEY`` (e.g. ``CollectableItemUnitVO``, bundle line 15494)
    """

    _value_: str
    server_key: str
    """The key the server sends this kind under; empty for ``CURRENCY`` and ``OTHER``."""

    def __new__(cls, value: str, server_key: str = "") -> CollectableKind:
        member = str.__new__(cls, value)
        member._value_ = value
        member.server_key = server_key
        return member

    RELIC_EQUIPMENT = "relicEquipment", "RI"
    WOOD = "wood", "W"
    STONE = "stone", "S"
    FOOD = "food", "F"
    COAL = "coal", "C"
    OIL = "oil", "O"
    GLASS = "glass", "G"
    IRON = "iron", "I"
    AQUAMARINE = "aquamarin", "A"
    MEAD = "mead", "MEAD"
    BEEF = "beef", "BEEF"
    HONEY = "honey", "HONEY"
    COINS = "cash", "C1"
    RUBIES = "gold", "C2"
    CURRENCY = "genericCurrency", ""
    UNITS = "units", "U"
    PLAGUE_DOCTORS = "plagueDoctors", "PLD"
    EQUIPMENT_RARENESS = "equipmentRandom", "GE"
    EQUIPMENT_UNIQUE = "equipmentUnique", "UE"
    EQUIPMENT_UNIQUE_ENCHANTED = "equipmentEnchanted", "EUE"
    HERO_RANDOM = "heroRandom", "RE"
    GEM = "gem", "GID"
    GEM_RANDOM = "gemRandom", "GLID"
    BOOSTER = "booster", "B"
    GLORY_BOOSTER = "gloryBooster", "PG"
    XP_BOOSTER = "xpBooster", "XPB"
    GALLANTRY_BOOSTER = "gallantryBooster", "GPB"
    KHAN_TABLET_BOOSTER = "khanTabletBooster", "KTB"
    SAMURAI_BOOSTER = "samuraiBooster", "STB"
    ALLIANCE_COIN_BOOSTER = "allianceCoinBooster", "ACB"
    LONG_TERM_POINT_EVENT_BOOSTER = "longTermPointEventBooster", "LTB"
    REPUTATION_BOOSTER = "reputatioPointBooster", "REPB"
    RAGE_POINT_BOOSTER = "rageBooster", "RPB"
    KHAN_MEDAL_POINT_BOOSTER = "khanMedalBooster", "KMB"
    VIP_POINTS = "vipPoints", "VP"
    VIP_TIME = "vipTime", "VT"
    XP = "xp", "XP"
    SKIP_DISCOUNT = "skipDiscount", "SD_DISABLED"
    EXTINGUISH_FIRE = "extinguishFire", "EF"
    ALIEN_PROTECTION = "alienProtection", "AIP"
    DUNGEON_PROTECTION = "dungeonProtectionTime", "DPT"
    BUILDING = "building", "D"
    RESOURCE_POINTS = "resourcePoints", "RP_OLD"
    ACHIEVEMENT_POINTS = "achievementPoints", "AP"
    CREST_SYMBOL = "crestSymbol", "CS"
    CONSTRUCTION_ITEM = "constructionItem", "CI"
    ALLIANCE_GIFT = "allianceGift", "AG"
    PERMANENT_UNIT_SLOT = "permanentUnitSlot", "PUS"
    PERMANENT_TOOL_SLOT = "permanentToolSlot", "PTS"
    CONSTRUCTION_ITEM_BLUEPRINT = "constructionItemBlueprint", "CIBP"
    MATERIAL_BAG = "materialBag", "RB"
    PAYMENT_DOUBLER = "paymentDoubler", "PD"
    GIFT_PACKAGE = "giftPackage", "GT"
    LOOT_BOX = "lootBox", "LB"
    ALLIANCE_CREST_LAYOUT = "allianceCrestLayout", "ACL"
    OTHER = "unknown", ""


class BoosterId(IntEnum):
    """
    Booster ids, as a booster reward (``{"ID": booster id, "D": duration}``) names them.

    Client: ``BoosterConst`` (dll line 18853)
    """

    OVERSEER_WOOD = 0
    OVERSEER_STONE = 1
    OVERSEER_FOOD = 2
    OVERSEER_HONEY = 3
    OVERSEER_MEAD = 4
    OVERSEER_BEEF = 5
    MARAUDER = 6
    TAX = 8
    INSTRUCTOR = 10
    CARAVAN_OVERLOADER = 11
    BUILDING_SKIP_DISCOUNT = 16
    GLORY = 17
    PERSONAL_GLORY = 18
    RETURNING_SPEED = 19
    KHAN_TABLET = 20
    XP = 21
    SAMURAI_TOKEN = 22
    LONG_TERM_POINT_EVENT = 23
    GALLANTRY_POINTS = 24
    XP_BUILDING = 25
    ALLIANCE_COIN = 26
    RAGE_POINT = 27
    KHAN_MEDAL = 28
    REPUTATION_POINT = 29
