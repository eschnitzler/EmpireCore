"""Attack options and the effect ids the combat maths reads."""

from enum import IntEnum


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
    KINGS_TOWER_CONQUER = 6
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

    Client: ``AutoSkipCooldownConst`` (dll line 18836), picked in
    ``CastlePostAttackHorseDialog.selectAutoskipOption`` (bundle line 99902)
    """

    OFF = 0
    MINUTE_SKIP = 1
    C2 = 2


class Flank(IntEnum):
    """Attack-screen flanks (``ClientConstCastle.FLANK_*``)."""

    LEFT = 0
    MIDDLE = 1
    RIGHT = 2
    YARD = 3
    REINFORCEMENT = 4


class CombatEffectType(IntEnum):
    """
    Effect type ids the attack path reads.

    Verified against both the client's ``EffectTypeEnum`` and the items
    ``effecttypes`` table.
    """

    MELEE_BONUS = 9
    RANGE_BONUS = 10
    WALL_REDUCTION = 19
    GATE_REDUCTION = 20
    MOAT_REDUCTION = 21
    OFFENSIVE_MELEE_BONUS = 23
    OFFENSIVE_RANGE_BONUS = 24
    ATTACK_UNIT_AMOUNT_FLANK = 28
    ATTACK_UNIT_AMOUNT_FRONT = 34
    REINFORCEMENT_BONUS = 179
    REINFORCEMENT_BOOST = 180
    ATTACK_BONUS = 36
    ADDITIONAL_WAVE = 156
