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
    class's ``SERVER_KEY`` and ``XML_KEY`` (e.g. ``CollectableItemUnitVO``, bundle line 15494)
    """

    _value_: str
    server_key: str
    """The key the server sends this kind under; empty for ``CURRENCY`` and ``OTHER``."""
    xml_keys: tuple[str, ...]
    """The columns the items tables give this kind under, as in a ``rewards`` row; empty for none."""

    def __new__(cls, value: str, server_key: str = "", xml_keys: tuple[str, ...] = ()) -> CollectableKind:
        member = str.__new__(cls, value)
        member._value_ = value
        member.server_key = server_key
        member.xml_keys = xml_keys
        return member

    RELIC_EQUIPMENT = "relicEquipment", "RI", ("relicEquipments",)
    WOOD = "wood", "W", ("wood",)
    STONE = "stone", "S", ("stone",)
    FOOD = "food", "F", ("food",)
    COAL = "coal", "C", ("coal",)
    OIL = "oil", "O", ("oil",)
    GLASS = "glass", "G", ("glass",)
    IRON = "iron", "I", ("iron",)
    AQUAMARINE = "aquamarin", "A", ("aquamarine",)
    MEAD = "mead", "MEAD", ("mead",)
    BEEF = "beef", "BEEF", ("beef",)
    HONEY = "honey", "HONEY", ("honey",)
    COINS = "cash", "C1", ("currency1", "c1")
    RUBIES = "gold", "C2", ("currency2", "c2")
    CURRENCY = "genericCurrency", ""
    UNITS = "units", "U", ("units",)
    PLAGUE_DOCTORS = "plagueDoctors", "PLD", ("plagueDoctor",)
    EQUIPMENT_RARENESS = "equipmentRandom", "GE", ("equipmentRarenessID",)
    EQUIPMENT_UNIQUE = "equipmentUnique", "UE", ("equipmentIDs",)
    EQUIPMENT_UNIQUE_ENCHANTED = "equipmentEnchanted", "EUE", ("enchantedEquipmentIDs",)
    HERO_RANDOM = "heroRandom", "RE"
    GEM = "gem", "GID", ("gemIDs",)
    GEM_RANDOM = "gemRandom", "GLID", ("gemLevelIDs",)
    BOOSTER = "booster", "B", ("boosters",)
    GLORY_BOOSTER = "gloryBooster", "PG"
    XP_BOOSTER = "xpBooster", "XPB"
    GALLANTRY_BOOSTER = "gallantryBooster", "GPB"
    KHAN_TABLET_BOOSTER = "khanTabletBooster", "KTB"
    SAMURAI_BOOSTER = "samuraiBooster", "STB"
    ALLIANCE_COIN_BOOSTER = "allianceCoinBooster", "ACB"
    LONG_TERM_POINT_EVENT_BOOSTER = "longTermPointEventBooster", "LTB", ("longTermPointEventBooster",)
    REPUTATION_BOOSTER = "reputatioPointBooster", "REPB", ("reputationPointBooster",)
    RAGE_POINT_BOOSTER = "rageBooster", "RPB"
    KHAN_MEDAL_POINT_BOOSTER = "khanMedalBooster", "KMB"
    VIP_POINTS = "vipPoints", "VP", ("vipPoints",)
    VIP_TIME = "vipTime", "VT", ("vipTime",)
    XP = "xp", "XP", ("xp",)
    SKIP_DISCOUNT = "skipDiscount", "SD_DISABLED", ("skipDiscount",)
    EXTINGUISH_FIRE = "extinguishFire", "EF", ("extinguishFire",)
    ALIEN_PROTECTION = "alienProtection", "AIP", ("alienProtection",)
    DUNGEON_PROTECTION = "dungeonProtectionTime", "DPT", ("dungeonProtectionTime",)
    BUILDING = "building", "D", ("decoWodID", "buildingWodID")
    RESOURCE_POINTS = "resourcePoints", "RP_OLD", ("resourcePoints",)
    ACHIEVEMENT_POINTS = "achievementPoints", "AP", ("achievementPoints",)
    CREST_SYMBOL = "crestSymbol", "CS", ("crestSymbolIDs",)
    CONSTRUCTION_ITEM = "constructionItem", "CI", ("constructionItemIDs",)
    ALLIANCE_GIFT = "allianceGift", "AG", ("allianceGift",)
    PERMANENT_UNIT_SLOT = "permanentUnitSlot", "PUS", ("unitSlot",)
    PERMANENT_TOOL_SLOT = "permanentToolSlot", "PTS", ("toolSlot",)
    CONSTRUCTION_ITEM_BLUEPRINT = "constructionItemBlueprint", "CIBP"
    MATERIAL_BAG = "materialBag", "RB", ("rewardBags",)
    PAYMENT_DOUBLER = "paymentDoubler", "PD", ("paymentDoppler",)
    GIFT_PACKAGE = "giftPackage", "GT", ("giftPackageIDs",)
    LOOT_BOX = "lootBox", "LB", ("lootBox",)
    ALLIANCE_CREST_LAYOUT = "allianceCrestLayout", "ACL", ("allianceCoatLayout",)
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


class RewardGrantType(IntEnum):
    """
    Who a reward goes to.

    Client: ``RewardConst.PLAYER``, ``ALLIANCE``, ``ALLIANCE_MEMBER`` (dll line 19709)
    """

    PLAYER = 0
    ALLIANCE = 1
    ALLIANCE_MEMBER = 2
