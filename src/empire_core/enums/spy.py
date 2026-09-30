"""Spy mission types and spy log subtypes."""

from enum import IntEnum


class SpyType(IntEnum):
    """
    Kind of spy mission, the ST field of ``csm`` and of a spy movement.

    ``SE`` in ``csm`` is the accuracy (50-100) for a military or economy
    mission and the damage (10-50) for sabotage. The client sends plague
    monks with ``cpm``, never with ``csm``.

    Client: ``ClientConstCastle.SPYTYPE_*`` (bundle line 1004),
    ``CastlePostSpyDialog.spyCastle`` (bundle line 38459),
    ``CastleSpyDialogPlagueState.spyCastle`` (bundle line 72135)
    """

    MILITARY = 0
    ECO = 1
    SABOTAGE = 2
    PLAGUE = 3


class SpyLogType(IntEnum):
    """
    Kind of mission a spy log in the mailbox is about: the first number of its header.

    These differ from :class:`SpyType`: a military mission's log is ``DEFENCE``.
    ``SABOTAGE`` (0) is also the subtype of an aborted mission.

    Client: ``MessageConst.SUBTYPE_SPY_*`` (dll line 19516)
    """

    SABOTAGE = 0
    DEFENCE = 1
    ECO = 2
    PLAGUE_MONK = 3


class SpyLogResult(IntEnum):
    """
    How a spy mission ended, the second number of a spy log's header.

    The spies were lost when the attacker failed or the defender succeeded.

    Client: ``MessageConst.SUBTYPE_ATTACKER_*`` and ``SUBTYPE_DEFENDER_*`` (dll line 19516),
    ``AMessageSpyVO.isFailedSpyLog`` (bundle line 40204)
    """

    ATTACKER_SUCCESS = 0
    DEFENDER_SUCCESS = 1
    ATTACKER_FAILED = 2
    DEFENDER_FAILED = 3
