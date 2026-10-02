"""Mailbox message types and the subtypes of spy and battle logs."""

from enum import IntEnum


class MessageType(IntEnum):
    """
    What a mailbox message is.

    Client: ``MessageConst.MESSAGE_TYPE_*`` and ``MESSAGE_RUIN_INFO`` (dll line 19516)
    """

    SYSTEM = 0
    USER_IN = 1
    USER_OUT = 2
    SPY_PLAYER = 3
    SPY_NPC = 4
    CONQUERABLE_AREA = 5
    BATTLE_LOG = 6
    ALLIANCE_REQUEST = 20
    ALLIANCE_WAR = 21
    ALLIANCE_NEWSLETTER = 22
    ALLIANCE_BOOKMARK = 23
    LOWLEVEL_UNDERWORLD = 40
    USER_SURVEY = 50
    ATTACK_CANCELLED = 67
    SPY_CANCELLED = 68
    STARVE_INFO = 70
    BUILDING_DISABLED = 71
    MARKET_CARRIAGE_ARRIVED = 75
    ABO = 80
    PAYMENT_DOPPLER = 81
    REBUY = 90
    SPECIAL_EVENT = 95
    STARVE_VILLAGE_LOST = 96
    TOURNAMENT_OVER = 97
    ISLAND_KINGDOM_TITLE = 98
    ISLAND_KINGDOM_REWARD = 99
    STARVE_ISLE_RESOURCE_LOST = 100
    RUIN_INFO = 102
    PLAYER_GIFT = 103
    SUBSCRIPTION = 104
    ATTACK_COUNT_THRESHOLD = 105
    THANK_YOU_PACKAGE = 117
    DOWNTIME_STATUS = 118
    DIVISION_CHANGE = 119
    ATTACK_ADVISOR_FAILURE = 120
    ATTACK_ADVISOR_SUMMARY = 121
    HIGHSCORE_BONUS = 122
    EVENT_ANNOUNCEMENT = 123
    POPUP = 124
    PATCH_NOTES = 125
    PRIVATE_OFFER = 126
    TEXT_ID = 127


class LogResult(IntEnum):
    """
    How the mission or battle a spy log or battle log reports ended.

    The second number of a spy log's header, the third of a battle log's.
    A spy log's spies were lost when the attacker failed or the defender succeeded.

    Client: ``MessageConst.SUBTYPE_ATTACKER_*`` and ``SUBTYPE_DEFENDER_*`` (dll line 19516),
    ``AMessageSpyVO.isFailedSpyLog`` (bundle line 40204)
    """

    ATTACKER_SUCCESS = 0
    DEFENDER_SUCCESS = 1
    ATTACKER_FAILED = 2
    DEFENDER_FAILED = 3


class BattleLogAttackType(IntEnum):
    """
    The kind of attack a battle log reports: the second number of its header.

    Client: ``MessageConst.SUBTYPE_ATTACK_NORMAL`` to ``SUBTYPE_ATTACK_SHADOW`` (dll line 19516)
    """

    NORMAL = 0
    CONQUER = 1
    NPC = 2
    OCCUPY = 3
    SHADOW = 4
