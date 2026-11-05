"""Army movement types."""

from enum import IntEnum


class MovementType(IntEnum):
    """Army movement type, the ``T`` of a movement record.

    A returning army is not a type: any type can be on its way home, which is
    the movement's ``D`` flag. ``SIEGE`` and ``OCCUPY_FACTION`` keep the client's
    names; the game shows both as occupations (see :attr:`is_occupation`).

    Client: ``ClientConstCastle.MOVEMENTTYPE_*`` (bundle line 1004)
    """

    ATTACK = 0
    DEFENCE = 1
    TRAVEL = 2
    SPY = 3
    MARKET = 4
    SIEGE = 5
    TREASUREHUNT = 6
    NPC_ATTACK = 11
    PLAGUE_DOCTOR = 14
    OCCUPY_FACTION = 15
    ALIEN_ATTACK = 17
    BERIMOND_ATTACK = 18
    ALLIANCE_CITY_ATTACK = 19
    ALLIANCE_CAMP_TAUNT_ATTACK = 20
    ALLIANCE_CAMP_ATTACK = 21
    COLLECTOR = 23
    COLLECTOR_OUTER_REALMS = 24
    RANKSWAP_OUTER_REALMS = 25
    DAIMYO_TOWNSHIP_DEFENSE = 26
    DAIMYO_TAUNT_ATTACK = 27
    DAIMYO_CASTLE_ATTACK = 28
    HORIZON_COLLECTOR_ATTACK = 29
    OUTER_REALMS_PVE_CHARGE = 30
    OUTER_REALMS_PVP_CHARGE = 31
    HORIZON_ALLIANCE_TOWER_SUPPORT = 32
    HORIZON_ALLIANCE_TOWER_ATTACK = 33
    WOLFGARD_TAUNT_ATTACK = 34

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
            MovementType.HORIZON_ALLIANCE_TOWER_SUPPORT,
        )

    @property
    def is_occupation(self) -> bool:
        """Types the client parses as ``SiegeMapmovementVO``: an occupation, ``SIEGE`` and ``OCCUPY_FACTION``.

        Players see it as the "Occupying forces" that hold an area after a capture attack won
        (``RenderSiege``, bundle line 67408, ``dialog_moveOverview_siege``). The capture attack
        before it is an attack whose attack type is conquer (``isConquerMovement``, bundle line 14404).
        """
        return self in (MovementType.SIEGE, MovementType.OCCUPY_FACTION)


_ATTACK_MOVEMENT_TYPES = frozenset(
    {
        MovementType.ATTACK,
        MovementType.NPC_ATTACK,
        MovementType.ALIEN_ATTACK,
        MovementType.BERIMOND_ATTACK,
        MovementType.ALLIANCE_CITY_ATTACK,
        MovementType.ALLIANCE_CAMP_TAUNT_ATTACK,
        MovementType.ALLIANCE_CAMP_ATTACK,
        MovementType.COLLECTOR,
        MovementType.COLLECTOR_OUTER_REALMS,
        MovementType.RANKSWAP_OUTER_REALMS,
        MovementType.DAIMYO_TAUNT_ATTACK,
        MovementType.DAIMYO_CASTLE_ATTACK,
        MovementType.HORIZON_COLLECTOR_ATTACK,
        MovementType.OUTER_REALMS_PVE_CHARGE,
        MovementType.OUTER_REALMS_PVP_CHARGE,
        MovementType.HORIZON_ALLIANCE_TOWER_ATTACK,
        MovementType.WOLFGARD_TAUNT_ATTACK,
    }
)


class MovementFilter(IntEnum):
    """
    A kind of movement the map shows or hides, an ``mvf`` filter index.

    Client: ``CastleSettingsData.parse_MVF`` (bundle line 139750) tests the ``AFS`` list for 0, 1 and 2;
    the options dialog pairs them with ``toggleMapPVPAttacks``, ``toggleMapPvPAttacksAlliance`` and
    ``toggleMapMarketBarrows``
    """

    PLAYER_ATTACKS = 0
    ALLIANCE_MEMBER_PLAYER_ATTACKS = 1
    MARKET_BARROWS = 2
