"""Event performance identifiers."""

from enum import Enum, IntEnum


class PerformanceStatistic(IntEnum):
    """Client: ``StatisticsConst`` (dll.pretty lines 86731-86751)."""

    CONTRIBUTION_TO_ALLIANCE_INFLUENCE = 1
    CITY_STATES_CONQUERED = 2
    CAPITALS_ATTACKED = 3
    INFLUENCE_FROM_CITY_STATES = 4
    INFLUENCE_FROM_ENEMY_CASTLES = 5
    INFLUENCE_FROM_ENEMY_CAPITALS = 6
    CONTRIBUTION_TO_ALLIANCE_TOWER_POINTS = 7
    ALLIANCE_TOWERS_DEFEATED = 8
    ALLIANCE_TOWERS_DEFENDED = 9
    ALLIANCE_CASTLES_DEFENDED = 10
    TOWER_EFFECT_BUFFS_ACTIVATED = 11
    TOWER_EFFECT_BUFFS_PURCHASED = 12
    SUPPORT_TROOPS_SENT_TO_ALLIANCE_TOWERS = 13
    RESOURCE_TOWERS_DEFEATED = 14
    AQUAMARINE_TOTAL = 15
    AQUAMARINE_RESOURCE_ISLE = 16
    AQUAMARINE_STORM_FORTRESS = 17
    AQUAMARINE_PVP = 18
    AQUAMARINE_SPENT = 19
    AQUAMARINE_LOST_PVP = 20
    AQUAMARINE_FIRST_POINTS_TIMESTAMP = 21


class BerimondFaction(IntEnum):
    """
    A side of the Battle for Berimond, by the name the game shows it: the blue House of Ursidae and the red House of
    Gerbrandt.

    Client: ``FactionConst.BLUE_FACTION`` and ``RED_FACTION`` (dll line 19333); names from the ``blue_faction`` and
    ``red_faction`` texts
    """

    URSIDAE = 0
    """The House of Ursidae, the blue faction."""
    GERBRANDT = 1
    """The House of Gerbrandt, the red faction."""


class BerimondSpecialCampType(str, Enum):
    """
    What a Battle for Berimond special camp is, by the name the game shows it; the value is its ``type`` column.

    Client: ``FactionEventVO.parseAdditionalXmlFromRoot`` (bundle line 7398) reads ``DUNGEON`` rows as towers and
    ``CAPITAL`` rows as capitals; names from ``FactionTowerMapobjectVO``, ``FactionCapitalMapobjectVO`` and
    ``FactionVillageMapobjectVO.areaNameString`` (bundle lines 22840, 22792, 28559)
    """

    WATCHTOWER = "DUNGEON"
    CAPITAL = "CAPITAL"
    RESOURCE_VILLAGE = "VILLAGES"


class BerimondLane(IntEnum):
    """
    A lane of the Battle for Berimond map, each leading to a faction's capital; red is the House of Gerbrandt, blue
    the House of Ursidae (:class:`BerimondFaction`).

    Client: ``FactionCapitalInfoVO.RED_TOP`` to ``BLUE_CAPITAL`` (bundle line 88021)
    """

    GERBRANDT_TOP = 1
    GERBRANDT_MIDDLE = 2
    GERBRANDT_BOTTOM = 3
    GERBRANDT_CAPITAL = 4
    URSIDAE_TOP = 5
    URSIDAE_MIDDLE = 6
    URSIDAE_BOTTOM = 7
    URSIDAE_CAPITAL = 8


class RaidBossCardStatus(IntEnum):
    """Client: ``AllianceRaidConst`` (dll.pretty lines 78938-78942)."""

    AVAILABLE = 0
    UNAVAILABLE = 1
    ONGOING = 2
    LOCKED_FINAL_DEFEATED = 3
    LOCKED_ABORTED = 4


class WheelOfFortuneType(IntEnum):
    """
    Which Wheel of Fortune a spin turns.

    Client: ``C2SLuckyWheelSpinVO`` (bundle line 59784) spins the Wheel of Unimaginable Affluence for 1, the Wheel of
    Fortune otherwise
    """

    WHEEL_OF_FORTUNE = 0
    WHEEL_OF_UNIMAGINABLE_AFFLUENCE = 1


class GachaRarity(IntEnum):
    """Client: ``GachaComponentRewards.addRarityAnimation`` (bundle lines 57184-57192)."""

    COMMON = 1
    RARE = 2
    EPIC = 3
    LEGENDARY = 4


class WorldCupVote(IntEnum):
    """Client: ``WorldCupEventVO.VOTE_VALUE_*`` (bundle line 24601); -1 means no vote yet."""

    DRAW = 0
    TEAM_A = 1
    TEAM_B = 2


class PackageBuyType(IntEnum):
    """
    Where a package was bought.

    Client: ``PackageConst.BUY_TYPE_*`` (dll line 19553)
    """

    EVENT = 0
    PRIVATE_OFFER = 1
    VIP = 2
    SLUM = 3
    PRIME_DAY = 4
    CRUSADE_MAP = 5
    GIFT = 6
    FUSION = 7
    OFFERINGS = 8
    GENERAL_SKILLS_RESET_TOKEN = 9
