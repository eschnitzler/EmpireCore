"""Tests for the map models."""

from typing import Any

import pytest

from empire_core.enums import Kingdom, MapItemType
from empire_core.map.models.areas import GetMapAreaRequest, GetMapAreaResponse
from empire_core.map.models.items import ROW_PARSERS, MapAreaItem, parse_area_rows
from empire_core.protocol.models import parse_response

# A castle row in the layout InteractiveMapobjectVO.parseAreaInfo (bundle line 3631) reads:
# [type, x, y, object id, owner, keep, wall, gate, tower, moat, name, attack cooldown,
#  sabotage cooldown, spied, outpost type, occupier, kingdom, skin, ABG connection, sabotage protection]
CASTLE_ROW: list[Any] = [1, 640, 655, 900, 4242, 6, 5, 4, 3, 2, "Castle", 30, 40, 50, 0, -1, 2, 77, [], 1]


def _row(area_type: MapItemType, *fields: Any) -> MapAreaItem:
    return MapAreaItem.from_list([int(area_type), 10, 20, *fields])


class TestGoldenMapArea:
    def test_registry_parses_gaa(self):
        assert isinstance(parse_response("gaa", {"KID": 0, "AI": []}), GetMapAreaResponse)

    def test_items_and_objects_parse(self):
        payload = {"KID": 2, "AI": [CASTLE_ROW], "OI": [{"OID": 4242, "N": "Owner", "AN": "Alliance", "L": 70}]}
        response = GetMapAreaResponse.model_validate(payload)
        item = response.items[0]
        assert (item.x, item.y, item.item_type, item.owner_id) == (640, 655, MapItemType.CASTLE, 4242)
        assert (response.owners[0].owner_id, response.owners[0].owner_name) == (4242, "Owner")

    # Shape of a live owner record, made up.
    OWNER: dict[str, Any] = {
        "OID": 1000001,
        "N": "Player",
        "L": 70,
        "LL": 950,
        "H": 1600,
        "MP": 40000000,
        "CF": 6000000,
        "HF": 130000000,
        "TI": -1,
        "SA": 0,
        "PF": 1,
        "VF": 0,
        "AID": 3000,
        "AR": 6,
        "AN": "Alliance",
        "AP": [[0, 1500001, 598, 201, 1], [0, 1500002, 600, 205, 4]],
        "VP": [],
        "FN": {"FID": 1, "TID": 113},
    }

    def test_owner_record_parses(self):
        owner = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "OI": [self.OWNER]}).owners[0]
        assert (owner.owner_id, owner.level, owner.legendary_level) == (1000001, 70, 950)
        assert owner.has_premium_flag is True and owner.is_searching_alliance is False
        assert [(p.kingdom_id, p.area_id, p.x, p.y, p.area_type) for p in owner.castle_positions] == [
            (0, 1500001, 598, 201, 1),
            (0, 1500002, 600, 205, 4),
        ]
        assert owner.faction is not None
        assert (owner.faction.faction_id, owner.faction.title_id, owner.faction.protection_status) == (1, 113, 0)
        assert owner.alliance_emblem is None
        assert (owner.prefix_title, owner.suffix_title, owner.via_refer_a_friend) == (None, None, False)

    def test_keys_the_client_does_not_read_off_an_owner_record_are_not_fields(self):
        # CF and HF are read only from the player's own fame replies, TI from gca.O
        from empire_core.map.models.areas import MapObject

        assert not any(field.alias in ("CF", "HF", "TI") for field in MapObject.model_fields.values())

    def test_owner_record_alliance_crest(self):
        record = {**self.OWNER, "aee": {"ACCA": {"ACLI": "4", "ACCS": [3, 7, 11]}}}
        owner = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "OI": [record]}).owners[0]
        assert owner.alliance_emblem is not None and owner.alliance_emblem.crest is not None
        assert (owner.alliance_emblem.crest.layout_id, owner.alliance_emblem.crest.color_ids) == (4, [3, 7, 11])

    def test_owner_record_blocks_that_are_not_objects_read_as_none(self):
        record = {**self.OWNER, "E": 0, "aee": [], "FN": 1}
        owner = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "OI": [record]}).owners[0]
        assert (owner.emblem, owner.alliance_emblem, owner.faction) == (None, None, None)

    def test_position_lists_lose_an_extra_wrapper(self):
        record = {**self.OWNER, "AP": [[[10, 5, 1, 2, 1]]], "VP": [[[0, 6, 3, 4, 2]]]}
        owner = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "OI": [record]}).owners[0]
        assert [(p.kingdom_id, p.area_id) for p in owner.castle_positions] == [(10, 5)]
        assert [(p.x, p.y, p.area_type) for p in owner.village_positions] == [(3, 4, 2)]

    def test_short_rows_are_read_as_the_client_reads_them(self):
        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [[31, 2, 3], [43, 4, 5], CASTLE_ROW]})
        assert [(i.item_type, i.x) for i in response.items] == [
            (MapItemType.DYNAMIC, 2),
            (MapItemType.ARE_PORTAL, 4),
            (MapItemType.CASTLE, 640),
        ]


class TestOwnerRecordConversions:
    """WorldMapOwnerInfoVO.fillFromParamObject (bundle line 10794) reads most keys through parseInt."""

    def test_numbers_are_read_through_parse_int(self):
        record = {"OID": "12abc", "L": "70.9", "LL": None, "RRD": "300s", "AID": "x", "AR": "6"}
        owner = GetMapAreaResponse.model_validate({"OI": [record]}).owners[0]
        assert (owner.owner_id, owner.level, owner.legendary_level) == (12, 70, 0)
        assert (owner.remaining_relocation_time, owner.alliance_id, owner.alliance_rank) == (300, None, 6)

    def test_flags_are_read_as_the_client_reads_them(self):
        record = {"OID": 5, "DUM": "1", "R": "1x", "SA": "0", "PF": [], "VF": 0, "IRF": "2"}
        owner = GetMapAreaResponse.model_validate({"OI": [record]}).owners[0]
        # 1 == e.DUM, 1 == parseInt(e.R), !!e.SA, !!e.PF, !!e.VF, !!parseInt(e.IRF)
        assert (owner.is_dummy, owner.is_ruin, owner.is_searching_alliance) == (True, True, True)
        assert (owner.has_premium_flag, owner.has_vip_flag, owner.via_refer_a_friend) == (True, False, True)

    def test_a_dummy_flag_that_is_not_one_is_not_a_dummy(self):
        # The v0.41.0 model failed the whole record on DUM: 2
        owner = GetMapAreaResponse.model_validate({"OI": [{"OID": 5, "DUM": 2}]}).owners[0]
        assert owner.is_dummy is False

    def test_an_empty_alliance_name_reads_as_empty(self):
        owner = GetMapAreaResponse.model_validate({"OI": [{"OID": 5, "AN": None}]}).owners[0]
        assert owner.alliance_name == ""

    def test_titles_are_read_only_when_sent(self):
        owner = GetMapAreaResponse.model_validate({"OI": [{"OID": 5, "PRE": 3, "SUF": 0}]}).owners[0]
        assert (owner.prefix_title, owner.suffix_title) == (3, 0)

    def test_a_record_without_an_owner_id_is_skipped(self):
        # CastleOtherPlayerData.parseOwnerInfo (bundle line 138996) returns null for one
        response = GetMapAreaResponse.model_validate({"OI": [{"N": "x"}, {"OID": 0}, {"OID": 5}]})
        assert [owner.owner_id for owner in response.owners] == [5]

    def test_an_unreadable_record_costs_only_itself(self):
        response = GetMapAreaResponse.model_validate({"OI": [{"OID": 5, "N": ["x"]}, "junk", {"OID": 6}]})
        assert [owner.owner_id for owner in response.owners] == [6]


class TestOwnerRecordLeniency:
    """Values the client reads through parseInt, int() or raw must not fail a whole reply."""

    def test_a_null_or_odd_crest_faction_or_alliance_crest_still_parses(self):
        owner = {
            "OID": 5,
            "E": {"IS": 2, "S1": None, "SC1": "#ff0000"},
            "FN": {"FID": 1, "PMS": None},
            "aee": {"ACCA": {"ACLI": 1, "ACCS": None}},
        }
        record = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "OI": [owner]}).owners[0]
        assert record.emblem is not None and record.emblem.is_set is True
        assert record.emblem.symbol1_color == 0xFF0000
        assert record.faction is not None and record.faction.protection_status == 0
        assert record.alliance_emblem is not None and record.alliance_emblem.crest is not None
        assert record.alliance_emblem.crest.color_ids == []

    def test_gaa_keys_follow_the_client_order(self):
        # C2SGetAreasVO declares KID, AX1, AY1, AX2, AY2
        request = GetMapAreaRequest(KID=Kingdom.FIRE, AX1=1, AY1=2, AX2=3, AY2=4)
        assert list(request.to_payload().items()) == [("KID", 3), ("AX1", 1), ("AY1", 2), ("AX2", 3), ("AY2", 4)]

    def test_a_row_the_client_cannot_read_costs_only_itself(self):
        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [[99, 2, 3, 4], [2, 5, 6, -1, 0, 0, 0]]})
        assert [item.item_type for item in response.items] == [MapItemType.DUNGEON]

    def test_a_gcl_row_that_cannot_be_read_costs_only_itself(self):
        from empire_core.protocol.models import GetCastlesResponse

        bad = [3, "x", 20, 99, 5, 1, 1, 1, 1, 1, "Capital", 0, 0, 0, 77, 0, 0]
        good = [1, 30, 40, 100, 5, 1, 1, 1, 1, 1, "Home", 0, 0, 0, 77, 0, 0]
        response = GetCastlesResponse.model_validate({"C": [{"KID": 0, "AI": [{"AI": bad}, {"AI": good}]}]})
        assert [castle.castle_id for castle in response.castles] == [100]

    def test_a_gcl_row_in_a_kingdom_the_client_does_not_define_costs_only_itself(self):
        from empire_core.protocol.models import GetCastlesResponse

        row = [1, 30, 40, 100, 5, 1, 1, 1, 1, 1, "Home", 0, 0, 0, 77, 0, 0]
        response = GetCastlesResponse.model_validate(
            {"C": [{"KID": 11, "AI": [{"AI": [*row[:3], 99, *row[4:]]}]}, {"KID": 2, "AI": [{"AI": row}]}]}
        )
        assert [(castle.castle_id, castle.kingdom_id) for castle in response.castles] == [(100, Kingdom.ICE)]


class TestAreaTypes:
    """MapAreaItem.item_type is the closed set WorldmapObjectFactory.mapObjectVOs (bundle line 5357) reads."""

    def test_every_type_the_client_registers_has_a_parser(self):
        registered = set(MapItemType) - {
            MapItemType.NO_LANDMARK,
            MapItemType.TROOP_HOSTEL,
            MapItemType.SAMURAI_ALIEN_CAMP,
            MapItemType.NO_OUTPOST,
        }
        assert set(ROW_PARSERS) == registered

    @pytest.mark.parametrize("area_type", [14, 20, 33, 99, 9999])
    def test_a_type_without_a_client_map_object_is_unreadable(self, area_type):
        with pytest.raises(ValueError, match="reads no map row"):
            MapAreaItem.from_list([area_type, 1, 2, 3])

    def test_the_type_goes_through_int(self):
        # WorldmapObjectFactory.parseWorldMapArea: U.int(e[0])
        assert MapAreaItem.from_list(["2", 1, 2, -1, 3, 0, 0]).item_type is MapItemType.DUNGEON

    @pytest.mark.parametrize("value", [None, [], "row"])
    def test_what_is_not_a_row_is_unreadable(self, value):
        with pytest.raises(ValueError):
            MapAreaItem.from_list(value)

    def test_parse_area_rows_counts_what_it_skips(self):
        items, skipped = parse_area_rows([[99, 1, 2], "x", [], [0, 1, 2]], Kingdom.SANDS)
        assert [(i.item_type, i.kingdom) for i in items] == [(MapItemType.EMPTY, Kingdom.SANDS)]
        assert skipped == 3


class TestCastleStyleRows:
    """InteractiveMapobjectVO, CapitalMapobjectVO and MetropolMapobjectVO rows."""

    def test_a_castle_row_reads_every_field(self):
        item = MapAreaItem.from_list(CASTLE_ROW)
        assert (item.location_id, item.owner_id, item.name) == (900, 4242, "Castle")
        assert (item.keep_level, item.wall_level, item.gate_level, item.tower_level, item.moat_level) == (6, 5, 4, 3, 2)
        assert (item.attack_cooldown_seconds, item.sabotage_cooldown_seconds, item.seconds_since_espionage) == (
            30,
            40,
            50,
        )
        assert (item.outpost_type, item.occupier_id, item.kingdom, item.skin_id) == (0, -1, Kingdom.ICE, 77)
        assert (item.abg_tower_connection, item.has_sabotage_protection, item.is_occupied) == ([], True, False)

    def test_castle_rows_floor_keep_wall_and_gate(self):
        item = MapAreaItem.from_list([1, 1, 2, 3, 4, 0, 0, 0, 2, 1, "c"])
        assert (item.keep_level, item.wall_level, item.gate_level, item.tower_level, item.moat_level) == (1, 1, 1, 2, 1)

    def test_castle_rows_read_their_numbers_through_int(self):
        item = MapAreaItem.from_list([1, "5", 6, 3, "4242", "7", "x", None, 2.9, "1", "c", "-1", 0, "12"])
        assert (item.x, item.owner_id, item.keep_level, item.wall_level, item.gate_level) == (5, 4242, 7, 1, 1)
        assert (item.tower_level, item.moat_level, item.attack_cooldown_seconds, item.seconds_since_espionage) == (
            2,
            1,
            -1,
            12,
        )

    def test_sabotage_protection_is_field_nineteen_on_every_castle_style_row(self):
        # 1 == int(e.length > 19 ? e[19] : 0); it is not a relocation flag
        for area_type in (1, 3, 4, 12, 15, 22):
            row = [area_type, 1, 2, 900, 4242, 1, 1, 1, 0, 0, "x", 0, 0, 0, 0, -1, 0, 0, 0, "1"]
            item = MapAreaItem.from_list(row)
            assert (item.has_sabotage_protection, item.is_relocating) == (True, False), area_type
        assert MapAreaItem.from_list(CASTLE_ROW[:19]).has_sabotage_protection is False

    def test_capital_rows_take_the_levels_as_sent(self):
        row = [3, 1, 2, 3, 4, 0, 5, 6, 7, 8, "cap", 1, 2, 3, 4343, 55, 1]
        item = MapAreaItem.from_list(row)
        assert (item.keep_level, item.wall_level, item.gate_level, item.tower_level, item.moat_level) == (0, 5, 6, 7, 8)
        assert (item.seconds_since_espionage, item.occupier_id, item.skin_id, item.kingdom) == (
            3,
            4343,
            55,
            Kingdom.SANDS,
        )
        assert (item.outpost_type, item.is_occupied) == (None, True)

    def test_a_metropolis_reads_its_mine_only_past_field_seventeen(self):
        base = [22, 1, 2, 3, 4, 1, 1, 1, 1, 1, "metro", 0, 0, 0, -1, 0, 0]
        assert MapAreaItem.from_list(base).abg_mine_out_seconds is None
        item = MapAreaItem.from_list([*base, "600", 9000])
        assert (item.abg_mine_out_seconds, item.abg_max_influence_points) == (600, 9000)

    def test_an_outpost_reads_its_occupier_at_fifteen(self):
        row = [4, 1, 2, 3, 4, 1, 1, 1, 0, 0, "op", 0, 0, 0, 2, 4343, 0]
        item = MapAreaItem.from_list(row)
        assert (item.outpost_type, item.occupier_id, item.is_occupied) == (2, 4343, True)

    def test_an_unclaimed_outpost_names_its_npc_owner(self):
        # OUTPOST_DEFAULT_OWNER_ID and OUTPOST_DEFAULT_AREA_ID are -300 (bundle line 19549)
        item = MapAreaItem.from_list([4, 630, 205, -300, -300, 0, 0, 0, 0, 0, ""])
        assert (item.location_id, item.owner_id, item.has_player_owner) == (-300, -300, False)

    def test_a_faction_camp_reads_as_a_castle_and_is_destroyed_by_its_last_field(self):
        item = MapAreaItem.from_list([15, 1, 2, 3, 4242, 1, 1, 1, 0, 0, "camp", 0, 0, 0, 0, -1, 10, 0, 1])
        assert (item.owner_id, item.kingdom, item.is_destroyed) == (4242, Kingdom.BERIMOND, True)
        assert MapAreaItem.from_list([15, 1, 2]).is_destroyed is None


class TestRelocatingCastles:
    """CastleMapobjectVO.parseAreaInfo (bundle line 18910), which KingdomCastleMapobjectVO inherits."""

    def test_a_four_field_castle_row_names_the_relocating_player(self):
        for area_type in (MapItemType.CASTLE, MapItemType.KINGDOM_CASTLE):
            item = MapAreaItem.from_list([int(area_type), 5, 6, 4242])
            assert (item.occupier_id, item.owner_id, item.is_relocating) == (4242, None, True)
            assert item.location_id is None and item.keep_level is None

    def test_a_free_plot_is_not_relocating(self):
        item = MapAreaItem.from_list([1, 632, 204, -1])
        assert (item.occupier_id, item.is_relocating) == (-1, False)

    def test_a_full_castle_row_is_not_relocating(self):
        assert MapAreaItem.from_list(CASTLE_ROW).is_relocating is False

    def test_an_outpost_is_never_relocating(self):
        assert MapAreaItem.from_list([4, 5, 6, 4242]).is_relocating is False

    def test_get_moving_flags_keys_by_the_relocating_player(self):
        response = GetMapAreaResponse.model_validate(
            {"KID": 0, "AI": [[1, 100, 200, 111], [1, 300, 400, -1], CASTLE_ROW, [12, 7, 8, 222]]}
        )
        assert response.get_moving_flags() == {111: (100, 200), 222: (7, 8)}

    def test_settled_castles_are_not_reported_as_moving(self):
        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [CASTLE_ROW] * 3})
        assert response.get_moving_flags() == {}


class TestLandmarkRows:
    def test_a_village(self):
        item = _row(MapItemType.VILLAGE, 900, "4242", "3", 1, 60, "village")
        assert (item.location_id, item.owner_id, item.village_type, item.kingdom) == (900, 4242, 3, Kingdom.SANDS)
        assert (item.seconds_since_espionage, item.name, item.wall_level) == (60, "village", None)

    def test_a_kings_tower(self):
        item = _row(MapItemType.KINGS_TOWER, 900, 4242, 2, 60, "tower")
        assert (item.location_id, item.owner_id, item.kingdom, item.seconds_since_espionage, item.name) == (
            900,
            4242,
            Kingdom.ICE,
            60,
            "tower",
        )
        assert item.keep_level is None

    def test_a_monument(self):
        item = _row(MapItemType.MONUMENT, 900, 4242, "2", 7, 3, 60, "monument")
        assert (item.monument_type, item.landmark_level, item.kingdom, item.name) == (2, 7, Kingdom.FIRE, "monument")

    def test_a_laboratory(self):
        item = _row(MapItemType.LABORATORY, 900, 4242, 9, 0, 60, "lab")
        assert (item.landmark_level, item.kingdom, item.seconds_since_espionage, item.name) == (
            9,
            Kingdom.GREEN,
            60,
            "lab",
        )

    def test_a_resource_isle(self):
        item = _row(MapItemType.ISLE_RESOURCE, 900, 4242, 4, "isle", 60, "12", 300)
        assert (item.kingdom, item.name, item.isle_id, item.remaining_occupier_seconds) == (
            Kingdom.STORM,
            "isle",
            12,
            300,
        )

    def test_landmarks_carry_no_structure_levels(self):
        for item in (
            _row(MapItemType.KINGS_TOWER, 3, 4, 0, 60, "tower"),
            _row(MapItemType.MONUMENT, 3, 4, 2, 7, 0, 60, "monument"),
            _row(MapItemType.LABORATORY, 3, 4, 9, 0, 60, "lab"),
            _row(MapItemType.VILLAGE, 3, 4, 1, 0, 60, "village"),
        ):
            assert (item.keep_level, item.wall_level, item.gate_level, item.tower_level, item.moat_level) == (None,) * 5


class TestFactionRows:
    def test_a_faction_village(self):
        item = _row(MapItemType.FACTION_VILLAGE, 4242, [[1, 2]], 60, "5", "30")
        assert (item.owner_id, item.protector_positions, item.dungeon_level, item.attack_cooldown_seconds) == (
            4242,
            [[1, 2]],
            5,
            30,
        )
        assert _row(MapItemType.FACTION_VILLAGE, 4242, 0).protector_positions == []

    def test_a_faction_tower(self):
        item = _row(MapItemType.FACTION_TOWER, 4242, 1, [], 60, 5, 2, 17)
        assert (item.owner_id, item.is_destroyed, item.dungeon_level, item.attacks_left, item.special_camp_id) == (
            4242,
            True,
            5,
            2,
            17,
        )

    def test_a_faction_capital(self):
        item = _row(MapItemType.FACTION_CAPITAL, 4242, [], 60, 5, 0, 18)
        assert (item.owner_id, item.dungeon_level, item.is_destroyed, item.special_camp_id) == (4242, 5, False, 18)
        assert item.location_id is None


class TestCampRows:
    def test_a_robber_baron_camp(self):
        item = _row(MapItemType.DUNGEON, -1, "297", -17639997, 0)
        assert (item.seconds_since_espionage, item.victory_count, item.attack_cooldown_seconds, item.kingdom) == (
            -1,
            297,
            -17639997,
            Kingdom.GREEN,
        )
        assert (item.owner_id, item.wall_level) == (None, None)

    def test_a_short_camp_row_reads_int_of_nothing_as_zero(self):
        item = _row(MapItemType.DUNGEON)
        assert (item.victory_count, item.seconds_since_espionage) == (0, None)

    def test_a_camp_in_a_kingdom_the_client_does_not_define_keeps_the_reply_kingdom(self):
        response = GetMapAreaResponse.model_validate({"KID": 3, "AI": [[2, 1, 2, -1, 5, 0, 99]]})
        assert response.items[0].kingdom is Kingdom.FIRE

    def test_a_treasure_dungeon_reads_as_a_camp(self):
        assert _row(MapItemType.TREASURE_DUNGEON, -1, 4, 0, 0).victory_count == 4

    def test_a_boss_dungeon(self):
        item = _row(MapItemType.BOSS_DUNGEON, 60, "40", 100, "4242", 1)
        assert (item.dungeon_level, item.attack_cooldown_seconds, item.defeater_player_id, item.kingdom) == (
            40,
            100,
            4242,
            Kingdom.SANDS,
        )

    def test_an_event_dungeon_and_the_wolf_king(self):
        event = _row(MapItemType.EVENT_DUNGEON, 60, 12, 1)
        wolf = _row(MapItemType.WOLF_KING, 60, 12, 0, 40, 50, 60)
        assert (event.dungeon_level, event.is_defeated, event.base_wall_bonus) == (12, True, None)
        assert (wolf.is_defeated, wolf.base_wall_bonus, wolf.base_gate_bonus, wolf.base_moat_bonus) == (
            False,
            40.0,
            50.0,
            60.0,
        )
        assert _row(MapItemType.EVENT_DUNGEON).dungeon_level is None

    def test_a_treasure_camp_names_its_map(self):
        # EventCampMapobjectVO.parseAreaInfo: _mapID = e[1] ? e[1] : 22
        assert MapAreaItem.from_list([8, 31]).map_id == 31
        assert MapAreaItem.from_list([8, 0]).map_id == 22

    def test_shadow_and_plague_areas(self):
        for area_type in (MapItemType.SHADOW_AREA, MapItemType.PLAGUE_AREA):
            item = _row(area_type, 100, 60)
            assert (item.attack_cooldown_seconds, item.seconds_since_espionage) == (100, 60)

    def test_an_alien_camp(self):
        assert _row(MapItemType.ALIEN_CAMP, 75).dungeon_level == 75
        assert _row(MapItemType.ALIEN_CAMP, 75).base_wall_bonus is None
        short = _row(MapItemType.RED_ALIEN_CAMP, 75, 60, 1, 30, 40, 50)
        assert (short.has_peace_mode, short.base_gate_bonus, short.already_rerolled, short.scaling_camp_id) == (
            True,
            40.0,
            False,
            -1,
        )
        full = _row(MapItemType.ALIEN_CAMP, 75, 60, 0, 30, 40, 50, 1, 9)
        assert (full.already_rerolled, full.scaling_camp_id) == (True, 9)

    def test_an_isle_dungeon(self):
        item = _row(MapItemType.ISLE_DUNGEON, 4, 60, "12", "100", 3, 0)
        assert (item.kingdom, item.isle_id, item.attack_cooldown_seconds, item.victory_count) == (
            Kingdom.STORM,
            12,
            100,
            3,
        )

    def test_samurai_and_nomad_camps_share_one_layout(self):
        # SamuraiCampMapObjectVO (bundle line 76493) and NomadCampMapObjectVO (bundle line 76379)
        for area_type in (MapItemType.SAMURAI_CAMP, MapItemType.NOMAD_CAMP):
            item = _row(area_type, -1, 4, 100, 0, 0, 7, 110, 120, 130)
            assert item.is_invasion_camp
            assert (item.seconds_since_espionage, item.victory_count, item.attack_cooldown_seconds) == (-1, 4, 100)
            assert (item.scaling_camp_id, item.base_wall_bonus, item.base_gate_bonus, item.base_moat_bonus) == (
                7,
                110.0,
                120.0,
                130.0,
            )
            assert _row(area_type).victory_count is None

    def test_a_faction_invasion_camp(self):
        item = _row(MapItemType.FACTION_INVASION_CAMP, 60, 4, 100, 0, "-2")
        assert (item.victory_count, item.attack_cooldown_seconds, item.dungeon_type) == (4, 100, -2)

    def test_daimyo_castles_and_townships(self):
        for area_type in (MapItemType.DAIMYO_CASTLE, MapItemType.DAIMYO_TOWNSHIP):
            item = _row(area_type, 60, 3, 100, "500", "20", "-1", 110, 110, 0)
            assert (item.camp_id, item.total_cooldown_seconds, item.skip_cost, item.scaling_camp_id) == (3, 500, 20, -1)
            assert (item.base_wall_bonus, item.victory_count) == (110.0, None)

    def test_alliance_camps(self):
        # AAllianceInvasionCampMapObjectVO.parseData: the nomad khan camp and the ABG resource tower
        for area_type in (MapItemType.ALLIANCE_NOMAD_CAMP, MapItemType.ALLIANCE_BATTLE_GROUND_RESOURCE_TOWER):
            item = _row(area_type, 60, "8", 100, 500, 20, 6, "3", 10, 20, 30)
            assert (item.camp_id, item.total_cooldown_seconds, item.skip_cost, item.victory_count) == (8, 500, 20, 6)
            assert (item.scaling_camp_id, item.base_wall_bonus, item.base_moat_bonus) == (3, 10.0, 30.0)

    def test_an_alliance_battle_ground_tower(self):
        item = _row(
            MapItemType.ALLIANCE_BATTLE_GROUND_TOWER, 900, "tower", 1, "4", "3000", "Alliance", [2, [1, 2]], [[5, 6]]
        )
        assert (item.location_id, item.name, item.is_attackable, item.victory_count) == (900, "tower", True, 4)
        assert (item.alliance_id, item.alliance_name, item.abg_connections) == (3000, "Alliance", [[5, 6]])
        assert item.alliance_crest is not None
        assert (item.alliance_crest.layout_id, item.alliance_crest.color_ids) == (2, [1, 2])
        assert item.owner_id is None

    @pytest.mark.parametrize("area_type", [MapItemType.EMPTY, MapItemType.DYNAMIC, MapItemType.ARE_PORTAL])
    def test_position_only_rows(self, area_type):
        item = _row(area_type, 1, 2, 3)
        assert (item.x, item.y, item.owner_id, item.victory_count) == (10, 20, None, None)


class TestRowKingdom:
    """GetMapAreaResponse reads each row in the reply's kingdom unless the row names its own."""

    def test_rows_without_a_kingdom_take_the_reply_kingdom(self):
        response = GetMapAreaResponse.model_validate({"KID": 2, "AI": [[31, 1, 2], [1, 3, 4, 4242]]})
        assert [item.kingdom for item in response.items] == [Kingdom.ICE, Kingdom.ICE]

    def test_from_list_takes_the_kingdom_it_is_given(self):
        assert MapAreaItem.from_list([31, 1, 2], Kingdom.STORM).kingdom is Kingdom.STORM


class TestRuinFlag:
    """A ruin is an owner-record flag, not a map item type."""

    _RUIN = {"OID": 2000001, "L": 70, "N": "Ruined", "R": 1}
    _LIVE = {"OID": 2000002, "L": 70, "N": "Standing", "R": 0}

    def test_ruin_owner_is_flagged(self):
        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "OI": [self._RUIN, self._LIVE]})
        ruins = response.get_ruins()
        assert [o.owner_id for o in ruins] == [2000001]
        assert ruins[0].owner_name == "Ruined"

    def test_missing_flag_is_not_a_ruin(self):
        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "OI": [{"OID": 5, "N": "x"}]})
        assert response.get_ruins() == []
        assert response.owners[0].is_ruin is False


class TestErrorCodeKeyCollision:
    """The payload key "E" is not reserved for the error code."""

    def test_a_crest_under_e_does_not_break_parsing(self):
        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "E": {"BGT": 0, "BGC1": 1644825, "IS": 1}})
        assert response.error_code == 0
        assert response.success

    def test_a_real_error_code_still_parses(self):
        assert GetMapAreaResponse.model_validate({"KID": 0, "E": 21}).error_code == 21
        assert not GetMapAreaResponse.model_validate({"KID": 0, "E": 21}).success
