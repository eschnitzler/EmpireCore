"""Castle buildings, resource carts and market scopes."""

from enum import IntEnum


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
