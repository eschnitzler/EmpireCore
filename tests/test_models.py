"""Tests for the protocol model registry and base behaviors."""

import logging

import pytest
from pydantic import Field, ValidationError

from empire_core.protocol.models import parse_response
from empire_core.protocol.models.alliance import (
    AllianceInfo,
    AllianceMember,
    AllianceSearchResult,
    GetAllianceInfoResponse,
)
from empire_core.protocol.models.base import (
    BaseResponse,
    decode_chat_text,
    encode_chat_text,
    get_response_model,
)
from empire_core.protocol.models.castle import (
    GetCastlesResponse,
    GetDetailedCastleResponse,
    PlayerCastle,
    RenameCastleRequest,
    RenameCastleResponse,
)
from empire_core.protocol.models.chat import AllianceChatLogResponse, AllianceChatMessageResponse
from empire_core.protocol.models.defense import GetSupportDefenseResponse
from empire_core.protocol.models.map import (
    GetMapAreaResponse,
    Kingdom,
    MapAreaItem,
    MapItemType,
)
from empire_core.protocol.models.player import GetPlayerInfoResponse, SearchPlayerResponse
from empire_core.protocol.models.ranking import GetHighscoreResponse, GetRankingListResponse, RankingEntry


class TestRegistry:
    def test_known_commands_registered(self):
        # Importing the models package must register all command modules,
        # including defense (previously forgotten in __init__).
        for command in ("gam", "gaa", "ain", "acm", "acl", "gdi", "dfc", "sdi", "hgh", "gcl", "dcl"):
            assert get_response_model(command) is not None, f"'{command}' not registered"

    def test_unknown_command_returns_none(self):
        assert get_response_model("nonexistent") is None
        assert parse_response("nonexistent", {}) is None

    def test_duplicate_registration_raises(self):
        class UniqueResponse(BaseResponse):
            command = "test_dup_cmd"

        with pytest.raises(TypeError, match="Duplicate response registration"):

            class ConflictingResponse(BaseResponse):
                command = "test_dup_cmd"

    def test_register_opt_out(self):
        class OptOutResponse(BaseResponse, register=False):
            command = "test_optout_cmd"

        assert get_response_model("test_optout_cmd") is None


class TestBaseResponse:
    def test_error_code_from_payload(self):
        class SomeResponse(BaseResponse, register=False):
            command = "test_some_cmd"

        response = SomeResponse.model_validate({"E": 21})
        assert response.error_code == 21
        assert response.success is False

        ok = SomeResponse.model_validate({})
        assert ok.error_code == 0
        assert ok.success is True

    def test_error_payload_parses_for_registered_models(self):
        # An error-shaped payload ({"E": code} and nothing else) must not
        # raise ValidationError for any registered response model.
        for command in ("ain", "acl", "gam", "gaa", "dfc", "gdi", "gcl"):
            response = parse_response(command, {"E": 21})
            assert response is not None, f"'{command}' has no model"
            assert response.error_code == 21
            assert response.success is False

    def test_to_payload_uses_aliases(self):
        class AliasedResponse(BaseResponse, register=False):
            command = "test_alias_cmd"
            castle_id: int = Field(alias="CID", default=0)

        response = AliasedResponse(CID=5)
        assert response.to_payload()["CID"] == 5


class TestAllianceInfoMemberInfo:
    """AMI is an unvalidated positional server array that has drifted format before.

    model_post_init exceptions are NOT wrapped by pydantic, so anything raised
    here escapes model_validate un-wrapped and defeats `except ValidationError`.
    """

    @pytest.mark.parametrize(
        "ami",
        [
            [5],  # entry is a bare int -> len() fails
            [None],  # entry is None
            [[1, 2]],  # entry too short
            [[[1, 2], 0, 0, 0, 3]],  # unhashable player id
            [{"OID": 1, "AT": 3}],  # drifted to dicts
            "not-a-list",  # whole field drifted
        ],
    )
    def test_malformed_ami_does_not_raise(self, ami):
        try:
            info = AllianceInfo.model_validate({"AID": 1, "AMI": ami})
        except ValidationError:
            # Rejecting the field outright is acceptable; crashing is not.
            return
        assert info.alliance_id == 1

    def test_malformed_ami_entry_is_logged(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.protocol.models.alliance"):
            AllianceInfo.model_validate({"AID": 1, "AMI": [5]})
        assert [r for r in caplog.records if r.levelno >= logging.WARNING], "malformed AMI logged nothing"

    def test_valid_ami_still_populates_activity_tier(self):
        info = AllianceInfo.model_validate(
            {
                "AID": 1,
                "M": [{"OID": 7, "N": "online_guy"}, {"OID": 8, "N": "afk_guy"}],
                "AMI": [[7, 0, 0, 0, 0], [8, 0, 0, 0, 4]],
            }
        )
        by_name = {m.name: m for m in info.members}
        assert by_name["online_guy"].activity_tier == 0
        assert by_name["online_guy"].is_online
        assert by_name["afk_guy"].activity_tier == 4
        assert not by_name["afk_guy"].is_online
        assert info.online_count == 1

    def test_good_entries_survive_a_bad_neighbour(self):
        info = AllianceInfo.model_validate(
            {
                "AID": 1,
                "M": [{"OID": 7, "N": "good"}],
                "AMI": [5, [7, 0, 0, 0, 2]],
            }
        )
        assert info.members[0].activity_tier == 2


class TestChatEncoding:
    def test_roundtrip_special_characters(self):
        original = "Hello 100% \"friend\" 'quoted'\nnew \\ line"
        assert decode_chat_text(encode_chat_text(original)) == original

    def test_backslash_wire_format(self):
        # Backslash must encode to literal %5C, not &percnt;5C
        assert encode_chat_text("\\") == "%5C"

    def test_literal_percent_5c_text_roundtrip(self):
        # A user literally typing "%5C" must not decode into a backslash
        original = "give me %5C please"
        assert decode_chat_text(encode_chat_text(original)) == original


# =============================================================================
# Golden payloads
#
# The dicts below are written in the shape the live server sends, positional
# arrays included. They exist so a format drift shows up as a failing parse
# here rather than as a runtime crash in a consumer.
# =============================================================================


def gdi_location_row(
    location_type: int,
    x: int,
    y: int,
    location_id: int,
    owner_id: int,
    name: str,
    kingdom: int,
    capturer_capital: int = -1,
    capturer_outpost: int = -1,
) -> list:
    """A 20-field gdi/gcl location row as the live server sends it.

    Index map (see GetPlayerInfoResponse's docstring): 0 type, 1 x, 2 y,
    3 location id, 4 owner id, 10 name, 14 capturer (Capital/Metro),
    15 capturer (Outpost), 16 kingdom.
    """
    return [
        location_type,
        x,
        y,
        location_id,
        owner_id,
        1,
        1,
        1,
        0,
        0,
        name,
        0,
        0,
        -1,
        capturer_capital,
        capturer_outpost,
        kingdom,
        190426,
        [],
        0,
    ]


GOLDEN_AIN = {
    "A": {
        "AID": 190426,
        "N": "Test Alliance",
        "A": "Welcome to the alliance",
        "MP": 4213377,
        "ML": 50,
        "STO": {"W": 120000, "S": 98000, "O": 45000, "C1": 3000, "C2": 12, "I": 400, "G": 7},
        "ABL": [{"BT": 1, "L": 5, "CD": -1}, {"BT": 2, "L": 3, "CD": 3600}],
        "M": [
            {
                "OID": 7001,
                "N": "LeaderGuy",
                "L": 70,
                "LL": 812,
                "AR": 8,
                "MP": 1200000,
                "RPT": 0,
                "AP": [[0, 12345, 640, 655, 1], [2, 22222, 300, 400, 4]],
                "E": {"BGT": 1, "BGC1": 2, "SPT": 3, "S1": 4, "IS": 1},
            },
            {"OID": 7002, "N": "OfficerGal", "L": 70, "AR": 4, "RPT": 7200, "AP": [[0, 12346, 641, 656, 1]]},
        ],
        "AMI": [[7001, 0, 0, 0, 0], [7002, 0, 0, 0, 2]],
    }
}

GOLDEN_DCL = {
    "PID": 17743260,
    "C": [
        {
            "KID": 0,
            "AI": [
                {
                    "AID": 16654596,
                    "W": 7000.0,
                    "S": 6999.5,
                    "F": 7000.0,
                    "C": 12.0,
                    "O": 0.0,
                    "G": 3.0,
                    "A": 0.0,
                    "I": 0.0,
                    "HONEY": 40.0,
                    "MEAD": 0.0,
                    "BEEF": 0.0,
                    "D": 57,
                    "gpa": {
                        "DFC": 90.0,
                        "DMEADC": 0.0,
                        "DBEEFC": 0.0,
                        "DW": 2239,
                        "DS": 1952,
                        "DF": 3502,
                        "DHONEY": 15,
                        "S": 0,
                        "WM": 110.0,
                        "SM": 110.0,
                        "FM": 110.0,
                        "MP": 0,
                        "FCR": 100,
                        "MEADCR": 100,
                        "BEEFCR": 100,
                        "MRW": 7000,
                        "SAFE_W": 1000.0,
                        "MRS": 7000,
                        "MRF": 7000,
                        "MRA": 51000,
                        "P": 80,
                        "NDP": 11927,
                        "R": 5,
                        "GRD": 5,
                        "RS1": 328.0,
                        "RS2": 318.0,
                        "RS3": 318.0,
                        "RSH": 318,
                        "BDB": 125,
                        "US": 0,
                        "M": 0,
                    },
                    # Unit stacks as positional pairs; the trailing 1-element
                    # entry is the kind of short row the server does send.
                    "AC": [[656, 1], [650, 213], [999]],
                    "SHI": [],
                    "HI": [[11, 5], [12, 15]],
                    "TU": [[620, 3]],
                    "MC": 5,
                    "B": 1,
                    "WS": 1,
                    "DW": 1,
                    "H": 1,
                    "OGT": 0,
                    "AOT": -1,
                },
                {"AID": 16656989, "W": 800.0, "S": 800.0, "F": 800.0, "AC": [[649, 18]], "B": 0},
            ],
        }
    ],
}

GOLDEN_GCL = {
    "PID": 17743260,
    "C": [
        {
            "KID": 0,
            "AI": [
                {"AI": gdi_location_row(1, 632, 243, 16654596, 17743260, "Château Heimlin", 0), "AOT": -1, "TA": -1},
                {"AI": gdi_location_row(4, 630, 244, 16656989, 17743260, "OP1", 0), "TA": 0},
            ],
        },
        {"KID": 2, "AI": [{"AI": gdi_location_row(12, 100, 200, 16700000, 17743260, "Sands", 0)}]},
    ],
}

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

GOLDEN_SDI = {
    "SCID": 12345,
    # Six defense positions, each a list of [unit_id, count] pairs.
    "S": [[[487, 5174], [488, 20]], [[487, 347]], [], [[301, 10]], [], []],
    "B": {"LID": -14},
    "gui": {"U": []},
    "gli": {"C": []},
    "UYL": 12000,
    "AUYL": 3000,
    "UWL": 5000,
}


class TestGoldenAllianceInfo:
    def test_registry_parses_ain_into_the_alliance_response(self):
        response = parse_response("ain", GOLDEN_AIN)
        assert isinstance(response, GetAllianceInfoResponse)
        assert response.success is True

    def test_alliance_header_fields(self):
        info = GetAllianceInfoResponse.model_validate(GOLDEN_AIN).alliance
        assert info is not None
        assert info.alliance_id == 190426
        assert info.name == "Test Alliance"
        assert info.announcement == "Welcome to the alliance"
        assert info.might == 4213377
        assert info.external_member_level == 50
        assert info.member_count == 2

    def test_storage_and_buildings(self):
        info = GetAllianceInfoResponse.model_validate(GOLDEN_AIN).alliance
        assert info is not None
        assert info.storage is not None
        assert (info.storage.wood, info.storage.stone, info.storage.food) == (120000, 98000, 45000)
        assert [(b.building_type, b.level, b.cooldown) for b in info.buildings] == [(1, 5, -1), (2, 3, 3600)]

    def test_members_get_their_activity_tier_from_ami(self):
        response = GetAllianceInfoResponse.model_validate(GOLDEN_AIN)
        by_name = {m.name: m for m in response.members}
        assert by_name["LeaderGuy"].activity_tier == 0
        assert by_name["OfficerGal"].activity_tier == 2
        assert [m.name for m in response.online_members] == ["LeaderGuy"]

    def test_member_castles_parse_from_the_positional_ap_array(self):
        response = GetAllianceInfoResponse.model_validate(GOLDEN_AIN)
        leader = response.members[0]
        assert [(c.kingdom_id, c.area_id, c.x, c.y, c.area_type) for c in leader.castle_positions] == [
            (0, 12345, 640, 655, 1),
            (2, 22222, 300, 400, 4),
        ]

    def test_member_derived_flags(self):
        response = GetAllianceInfoResponse.model_validate(GOLDEN_AIN)
        by_name = {m.name: m for m in response.members}
        assert by_name["LeaderGuy"].is_leader is True
        assert by_name["OfficerGal"].is_officer is True
        assert by_name["OfficerGal"].has_bird is True
        assert by_name["OfficerGal"].bird_end_time is not None
        assert by_name["LeaderGuy"].bird_end_time is None

    def test_typed_member_emblem(self):
        leader = GetAllianceInfoResponse.model_validate(GOLDEN_AIN).members[0]
        assert leader.emblem is not None
        assert (leader.emblem.background_type, leader.emblem.symbol1, leader.emblem.is_set) == (1, 4, True)

    def test_an_emblem_that_is_not_an_object_reads_as_none(self):
        assert AllianceMember.model_validate({"OID": 1, "E": 7}).emblem is None


class TestGoldenCastlePayloads:
    def test_gcl_rows_are_flattened_across_kingdoms(self):
        response = GetCastlesResponse.model_validate(GOLDEN_GCL)
        assert response.player_id == 17743260
        assert [(c.castle_id, c.castle_name, c.x, c.y, c.kingdom_id, c.castle_type) for c in response.castles] == [
            (16654596, "Château Heimlin", 632, 243, 0, 1),
            (16656989, "OP1", 630, 244, 0, 4),
            (16700000, "Sands", 100, 200, 2, 12),
        ]
        assert response.castles[0].owner_id == 17743260
        assert response.castles[2].position.kingdom == 2
        main, outpost = response.castles[0], response.castles[1]
        assert (main.keep_level, main.wall_level, main.gate_level, main.tower_level, main.moat_level) == (1, 1, 1, 0, 0)
        assert (main.abandon_outpost_seconds, main.no_abandon_seconds, main.open_gate_seconds) == (-1, -1, 0)
        assert (outpost.no_abandon_seconds, outpost.abandon_outpost_seconds) == (0, -1)
        assert outpost.occupier_id == -1

    def test_gcl_without_a_castle_section_is_empty(self):
        assert GetCastlesResponse.model_validate({"PID": 1}).castles == []

    def test_gcl_skips_rows_too_short_to_name_a_castle(self):
        payload = {
            "C": [{"KID": 0, "AI": [{"AI": [1, 2, 3]}, "junk", {"AI": gdi_location_row(1, 1, 1, 5, 9, "ok", 0)}]}]
        }
        assert [c.castle_id for c in GetCastlesResponse.model_validate(payload).castles] == [5]

    def test_registry_parses_dcl(self):
        assert isinstance(parse_response("dcl", GOLDEN_DCL), GetDetailedCastleResponse)

    def test_dcl_lists_every_castle_with_resources_and_units(self):
        response = GetDetailedCastleResponse.model_validate(GOLDEN_DCL)
        assert response.player_id == 17743260
        assert [c.castle_id for c in response.castles] == [16654596, 16656989]
        main = response.castles[0]
        assert main.kingdom_id == 0
        # Fractional amounts are truncated, not rejected.
        assert (main.wood, main.stone, main.food) == (7000, 6999, 7000)
        assert (main.coal, main.glass, main.honey, main.aquamarine) == (12, 3, 40, 0)
        assert main.defense_value == 57
        assert (main.has_barracks, main.has_siege_workshop, main.has_defense_workshop, main.has_hospital) == (
            True,
            True,
            True,
            True,
        )
        assert main.market_carriages == 5
        assert (main.open_gate_seconds, main.abandon_outpost_seconds) == (0, -1)
        assert main.units == {656: 1, 650: 213}
        assert main.hospital_units == {11: 5, 12: 15}
        assert main.travelling_units == {620: 3}
        assert main.stronghold_units == {}

    def test_dcl_production_area(self):
        gpa = GetDetailedCastleResponse.model_validate(GOLDEN_DCL).castles[0].production_area
        assert gpa is not None
        assert (gpa.population, gpa.neutral_deco_points, gpa.sickness, gpa.riot, gpa.guards) == (80, 11927, 0, 5, 5)
        assert (gpa.build_speed_percent, gpa.morale, gpa.unit_capacity) == (125, 0, 0)
        # The client divides the D<key> deltas by ten to get an hourly rate.
        assert (gpa.production.wood, gpa.production.stone, gpa.production.food) == (223.9, 195.2, 350.2)
        assert gpa.production.honey == 1.5
        assert (gpa.storage_capacity.wood, gpa.storage_capacity.aquamarine, gpa.storage_capacity.coal) == (
            7000,
            51000,
            0,
        )
        assert (gpa.production_bonus_percent.wood, gpa.production_bonus_percent.coal) == (110.0, 0.0)
        assert (gpa.safe_amount.wood, gpa.safe_amount.stone) == (1000, 0)
        assert (gpa.food_consumption_per_hour, gpa.food_consumption_reduction_percent) == (9.0, 100)
        assert (gpa.barracks_speed, gpa.workshop_speed, gpa.defense_workshop_speed, gpa.hospital_speed) == (
            328.0,
            318.0,
            318.0,
            318.0,
        )

    def test_dcl_castle_without_gpa(self):
        castle = GetDetailedCastleResponse.model_validate(GOLDEN_DCL).castles[1]
        assert castle.production_area is None
        assert castle.has_barracks is False

    def test_dcl_castle_lookup_by_id(self):
        response = GetDetailedCastleResponse.model_validate(GOLDEN_DCL)
        outpost = response.castle(16656989)
        assert outpost is not None
        assert outpost.units == {649: 18}
        assert response.castle(1) is None


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
        tower = gdi_location_row(1, 50, 60, 888, 4242, "Tower", 0)
        tower[0] = 23
        response = GetPlayerInfoResponse.model_validate(
            {
                "gcl": {"C": [{"KID": 0, "AI": [{"AI": gdi_location_row(1, 640, 655, 12345, 4242, "Main", 0)}]}]},
                "gkl": {"AI": [[tower]]},
                "gml": {"AI": []},
            }
        )
        assert [c.castle_id for c in response.get_castles()] == [12345, 888]

    def test_a_gcl_row_in_an_extra_list_is_not_unwrapped(self):
        wrapped = {"AI": [gdi_location_row(1, 640, 655, 12345, 4242, "Main", 0)]}
        response = GetPlayerInfoResponse.model_validate({"gcl": {"C": [{"KID": 0, "AI": [wrapped]}]}})
        assert response.get_castles() == []


class TestGoldenSupportDefense:
    def test_registry_parses_sdi(self):
        assert isinstance(parse_response("sdi", GOLDEN_SDI), GetSupportDefenseResponse)

    def test_total_defenders_sums_every_position(self):
        response = GetSupportDefenseResponse.model_validate(GOLDEN_SDI)
        assert response.get_total_defenders() == 5174 + 20 + 347 + 10

    def test_units_are_grouped_per_position(self):
        response = GetSupportDefenseResponse.model_validate(GOLDEN_SDI)
        assert response.get_units_by_position() == [{487: 5174, 488: 20}, {487: 347}, {}, {301: 10}, {}, {}]

    def test_capacity_fields(self):
        response = GetSupportDefenseResponse.model_validate(GOLDEN_SDI)
        assert (response.yard_limit, response.available_yard_limit, response.wall_limit) == (12000, 3000, 5000)
        assert response.get_max_defense() == 12000

    def test_empty_defense_is_zero_not_an_error(self):
        response = GetSupportDefenseResponse.model_validate({"SCID": 1})
        assert response.get_total_defenders() == 0
        assert response.get_units_by_position() == []


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


class TestGoldenChatPayloads:
    def test_incoming_message_decodes(self):
        payload = {"CM": {"PN": "LeaderGuy", "MT": "100&percnt; ready, said &quot;go&quot;", "PID": 7001}}
        response = AllianceChatMessageResponse.model_validate(payload)
        assert response.player_name == "LeaderGuy"
        assert response.player_id == 7001
        assert response.decoded_text == '100% ready, said "go"'
        assert response.message_text.startswith("100&percnt;")

    def test_missing_chat_block_yields_empty_accessors(self):
        response = AllianceChatMessageResponse.model_validate({})
        assert (response.player_name, response.message_text, response.decoded_text) == ("", "", "")
        assert response.player_id == 0

    def test_chat_log_entries_decode(self):
        payload = {
            "CL": [
                {"PN": "LeaderGuy", "MT": "line&145;s one", "PID": 7001, "T": 1712345678},
                {"PN": "OfficerGal", "MT": "two<br />lines", "PID": 7002},
            ]
        }
        response = AllianceChatLogResponse.model_validate(payload)
        assert [e.decoded_text for e in response.chat_log] == ["line's one", "two\nlines"]
        assert response.chat_log[1].timestamp is None


class TestGoldenRankingPayloads:
    def test_dict_details_layout(self):
        payload = {"L": [[1, 999999, {"OID": 7001, "N": "LeaderGuy", "AID": 190426, "AN": "HOPE"}]]}
        entry = GetHighscoreResponse.model_validate(payload).entries[0]
        assert (entry.rank, entry.score, entry.entity_id, entry.name) == (1, 999999, 7001, "LeaderGuy")
        assert (entry.alliance_id, entry.alliance_name) == (190426, "HOPE")

    def test_list_details_layout(self):
        payload = {"L": [[2, 888888, [7002, "OfficerGal"]]]}
        entry = GetHighscoreResponse.model_validate(payload).entries[0]
        assert (entry.rank, entry.score, entry.entity_id, entry.name) == (2, 888888, 7002, "OfficerGal")

    def test_nested_name_field_is_flattened(self):
        payload = {"L": [[2, 888888, [7002, ["OfficerGal"]]]]}
        assert GetHighscoreResponse.model_validate(payload).entries[0].name == "OfficerGal"

    def test_cargo_layout_has_a_leading_extra_value(self):
        # LT=13 prepends the cargo value: [cargo, rank, score, {details}].
        payload = {"L": [[5000, 3, 777777, {"OID": 7003, "N": "AfkDude"}]]}
        entry = GetHighscoreResponse.model_validate(payload).entries[0]
        assert (entry.rank, entry.score, entry.entity_id, entry.name) == (3, 777777, 7003, "AfkDude")

    def test_flat_layout(self):
        payload = {"L": [[4, 666, 7004, "FlatGuy"]]}
        entry = GetHighscoreResponse.model_validate(payload).entries[0]
        assert (entry.rank, entry.score, entry.entity_id, entry.name) == (4, 666, 7004, "FlatGuy")

    def test_ranking_list_dict_layout(self):
        payload = {"L": [{"R": 3, "S": 500, "P": "SomePlayer", "A": "SomeAlliance"}], "T": 12345}
        response = GetRankingListResponse.model_validate(payload)
        assert response.total == 12345
        entry = response.entries[0]
        assert (entry.rank, entry.score, entry.name, entry.alliance_name) == (3, 500, "SomePlayer", "SomeAlliance")

    def test_unranked_synthetic_entry(self):
        entry = RankingEntry.unranked("Nobody")
        assert (entry.rank, entry.score, entry.name) == (-1, 0, "Nobody")


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

    @pytest.mark.parametrize("data", [[], [1], [1, 2], [1, 2, 3], [1, 2, 3, 4]])
    def test_map_area_item_tolerates_short_arrays(self, data):
        item = MapAreaItem.from_list(data)
        assert item.raw_data == data
        assert item.is_relocating is False

    def test_map_area_item_defaults_for_an_empty_array(self):
        item = MapAreaItem.from_list([])
        assert (item.item_type, item.x, item.y, item.owner_id) == (0, 0, 0, -1)
        assert item.player_id == -1
        assert item.type_name == "EMPTY"

    @pytest.mark.parametrize(
        "item_type",
        [
            MapItemType.CASTLE,
            MapItemType.CAPITAL,
            MapItemType.OUTPOST,
            MapItemType.VILLAGE,
            MapItemType.KINGDOM_CASTLE,
            MapItemType.METRO,
            MapItemType.KINGS_TOWER,
            MapItemType.MONUMENT,
            MapItemType.LABORATORY,
        ],
    )
    def test_map_area_item_owner_is_field_four_for_every_owned_type(self, item_type):
        item = MapAreaItem.from_list([item_type, 1, 2, 900, 4242])
        assert (item.location_id, item.owner_id, item.player_id) == (900, 4242, 4242)
        assert item.has_owner_field

    @pytest.mark.parametrize(
        "item_type", [MapItemType.FACTION_VILLAGE, MapItemType.FACTION_TOWER, MapItemType.FACTION_CAPITAL]
    )
    def test_map_area_item_faction_landmark_owner_is_field_three(self, item_type):
        item = MapAreaItem.from_list([item_type, 1, 2, 4242, [], -1, 3])
        assert (item.owner_id, item.location_id) == (4242, -1)
        assert item.has_owner_field

    def test_map_area_item_empty_castle_slot_has_no_owner(self):
        # A free plot comes as a four-field row: [1, x, y, -1].
        item = MapAreaItem.from_list([MapItemType.CASTLE, 632, 204, -1])
        assert (item.location_id, item.owner_id) == (-1, -1)

    def test_map_area_item_unclaimed_outpost_has_no_owner(self):
        # The client's OUTPOST_DEFAULT_OWNER_ID and OUTPOST_DEFAULT_AREA_ID are -300.
        unclaimed = MapAreaItem.from_list([MapItemType.OUTPOST, 630, 205, 14824223, -300, 1, 1, 1, 0, 0, ""])
        assert (unclaimed.location_id, unclaimed.owner_id) == (14824223, -1)
        bare = MapAreaItem.from_list([MapItemType.OUTPOST, 630, 180, -300, -300, 0, 0, 0, 0, 0, ""])
        assert (bare.location_id, bare.owner_id) == (-1, -1)

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
        assert (item.owner_id, item.location_id) == (-1, -1)
        assert not item.has_owner_field

    def test_map_area_item_unknown_type_name_is_labeled(self):
        assert MapAreaItem.from_list([9999, 1, 2, 3]).type_name == "UNKNOWN_9999"

    @pytest.mark.parametrize("data", [["?", "?", "?", "?"], [1, [2], 3, 4], [1, None, 2, 3]])
    def test_map_area_item_rejects_wrong_types_as_validation_errors(self, data):
        # The map scanner relies on this being a ValidationError to skip the
        # row and carry on with the chunk.
        with pytest.raises(ValidationError):
            MapAreaItem.from_list(data)

    @pytest.mark.parametrize("data", [[], [[]], [0], [0, 1], [0, 1, 2], ["a", "b", "c", "d", "e"], "abcde"])
    def test_castle_position_rows_that_do_not_fit_are_skipped(self, data):
        member = AllianceMember.model_validate({"OID": 1, "AP": [data, [0, 12345, 640, 655, 1]]})
        assert [(c.area_id, c.area_type) for c in member.castle_positions] == [(12345, 1)]

    def test_a_castle_position_without_its_area_type_is_kept(self):
        # MinWorldMapCastleInfoVO.fillFromParamObject reads row[4] raw, so a four-field row still counts
        member = AllianceMember.model_validate({"OID": 1, "AP": [[0, 12345, 640, 655]]})
        assert [(c.area_id, c.area_type) for c in member.castle_positions] == [(12345, 0)]

    def test_castle_positions_unwrap_a_doubly_nested_entry(self):
        member = AllianceMember.model_validate(
            {"OID": 1, "AP": [[[0, 12345, 640, 655, 1]]], "VP": [[[0, 6, 3, 4, 10]]]}
        )
        assert [(c.kingdom_id, c.area_id, c.x, c.y, c.area_type) for c in member.castle_positions] == [
            (0, 12345, 640, 655, 1)
        ]
        assert [c.area_type for c in member.village_positions] == [10]

    @pytest.mark.parametrize("data", [[], [1], [1, 2], [1, 2, 3]])
    def test_player_castle_short_array_yields_defaults(self, data):
        castle = PlayerCastle.from_list(data, kingdom=2)
        assert castle.kingdom == 2
        assert (castle.x, castle.y, castle.location_id) == (0, 0, 0)

    def test_player_castle_keeps_the_passed_kingdom_when_the_row_is_short(self):
        row = [1, 640, 655, 12345, 4242]
        assert PlayerCastle.from_list(row, kingdom=3).kingdom == 3

    def test_player_castle_row_kingdom_wins_when_present(self):
        row = gdi_location_row(1, 640, 655, 12345, 4242, "Main", 4)
        assert PlayerCastle.from_list(row, kingdom=0).kingdom == 4

    @pytest.mark.parametrize("data", [[1, "x", 3, 4], "abcd", [1, 2, 3, [4]]])
    def test_player_castle_rejects_wrong_types(self, data):
        with pytest.raises(ValidationError):
            PlayerCastle.from_list(data)

    @pytest.mark.parametrize("data", [[], [1], [1, 2], [1, 2, "nope"], [1, 2, []], [1, 2, {}]])
    def test_alliance_search_result_without_an_alliance_row_has_defaults(self, data):
        result = AllianceSearchResult.model_validate(data)
        assert (result.alliance_id, result.name, result.member_count) == (0, "", 0)

    def test_alliance_search_result_reads_numbers_like_the_client(self):
        result = AllianceSearchResult.model_validate(["3", 2.0, ["x", 7, "12", None]])
        assert (result.rank, result.score, result.alliance_id, result.name, result.member_count) == (3, 2, 0, "7", 12)
        assert result.fame_points == 0


class TestRankingEntryDriftedLayouts:
    """RankingEntry parses four different shapes and must never raise."""

    @pytest.mark.parametrize(
        "raw",
        [
            {},
            [],
            [1],
            [1, 2],
            None,
            "abcd",
            [1, 2, None],
            [None, None, {}],
            [1, 2, {"unexpected": "keys"}],
            [[1, 2], [3, 4]],
        ],
    )
    def test_drifted_entries_never_raise(self, raw):
        entry = RankingEntry(raw)
        assert entry.raw is raw
        assert repr(entry)

    @pytest.mark.parametrize("raw", [[], [1, 2]])
    def test_unknown_layout_is_logged_and_left_unranked(self, raw, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.protocol.models.ranking"):
            entry = RankingEntry(raw)
        assert entry.rank == -1
        assert "Unknown RankingEntry format" in caplog.text

    def test_a_layout_that_raises_internally_is_logged_as_an_error(self, caplog):
        with caplog.at_level(logging.ERROR, logger="empire_core.protocol.models.ranking"):
            # Deliberately not a list/dict: the point of the test is that an
            # unparseable layout degrades to rank -1 rather than raising.
            entry = RankingEntry(None)  # type: ignore[arg-type]
        assert entry.rank == -1
        assert "Failed to parse RankingEntry" in caplog.text


class TestMalformedNestedResponsePayloads:
    """One bad element inside a keyed batch, as the server would send it."""

    def test_chat_message_missing_the_player_id_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            AllianceChatMessageResponse.model_validate({"CM": {"PN": "a", "MT": "b"}})

    def test_chat_message_with_a_non_dict_block_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            AllianceChatMessageResponse.model_validate({"CM": "junk"})

    def test_one_bad_chat_log_entry_discards_the_history(self):
        payload = {"CL": [{"PN": "a", "MT": "b", "PID": 1}, {"PN": "c", "MT": "d"}]}
        with pytest.raises(ValidationError):
            AllianceChatLogResponse.model_validate(payload)

    def test_non_dict_alliance_member_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            AllianceInfo.model_validate({"AID": 1, "M": ["junk"]})

    def test_drifted_unit_array_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            GetDetailedCastleResponse.model_validate({"C": [{"AI": [{"AID": 1, "AC": "junk"}]}]})
        with pytest.raises(ValidationError):
            GetDetailedCastleResponse.model_validate({"C": [{"AI": [{"AID": 1, "AC": [[201, "x"]]}]}]})

    def test_dcl_castle_without_an_id_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            GetDetailedCastleResponse.model_validate({"C": [{"AI": [{"W": 1.0}]}]})

    def test_drifted_defense_array_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            GetSupportDefenseResponse.model_validate({"SCID": 1, "S": "nope"})

    def test_a_missing_alliance_block_is_not_an_error(self):
        response = GetAllianceInfoResponse.model_validate({"A": None})
        assert response.members == []
        assert response.online_members == []

    def test_drifted_map_row_is_skipped_and_counted_at_parse_time(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.protocol.models.map"):
            response = GetMapAreaResponse.model_validate({"KID": 1, "AI": [["?", "?", "?", "?"]]})
        assert response.kingdom == Kingdom.SANDS
        assert response.items == []
        assert response.get_moving_flags() == {}
        assert "Skipped 1/1" in caplog.text
        assert "kingdom 1" in caplog.text

    def test_map_rows_survive_a_drifted_neighbour(self, caplog):
        good_row = [1, 640, 655, 900, 4242]
        with caplog.at_level(logging.WARNING, logger="empire_core.protocol.models.map"):
            response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [["?", "?", "?", "?"], good_row, "junk"]})
        assert [(i.x, i.y, i.owner_id) for i in response.items] == [(640, 655, 4242)]
        assert response.items[0].raw_data == good_row
        assert "Skipped 1/3" in caplog.text

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
        with caplog.at_level(logging.WARNING, logger="empire_core.protocol.models.castle"):
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
        with caplog.at_level(logging.WARNING, logger="empire_core.protocol.models.defense"):
            assert response.get_total_defenders() == 100
            assert response.get_units_by_position() == [{487: 100}]
        assert not [r for r in caplog.records if r.levelno == logging.WARNING]


class TestRenameCastle:
    def test_a_rename_sends_p_1(self):
        request = RenameCastleRequest(CID=1, N="Keep", AT=1, KID=2)
        assert request.to_payload() == {"CID": 1, "N": "Keep", "AT": 1, "KID": 2, "P": 1}

    def test_the_reply_reads_p(self):
        assert RenameCastleResponse.model_validate({"CID": 1, "KID": 2, "P": 0}).is_rename == 0


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

    def test_an_unhashable_area_type_costs_only_its_row(self):
        from empire_core.protocol.models import GetMapAreaResponse

        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [[[1], 2, 3, 4], [2, 5, 6, -1, 0, 0, 0]]})
        assert [item.item_type for item in response.items] == [2]

    def test_a_gcl_row_that_cannot_be_read_costs_only_itself(self):
        from empire_core.protocol.models import GetCastlesResponse

        bad = [3, 10, 20, 99, 5, None, None, None, None, None, None, 0, 0, 0, 77, 0, 0]
        good = [1, 30, 40, 100, 5, 1, 1, 1, 1, 1, "Home", 0, 0, 0, 77, 0, 0]
        response = GetCastlesResponse.model_validate({"C": [{"KID": 0, "AI": [{"AI": bad}, {"AI": good}]}]})
        assert [castle.castle_id for castle in response.castles] == [100]


class TestLeaderboardLeniency:
    def test_null_and_odd_values_read_as_the_getter_defaults(self):
        from empire_core.protocol.models import GetRankingListResponse

        response = GetRankingListResponse.model_validate(
            {"L": [{"R": 1, "S": 10, "P": "a", "A": None}, {"R": None, "S": None, "P": None, "I": "abc"}]}
        )
        first, second = response.scores
        assert (first.rank, first.alliance_name) == (1, "")
        assert (second.rank, second.score, second.player_name, second.instance_id) == (-1, -1, "", 0)


class TestRelicInfo:
    # A captured relic row: index 12 is [relic_type_id, relic_category_id, might, gem]
    RELIC = [
        6109572530, 1, 2, 5, -1,
        [[4, 84, [116.2]], [5, 61, [75.1]], [103, 53, [11.7]]],
        -1, -1, 0, -1, -1, 3,
        [1, 6, 2980, [890593, 32, 6, 2770, [[302, 61, [34.7]], [305, 62, [10.0]], [307, 54, [4.6]]], 0]],
    ]  # fmt: skip

    def test_a_relic_carries_its_type_might_and_gem(self):
        from empire_core.protocol.models.commanders import Equipment

        item = Equipment.model_validate(self.RELIC)
        assert item.is_relic and len(item.relic_bonuses) == 3
        info = item.relic_info
        assert info is not None and (info.relic_type_id, info.relic_category_id, info.might) == (1, 6, 2980)
        assert info.gem is not None
        assert (info.gem.gem_id, info.gem.relic_type_id, info.gem.might, info.gem.enchantment_level) == (
            890593, 32, 2770, 0,
        )  # fmt: skip
        assert [b.relic_effect_id for b in info.gem.bonuses] == [302, 305, 307]

    def test_no_gem_and_ordinary_items(self):
        from empire_core.protocol.models.commanders import Equipment

        assert Equipment.model_validate([*self.RELIC[:12], [1, 6, 2980, []]]).relic_info.gem is None  # type: ignore[union-attr]
        assert Equipment.model_validate([*self.RELIC[:12], "junk"]).relic_info is None
        ordinary = [*self.RELIC[:11], 0, [1, 6, 2980, []]]
        assert Equipment.model_validate(ordinary).relic_info is None


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


class TestAllianceInfoFlags:
    def test_settings_read_as_alliance_info_vo_does(self):
        from empire_core.protocol.models.alliance import AllianceInfo

        info = AllianceInfo.model_validate(
            {
                "CF": "1200",
                "HF": 3000,
                "IS": 1,
                "IA": 0,
                "KA": 1,
                "AW": 1,
                "HP": 0,
                "SP": 1,
                "AA": 3,
                "AP": 12.5,
                "A": None,
            }
        )
        assert (info.fame_points, info.highest_fame_points, info.application_count, info.aqua_points) == (
            1200,
            3000,
            3,
            12.5,
        )
        assert (info.is_searching_members, info.is_accepting_members, info.is_king_alliance, info.auto_war) == (
            True, False, True, True,
        )  # fmt: skip
        assert (info.can_be_invited_to_hard_pact, info.can_be_invited_to_soft_pact, info.announcement) == (
            False,
            True,
            " ",
        )


class TestAllianceInfoText:
    def test_description_and_announcement_read_as_chat_text(self):
        from empire_core.protocol.models.alliance import AllianceInfo

        info = AllianceInfo.model_validate({"D": "Say &quot;hi&quot;<br />now", "A": "", "RT": "30"})
        assert info.description == 'Say "hi"\nnow'
        assert info.announcement == " "
        # parseChatJSONMessage: &percnt; before %5C, and brackets become spaces
        assert AllianceInfo.model_validate({"D": "[TAG] 100&percnt;5C"}).description == " TAG  100\\"
        assert AllianceInfo.model_validate({}).announcement == " "
        assert info.refresh_seconds == 30

    def test_forge_fields_are_read_only_with_mf_and_if(self):
        from empire_core.protocol.models.alliance import AllianceInfo

        assert AllianceInfo.model_validate({"MF": 1, "SRFU": 4}).soft_relic_forge_uses == 0
        both = AllianceInfo.model_validate({"MF": 1, "IF": 0, "SRFU": 4})
        assert (both.is_able_to_forge, both.soft_relic_forge_uses) == (True, 4)
