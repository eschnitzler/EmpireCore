"""Game enumerations.

One enum per server ID space, and the enum lives next to the packets that
describe it:

- kingdom IDs: :class:`empire_core.protocol.models.map.Kingdom` (re-exported
  here as ``KingdomType`` for backwards compatibility),
- map-scan item types (the ``AI`` array of a ``gaa`` response):
  :class:`empire_core.protocol.models.map.MapItemType`,
- movement area types (``TA``/``SA`` arrays of a ``gam``/``mrm`` movement):
  :class:`MapObjectType` below.
"""

from enum import IntEnum

from empire_core.protocol.models.map import Kingdom

# ``KingdomType`` used to be a second, shorter copy of the kingdom ID table (it
# was missing BERIMOND = 10). It is now an alias of the authoritative enum, so
# ``KingdomType`` and ``Kingdom`` are the same object and compare equal
# everywhere. Deprecated: new code should use ``Kingdom`` (exported from
# ``empire_core``); the alias is kept because it is part of the published API.
KingdomType = Kingdom


class MapObjectType(IntEnum):
    """Object types found in a movement's target/source area array.

    This is the type stored in :attr:`Movement.target_type
    <empire_core.state.world_models.Movement.target_type>` (``TA[0]``), i.e. the
    thing an army is marching at.

    .. warning::

       ``MapObjectType`` and
       :class:`empire_core.protocol.models.map.MapItemType` (the ``AI`` array of
       a map scan) overlap and agree on 0, 1, 3, 4, 22, 23, 26 and 28, which
       suggests one shared server ID space -- but they contradict each other on
       three IDs:

       ==== ============================ ==============================
       ID   ``MapObjectType``            ``MapItemType``
       ==== ============================ ==============================
       2    ``DUNGEON``                  ``EMPTY_CASTLE_SLOT``
       7    ``TREASURE_DUNGEON``         ``KHAN_TENT``
       12   ``KINGDOM_CASTLE``           ``EXTERNAL_KINGDOM``
       ==== ============================ ==============================

       At least one of the two tables is wrong for the overlapping IDs, and
       neither has been verified against live packets. Until it is, both are
       kept as-is: use ``MapObjectType`` only for movement areas and
       ``MapItemType`` only for map-scan items, and do not mix them in a
       comparison. TODO: confirm 2/7/12 against captured ``gaa``/``gam``
       payloads and collapse the tables into one.
    """

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
