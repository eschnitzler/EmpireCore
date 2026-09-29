"""Game enumerations.

One enum per server ID space, and the enum lives next to the packets that
describe it:

- kingdom ids: :class:`empire_core.protocol.models.base.Kingdom`,
- area types, the first field of a map row (a scan's ``AI`` array and a
  movement's ``TA``/``SA`` arrays):
  :class:`empire_core.protocol.models.base.MapItemType`,
- movement types: :class:`MovementType` below.
"""

from enum import IntEnum


class MovementType(IntEnum):
    """Army movement type, the ``T`` of a movement record.

    A returning army is not a type: any type can be on its way home, which is
    the movement's ``D`` flag.

    Client: ``ClientConstCastle`` MOVEMENTTYPE_* constants.
    """

    ATTACK = 0
    DEFENCE = 1
    TRAVEL = 2
    SPY = 3
    MARKET = 4
    SIEGE = 5
    TREASUREHUNT = 6
    NPC_ATTACK = 11
    PLAGUEMONK = 14
    OCCUPY_FACTION = 15
    ALIEN_ATTACK = 17
    FACTION_ATTACK = 18
    ALLIANCE_CITY_ATTACK = 19
    ALLIANCE_CAMP_TAUNT_ATTACK = 20
    ALLIANCE_CAMP_ATTACK = 21
    COLLECTOR = 23
    COLLECTOR_TEMP_SERVER = 24
    RANKSWAP_TEMP_SERVER = 25
    DAIMYO_TOWNSHIP_DEFENSE = 26
    DAIMYO_TAUNT_ATTACK = 27
    DAIMYO_CASTLE_ATTACK = 28
    ALLIANCE_BATTLE_GROUND_COLLECTOR_ATTACK = 29
    TEMPSERVER_PVE_CHARGE = 30
    TEMPSERVER_PVP_CHARGE = 31
    ABG_ALLIANCE_TOWER_SUPPORT = 32
    ABG_ALLIANCE_TOWER_ATTACK = 33
    WOLFKING_TAUNT_ATTACK = 34
    UNKNOWN = -1

    @property
    def is_attack(self) -> bool:
        """Types the client parses as an attack army (``ArmyAttackMapmovementVO`` or a subclass)."""
        return self in _ATTACK_MOVEMENT_TYPES

    @property
    def is_support(self) -> bool:
        """Types the client parses as a support army (``SupportDefenceMapmovementVO``)."""
        return self in (
            MovementType.DEFENCE,
            MovementType.DAIMYO_TOWNSHIP_DEFENSE,
            MovementType.ABG_ALLIANCE_TOWER_SUPPORT,
        )

    @property
    def is_siege(self) -> bool:
        """Types the client parses as a siege (``SiegeMapmovementVO``)."""
        return self in (MovementType.SIEGE, MovementType.OCCUPY_FACTION)


_ATTACK_MOVEMENT_TYPES = frozenset(
    {
        MovementType.ATTACK,
        MovementType.NPC_ATTACK,
        MovementType.ALIEN_ATTACK,
        MovementType.FACTION_ATTACK,
        MovementType.ALLIANCE_CITY_ATTACK,
        MovementType.ALLIANCE_CAMP_TAUNT_ATTACK,
        MovementType.ALLIANCE_CAMP_ATTACK,
        MovementType.COLLECTOR,
        MovementType.COLLECTOR_TEMP_SERVER,
        MovementType.RANKSWAP_TEMP_SERVER,
        MovementType.DAIMYO_TAUNT_ATTACK,
        MovementType.DAIMYO_CASTLE_ATTACK,
        MovementType.ALLIANCE_BATTLE_GROUND_COLLECTOR_ATTACK,
        MovementType.TEMPSERVER_PVE_CHARGE,
        MovementType.TEMPSERVER_PVP_CHARGE,
        MovementType.ABG_ALLIANCE_TOWER_ATTACK,
        MovementType.WOLFKING_TAUNT_ATTACK,
    }
)
