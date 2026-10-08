"""Castle buildings, resource carts, market goods, market scopes and tax collection."""

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
    What a transfer to another kingdom carries, the ``TT`` of a transfer skip.

    The client names no constant; it passes the numbers itself.

    Client: ``KingdomUnitsTravelMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 37497),
    ``KingdomGoodsTravelMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 55567)
    """

    UNITS = 1
    GOODS = 2
