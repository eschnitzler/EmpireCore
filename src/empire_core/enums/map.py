"""Kingdom ids, map area types and NPC owner ids."""

from enum import IntEnum


class Kingdom(IntEnum):
    """
    Kingdom identifiers used throughout the game.

    Each kingdom has different terrain and unit types.

    Client: ``WorldClassic.KINGDOM_ID`` (dll line 19928), ``WorldDessert``
    (20019), ``WorldIce`` (20035), ``WorldVolcano`` (20067), ``WorldIsland``
    (20051), ``FactionConst.KINGDOM_ID`` (19333)
    """

    GREEN = 0
    SANDS = 1
    ICE = 2
    FIRE = 3
    STORM = 4
    BERIMOND = 10

    @property
    def text_id(self) -> str:
        """
        The text id of the kingdom's name, ``kingdomName_<kingdomName>``: ``text(Kingdom.SANDS.text_id)`` is
        ``"The Burning Sands"`` (:func:`empire_core.texts.text`).

        Client: ``CastleKingdomVO.kingdomNameString`` (bundle line 134711), with the ``kingdomName``
        column of the items ``kingdoms`` table (``CastleKingdomVO.fillFromParamXML``, bundle line 134695)
        """
        return f"kingdomName_{_KINGDOM_NAMES[self]}"


# The items kingdoms table's kingdomName column, by kID
_KINGDOM_NAMES = {
    Kingdom.GREEN: "Classic",
    Kingdom.SANDS: "Dessert",
    Kingdom.ICE: "Icecream",
    Kingdom.FIRE: "Volcano",
    Kingdom.STORM: "Eiland",
    Kingdom.BERIMOND: "Faction",
}


class MapItemType(IntEnum):
    """
    Area types: the first field of a map row, as in a scan's AI array.

    These mirror the game client's own ``WorldConst.AREA_TYPE_*`` constants,
    a superset of the types ``WorldmapObjectFactory.mapObjectVOs`` (bundle
    line 5357) registers a map object for: NO_LANDMARK (14), TROOP_HOSTEL
    (20), SAMURAI_ALIEN_CAMP (33) and NO_OUTPOST (99) have none, so the client
    cannot read a map row of those types.

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
    CAPITAL = 3  # Player capital
    OUTPOST = 4  # Player outpost
    TREASURE_DUNGEON = 7
    TREASURE_CAMP = 8
    SHADOW_AREA = 9
    VILLAGE = 10
    BOSS_DUNGEON = 11
    KINGDOM_CASTLE = 12  # Player castle in another kingdom
    EVENT_DUNGEON = 13
    NO_LANDMARK = 14
    FACTION_CAMP = 15
    FACTION_VILLAGE = 16
    FACTION_TOWER = 17
    FACTION_CAPITAL = 18
    PLAGUE_AREA = 19
    TROOP_HOSTEL = 20
    ALIEN_CAMP = 21
    METROPOL = 22
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
    DAIMYO_CASTLE = 37
    DAIMYO_TOWNSHIP = 38
    ALLIANCE_BATTLE_GROUND_RESOURCE_TOWER = 40
    ALLIANCE_BATTLE_GROUND_TOWER = 41
    WOLF_KING = 42
    ARE_PORTAL = 43
    NO_OUTPOST = 99


class NPCOwner(IntEnum):
    """
    The player ids the game gives its NPC owners; every NPC id is below 0.

    Members take the client's names, with its kingdom words (desert, ice,
    volcano, island for the Sands, Ice, Fire and Storm kingdoms). Some owners
    are a run of ids the client computes and names only by their first:
    robber barons are ``ROBBER_BARON`` minus 0 to 12, nomad camps
    ``NOMAD_CAMP`` minus 0 to 3, kingdom dungeons ``DESERT_DUNGEON`` minus 0
    to 4, and villages ``VillageConst.DEFAULT_OWNER_OFFSET`` (-400) minus the
    kingdom id less one, -399 to -403.

    ``ABG_CULTISTS`` is the same id as ``VOLCANO_DUNGEON``, so
    ``NPCOwner(-222)`` is ``VOLCANO_DUNGEON``.

    Client: ``DungeonConst`` (dll line 19157), ``OutpostConst`` (19549),
    ``VillageConst`` (19897), ``SpyConst.PLAGUEMONK_OWNER_ID`` (19757),
    ``ClientConstNPCs`` (bundle lines 5046-5047),
    ``CastleNPCOwnerFactory.generateUnknownNPC`` (14582)
    """

    ROBBER_BARON = -202
    DESERT_DUNGEON = -220
    ICE_DUNGEON = -221
    VOLCANO_DUNGEON = -222
    ABG_CULTISTS = -222
    ISLAND_DUNGEON = -223
    DESERT_BOSS_DUNGEON = -230
    ICE_BOSS_DUNGEON = -231
    VOLCANO_BOSS_DUNGEON = -232
    OUTPOST = -300
    PLAGUE_MONK = -334
    UNKNOWN = -366
    ISLAND_VILLAGE = -403
    BLUE_FACTION_KING = -410
    RED_FACTION_KING = -411
    CLASSIC_CAPITAL = -432
    ICE_CAPITAL = -433
    DESERT_CAPITAL = -434
    VOLCANO_CAPITAL = -435
    METROPOL = -440
    KINGS_TOWER = -450
    MONUMENT = -460
    CLASSIC_LABORATORY = -470
    ICE_LABORATORY = -471
    DESERT_LABORATORY = -472
    VOLCANO_LABORATORY = -473
    ALLIANCE_BATTLE_GROUND = -480
    RANDOM_DUNGEON_EVENT = -500
    APRIL_DUNGEON_EVENT = -501
    ST_PATRICKS_DAY_DUNGEON_EVENT = -502
    EASTER_DUNGEON_EVENT = -503
    NOMAD_CAMP = -601
    SAMURAI_CAMP = -651
    TUTORIAL_DUNGEON = -666
    THORNKING_DUNGEON = -700
    THORNKING_VILLAGE = -701
    THORNKING_COW_DUNGEON = -702
    SEA_QUEEN_DUNGEON = -703
    SEA_QUEEN_SHIPS = -704
    TREASURE_HUNT_DUNGEON = -705
    UNDERWORLD_DUNGEON = -706
    UNDERWORLD_VILLAGE = -707
    ALLIANCE_NOMAD_CAMP = -801
    DAIMYO_CASTLE = -811
    DAIMYO_TOWNSHIP = -815
    TEMP_CHARGE_CAMP = -821
    ALIEN_INVASION = -1000
    SAMURAI_ALIEN = -1001
    RED_ALIEN_INVASION = -1002
    COLLECTOR_HALLOWEEN = -1101
    COLLECTOR_CHRISTMAS = -1102
    COLLECTOR_CARNIVAL = -1103
    COLLECTOR_SPRING = -1104
    COLLECTOR_ELEMENTAL = -1105
    COLLECTOR_HALLOWEEN2 = -1106
    COLLECTOR_CHRISTMAS2 = -1107
    COLLECTOR_CARNIVAL2 = -1108
    COLLECTOR_SUMMER = -1109
    COLLECTOR_10TH_ANNIVERSARY = -1110
    COLLECTOR_HALLOWEEN3 = -1111
    COLLECTOR_CHRISTMAS3 = -1112
    COLLECTOR_CHRISTMAS4 = -1113
    COLLECTOR_SPRING2 = -1114
    ALLIANCE_BATTLE_GROUND_RESOURCE_TOWER = -1200
    WOLF_KING = -1201
    ARE_PORTAL = -1202
    UNKNOWN_EVENT_OWNER = -1234


class PeaceModeStatus(IntEnum):
    """
    Where the player's peace mode stands, a ``uap`` block's ``PMS`` outside Berimond.

    Client: ``CastleUserData.PEACEMODE_STATUS_*`` (bundle line 10188)
    """

    OFF = -1
    PRETIME = 0
    PEACETIME = 1
    POSTTIME = 2
