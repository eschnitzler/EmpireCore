"""Tests for the player models."""

import pytest

from empire_core.castle.models.castles import GetCastlesResponse
from empire_core.enums import Kingdom, MapItemType
from empire_core.player.models.info import (
    GetPlayerInfoResponse,
    PlayerOwnerInfo,
    SearchPlayerRequest,
    SearchPlayerResponse,
)
from empire_core.protocol.models import parse_response
from tests.model_helpers import gdi_location_row

GOLDEN_GDI = {
    "O": {
        "OID": 4242,
        "N": "TargetPlayer",
        "L": 70,
        "LL": 500,
        "AID": 190426,
        "AN": "Test Alliance",
        "RPT": 3600,
        "AP": [[0, 12345, 640, 655, 1]],
        "E": {"BGT": 1},
    },
    "gcl": {
        "PID": 4242,
        "C": [
            {
                "KID": 0,
                "AI": [
                    {"AI": gdi_location_row(1, 640, 655, 12345, 4242, "Main Castle", 0)},
                    {"AI": gdi_location_row(4, 700, 700, 55555, 4242, "Outpost North", 0, capturer_outpost=9999)},
                ],
            },
            {
                "KID": 2,
                "AI": [{"AI": gdi_location_row(3, 300, 400, 77777, 4242, "Ice Capital", 2, capturer_capital=8888)}],
            },
        ],
    },
}


class TestGoldenPlayerInfo:
    def test_registry_parses_gdi(self):
        assert isinstance(parse_response("gdi", GOLDEN_GDI), GetPlayerInfoResponse)

    def test_owner_fields_are_exposed_through_the_response(self):
        response = GetPlayerInfoResponse.model_validate(GOLDEN_GDI)
        assert response.player_id == 4242
        assert response.player_name == "TargetPlayer"
        assert response.alliance_id == 190426
        assert response.alliance_name == "Test Alliance"
        assert response.has_bird is True
        assert response.bird_end_time is not None

    def test_castles_are_flattened_across_kingdoms(self):
        castles = GetPlayerInfoResponse.model_validate(GOLDEN_GDI).get_castles()
        assert [(c.castle_name, c.kingdom_id, c.x, c.y, c.castle_type) for c in castles] == [
            ("Main Castle", 0, 640, 655, 1),
            ("Outpost North", 0, 700, 700, 4),
            ("Ice Capital", 2, 300, 400, 3),
        ]

    def test_the_castle_list_is_the_gcl_model(self):
        response = GetPlayerInfoResponse.model_validate(GOLDEN_GDI)
        assert isinstance(response.castle_list, GetCastlesResponse)
        assert response.castle_list.player_id == 4242
        assert [c.castle_id for c in response.castle_list.castles] == [12345, 55555, 77777]

    def test_an_unwrapped_row_parses_too(self):
        row = gdi_location_row(1, 640, 655, 12345, 4242, "Main Castle", 0)
        response = GetPlayerInfoResponse.model_validate({"gcl": {"C": [{"KID": 0, "AI": [{"AI": row, "AOT": 30}]}]}})
        assert [(c.castle_id, c.abandon_outpost_seconds) for c in response.get_castles()] == [(12345, 30)]

    def test_capturer_id_is_read_from_the_type_specific_index(self):
        # Outposts carry it at index 15, capitals at index 14 - reading the
        # wrong one reports a capture that is not happening (or misses one).
        castles = {c.castle_name: c for c in GetPlayerInfoResponse.model_validate(GOLDEN_GDI).get_castles()}
        assert castles["Main Castle"].occupier_id == -1
        assert castles["Outpost North"].occupier_id == 9999
        assert castles["Ice Capital"].occupier_id == 8888

    def test_captures_are_extracted_with_their_kingdom(self):
        captures = GetPlayerInfoResponse.model_validate(GOLDEN_GDI).get_location_captures()
        assert {(c.location_id, c.capturer_id, c.kingdom) for c in captures} == {
            (55555, 9999, Kingdom.GREEN),
            (77777, 8888, Kingdom.ICE),
        }

    def test_captures_include_main_and_kingdom_castles_occupied_by_player_zero(self):
        # isOccupied is an occupier id above -1, and castles read it at field 15 like outposts
        rows = [
            gdi_location_row(1, 1, 1, 501, 4242, "Main", 0, capturer_outpost=0),
            gdi_location_row(12, 2, 2, 502, 4242, "Sands", 1, capturer_outpost=77),
            gdi_location_row(4, 3, 3, 503, 4242, "Free", 0, capturer_outpost=-2),
        ]
        response = GetPlayerInfoResponse.model_validate({"gcl": {"C": [{"KID": 0, "AI": [{"AI": r} for r in rows]}]}})
        assert response.get_all_captures_by_location() == {501: 0, 502: 77}
        assert [c.location_type for c in response.get_location_captures()] == [
            MapItemType.CASTLE,
            MapItemType.KINGDOM_CASTLE,
        ]

    def test_captures_by_location_mapping(self):
        response = GetPlayerInfoResponse.model_validate(GOLDEN_GDI)
        assert response.get_all_captures_by_location() == {55555: 9999, 77777: 8888}

    def test_empty_gdi_payload_is_harmless(self):
        response = GetPlayerInfoResponse.model_validate({})
        assert response.player_id == 0
        assert response.player_name == ""
        assert response.get_castles() == []
        assert response.get_location_captures() == []
        assert response.has_bird is False

    def test_the_owner_crest_is_typed(self):
        owner = GetPlayerInfoResponse.model_validate(GOLDEN_GDI).owner
        assert owner is not None and owner.emblem is not None
        assert (owner.emblem.background_type, owner.emblem.is_set) == (1, False)
        assert [(c.area_id, c.area_type) for c in owner.castle_positions] == [(12345, 1)]


class TestSearchPlayer:
    """WSPCommand.executeCommand: gaa is a map area reply."""

    def test_the_found_player_is_the_first_owner_record(self):
        payload = {
            "X": 640,
            "Y": 655,
            "gaa": {
                "AI": [[1, 640, 655, 12345, 4242, 5, 5, 5, 0, 0, "Main Castle"]],
                "OI": [{"OID": 4242, "N": "TargetPlayer", "L": 70, "AID": 190426}],
            },
        }
        response = SearchPlayerResponse.model_validate(payload)
        player = response.get_player()
        assert player is not None
        assert (player.owner_id, player.owner_name, player.level, player.alliance_id) == (
            4242,
            "TargetPlayer",
            70,
            190426,
        )
        assert [(i.x, i.y, i.owner_id) for i in response.area.items] == [(640, 655, 4242)]

    def test_the_gaa_block_is_the_map_area_fnm_reads(self):
        # WSPCommand.executeCommand (bundle line 131619) reads gaa.OI and gaa.AI as FNMCommand does
        from empire_core.map.models.areas import MapArea

        assert isinstance(SearchPlayerResponse.model_validate({"gaa": {"AI": [], "OI": []}}).area, MapArea)

    def test_the_found_player_owns_the_area_at_x_y(self):
        # parseSearchInfos opens the area at X/Y, so a neighbour listed first is not the player
        payload = {
            "X": 640,
            "Y": 655,
            "gaa": {
                "AI": [
                    [1, 600, 600, 111, 7, 5, 5, 5, 0, 0, "Neighbour"],
                    [1, 640, 655, 12345, 4242, 5, 5, 5, 0, 0, "Main Castle"],
                ],
                "OI": [{"OID": 7, "N": "Neighbour"}, {"OID": 4242, "N": "TargetPlayer"}],
            },
        }
        player = SearchPlayerResponse.model_validate(payload).get_player()
        assert player is not None and player.owner_id == 4242

    @pytest.mark.parametrize("payload", [{}, {"gaa": "junk"}, {"gaa": {"OI": []}}])
    def test_no_owner_record_is_no_player(self, payload):
        assert SearchPlayerResponse.model_validate(payload).get_player() is None


class TestPlayerInfoLandmarks:
    def test_landmark_lists_join_the_first_kingdom(self):
        # GDICommand.addGKLToGC and friends unwrap each row and push it into gcl.C[0].AI
        response = GetPlayerInfoResponse.model_validate(
            {
                "gcl": {"C": [{"KID": 0, "AI": [{"AI": gdi_location_row(1, 640, 655, 12345, 4242, "Main", 0)}]}]},
                "gkl": {"AI": [[[23, 50, 60, 888, 4242, 0, -1, "Tower"], []]]},
                "gml": {"AI": [[[26, 51, 61, 889, 4242, 1, 5, 0, -1, "Monument"], []]]},
                "gll": {"AI": [[[28, 52, 62, 890, 4242, 3, 0, -1, "Lab"], []]]},
            }
        )
        castles = response.get_castles()
        assert [(c.castle_id, c.castle_type, c.castle_name) for c in castles] == [
            (12345, MapItemType.CASTLE, "Main"),
            (888, MapItemType.KINGS_TOWER, "Tower"),
            (889, MapItemType.MONUMENT, "Monument"),
            (890, MapItemType.LABORATORY, "Lab"),
        ]
        assert [c.landmark_level for c in castles] == [None, None, 5, 3]
        assert castles[1].keep_level is None

    def test_a_gcl_row_in_an_extra_list_is_not_unwrapped(self):
        wrapped = {"AI": [gdi_location_row(1, 640, 655, 12345, 4242, "Main", 0)]}
        response = GetPlayerInfoResponse.model_validate({"gcl": {"C": [{"KID": 0, "AI": [wrapped]}]}})
        assert response.get_castles() == []


class TestOwnerRecord:
    """As WorldMapOwnerInfoVO.fillFromParamObject (bundle line 10794) reads it."""

    def test_the_keys_the_client_reads(self):
        owner = PlayerOwnerInfo.model_validate(
            {
                "OID": "4242",
                "N": "TargetPlayer",
                "RNP": 3600,
                "R": "1",
                "AID": 190426,
                "AR": 8,
                "SA": 1,
                "PF": 1,
                "VF": 0,
                "DUM": "1",
                "RRD": 120,
                "FN": {"FID": 2, "PMS": 1, "PMT": 60, "TID": 3},
                "SUF": 17,
                "PRE": "4",
                "IRF": "1",
            }
        )
        assert owner.player_id == 4242
        assert owner.beginner_protection_seconds == 3600
        assert owner.is_ruin is True
        assert owner.is_searching_alliance is True
        assert (owner.has_premium_flag, owner.has_vip_flag, owner.is_dummy) == (True, False, True)
        assert owner.relocation_remaining_seconds == 120
        assert owner.faction is not None and (owner.faction.faction_id, owner.faction.title_id) == (2, 3)
        assert (owner.title_suffix, owner.title_prefix) == (17, 4)
        assert owner.via_refer_a_friend is True

    def test_what_a_bare_record_reads_as(self):
        owner = PlayerOwnerInfo.model_validate({"OID": 1})
        assert (owner.alliance_id, owner.is_in_alliance, owner.is_leader) == (-1, False, False)
        assert (owner.title_suffix, owner.title_prefix) == (None, None)
        assert (owner.is_ruin, owner.is_searching_alliance, owner.via_refer_a_friend) == (False, False, False)
        assert owner.faction is None

    def test_a_negative_relocation_reads_as_none_left(self):
        assert PlayerOwnerInfo.model_validate({"RRD": -5}).relocation_remaining_seconds == 0

    def test_only_ruin_value_one_is_a_ruin(self):
        assert PlayerOwnerInfo.model_validate({"R": 2}).is_ruin is False

    def test_the_alliance_crest_is_read_only_inside_an_alliance(self):
        aee = {"ACCA": {"ACLI": 3, "ACCS": [1, 2]}}
        inside = PlayerOwnerInfo.model_validate({"AID": 5, "aee": aee})
        assert inside.alliance_emblem is not None and inside.alliance_emblem.crest is not None
        assert inside.alliance_emblem.crest.layout_id == 3
        assert PlayerOwnerInfo.model_validate({"AID": -1, "aee": aee}).alliance_emblem is None
        assert PlayerOwnerInfo.model_validate({"AID": 5, "aee": {}}).alliance_emblem is None

    def test_a_player_outside_an_alliance_is_not_its_leader(self):
        assert PlayerOwnerInfo.model_validate({"AR": 0}).is_leader is False

    def test_no_owner_is_no_alliance(self):
        assert GetPlayerInfoResponse.model_validate({}).alliance_id == -1


def test_a_player_search_encodes_the_name_as_chat_text():
    # C2SSearchPlayerVO runs PN through TextValide.getValideSmartFoxJSONTextMessage
    request = SearchPlayerRequest(PN="O'Brien 100%")
    assert request.to_payload() == {"PN": "O&145;Brien 100&percnt;"}
    assert request.player_name == "O'Brien 100%"
