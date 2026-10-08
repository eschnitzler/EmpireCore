"""Alliance ranks, diplomacy, member presence, help requests, bookmarks, buffs and the chronicle."""

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

    @property
    def text_id(self) -> str:
        """
        The text id of the rank's name, ``dialog_alliance_rank<n>``, numbered in an order of its own:
        ``text(AllianceRank.COLEADER.text_id)`` is ``"Deputy"`` (:func:`empire_core.texts.text`).

        Client: ``"dialog_alliance_rank" + CastleAllianceData.getTextIDForRank(rank)`` (bundle line
        44529), numbered by ``CastleAllianceData.TEXT_IDS_FOR_RANK_IDS`` (bundle line 11626)
        """
        return f"dialog_alliance_rank{_RANK_TEXT_NUMBERS[self]}"


_RANK_TEXT_NUMBERS = {
    AllianceRank.LEADER: 0,
    AllianceRank.GENERAL: 1,
    AllianceRank.SERGEANT: 2,
    AllianceRank.MEMBER: 3,
    AllianceRank.COLEADER: 4,
    AllianceRank.MARSHAL: 5,
    AllianceRank.TREASURER: 6,
    AllianceRank.DIPLOMAT: 7,
    AllianceRank.RECRUITER: 8,
    AllianceRank.APPLICANT: 9,
}


class DiplomacyStatus(IntEnum):
    """
    An alliance's standing with another alliance.

    Client: ``AllianceConst.DIPLOMACY_*`` (dll line 18805)
    """

    IN_WAR = 0
    NEUTRAL = 1
    SOFT_ALLIED = 2
    REAL_ALLIED = 3

    @property
    def text_id(self) -> str:
        """
        The text id of the status's name, ``dialog_allianceDiplomacy_status<n>``: ``"War"`` for ``IN_WAR``.

        Client: ``AllianceActionListItemVO.getActionText`` (bundle line 66342)
        """
        return f"dialog_allianceDiplomacy_status{self.value}"


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
    """
    What an alliance help request asks for.

    Client: ``AllianceConst.ALLIANCE_HELP_*`` (dll line 18805)
    """

    RECRUITMENT = 1
    HEAL_UNIT = 2
    REPAIR = 3
    BUILD = 4
    LOOP_RECRUIT = 5
    RECRUITMENT_LIST = 6


class BookmarkType(IntEnum):
    """
    What a map bookmark marks.

    Client: ``AllianceConst.BOOKMARK_TYPE_*`` (dll line 18805)
    """

    PLAYER_ENEMY = 0
    PLAYER_FRIEND = 1
    ALLIANCE_FREE_ATTACK = 2
    ALLIANCE_DEFEND = 3
    ALLIANCE_ATTACK_ORDER = 4


class AllianceChronicleAction(IntEnum):
    """
    What an entry of the alliance chronicle records.

    Names follow ``AllianceConst`` with its abbreviations spelled out
    (C1 coins, C2 rubies, RES resources, TRIBUT tribute, METROPOL metropolis).

    Client: ``AllianceConst`` action values (dll line 18805)
    """

    MEMBER_JOIN = 0
    MEMBER_LEFT = 1
    MEMBER_KICKED = 2
    MEMBER_NEW_LEADER = 3
    MEMBER_DEMOTE = 4
    MEMBER_PROMOTE = 5
    MEMBER_DONATE_COINS = 6
    MEMBER_DONATE_RUBIES = 7
    MEMBER_DONATE_RESOURCES = 8
    CHANGE_NAME = 9
    CHANGE_ANNOUNCEMENT = 10
    CHANGE_DESCRIPTION = 11
    UPGRADE = 12
    CHANGE_DIPLOMACY = 13
    GET_REQUEST_DIPLOMACY = 14
    SEND_REQUEST_DIPLOMACY = 15
    REFUSE_DIPLOMACY = 16
    LEVEL_UP = 17
    LEVEL_DOWN = 18
    DONATE_COINS_BY_LEVEL_UP = 19
    DONATE_RUBIES_BY_LEVEL_UP = 20
    DONATE_RESOURCES_BY_LEVEL_UP = 21
    MEMBER_EARN_FAME = 22
    CONQUERED_CAPITAL = 23
    LOST_CAPITAL = 24
    LOSING_CAPITAL = 25
    TOURNAMENT_REWARD = 26
    TOURNAMENT_RANK = 27
    CONQUERED_METROPOLIS = 28
    LOST_METROPOLIS = 29
    LOSING_METROPOLIS = 30
    MEMBER_INACTIVE_KICK = 31
    ALLIANCE_RANK_OF_LAST_ROUND = 32
    NEW_KINGS_NAME = 33
    PRIZE_COINS_OF_LAST_ROUND = 35
    PRIZE_RUBIES_OF_LAST_ROUND = 36
    STORM_ISLAND_ENDED = 37
    TRIBUTE_PAY_COINS = 38
    TRIBUTE_PAY_RUBIES = 39
    TRIBUTE_PAY_RESOURCES = 40
    TRIBUTE_GET_COINS = 41
    TRIBUTE_GET_RUBIES = 42
    TRIBUTE_GET_RESOURCES = 43
    ACTIVATE_TEMP_BUFF = 44
    EXTEND_TEMP_BUFF = 45
    ABANDONED_CAPITAL = 46
    ABANDONED_METROPOLIS = 47
    ALLIANCE_FOUNDED = 48
    FOUNDED_NOBLE_HOUSE = 49
    SET_EMBLEM = 50
    KING_CONFERRED_ISLAND_TITLE = 56
    CAPITAL_OWNER_JOINED = 57
    METROPOLIS_OWNER_JOINED = 58
    REWARD_COINS = 59
    REWARD_RUBIES = 60
    ALLIANCE_BATTLE_GROUND_OWNED_TOWER_DEFEATED = 61
    ALLIANCE_BATTLE_GROUND_MALUS_INCREASED = 62
    ALLIANCE_BATTLE_GROUND_POINTS_GAINED = 63
    ALLIANCE_BATTLE_GROUND_MALUS_RESET = 64
    DAIMYO_ALLIANCE_CASTLE_CONTRACT_COMPLETED = 65
    DAIMYO_ALLIANCE_TOWNSHIP_CONTRACT_COMPLETED = 66


class AllianceBuffType(IntEnum):
    """
    An alliance upgrade or boost: the series an alliance buff's levels belong to.

    Names follow ``AllianceConst.TYPE_*`` (``DAIYMO`` spelled ``DAIMYO``); ``MEMBERS`` raises the member limit and
    ``FORGE_UPGRADE`` upgrades the alliance smithy.

    Client: ``AllianceConst.TYPE_*`` (dll line 18805), the series ids of
    ``allianceBuffData.getAllianceBuffVoBySeriesIDAndLevel`` (bundle line 27189); 22 to 25 are
    ``AllianceRaidConst.BUFF_SERIES_RAID_BOSS_ATTACK_*`` (bundle line 33863)
    """

    MEMBERS = 0
    DEFENSE_SPEED_BOOST = 1
    MARKET_SPEED_BOOST = 2
    DEPOSIT_BONUS = 3
    MARAUDER_BONUS = 4
    ATTACK_SPEED_BOOST = 5
    FORGE_UPGRADE = 6
    TEMP_ATTACK_POWER_BOOST = 7
    TEMP_DEFENSE_POWER_BOOST = 8
    TEMP_GLORY_BOOST = 9
    TEMP_DEFENSE_SPEED_BOOST = 10
    NOBLE_HOUSE = 11
    RAGE_POINT_BOOST = 12
    COOLDOWN_REDUCTION_KHAN = 13
    COOLDOWN_REDUCTION_NOMADS = 14
    INFLUENCE_POINT_BOOST = 15
    ALIEN_ATTACK_BOOST = 16
    DAIMYO_ATTACK_BOOST = 17
    KHAN_DEFENSE_BOOST = 18
    HEALING_SPEED_BOOST = 19
    COOLDOWN_REDUCTION_SAMURAI_CAMP = 20
    COOLDOWN_REDUCTION_DAIMYO = 21
    TEMP_RAID_BOSS_COMMON_ATTACK_BOOST = 22
    TEMP_RAID_BOSS_RARE_ATTACK_BOOST = 23
    TEMP_RAID_BOSS_EPIC_ATTACK_BOOST = 24
    TEMP_RAID_BOSS_LEGENDARY_ATTACK_BOOST = 25

    @property
    def text_id(self) -> str | None:
        """
        The text id of the buff's name, None for ``FORGE_UPGRADE`` and ``NOBLE_HOUSE``, which have none.

        Client: ``CastleEffectsHelper.getNameTextId`` (bundle line 4191)
        """
        return _BUFF_TEXT_IDS.get(self)


_BUFF_TEXT_IDS = {
    AllianceBuffType.MEMBERS: "dialog_alliance_member",
    AllianceBuffType.DEFENSE_SPEED_BOOST: "dialog_alliance_defenseBoost",
    AllianceBuffType.MARKET_SPEED_BOOST: "dialog_alliance_marketBoost",
    AllianceBuffType.DEPOSIT_BONUS: "dialog_alliance_depositBonus",
    AllianceBuffType.MARAUDER_BONUS: "dialog_alliance_permanentBoost_lootCapacity",
    AllianceBuffType.ATTACK_SPEED_BOOST: "dialog_alliance_movementBoost",
    AllianceBuffType.TEMP_GLORY_BOOST: "dialog_alliance_temporaryBoost_glory",
    AllianceBuffType.TEMP_DEFENSE_SPEED_BOOST: "dialog_alliance_temporaryBoost_supportTravel",
    AllianceBuffType.TEMP_ATTACK_POWER_BOOST: "dialog_alliance_temporaryBoost_attackPower",
    AllianceBuffType.TEMP_DEFENSE_POWER_BOOST: "dialog_alliance_temporaryBoost_defencePower",
    AllianceBuffType.RAGE_POINT_BOOST: "dialog_alliance_temporaryBoost_allianceRageBoost",
    AllianceBuffType.COOLDOWN_REDUCTION_KHAN: "dialog_alliance_temporaryBoost_allianceCooldownReductionKhan",
    AllianceBuffType.COOLDOWN_REDUCTION_NOMADS: "dialog_alliance_temporaryBoost_allianceCooldownReductionNomad",
    AllianceBuffType.ALIEN_ATTACK_BOOST: "dialog_alliance_temporaryBoost_allianceAttackBoostAliens",
    AllianceBuffType.DAIMYO_ATTACK_BOOST: "dialog_alliance_temporaryBoost_allianceAttackBoostDaimyo",
    AllianceBuffType.KHAN_DEFENSE_BOOST: "dialog_alliance_temporaryBoost_allianceDefenseBoostKhan",
    AllianceBuffType.HEALING_SPEED_BOOST: "dialog_alliance_temporaryBoost_healingSpeedIncreaseBoostPremium",
    AllianceBuffType.INFLUENCE_POINT_BOOST: "dialog_alliance_temporaryBoost_BGCollectorBoost",
    AllianceBuffType.COOLDOWN_REDUCTION_SAMURAI_CAMP: "dialog_alliance_temporaryBoost_allianceSamuraiCooldownReduction",
    AllianceBuffType.COOLDOWN_REDUCTION_DAIMYO: "dialog_alliance_temporaryBoost_allianceDaimyoCooldownReduction",
    AllianceBuffType.TEMP_RAID_BOSS_COMMON_ATTACK_BOOST: "dialog_alliance_temporaryBoost_TemporaryCommonAttackBonus",
    AllianceBuffType.TEMP_RAID_BOSS_RARE_ATTACK_BOOST: "dialog_alliance_temporaryBoost_TemporaryRareAttackBonus",
    AllianceBuffType.TEMP_RAID_BOSS_EPIC_ATTACK_BOOST: "dialog_alliance_temporaryBoost_TemporaryEpicAttackBonus",
    AllianceBuffType.TEMP_RAID_BOSS_LEGENDARY_ATTACK_BOOST: (
        "dialog_alliance_temporaryBoost_TemporaryLegendaryAttackBonus"
    ),
}
