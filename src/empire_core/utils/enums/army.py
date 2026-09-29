"""Unit production lists and slots."""

from enum import Enum, IntEnum


class ProductionListId(IntEnum):
    """
    The client's unit package lists, one per kind of production.

    Client: ``UnitProductionConst`` (dll line 19891), picked by
    ``CastleMilitaryData.getListIdByCategory`` (bundle line 138870)
    """

    SOLDIERS = 0
    TOOLS = 1
    HOSPITAL = 2
    AUXILIARIES = 3


class SlotType(str, Enum):
    """
    Whether a slot is the one producing now or one waiting in the queue.

    Client: ``RecruitmentConst.PRODUCTION_SLOT_TYPE_NAME`` / ``QUEUE_SLOT_TYPE_NAME``
    (dll line 19660)
    """

    PRODUCTION = "production"
    QUEUE = "queue"
