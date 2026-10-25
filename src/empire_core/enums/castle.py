"""Castle buildings, crafting slots, fusion catalysts, resource carts, market goods, market scopes, tax
collection and the server's weekdays."""

from enum import Enum, IntEnum


class BuildingState(IntEnum):
    """
    What a building in a castle is doing.

    Client: ``IsoBuildingStateEnum`` (bundle line 3443); an id it does not
    define reads as ``INITIAL`` (``getTypeById``, bundle line 3422)
    """

    INITIAL = 0
    BUILD_STOPPED = 1
    BUILD_IN_PROGRESS = 2
    BUILD_COMPLETED = 4
    DISASSEMBLE_STOPPED = 5
    DISASSEMBLE_IN_PROGRESS = 6
    DISASSEMBLE_COMPLETED = 8
    REPAIR_STOPPED = 9
    REPAIR_IN_PROGRESS = 10
    UPGRADE_STOPPED = 12
    UPGRADE_IN_PROGRESS = 13
    UPGRADE_COMPLETED = 15
    WAIT_FOR_SERVER = 100


class ResourceCartType(IntEnum):
    """
    The resource a resource cart carries, the ``RT`` of ``rcc``.

    Client: ``CastleResourceCartsData.getIndexFromEnumItem`` (bundle line 28808)
    """

    WOOD = 0
    STONE = 1
    FOOD = 2


class Resource(str, Enum):
    """
    A resource a market carriage can carry, by its wire key in ``G`` of ``crm``.

    The send dialog offers these on three tabs: classic (wood, stone, food),
    kingdom (coal, oil, glass, iron) and mead (honey, mead, beef). Aquamarine
    (``A``) is a collectable too but on none of the tabs.

    Client: ``CastleSendGoodsComponent.resCollectableEnums*`` (bundle line 44358),
    each ``CollectableItem*VO.SERVER_KEY`` (bundle lines 10679, 10670, 16811,
    23303, 23326, 23310, 23317, 23333, 19934, 17834)
    """

    WOOD = "W"
    STONE = "S"
    FOOD = "F"
    COAL = "C"
    OIL = "O"
    GLASS = "G"
    IRON = "I"
    HONEY = "HONEY"
    MEAD = "MEAD"
    BEEF = "BEEF"


class MarketScope(IntEnum):
    """
    Which castles a market info request covers, the ``S`` of ``cmi``.

    Client: ``C2SMarketInfoVO.SCOPE_*`` (bundle line 27014)
    """

    CURRENT_KINGDOM = 0
    ALL_KINGDOMS = 1


class ExpansionType(IntEnum):
    """
    How a castle expansion is paid for, the ``CT`` of ``ebe``.

    Client: ``IsoExpansionEnum`` (bundle line 49539)
    """

    PREMIUM = 0
    NORMAL = 1


class TaxStatus(IntEnum):
    """
    Where a tax collection stands.

    Client: ``TaxInfoVO.TAXSTATUS_*`` (bundle line 29576)
    """

    NONE = 0
    COLLECTING = 1
    WAIT_FOR_COLLECT = 2


class KingdomTransferType(IntEnum):
    """
    What a transfer to another kingdom or to a treasure map carries, the ``TT`` of a transfer skip.

    The client names no constant; it passes the numbers itself.

    Client: ``KingdomUnitsTravelMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 37497),
    ``KingdomGoodsTravelMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 55567),
    ``CastleStartSeasonEventDialogSupport.onMouseUp`` (bundle lines 99541, 99543)
    """

    UNITS = 1
    GOODS = 2


class ConstructionItemMode(IntEnum):
    """How to equip a construction item.

    REPLACE returns the previous item to storage for its coin removal cost;
    OVERWRITE discards it. ADD fills an empty slot.

    Client: ``C2SConstructionItemModeEnum`` (bundle lines 49017-49018),
    ``CastleConstructionItemsOverwriteDialog`` (bundle lines 79292-79307).
    """

    ADD = 0
    REPLACE = 1
    OVERWRITE = 2


class Weekday(IntEnum):
    """
    A day of the week as the server numbers it, Sunday first.

    Client: ``TimeConst`` (dll line 19802)
    """

    SUNDAY = 1
    MONDAY = 2
    TUESDAY = 3
    WEDNESDAY = 4
    THURSDAY = 5
    FRIDAY = 6
    SATURDAY = 7


class DecorationStorageId(IntEnum):
    """
    A decoration storage, a ``sin`` storage's ``SID``; an event kingdom's own storage is its kingdom or map id.

    Client: ``DecorationConst.GLOBAL_DECORATION_STORAGE_ID`` and ``AREA_INVENTORY_STORAGE_ID``,
    ``getStorageID`` (dll lines 19001-19016)
    """

    GLOBAL = 1
    AREA_INVENTORY = 2


class CraftingSlotType(str, Enum):
    """
    The two kinds of slot in a crafting queue: the slots crafting now, and the slots waiting behind them.

    Client: ``CraftingSlotVO.SLOT_TYPE_PRODUCTION`` and ``SLOT_TYPE_QUEUE`` (bundle line 17023), sent as
    ``"production"``, else ``"queue"`` (``C2SCraftingCancelVO``, bundle line 111472)
    """

    PRODUCTION = "production"
    QUEUE = "queue"


class CatalystConversion(IntEnum):
    """
    Which way fusion catalysts are converted.

    Client: ``ClientConstFusion.CATALYST_CONVERSION_DIRECTION_ASSEMBLE`` and ``_DISASSEMBLE`` (bundle line 7919)
    """

    ASSEMBLE = 0
    DISASSEMBLE = 1
