"""NPCOwner values and the owner-id sets built from it, against the client's constants."""

import empire_core.map
from empire_core.combat.capacity import ALIEN_INVASION_AREA_TYPES, ALIEN_INVASION_PLAYER_IDS, COLLECTOR_PLAYER_IDS
from empire_core.enums import MapItemType, NPCOwner
from empire_core.movements.tracked import DUNGEON_OWNER_IDS

# DungeonConst (dll 19157), OutpostConst (19549), VillageConst (19897), SpyConst (19757),
# ClientConstNPCs (bundle 5046-5047), CastleNPCOwnerFactory.generateUnknownNPC (14582).
CLIENT_VALUES = {
    "ROBBER_BARON": -202,
    "DESERT_DUNGEON": -220,
    "ICE_DUNGEON": -221,
    "VOLCANO_DUNGEON": -222,
    "ABG_CULTISTS": -222,
    "ISLAND_DUNGEON": -223,
    "DESERT_BOSS_DUNGEON": -230,
    "ICE_BOSS_DUNGEON": -231,
    "VOLCANO_BOSS_DUNGEON": -232,
    "OUTPOST": -300,
    "PLAGUE_MONK": -334,
    "UNKNOWN": -366,
    "ISLAND_VILLAGE": -403,
    "BLUE_FACTION_KING": -410,
    "RED_FACTION_KING": -411,
    "CLASSIC_CAPITAL": -432,
    "ICE_CAPITAL": -433,
    "DESERT_CAPITAL": -434,
    "VOLCANO_CAPITAL": -435,
    "METROPOL": -440,
    "KINGS_TOWER": -450,
    "MONUMENT": -460,
    "CLASSIC_LABORATORY": -470,
    "ICE_LABORATORY": -471,
    "DESERT_LABORATORY": -472,
    "VOLCANO_LABORATORY": -473,
    "ALLIANCE_BATTLE_GROUND": -480,
    "RANDOM_DUNGEON_EVENT": -500,
    "APRIL_DUNGEON_EVENT": -501,
    "ST_PATRICKS_DAY_DUNGEON_EVENT": -502,
    "EASTER_DUNGEON_EVENT": -503,
    "NOMAD_CAMP": -601,
    "SAMURAI_CAMP": -651,
    "TUTORIAL_DUNGEON": -666,
    "THORNKING_DUNGEON": -700,
    "THORNKING_VILLAGE": -701,
    "THORNKING_COW_DUNGEON": -702,
    "SEA_QUEEN_DUNGEON": -703,
    "SEA_QUEEN_SHIPS": -704,
    "TREASURE_HUNT_DUNGEON": -705,
    "UNDERWORLD_DUNGEON": -706,
    "UNDERWORLD_VILLAGE": -707,
    "ALLIANCE_NOMAD_CAMP": -801,
    "DAIMYO_CASTLE": -811,
    "DAIMYO_TOWNSHIP": -815,
    "TEMP_CHARGE_CAMP": -821,
    "ALIEN_INVASION": -1000,
    "SAMURAI_ALIEN": -1001,
    "RED_ALIEN_INVASION": -1002,
    "COLLECTOR_HALLOWEEN": -1101,
    "COLLECTOR_CHRISTMAS": -1102,
    "COLLECTOR_CARNIVAL": -1103,
    "COLLECTOR_SPRING": -1104,
    "COLLECTOR_ELEMENTAL": -1105,
    "COLLECTOR_HALLOWEEN2": -1106,
    "COLLECTOR_CHRISTMAS2": -1107,
    "COLLECTOR_CARNIVAL2": -1108,
    "COLLECTOR_SUMMER": -1109,
    "COLLECTOR_10TH_ANNIVERSARY": -1110,
    "COLLECTOR_HALLOWEEN3": -1111,
    "COLLECTOR_CHRISTMAS3": -1112,
    "COLLECTOR_CHRISTMAS4": -1113,
    "COLLECTOR_SPRING2": -1114,
    "ALLIANCE_BATTLE_GROUND_RESOURCE_TOWER": -1200,
    "WOLF_KING": -1201,
    "ARE_PORTAL": -1202,
    "UNKNOWN_EVENT_OWNER": -1234,
}


def test_members_match_the_client_constants() -> None:
    assert {name: int(member) for name, member in NPCOwner.__members__.items()} == CLIENT_VALUES


def test_abg_cultists_shares_the_volcano_dungeon_id() -> None:
    assert NPCOwner.ABG_CULTISTS is NPCOwner.VOLCANO_DUNGEON
    assert NPCOwner(-222) is NPCOwner.VOLCANO_DUNGEON


def test_map_package_reexports_it() -> None:
    assert empire_core.map.NPCOwner is NPCOwner


def test_dungeon_owner_ids_are_the_factory_dungeon_owners() -> None:
    expected = {
        *range(-214, -201),
        *range(-224, -219),
        *range(-232, -229),
        *range(-403, -398),
        -410,
        -411,
        -450,
        -460,
        *range(-473, -469),
        *range(-503, -499),
        *range(-604, -600),
        -651,
        -666,
        *range(-707, -699),
        -801,
        -811,
        -1000,
        -1002,
        *range(-1114, -1100),
        -1201,
        -1202,
        -1234,
    }
    assert DUNGEON_OWNER_IDS == expected
    # Owners the factory builds without isDungeonOwner.
    for owner in (NPCOwner.OUTPOST, NPCOwner.CLASSIC_CAPITAL, NPCOwner.METROPOL, NPCOwner.PLAGUE_MONK):
        assert owner not in DUNGEON_OWNER_IDS


def test_player_helper_sets_keep_their_ids() -> None:
    assert ALIEN_INVASION_PLAYER_IDS == {-1000, -1002}
    assert COLLECTOR_PLAYER_IDS == {-1103, -1102, -1107, -1109, -1110, -1105, -1101, -1106, -1104}
    assert ALIEN_INVASION_AREA_TYPES == {int(MapItemType.ALIEN_CAMP): -1000, int(MapItemType.RED_ALIEN_CAMP): -1002}
