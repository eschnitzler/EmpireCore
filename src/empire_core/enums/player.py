"""Player progress constants."""

from enum import Enum, IntEnum


class TitleSystem(str, Enum):
    """
    A title system: the ``type`` of a title in the items data, and a ``uar``'s ``PFX`` and ``SFX``.

    Client: ``ClientConstTitle.GLORY_TITLE``, ``BRAVERY_TITLE`` and ``ISLAND_TITLE`` (bundle line 6767)
    """

    GLORY = "FAME"
    FACTION = "FACTION"
    ISLAND = "ISLE"


class PremiumAccountType(IntEnum):
    """
    The premium account's type, a ``boi``'s ``PT``.

    Client: ``PremiumConst.PREMIUM_ACCOUNT_*`` (dll line 19628), compared with ``PT`` in
    ``TaxConst.getCollectorC2Costs`` (dll line 19779); ``PT`` also indexes the three-entry
    ``PremiumConst.FACTOR_*`` arrays (dll lines 19622-19625, bundle line 90238)
    """

    BRONZE = 0
    SILVER = 1
    GOLD = 2


class MercenaryMissionState(IntEnum):
    """
    Where a mercenary mission stands, an ``mpe`` mission's ``S``.

    Client: ``CastleMercenaryData.MISSION_STATE_DEFAULT`` to ``MISSION_STATE_COLLECTED`` (bundle line 28881)
    """

    OPEN = 0
    STARTED = 1
    COLLECTABLE = 2
    COLLECTED = 3


class MercenaryMissionRarity(IntEnum):
    """
    A mercenary mission's rarity, an ``mpe`` mission's ``Q``.

    Client: ``CastleMercenaryMissionItemVO.RARITY_FREE`` to ``RARITY_LEGENDARY`` (bundle line 81149)
    """

    FREE = 0
    COMMON = 1
    RARE = 2
    EPIC = 3
    LEGENDARY = 4
