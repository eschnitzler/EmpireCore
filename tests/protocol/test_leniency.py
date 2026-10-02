"""Parse-leniency tests that cover several areas' models at once."""

import logging

import pytest
from pydantic import ValidationError

from empire_core.alliance.models.chat import AllianceChatLogResponse, AllianceChatMessageResponse
from empire_core.alliance.models.info import AllianceInfo, AllianceMember, GetAllianceInfoResponse
from empire_core.alliance.models.search import AllianceSearchResult
from empire_core.castle.models.actions import RelocateCastleRequest
from empire_core.castle.models.castles import CastleInfo, GetCastlesResponse, PlayerCastle
from empire_core.castle.models.details import GetDetailedCastleResponse
from empire_core.commanders.models.roster import Equipment
from empire_core.defense.models import GetSupportDefenseResponse
from empire_core.enums import DiplomacyStatus, Kingdom, MapItemType, OnlineState, Rareness
from empire_core.map.models.areas import GetMapAreaResponse
from empire_core.map.models.items import MapAreaItem
from empire_core.player.models.info import GetPlayerInfoResponse
from tests.model_helpers import gdi_location_row

# =============================================================================
# Malformed nested payloads
#
# Every case below is a *plausible* server drift, not random fuzz: a batch with
# one bad element, a positional array of the wrong arity, or a numeric field
# arriving as a string. What is pinned is which exception type escapes, because
# callers can only defend against the type they are told about.
# =============================================================================


class TestPositionalArrayParsers:
    """``from_list`` helpers read raw server arrays by index.

    They are total for short arrays (missing trailing fields fall back to
    defaults) but not for wrong *types* - those surface as ValidationError,
    which is what the callers above them catch.
    """

    @pytest.mark.parametrize("data", [[1], [1, 2], [1, 2, 3], [1, 2, 3, 4], [2, 1]])
    def test_map_area_item_tolerates_short_arrays(self, data):
        item = MapAreaItem.from_list(data)
        assert item.raw_data == data
        assert item.is_relocating is (data == [1, 2, 3, 4])

    def test_map_area_item_rejects_an_empty_array(self):
        with pytest.raises(ValueError):
            MapAreaItem.from_list([])

    @pytest.mark.parametrize(
        "item_type",
        [
            MapItemType.CASTLE,
            MapItemType.CAPITAL,
            MapItemType.OUTPOST,
            MapItemType.VILLAGE,
            MapItemType.KINGDOM_CASTLE,
            MapItemType.METROPOL,
            MapItemType.KINGS_TOWER,
            MapItemType.MONUMENT,
            MapItemType.LABORATORY,
            MapItemType.ISLE_RESOURCE,
        ],
    )
    def test_map_area_item_owner_is_field_four_for_every_owned_type(self, item_type):
        item = MapAreaItem.from_list([item_type, 1, 2, 900, 4242, 0])
        assert (item.location_id, item.owner_id, item.has_player_owner) == (900, 4242, True)

    @pytest.mark.parametrize(
        "item_type", [MapItemType.FACTION_VILLAGE, MapItemType.FACTION_TOWER, MapItemType.FACTION_CAPITAL]
    )
    def test_map_area_item_faction_landmark_owner_is_field_three(self, item_type):
        item = MapAreaItem.from_list([item_type, 1, 2, 4242])
        assert (item.owner_id, item.location_id) == (4242, None)

    def test_map_area_item_empty_castle_slot_has_no_owner(self):
        # A free plot comes as a four-field row: [1, x, y, -1].
        item = MapAreaItem.from_list([MapItemType.CASTLE, 632, 204, -1])
        assert (item.location_id, item.owner_id, item.occupier_id) == (None, None, -1)

    def test_map_area_item_unclaimed_outpost_has_an_npc_owner(self):
        # The client's OUTPOST_DEFAULT_OWNER_ID and OUTPOST_DEFAULT_AREA_ID are -300.
        unclaimed = MapAreaItem.from_list([MapItemType.OUTPOST, 630, 205, 14824223, -300, 1, 1, 1, 0, 0, ""])
        assert (unclaimed.location_id, unclaimed.owner_id, unclaimed.has_player_owner) == (14824223, -300, False)
        bare = MapAreaItem.from_list([MapItemType.OUTPOST, 630, 180, -300, -300, 0, 0, 0, 0, 0, ""])
        assert (bare.location_id, bare.owner_id) == (-300, -300)

    @pytest.mark.parametrize(
        "row",
        [
            [MapItemType.DUNGEON, 1, 2, 300, 5, -1, 0],
            [MapItemType.NOMAD_CAMP, 1, 2, -1, 297, -100, 0, 0, -1, 0, 0, 0],
            [MapItemType.BOSS_DUNGEON, 1, 2, -1, 40, 0, 4242, 2],
            [MapItemType.SAMURAI_CAMP, 1, 2, -1, 12, 0, 0, 0, -1, 0, 0, 0],
            [MapItemType.DYNAMIC, 632, 201],
        ],
    )
    def test_map_area_item_camp_rows_report_no_owner(self, row):
        item = MapAreaItem.from_list(row)
        assert (item.owner_id, item.location_id) == (None, None)

    def test_map_area_item_unknown_type_is_unreadable(self):
        with pytest.raises(ValueError, match="9999"):
            MapAreaItem.from_list([9999, 1, 2, 3])

    @pytest.mark.parametrize("data", [[1, 2, 3, 4, 5, 1, 1, 1, 0, 0, ["name"]], [10, 1, 2, "id", 5]])
    def test_map_area_item_rejects_wrong_types_as_validation_errors(self, data):
        # A value the client stores as sent must be of the field's kind; the
        # callers catch ValueError, which ValidationError is.
        with pytest.raises(ValidationError):
            MapAreaItem.from_list(data)

    def test_map_area_item_reads_what_the_client_reads_through_int(self):
        # int("?") is 0: the empty tile, as WorldmapObjectFactory reads it
        item = MapAreaItem.from_list(["?", "?", "?", "?"])
        assert (item.item_type, item.x, item.y) == (MapItemType.EMPTY, 0, 0)

    @pytest.mark.parametrize("data", [[], [[]], [0], [0, 1], [0, 1, 2], ["a", "b", "c", "d", "e"], "abcde"])
    def test_castle_position_rows_that_do_not_fit_are_skipped(self, data):
        member = AllianceMember.model_validate({"OID": 1, "AP": [data, [0, 12345, 640, 655, 1]]})
        assert [(c.area_id, c.area_type) for c in member.castle_positions] == [(12345, 1)]

    def test_a_castle_position_without_its_area_type_is_kept(self):
        # MinWorldMapCastleInfoVO.fillFromParamObject reads row[4] raw, so a four-field row still counts
        member = AllianceMember.model_validate({"OID": 1, "AP": [[0, 12345, 640, 655]]})
        assert [(c.area_id, c.area_type) for c in member.castle_positions] == [(12345, None)]

    def test_a_movement_owner_reads_its_positions_as_every_owner_record_does(self):
        from empire_core.map.models.owners import OwnerCastlePosition
        from empire_core.movements.models import MovementOwner

        owner = MovementOwner.model_validate(
            {"OID": 1, "AP": [[[0, "12345", 640, 655, 1, 99]], [0, 1, "x", 2], [0, 1]], "VP": None}
        )
        assert owner.castle_positions == [OwnerCastlePosition(0, 12345, 640, 655, 1)]
        assert isinstance(owner.castle_positions[0], tuple)
        assert owner.village_positions == []

    def test_castle_positions_unwrap_a_doubly_nested_entry(self):
        member = AllianceMember.model_validate(
            {"OID": 1, "AP": [[[0, 12345, 640, 655, 1]]], "VP": [[[0, 6, 3, 4, 10]]]}
        )
        assert [(c.kingdom_id, c.area_id, c.x, c.y, c.area_type) for c in member.castle_positions] == [
            (0, 12345, 640, 655, 1)
        ]
        assert [c.area_type for c in member.village_positions] == [10]

    @pytest.mark.parametrize("data", [[], [1], [1, 2], [1, 2, 3], [1, 640, 655, 12345, 4242]])
    def test_a_row_too_short_for_its_type_is_refused(self, data):
        with pytest.raises(ValueError):
            PlayerCastle.from_list(data, kingdom=Kingdom.ICE)

    def test_player_castle_keeps_the_passed_kingdom_when_the_row_has_none(self):
        row = [1, 640, 655, 12345, 4242, 1, 1, 1, 0, 0, "Main"]
        assert PlayerCastle.from_list(row, kingdom=Kingdom.FIRE).kingdom is Kingdom.FIRE

    @pytest.mark.parametrize("stray", [11, "2", None, [4], True])
    def test_a_stray_row_kingdom_reads_as_the_block_kingdom(self, stray):
        # The client stores field 16 as sent and keys the castle by its block's KID
        row = gdi_location_row(1, 640, 655, 12345, 4242, "Main", 0)
        row[16] = stray
        assert PlayerCastle.from_list(row, kingdom=Kingdom.ICE).kingdom is Kingdom.ICE

    def test_a_castle_row_reads_its_levels_as_the_client_does(self):
        # InteractiveMapobjectVO: keep, wall and gate through int() and at least 1; tower and moat through int()
        row = gdi_location_row(1, 640, 655, 12345, 4242, "Main", 0)
        row[5:10] = [0, "3", 2.7, "4", None]
        castle = PlayerCastle.from_list(row)
        levels = (castle.keep_level, castle.wall_level, castle.gate_level, castle.tower_level, castle.moat_level)
        assert levels == (1, 3, 2, 4, 0)
        assert castle.landmark_level is None

    def test_a_capital_row_takes_its_levels_as_sent(self):
        row = gdi_location_row(3, 640, 655, 12345, 4242, "Capital", 0)
        row[5:10] = [0, 7, 7, 3, 2]
        castle = PlayerCastle.from_list(row)
        assert (castle.keep_level, castle.wall_level, castle.moat_level) == (0, 7, 2)

    def test_a_kings_tower_row_has_its_own_layout(self):
        # KingstowerMapobjectVO: object 3, owner 4, kingdom 5, espionage 6, name 7
        castle = PlayerCastle.from_list([23, 50, 60, 888, 4242, 2, -1, "Tower"], kingdom=Kingdom.GREEN)
        assert (castle.location_id, castle.owner_id, castle.kingdom, castle.name) == (888, 4242, Kingdom.ICE, "Tower")
        assert (castle.keep_level, castle.landmark_level, castle.occupier_id) == (None, None, -1)

    def test_a_monument_row_has_its_own_layout(self):
        # MonumentMapobjectVO: object 3, owner 4, type 5, level 6, kingdom 7, espionage 8, name 9
        castle = PlayerCastle.from_list([26, 50, 60, 889, 4242, 1, 5, 0, -1, "Monument"])
        assert (castle.location_id, castle.landmark_level, castle.kingdom, castle.name) == (
            889,
            5,
            Kingdom.GREEN,
            "Monument",
        )
        assert castle.keep_level is None

    def test_a_laboratory_row_has_its_own_layout(self):
        # LaboratoryMapobjectVO: object 3, owner 4, level 5, kingdom 6, espionage 7, name 8
        castle = PlayerCastle.from_list([28, 50, 60, 890, 4242, 3, 1, -1, "Lab"])
        assert (castle.location_id, castle.landmark_level, castle.kingdom, castle.name) == (
            890,
            3,
            Kingdom.SANDS,
            "Lab",
        )

    def test_a_faction_capital_row_has_no_object_id_or_name(self):
        # FactionCapitalMapobjectVO: owner 3, protectors 4, espionage 5, level 6, destroyed 7, camp id 8
        castle = PlayerCastle.from_list([18, 50, 60, -600, [], -1, 40, 0, 12], kingdom=Kingdom.BERIMOND)
        assert (castle.location_id, castle.owner_id, castle.name, castle.kingdom) == (
            None,
            -600,
            None,
            Kingdom.BERIMOND,
        )

    @pytest.mark.parametrize(("occupier", "occupied"), [(0, True), (-1, False), (-2, False)])
    def test_occupied_means_an_occupier_id_above_minus_one(self, occupier, occupied):
        # CastleMapobjectVO.isOccupied is _occupierID > -1
        row = gdi_location_row(1, 640, 655, 12345, 4242, "Main", 0, capturer_outpost=occupier)
        assert PlayerCastle.from_list(row).is_occupied is occupied
        entry = CastleInfo.from_entry({"AI": row})
        assert entry is not None and entry.is_occupied is occupied

    def test_a_castle_without_a_name_is_kept(self):
        # the client stores e[10] as sent, and its name getters handle null
        row = gdi_location_row(4, 640, 655, 12345, 4242, "x", 0)
        row[10] = None
        entry = CastleInfo.from_entry({"AI": row})
        assert entry is not None and (entry.castle_id, entry.castle_name) == (12345, "")

    def test_rows_that_name_no_castle_are_left_out_quietly(self, caplog):
        # FactionCapitalMapobjectVO has no object id; a faction camp of 3 fields is not on the map
        payload = {"C": [{"KID": 10, "AI": [[18, 50, 60, -600, [], -1, 40, 0, 12]]}, {"KID": 10, "AI": [[15, 1, 2]]}]}
        with caplog.at_level(logging.WARNING, logger="empire_core.castle.models.castles"):
            response = GetCastlesResponse.model_validate(payload)
        assert response.castles == []
        assert caplog.text == ""

    def test_player_castle_row_kingdom_wins_when_present(self):
        row = gdi_location_row(1, 640, 655, 12345, 4242, "Main", 4)
        assert PlayerCastle.from_list(row, kingdom=Kingdom.GREEN).kingdom is Kingdom.STORM

    @pytest.mark.parametrize(
        ("area_type", "capturer"),
        [
            (MapItemType.OUTPOST, 77),
            (MapItemType.CASTLE, 77),
            (MapItemType.KINGDOM_CASTLE, 77),
            (MapItemType.CAPITAL, 66),
            (MapItemType.METROPOL, 66),
        ],
    )
    def test_player_castle_capturer_depends_on_the_area_type(self, area_type, capturer):
        # InteractiveMapobjectVO.parseAreaInfo reads the occupier at 15; Capital and Metropol parsers at 14
        row = gdi_location_row(area_type, 640, 655, 12345, 4242, "Main", 0, capturer_capital=66, capturer_outpost=77)
        assert PlayerCastle.from_list(row).occupier_id == capturer

    @pytest.mark.parametrize("area_type", [200, MapItemType.NO_LANDMARK, MapItemType.NO_OUTPOST, MapItemType.VILLAGE])
    def test_a_row_of_an_area_type_a_castle_list_does_not_hold_is_refused(self, area_type):
        # 14, 20, 33 and 99 have no map object in WorldmapObjectFactory.mapObjectVOs; villages come in kgv
        with pytest.raises(ValueError):
            PlayerCastle.from_list(gdi_location_row(area_type, 640, 655, 12345, 4242, "Main", 0))

    def test_a_gcl_row_of_an_unknown_area_type_costs_only_itself(self):
        from empire_core.protocol.models import GetCastlesResponse

        rows = [{"AI": gdi_location_row(t, 640, 655, 100 + t, 4242, "Main", 0)} for t in (200, 4)]
        response = GetCastlesResponse.model_validate({"C": [{"KID": 0, "AI": rows}]})
        assert [(c.castle_id, c.castle_type) for c in response.castles] == [(104, MapItemType.OUTPOST)]

    def test_relocate_sends_only_the_position(self):
        # C2SStartRelocationVO(posX, posY) declares PX and PY and nothing else
        assert list(RelocateCastleRequest(x=10, y=20).to_payload().items()) == [("PX", 10), ("PY", 20)]

    @pytest.mark.parametrize("field", [1, 3, 10])
    def test_player_castle_rejects_wrong_types(self, field):
        row = gdi_location_row(1, 640, 655, 12345, 4242, "Main", 0)
        row[field] = [4]
        with pytest.raises(ValidationError):
            PlayerCastle.from_list(row)

    def test_player_castle_rejects_what_is_not_a_row(self):
        with pytest.raises(ValueError):
            PlayerCastle.from_list("abcd")

    @pytest.mark.parametrize("data", [[], [1], [1, 2], [1, 2, "nope"], [1, 2, []], [1, 2, {}]])
    def test_alliance_search_result_without_an_alliance_row_has_defaults(self, data):
        result = AllianceSearchResult.model_validate(data)
        assert (result.alliance_id, result.name, result.member_count) == (0, "", 0)

    def test_alliance_search_result_reads_numbers_like_the_client(self):
        result = AllianceSearchResult.model_validate(["3", 2.0, ["x", 7, "12", None]])
        assert (result.rank, result.score, result.alliance_id, result.name, result.member_count) == (3, 2, 0, "7", 12)
        assert result.fame_points == 0


class TestMalformedNestedResponsePayloads:
    """One bad element inside a keyed batch, as the server would send it."""

    def test_chat_message_missing_the_player_id_reads_it_as_zero(self):
        response = AllianceChatMessageResponse.model_validate({"CM": {"PN": "a", "MT": "b"}})
        assert response.player_id == 0

    def test_chat_message_with_a_non_dict_block_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            AllianceChatMessageResponse.model_validate({"CM": "junk"})

    def test_one_bad_chat_log_entry_costs_only_itself(self, caplog):
        # parseHistory throws on a null entry and keeps a non-object as a blank
        # message; the library skips such entries instead, deliberately
        payload = {"CM": [{"PID": 1, "PN": "a", "MT": "b"}, None, "junk", {"PID": 2, "PN": ["c"]}, {"PID": 3}]}
        with caplog.at_level("WARNING", logger="empire_core.alliance.models.chat"):
            response = AllianceChatLogResponse.model_validate(payload)
        assert [e.player_id for e in response.chat_log] == [1, 3]
        assert "Skipped 2/5 unreadable alliance chat messages" in caplog.text

    @pytest.mark.parametrize("value", [None, "junk", {"PID": 1}, 5])
    def test_a_chat_log_that_is_no_list_reads_as_empty(self, value):
        assert AllianceChatLogResponse.model_validate({"CM": value}).chat_log == []

    def test_an_unreadable_alliance_member_costs_only_itself(self):
        # parseOwnerInfo gives null for a record without an OID, and parseMemberList's
        # rank sort then throws on it; the library skips such entries instead, deliberately
        info = AllianceInfo.model_validate({"AID": 1, "M": ["junk", {"N": "no id"}, {"OID": 0}, {"OID": 7, "AR": 8}]})
        assert [m.player_id for m in info.members] == [7]

    def test_drifted_unit_array_reads_as_the_client_reads_it(self):
        # AUnitInventory.fillFromWodAmountArray: array entries only, each value through int()
        junk = GetDetailedCastleResponse.model_validate({"C": [{"AI": [{"AID": 1, "AC": "junk"}]}]})
        assert junk.castles[0].raw_units == []
        drifted = GetDetailedCastleResponse.model_validate({"C": [{"AI": [{"AID": 1, "AC": [[201, "x"]]}]}]})
        assert drifted.castles[0].raw_units == [[201, 0]]

    def test_dcl_castle_without_an_id_is_skipped(self):
        response = GetDetailedCastleResponse.model_validate({"C": [{"AI": [{"W": 1.0}, {"AID": 2}]}]})
        assert [c.castle_id for c in response.castles] == [2]

    def test_drifted_defense_array_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            GetSupportDefenseResponse.model_validate({"SCID": 1, "S": "nope"})

    def test_a_missing_alliance_block_is_not_an_error(self):
        response = GetAllianceInfoResponse.model_validate({"A": None})
        assert response.members == []
        assert response.online_members == []

    def test_drifted_map_row_is_skipped_and_counted_at_parse_time(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.map.models.areas"):
            response = GetMapAreaResponse.model_validate({"KID": 1, "AI": [[99, "?", "?", "?"]]})
        assert response.kingdom == Kingdom.SANDS
        assert response.items == []
        assert response.get_moving_flags() == {}
        assert "Skipped 1/1" in caplog.text
        assert "kingdom 1" in caplog.text

    def test_map_rows_survive_a_drifted_neighbour(self, caplog):
        good_row = [1, 640, 655, 900, 4242]
        with caplog.at_level(logging.WARNING, logger="empire_core.map.models.areas"):
            response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [[99, "?", "?", "?"], good_row, "junk"]})
        assert [(i.x, i.y, i.owner_id) for i in response.items] == [(640, 655, 4242)]
        assert response.items[0].raw_data == good_row
        assert "Skipped 2/3" in caplog.text

    def test_a_map_area_without_a_row_list_has_no_items(self):
        assert GetMapAreaResponse.model_validate({"KID": 0, "AI": {"x": 1}}).items == []


class TestDriftedPayloadsMustNotCrashAccessors:
    """Accessors on a parsed response are called by consumer code.

    They already shape-check their input, so a raw AttributeError/TypeError
    escaping one of them is a hole: callers are told to catch EmpireError (or
    ValidationError at parse time) and cannot defend against these.
    """

    def test_castle_wrapper_that_is_not_a_dict_is_skipped(self):
        # This one is guarded: the wrapper check exists.
        response = GetPlayerInfoResponse.model_validate({"gcl": {"C": [{"KID": 0, "AI": ["junk"]}]}})
        assert response.get_castles() == []

    def test_castle_location_list_of_the_wrong_type_is_skipped(self):
        response = GetPlayerInfoResponse.model_validate({"gcl": {"C": [{"KID": 0, "AI": "junk"}]}})
        assert response.get_castles() == []

    def test_drifted_kingdom_entry_is_skipped_rather_than_crashing(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.castle.models.castles"):
            response = GetPlayerInfoResponse.model_validate(
                {
                    "gcl": {
                        "C": [
                            {"KID": 0, "AI": [{"AI": gdi_location_row(1, 1, 2, 3, 4, "Keep", 0)}]},
                            "unexpected-string-entry",
                        ]
                    }
                }
            )
        assert [c.castle_name for c in response.get_castles()] == ["Keep"]
        # Skipped silently is a hole too: the drop must be visible, once.
        assert caplog.text.count("Skipped 1/2") == 1

    def test_string_unit_count_does_not_crash_the_defense_total(self):
        response = GetSupportDefenseResponse.model_validate({"SCID": 1, "S": [[[487, 100]], [[488, "20"]]]})
        assert response.get_total_defenders() >= 100

    def test_string_unit_count_does_not_crash_the_per_position_grouping(self):
        response = GetSupportDefenseResponse.model_validate({"SCID": 1, "S": [[[488, "20"]]]})
        assert response.get_units_by_position() == [{488: 20}]

    def test_defense_rows_of_the_wrong_shape_are_already_skipped(self):
        response = GetSupportDefenseResponse.model_validate({"SCID": 1, "S": [[[487]], ["junk"], [[487, 5]]]})
        assert response.get_total_defenders() == 5

    def test_unreadable_defense_counts_read_as_zero_like_the_client(self):
        # fillFromWodAmountArray reads int() of each value, and UnitInventoryList.addUnit skips 0
        response = GetSupportDefenseResponse.model_validate(
            {"SCID": 7, "S": [[[487, "x"], [488, None], [489, 5]], ["junk"]]}
        )
        assert response.defense_positions == [[[489, 5]], []]
        assert response.get_total_defenders() == 5

    def test_zero_counts_are_left_out_of_the_per_position_grouping(self):
        response = GetSupportDefenseResponse.model_validate({"SCID": 7, "S": [[[487, "x"], [488, 20]]]})
        assert response.get_units_by_position() == [{488: 20}]

    def test_clean_defense_payloads_log_nothing(self, caplog):
        response = GetSupportDefenseResponse.model_validate({"SCID": 1, "S": [[[487, 100]]]})
        with caplog.at_level(logging.WARNING, logger="empire_core.defense.models"):
            assert response.get_total_defenders() == 100
            assert response.get_units_by_position() == [{487: 100}]
        assert not [r for r in caplog.records if r.levelno == logging.WARNING]


class TestReplyEnumProperties:
    """Reply fields stay ints; the enum properties read None for a value the client does not define."""

    def test_alliance_standing_and_activity_read_as_client_constants(self):
        info = AllianceInfo.model_validate(
            {
                "DOA": 3,
                "ADL": [{"AID": 5, "AS": 0, "AC": 1}, {"AID": 6, "AS": 9, "AC": 0}],
                "AMI": [[42, 0, 0, 0, 1], [43, 0, 0, 0, 7]],
            }
        )
        assert info.status_to_own_alliance == 3
        assert info.status_to_own_alliance_enum is DiplomacyStatus.REAL_ALLIED
        assert [s.status for s in info.alliance_diplomacy] == [0, 9]
        assert [s.status_enum for s in info.alliance_diplomacy] == [DiplomacyStatus.IN_WAR, None]
        assert [m.login_activity_enum for m in info.member_info] == [OnlineState.LAST_12_HOURS, None]

    def test_equipment_rarity_reads_as_rareness(self):
        assert Rareness.HERO_BEGINN is Rareness.HERO_UNIQUE
        assert Equipment(rarity_id=4).rarity_enum is Rareness.LEGENDARY
        assert Equipment(rarity_id=13).rarity_enum is Rareness.HERO_EPIC
        assert Equipment(rarity_id=7).rarity_enum is None

    def test_a_scan_of_a_kingdom_the_client_does_not_define_is_refused(self):
        # GAACommand has no fallback for a kingdom id, and Kingdom holds every one the client defines
        assert GetMapAreaResponse.model_validate({"KID": 2, "AI": []}).kingdom is Kingdom.ICE
        with pytest.raises(ValidationError):
            GetMapAreaResponse.model_validate({"KID": 11, "AI": []})

    def test_a_camp_row_in_a_kingdom_the_client_does_not_define_keeps_the_row(self):
        # A kingdom the client does not define leaves the row in the reply's kingdom
        response = GetMapAreaResponse.model_validate(
            {"KID": 0, "AI": [[2, 510, 256, -1, 297, 5, 11], [2, 1, 2, -1, 3, 5, 2]]}
        )
        assert [(item.victory_count, item.kingdom) for item in response.items] == [
            (297, Kingdom.GREEN),
            (3, Kingdom.ICE),
        ]


@pytest.mark.parametrize("dump", [{"by_alias": True}, {"by_alias": True, "mode": "json"}])
def test_owner_positions_survive_a_dump_and_validate_round_trip(dump):
    from empire_core.map.models.areas import MapObject
    from empire_core.movements.models import MovementOwner
    from empire_core.player.models.info import PlayerOwnerInfo

    record = {"OID": 5, "N": "p", "AP": [[0, 12345, 640, 655, 1]], "VP": [[0, 6, 3, 4, 10]]}
    for model in (MapObject, MovementOwner, PlayerOwnerInfo):
        first = model.model_validate(record)
        again = model.model_validate(first.model_dump(**dump))
        assert again.castle_positions == first.castle_positions == [(0, 12345, 640, 655, 1)], model
        assert again.village_positions == first.village_positions == [(0, 6, 3, 4, 10)], model
        assert model.model_validate(first.to_payload()).castle_positions == first.castle_positions, model
