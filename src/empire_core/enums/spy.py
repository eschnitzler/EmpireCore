"""Spy mission types."""

from enum import IntEnum


class SpyType(IntEnum):
    """
    Kind of spy mission, the ST field of ``csm``.

    Client: ``ClientConstCastle.SPYTYPE_*`` (bundle line 1004)
    """

    MILITARY = 0
    ECO = 1
    SABOTAGE = 2
    PLAGUE = 3
