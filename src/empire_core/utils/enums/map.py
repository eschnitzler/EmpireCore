"""Kingdom ids and map area types."""

from enum import IntEnum


class Kingdom(IntEnum):
    """
    Kingdom identifiers used throughout the game.

    Each kingdom has different terrain and unit types. Inputs take
    ``Kingdom | int``: the server may use kingdom ids this list lacks.

    Client: ``WorldClassic.KINGDOM_ID`` (dll line 19928), ``WorldDessert``
    (20019), ``WorldIce`` (20035), ``WorldVolcano`` (20067), ``WorldIsland``
    (20051), ``FactionConst.KINGDOM_ID`` (19333)
    """

    GREEN = 0  # Green Kingdom - basic/starter kingdom
    SANDS = 1  # Sand Kingdom - desert units
    ICE = 2  # Ice Kingdom - ice/frost units
    FIRE = 3  # Fire Kingdom - lava/fire units
    STORM = 4  # Storm Kingdom - storm/lightning units
    BERIMOND = 10  # Berimond event kingdom


class MapItemType(IntEnum):
    """
    Area types: the first field of a map row, as in a scan's AI array.

    These mirror the game client's own ``WorldConst.AREA_TYPE_*`` constants,
    cross-checked against the client's area-type-to-map-object registration.

    Two things that are not separate types:

    - A ruin is not an item type: the client registers no ruin map object, and
      the flag lives on the owner record instead (``R`` in a scan's OI list,
      exposed as :attr:`MapObject.is_ruin`).
    - The nomad khan camp, which appears while the nomad event runs, is
      ``ALLIANCE_NOMAD_CAMP`` (``NomadKhanCampMapObjectVO``).

    The same ids type a movement's area rows (``TA``/``SA``) and every
    ``area_type`` input.

    Client: ``WorldConst.AREA_TYPE_*`` (dll line 20003)
    """

    EMPTY = 0
    CASTLE = 1  # Player main castle (while relocating, x/y is its in-transit position)
    DUNGEON = 2  # NPC camp - what players call a robber baron castle
    ROBBER_BARON = 2  # Alias of DUNGEON
    CAPITAL = 3  # Player capital
    OUTPOST = 4  # Player outpost
    TREASURE_DUNGEON = 7
    TREASURE_CAMP = 8
    SHADOW_AREA = 9
    VILLAGE = 10
    BOSS_DUNGEON = 11
    KINGDOM_CASTLE = 12  # Player castle in another kingdom
    EXTERNAL_KINGDOM = 12  # Alias of KINGDOM_CASTLE
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
    DYNAMIC = 31  # Dynamically placed event object
    SAMURAI_ALIEN_CAMP = 33
    RED_ALIEN_CAMP = 34
    ALLIANCE_NOMAD_CAMP = 35  # Nomad khan camp
    KHAN_CAMP = 35  # Alias of ALLIANCE_NOMAD_CAMP
    KHAN_TENT = 35  # Alias of ALLIANCE_NOMAD_CAMP
    DAIMYO_CASTLE = 37
    DAIMYO_TOWNSHIP = 38
    ABG_RESOURCE_TOWER = 40
    ABG_TOWER = 41
    WOLF_KING = 42
    ARE_PORTAL = 43
    NO_OUTPOST = 99
