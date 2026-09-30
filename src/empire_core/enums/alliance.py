"""Alliance ranks, diplomacy, member presence and help requests."""

from enum import IntEnum


class AllianceRank(IntEnum):
    """
    A member's rank in an alliance; a lower value is a higher rank.

    Client: ``AllianceConst.RANK_*`` (dll line 18805)
    """

    LEADER = 0
    COLEADER = 1
    MARSHAL = 2
    TREASURER = 3
    DIPLOMAT = 4
    RECRUITER = 5
    GENERAL = 6
    SERGEANT = 7
    MEMBER = 8
    APPLICANT = 9


class DiplomacyStatus(IntEnum):
    """
    An alliance's standing with another alliance.

    Client: ``AllianceConst.DIPLOMACY_*`` (dll line 18805)
    """

    IN_WAR = 0
    NEUTRAL = 1
    SOFT_ALLIED = 2
    REAL_ALLIED = 3


class OnlineState(IntEnum):
    """
    How recently an alliance member was online.

    Client: ``AllianceConst.ONLINESTATE_*`` (dll line 18805)
    """

    ONLINE = 0
    LAST_12_HOURS = 1
    LAST_48_HOURS = 2
    LAST_1_WEEK = 3
    LONG_AGO = 4


class HelpType(IntEnum):
    """Types of help requests in alliance."""

    HEAL = 2  # Heal wounded soldiers
    REPAIR = 3  # Repair building
    RECRUIT = 6  # Recruit soldiers
