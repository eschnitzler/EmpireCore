"""Tests for the map models."""

from typing import Any

import pytest

from empire_core.enums import Kingdom, MapItemType
from empire_core.map.models.areas import GetMapAreaRequest, GetMapAreaResponse
from empire_core.map.models.items import MapAreaItem
from empire_core.protocol.models import parse_response


class TestGoldenMapArea:
    CASTLE_ROW = [
        MapItemType.CASTLE,
        640,
        655,
        900,
        4242,
        1,
        1,
        1,
        0,
        0,
        "SomeCastle",
        0,
        0,
        -1,
        -1,
        -1,
        0,
        190426,
        [],
        0,
    ]

    def test_registry_parses_gaa(self):
        assert isinstance(parse_response("gaa", {"KID": 0, "AI": []}), GetMapAreaResponse)

    def test_items_and_objects_parse(self):
        payload = {
            "KID": 0,
            "AI": [self.CASTLE_ROW],
            "OI": [{"OID": 4242, "N": "TargetPlayer", "AN": "HOPE", "L": 70}],
        }
        response = GetMapAreaResponse.model_validate(payload)
        assert [(i.x, i.y, i.item_type) for i in response.items] == [(640, 655, int(MapItemType.CASTLE))]
        assert response.items[0].player_id == 4242
        assert response.owners[0].owner_id == 4242
        assert response.owners[0].owner_name == "TargetPlayer"

    # Shape of a live green-kingdom owner record, anonymised.
    OWNER = {
        "OID": 1385991,
        "N": "Player",
        "L": 70,
        "LL": 950,
        "H": 1649,
        "MP": 44562022,
        "CF": 6469992,
        "HF": 132766143,
        "TI": -1,
        "SA": 0,
        "PF": 1,
        "VF": 0,
        "AID": 3318,
        "AR": 6,
        "AN": "Alliance",
        "AP": [[0, 1591282, 598, 201, 1], [0, 16512168, 600, 205, 4]],
        "VP": [],
        "FN": {"FID": 1, "TID": 113},
    }

    def test_owner_record_parses(self):
        owner = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "OI": [self.OWNER]}).owners[0]
        assert (owner.owner_id, owner.level, owner.legendary_level) == (1385991, 70, 950)
        assert (owner.glory_points, owner.highest_glory_points, owner.storm_title_id) == (6469992, 132766143, -1)
        assert owner.has_premium_flag is True and owner.is_searching_alliance is False
        assert owner.area_positions == [[0, 1591282, 598, 201, 1], [0, 16512168, 600, 205, 4]]
        assert owner.faction is not None
        assert (owner.faction.faction_id, owner.faction.title_id) == (1, 113)
        assert owner.alliance_emblem is None

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
        assert owner.area_positions == [[10, 5, 1, 2, 1]]
        assert owner.village_positions == [[0, 6, 3, 4, 2]]

    def test_short_rows_are_filtered_out_of_items(self):
        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [[1, 2, 3], self.CASTLE_ROW]})
        assert len(response.items) == 1


class TestOwnerRecordLeniency:
    """Values the client reads through parseInt, int() or raw must not fail a whole reply."""

    def test_a_null_or_odd_crest_faction_or_alliance_crest_still_parses(self):
        from empire_core.protocol.models import GetMapAreaResponse

        owner = {
            "OID": 5,
            "E": {"IS": 2, "S1": None, "SC1": "#ff0000"},
            "FN": {"FID": 1, "PMS": None},
            "aee": {"ACCA": {"ACLI": 1, "ACCS": None}},
        }
        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "OI": [owner]})
        record = response.owners[0]
        assert record.emblem is not None and record.emblem.is_set is True
        assert record.emblem.symbol1_color == 0xFF0000
        assert record.faction is not None and record.faction.protection_status == 0
        assert record.alliance_emblem is not None and record.alliance_emblem.crest is not None
        assert record.alliance_emblem.crest.color_ids == []

    def test_gaa_keys_follow_the_client_order(self):
        # C2SGetAreasVO declares KID, AX1, AY1, AX2, AY2
        request = GetMapAreaRequest(KID=Kingdom.FIRE, AX1=1, AY1=2, AX2=3, AY2=4)
        assert list(request.to_payload().items()) == [("KID", 3), ("AX1", 1), ("AY1", 2), ("AX2", 3), ("AY2", 4)]

    def test_an_unhashable_area_type_costs_only_its_row(self):
        from empire_core.protocol.models import GetMapAreaResponse

        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [[[1], 2, 3, 4], [2, 5, 6, -1, 0, 0, 0]]})
        assert [item.item_type for item in response.items] == [2]

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


class TestMapAreaStructureLevels:
    """Only castle-like rows carry levels at fields 5 to 9 (InteractiveMapobjectVO, Capital, Metropol)."""

    def test_castle_rows_floor_keep_wall_and_gate(self):
        item = MapAreaItem.from_list([1, 1, 2, 3, 4, 0, 0, 0, 2, 1, "c"])
        assert (item.keep_level, item.wall_level, item.gate_level, item.tower_level, item.moat_level) == (1, 1, 1, 2, 1)

    def test_capital_rows_take_the_levels_as_sent(self):
        item = MapAreaItem.from_list([MapItemType.CAPITAL, 1, 2, 3, 4, 0, 5, 6, 7, 8, "cap"])
        assert (item.keep_level, item.wall_level, item.gate_level, item.tower_level, item.moat_level) == (0, 5, 6, 7, 8)

    def test_landmarks_carry_no_structure_levels(self):
        tower = MapAreaItem.from_list([MapItemType.KINGS_TOWER, 1, 2, 3, 4, 0, 60, "tower"])
        monument = MapAreaItem.from_list([MapItemType.MONUMENT, 1, 2, 3, 4, 2, 7, 0, 60, "monument"])
        laboratory = MapAreaItem.from_list([MapItemType.LABORATORY, 1, 2, 3, 4, 9, 0, 60, "lab"])
        for item in (tower, monument, laboratory):
            assert (item.keep_level, item.wall_level, item.gate_level, item.tower_level, item.moat_level) == (0,) * 5
        assert (tower.landmark_level, monument.landmark_level, laboratory.landmark_level) == (None, 7, 9)


def _castle_entry(
    x: int,
    y: int,
    castle_id: int = 900,
    # Deliberately untyped: several tests pass values the server would never
    # send (a string player id, a missing flag) to pin how drifted entries are
    # handled, so this helper has to be able to build malformed entries too.
    player_id: Any = 4242,
    relocating: Any = 0,
) -> list:
    """A 20-field gaa type-1 (CASTLE) entry as the live server sends it.

    Layout (reverse-engineered, confirmed against the live server):
        [type, x, y, castle_id, player_id, lvl, lvl, lvl, ?, ?, name,
         0, 0, -1, -1, -1, 0, alliance_id, [], relocating_flag]
    """
    return [
        MapItemType.CASTLE,
        x,
        y,
        castle_id,
        player_id,
        1,
        1,
        1,
        0,
        0,
        "SomeCastle",
        0,
        0,
        -1,
        -1,
        -1,
        0,
        77,
        [],
        relocating,
    ]


class TestMovingFlags:
    """Finding 2: relocation detection and player-id keying."""

    def test_player_id_is_field_four(self):
        item = MapAreaItem.from_list(_castle_entry(10, 20, castle_id=900, player_id=4242))
        assert item.player_id == 4242
        assert item.owner_id == 4242
        assert item.location_id == 900

    def test_is_relocating_reads_field_nineteen(self):
        settled = MapAreaItem.from_list(_castle_entry(10, 20, relocating=0))
        moving = MapAreaItem.from_list(_castle_entry(10, 20, relocating=1))
        assert settled.is_relocating is False
        assert moving.is_relocating is True

    def test_is_moving_flag_matches_is_relocating_and_warns(self):
        settled = MapAreaItem.from_list(_castle_entry(1, 2, relocating=0))
        moving = MapAreaItem.from_list(_castle_entry(1, 2, relocating=1))
        with pytest.warns(DeprecationWarning, match="is_relocating"):
            assert settled.is_moving_flag is False
        with pytest.warns(DeprecationWarning, match="is_relocating"):
            assert moving.is_moving_flag is True

    def test_short_entry_has_no_relocation_data(self):
        item = MapAreaItem.from_list([MapItemType.CASTLE, 5, 6, 900])
        assert item.player_id == -1
        assert item.is_relocating is False

    def test_non_castle_entry_is_never_relocating(self):
        outpost = MapAreaItem.from_list([MapItemType.OUTPOST, 5, 6, 900, 4242] + [0] * 14 + [1])
        assert outpost.is_relocating is False

    def test_get_moving_flags_keys_by_player_id(self):
        response = GetMapAreaResponse.model_validate(
            {
                "KID": 0,
                "AI": [
                    _castle_entry(100, 200, castle_id=901, player_id=111, relocating=1),
                    _castle_entry(300, 400, castle_id=902, player_id=222, relocating=0),
                ],
            }
        )
        assert response.get_moving_flags() == {111: (100, 200)}

    def test_get_moving_flags_ignores_invalid_player_ids(self):
        response = GetMapAreaResponse.model_validate(
            {
                "KID": 0,
                "AI": [
                    _castle_entry(1, 2, player_id=0, relocating=1),
                    _castle_entry(3, 4, player_id=-1, relocating=1),
                    _castle_entry(5, 6, player_id="nope", relocating=1),
                ],
            }
        )
        assert response.get_moving_flags() == {}

    def test_settled_castles_are_not_reported_as_moving(self):
        # The old heuristic (owned type-1) reported every castle in the area.
        response = GetMapAreaResponse.model_validate(
            {"KID": 0, "AI": [_castle_entry(i, i, castle_id=900 + i, player_id=1000 + i) for i in range(5)]}
        )
        assert response.get_moving_flags() == {}


class TestDefenderStructureLevels:
    """An owned location's row carries the structures that defend it."""

    # Captured live: keep 6, wall 5, gate 5, tower 5, moat 2.
    SKAAR = [1, 629, 235, 14733404, 15156637, 6, 5, 5, 5, 2, "skaar"]
    # A level 13 castle: far smaller walls, no moat at all.
    SMALL = [1, 632, 243, 16654596, 17743260, 2, 2, 2, 1, 0, "Chateau Heimlin"]

    def test_structure_levels_are_read(self):
        item = MapAreaItem.from_list(self.SKAAR)

        assert item.keep_level == 6
        assert item.wall_level == 5
        assert item.gate_level == 5
        assert item.tower_level == 5
        assert item.moat_level == 2

    def test_a_smaller_castle_has_smaller_structures(self):
        item = MapAreaItem.from_list(self.SMALL)

        assert (item.wall_level, item.gate_level) == (2, 2)
        assert item.moat_level == 0

    def test_keep_wall_and_gate_are_floored_at_one(self):
        # The client applies Math.max(level, 1) to these three.
        item = MapAreaItem.from_list([1, 1, 1, 900, 4242, 0, 0, 0, 0, 0, "x"])

        assert (item.keep_level, item.wall_level, item.gate_level) == (1, 1, 1)
        assert (item.tower_level, item.moat_level) == (0, 0)

    def test_a_camp_has_no_structures_in_its_row(self):
        # A camp row means something else at those indices entirely.
        camp = MapAreaItem.from_list([2, 630, 243, -1, 297, -17639997, 0])

        assert camp.wall_level == 0
        assert camp.gate_level == 0


class TestErrorCodeKeyCollision:
    """The payload key "E" is not reserved for the error code."""

    def test_a_crest_under_e_does_not_break_parsing(self):
        # A live aci response carries the player's crest under "E".
        from empire_core.protocol.models import GetMapAreaResponse

        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "E": {"BGT": 0, "BGC1": 1644825, "IS": 1}})

        assert response.error_code == 0
        assert response.success

    def test_a_real_error_code_still_parses(self):
        from empire_core.protocol.models import GetMapAreaResponse

        assert GetMapAreaResponse.model_validate({"KID": 0, "E": 21}).error_code == 21
        assert not GetMapAreaResponse.model_validate({"KID": 0, "E": 21}).success


class TestNpcCampRows:
    """A type-2 row is a camp, not an owned location."""

    # Captured live: [type, x, y, seconds_since_espionage, victory_count,
    #                 cooldown, kingdom]
    CAMP = [2, 630, 243, -1, 297, -17639997, 0]

    def test_camp_fields_are_exposed(self):
        item = MapAreaItem.from_list(self.CAMP)

        assert item.item_type == MapItemType.DUNGEON
        assert (item.x, item.y) == (630, 243)
        assert item.victory_count == 297
        assert item.seconds_since_espionage == -1
        assert item.attack_cooldown_seconds == -17639997
        assert item.camp_kingdom_id is Kingdom.GREEN

    def test_a_camp_has_no_owner(self):
        # Field 3 is the espionage age; reading it as an owner id was wrong.
        assert MapAreaItem.from_list(self.CAMP).owner_id == -1

    def test_camp_fields_are_none_for_other_types(self):
        castle = MapAreaItem.from_list([1, 5, 6, 900, 4242])

        assert castle.victory_count is None
        assert castle.seconds_since_espionage is None
        assert castle.attack_cooldown_seconds is None

    def test_short_camp_row_reports_what_it_has(self):
        item = MapAreaItem.from_list([2, 10, 11])

        assert item.victory_count is None
        assert (item.x, item.y) == (10, 11)


class TestRuinFlag:
    """A ruin is an owner-record flag, not a map item type."""

    # Captured from a live green-kingdom scan.
    _RUIN = {"OID": 2612805, "L": 70, "N": "HardCoreHenri", "R": 1}
    _LIVE = {"OID": 17447818, "L": 70, "N": "Colossus", "R": 0}

    def test_ruin_owner_is_flagged(self):
        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "OI": [self._RUIN, self._LIVE]})

        ruins = response.get_ruins()

        assert [o.owner_id for o in ruins] == [2612805]
        assert ruins[0].owner_name == "HardCoreHenri"

    def test_missing_flag_is_not_a_ruin(self):
        # Most owner records omit R entirely.
        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [], "OI": [{"OID": 5, "N": "x"}]})

        assert response.get_ruins() == []
        assert response.owners[0].is_ruin is False
