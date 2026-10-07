"""Attack options and the effect ids the combat maths reads."""

from enum import Enum, IntEnum


class AttackType(IntEnum):
    """
    Values for the ATT field.

    Client: ``CombatConst.ATTACK_TYPE_*`` (dll line 18941)
    """

    ATTACK = 0
    OUTPOST_CONQUER = 1
    VILLAGE_CONQUER = 2
    CAPITAL_CONQUER = 3
    METROPOL_CONQUER = 5
    KINGTOWER_CONQUER = 6
    CONQUER = 7
    MONUMENT_CONQUER = 8
    LABORATORY_CONQUER = 9


class LootPriority(IntEnum):
    """
    The resource an attack loots first, the LP field; NO loots everything evenly.

    The client offers the dropdown from player level ``LOOT_PRIO_MIN_LEVEL`` (20).

    Client: ``CombatConst.LOOT_PRIO_*`` (dll line 18941), offered by
    ``CastlePostAttackDialog.initLootPriority`` (bundle line 38351)
    """

    NO = 0
    WOOD = 1
    STONE = 2
    FOOD = 3
    COAL = 4
    OIL = 5
    GLASS = 6
    AQUAMARINE = 7
    IRON = 8
    HONEY = 9
    MEAD = 10
    BEEF = 11


class AutoSkipCooldownType(IntEnum):
    """
    How the target's cooldown is skipped when the attack lands, the ASCT field.

    RUBIES pays rubies to skip it.

    Client: ``AutoSkipCooldownConst`` (dll line 18836), picked in
    ``CastlePostAttackHorseDialog.selectAutoskipOption`` (bundle line 99902)
    """

    OFF = 0
    MINUTE_SKIP = 1
    RUBIES = 2


class AttackAdvisorType(IntEnum):
    """
    The attack advisor that sent an attack, the AAT field.

    NONE is the client's default for an attack no advisor sent; it has no constant.

    Client: ``AttackAdvisorConst.ADVISOR_TYPE_*`` (dll line 18832), the default ``_advisorType=0``
    (bundle line 30619), read as ``advisorType>0`` (bundle line 14344)
    """

    NONE = 0
    NOMAD = 1
    SAMURAI = 2
    BERIMOND = 3
    BARON = 4


class Flank(IntEnum):
    """
    Battle flanks.

    REINFORCEMENT_SUMMARY is not a flank troops stand on; it only appears in
    the battle log.

    Client: ``ClientConstCastle.FLANK_*`` (bundle line 1004), the summary used by
    ``CastleBattleLogDetailAdvancedDialog`` (bundle line 135711)
    """

    LEFT = 0
    MIDDLE = 1
    RIGHT = 2
    YARD = 3
    REINFORCEMENT = 4
    REINFORCEMENT_SUMMARY = 5


class BattleLogFlank(str, Enum):
    """
    The flank a general's ability took effect on, as a battle log names it.

    Client: ``CastleBattleLogPopUpDialog.getFlankNameBattleLog`` (bundle lines 135871-135877) maps the
    dialog's flank to these names; -2 and -3, its PW and EW, are the dialog's
    ``WAVE_INDEX_PRE_ATTACK`` and ``WAVE_INDEX_POST_ATTACK`` (bundle line 135994)
    """

    LEFT = "L"
    MIDDLE = "M"
    RIGHT = "R"
    YARD = "Y"
    PRE_ATTACK = "PW"
    POST_ATTACK = "EW"


class CombatEffectType(IntEnum):
    """
    Effect type ids the library reads: a subset of the client's effect types.

    Names are the client's minus the ``EFFECT_TYPE_`` prefix.

    Client: ``EffectTypeEnum`` (bundle line 1322)
    """

    WALL_BONUS = 6
    GATE_BONUS = 7
    MOAT_BONUS = 8
    MELEE_BONUS = 9
    RANGE_BONUS = 10
    WALL_REDUCTION = 19
    GATE_REDUCTION = 20
    MOAT_REDUCTION = 21
    OFFENSIVE_MELEE_BONUS = 23
    OFFENSIVE_RANGE_BONUS = 24
    ATTACK_UNIT_AMOUNT_FLANK = 28
    DEFENSE_BONUS = 31
    DEFENSE_BOOST_YARD = 32
    ATTACK_UNIT_AMOUNT_FRONT = 34
    ATTACK_BONUS = 36
    DEFENSE_SUPPORT_UNITS = 47
    DEFENSE_BOOST_FRONT = 49
    DEFENSE_BOOST_FLANK = 50
    ATTACK_SUPPORT_UNITS = 51
    RECRUITMENT_COST_DECREASE = 70
    RECRUITMENT_SPEED_BOOST = 71
    TOOL_PRODUCTION_SPEED_BOOST = 72
    UNIT_SPEED_BONUS = 102
    ATTACK_BONUS_UNIT = 148
    SPEED_BOOST_UNIT = 149
    LOOT_VALUE_BOOST_UNIT = 150
    FAME_BOOST_UNIT = 154
    ADDITIONAL_WAVE = 156
    CURRENCY_LOOT_BOOST = 168
    UNLOCK_ABILITY = 178
    ATTACK_UNIT_AMOUNT_REINFORCEMENT_BONUS = 179
    ATTACK_UNIT_AMOUNT_REINFORCEMENT_BOOST = 180
    CRAFTING_QUEUE_PRODUCTION_BOOST = 188
    RESERVE_UNIT_KILL = 208
    SPAWN_RESERVE_UNIT = 213
    MUTATE_RESERVE_UNIT = 214
    MELEE_DEFENSE_MALUS = 215
    RANGE_DEFENSE_MALUS = 217
    ABILITY_PLUNDER = 1026
