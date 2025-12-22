from enum import IntEnum


class MapObjectType(IntEnum):
    EMPTY = 0
    CASTLE = 1
    DUNGEON = 2
    CAPITAL = 3
    OUTPOST = 4
    TREASURE_DUNGEON = 7
    TREASURE_CAMP = 8
    SHADOW_AREA = 9
    VILLAGE = 10
    BOSS_DUNGEON = 11
    KINGDOM_CASTLE = 12
    EVENT_DUNGEON = 13
    NO_LANDMARK = 14
    FACTION_CAMP = 15
    FACTION_VILLAGE = 16
    FACTION_TOWER = 17
    FACTION_CAPITAL = 18
    PLAGUE_AREA = 19
    TROOP_HOSTEL = 20
    ALIEN_CAMP = 21
    METRO = 22
    KINGS_TOWER = 23
    ISLE_RESOURCE = 24
    ISLE_DUNGEON = 25
    MONUMENT = 26
    NOMAD_CAMP = 27
    LABORATORY = 28
    SAMURAI_CAMP = 29
    FACTION_INVASION_CAMP = 30
    DYNAMIC = 31
    ROBBER_BARON_CASTLE = 32  # Added explicitly
    SAMURAI_ALIEN_CAMP = 33
    RED_ALIEN_CAMP = 34
    ALLIANCE_NOMAD_CAMP = 35
    DAIMYO_CASTLE = 37
    DAIMYO_TOWNSHIP = 38
    ABG_RESOURCE_TOWER = 40
    ABG_TOWER = 41
    WOLF_KING = 42
    NO_OUTPOST = 99
    UNKNOWN = -1

    @property
    def is_player(self) -> bool:
        """Is this object a player-owned entity?"""
        return self in (
            MapObjectType.CASTLE,
            MapObjectType.OUTPOST,
            MapObjectType.CAPITAL,
            MapObjectType.METRO,
        )

    @property
    def is_npc(self) -> bool:
        """Is this a permanent NPC/Robber Baron target?"""
        return self in (
            MapObjectType.DUNGEON,
            MapObjectType.ROBBER_BARON_CASTLE,
            MapObjectType.BOSS_DUNGEON,
        )

    @property
    def is_event(self) -> bool:
        """Is this a temporary event target (Nomad, Samurai, Alien)?"""
        return self in (
            MapObjectType.NOMAD_CAMP,
            MapObjectType.SAMURAI_CAMP,
            MapObjectType.ALIEN_CAMP,
            MapObjectType.SAMURAI_ALIEN_CAMP,
            MapObjectType.RED_ALIEN_CAMP,
            MapObjectType.ALLIANCE_NOMAD_CAMP,
            MapObjectType.EVENT_DUNGEON,
        )

    @property
    def is_resource(self) -> bool:
        """Is this a resource village or island?"""
        return self in (
            MapObjectType.VILLAGE,
            MapObjectType.ISLE_RESOURCE,
            MapObjectType.FACTION_VILLAGE,
        )


class KingdomType(IntEnum):
    GREEN = 0
    SANDS = 1
    ICE = 2
    FIRE = 3
    STORM = 4


class MovementType(IntEnum):
    """Types of army movements."""

    ATTACK = 1
    SUPPORT = 2
    TRANSPORT = 3
    SPY = 4
    RAID = 5
    SETTLE = 6
    CAMP = 7
    TRADE = 8
    ATTACK_CAMP = 9
    RAID_CAMP = 10
    RETURN = 11
    UNKNOWN = -1
