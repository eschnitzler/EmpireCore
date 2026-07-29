"""Tests for the protocol model registry and base behaviors."""

import logging

import pytest
from pydantic import Field, ValidationError

from empire_core.protocol.models import parse_response
from empire_core.protocol.models.alliance import (
    AllianceInfo,
    AllianceSearchResult,
    GetAllianceInfoResponse,
    MemberCastle,
)
from empire_core.protocol.models.base import (
    BaseResponse,
    decode_chat_text,
    encode_chat_text,
    get_response_model,
)
from empire_core.protocol.models.castle import GetCastlesResponse, GetDetailedCastleResponse
from empire_core.protocol.models.chat import AllianceChatLogResponse, AllianceChatMessageResponse
from empire_core.protocol.models.defense import GetSupportDefenseResponse
from empire_core.protocol.models.map import (
    GetMapAreaResponse,
    GetMovementsResponse,
    Kingdom,
    MapAreaItem,
    MapItemType,
)
from empire_core.protocol.models.player import GetPlayerInfoResponse, PlayerCastle
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
        "N": "Knights of HOPE",
        "A": "HOPE",
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
    "C": {
        "CID": 12345,
        "CN": "Main Castle",
        "X": 640,
        "Y": 655,
        "KID": 0,
        "L": 70,
        "B": [
            {"BID": 1, "BT": 12, "L": 5, "X": 3, "Y": 4, "S": 0, "H": 100},
            {"BID": 2, "BT": 40, "L": 1, "X": 8, "Y": 9, "S": 2, "H": 40},
        ],
        "R": {"W": 100000, "S": 90000, "F": 5000, "C": 12345, "R": 300},
        "P": 1200,
        "MP": 1500,
        "AC": [[201, 5], [305, 2], [999]],
    }
}

GOLDEN_GDI = {
    "O": {
        "OID": 4242,
        "N": "TargetPlayer",
        "L": 70,
        "LL": 500,
        "AID": 190426,
        "AN": "Knights of HOPE",
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
                    {"AI": [gdi_location_row(1, 640, 655, 12345, 4242, "Main Castle", 0)]},
                    {"AI": [gdi_location_row(4, 700, 700, 55555, 4242, "Outpost North", 0, capturer_outpost=9999)]},
                ],
            },
            {
                "KID": 2,
                "AI": [{"AI": [gdi_location_row(3, 300, 400, 77777, 4242, "Ice Capital", 2, capturer_capital=8888)]}],
            },
        ],
    },
}

GOLDEN_SDI = {
    "SCID": 12345,
    # Six defence positions, each a list of [unit_id, count] pairs.
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
        assert info.name == "Knights of HOPE"
        assert info.abbreviation == "HOPE"
        assert info.might == 4213377
        assert info.member_limit == 50
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
        assert [(c.kingdom, c.area_id, c.x, c.y, c.castle_type) for c in leader.castles] == [
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
        assert (leader.emblem.background_type, leader.emblem.symbol1, leader.emblem.icon_style) == (1, 4, 1)


class TestGoldenCastlePayloads:
    def test_gcl_list_parses(self):
        payload = {
            "C": [
                {"CID": 12345, "CN": "Main Castle", "X": 640, "Y": 655, "KID": 0, "CT": 0, "L": 70},
                {"CID": 55555, "CN": "Outpost North", "X": 700, "Y": 700, "KID": 0, "CT": 1, "L": 12},
            ]
        }
        response = GetCastlesResponse.model_validate(payload)
        assert [(c.castle_id, c.castle_name) for c in response.castles] == [
            (12345, "Main Castle"),
            (55555, "Outpost North"),
        ]
        assert response.castles[0].position.kingdom == 0

    def test_registry_parses_dcl(self):
        assert isinstance(parse_response("dcl", GOLDEN_DCL), GetDetailedCastleResponse)

    def test_dcl_buildings_and_resources(self):
        castle = GetDetailedCastleResponse.model_validate(GOLDEN_DCL).castle
        assert castle is not None
        assert castle.castle_name == "Main Castle"
        assert [(b.building_id, b.building_type, b.level) for b in castle.buildings] == [(1, 12, 5), (2, 40, 1)]
        assert castle.buildings[1].status == 2
        assert castle.buildings[1].health == 40
        assert castle.resources is not None
        assert castle.resources.coins == 12345
        assert (castle.population, castle.max_population) == (1200, 1500)

    def test_dcl_item_array_skips_short_rows(self):
        castle = GetDetailedCastleResponse.model_validate(GOLDEN_DCL).castle
        assert castle is not None
        assert castle.items == {201: 5, 305: 2}


class TestGoldenPlayerInfo:
    def test_registry_parses_gdi(self):
        assert isinstance(parse_response("gdi", GOLDEN_GDI), GetPlayerInfoResponse)

    def test_owner_fields_are_exposed_through_the_response(self):
        response = GetPlayerInfoResponse.model_validate(GOLDEN_GDI)
        assert response.player_id == 4242
        assert response.player_name == "TargetPlayer"
        assert response.alliance_id == 190426
        assert response.alliance_name == "Knights of HOPE"
        assert response.has_bird is True
        assert response.bird_end_time is not None

    def test_castles_are_flattened_across_kingdoms(self):
        castles = GetPlayerInfoResponse.model_validate(GOLDEN_GDI).get_castles()
        assert [(c.name, c.kingdom, c.x, c.y, c.castle_type) for c in castles] == [
            ("Main Castle", 0, 640, 655, 1),
            ("Outpost North", 0, 700, 700, 4),
            ("Ice Capital", 2, 300, 400, 3),
        ]

    def test_castle_type_names_are_resolved(self):
        castles = GetPlayerInfoResponse.model_validate(GOLDEN_GDI).get_castles()
        assert [c.castle_type_name for c in castles] == ["Castle", "Outpost", "Capital"]

    def test_capturer_id_is_read_from_the_type_specific_index(self):
        # Outposts carry it at index 15, capitals at index 14 - reading the
        # wrong one reports a capture that is not happening (or misses one).
        castles = {c.name: c for c in GetPlayerInfoResponse.model_validate(GOLDEN_GDI).get_castles()}
        assert castles["Main Castle"].is_being_captured is False
        assert castles["Outpost North"].capturer_id == 9999
        assert castles["Ice Capital"].capturer_id == 8888

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

    def test_empty_defence_is_zero_not_an_error(self):
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
            "OI": [{"OID": 900, "X": 640, "Y": 655, "PN": "TargetPlayer", "AN": "HOPE", "L": 70}],
        }
        response = GetMapAreaResponse.model_validate(payload)
        assert [(i.x, i.y, i.item_type) for i in response.items] == [(640, 655, int(MapItemType.CASTLE))]
        assert response.items[0].player_id == 4242
        assert response.objects[0].resolved_owner_name == "TargetPlayer"
        assert response.objects[0].resolved_owner_id == 900

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

GOOD_MOVEMENT = {"MID": 1, "MT": 1, "SX": 1, "SY": 2, "TX": 3, "TY": 4, "ST": 100, "AT": 200}


class TestMalformedMovementBatch:
    """A gam batch is all-or-nothing today; that is worth knowing about."""

    def test_one_entry_missing_a_required_field_discards_the_batch(self):
        broken = {key: value for key, value in GOOD_MOVEMENT.items() if key != "MID"}
        with pytest.raises(ValidationError) as exc_info:
            GetMovementsResponse.model_validate({"M": [GOOD_MOVEMENT, broken]})
        # The error names the offending index and field, which is what makes a
        # drift diagnosable from a log line.
        assert "MID" in str(exc_info.value)

    def test_non_dict_entry_discards_the_batch(self):
        with pytest.raises(ValidationError):
            GetMovementsResponse.model_validate({"M": [GOOD_MOVEMENT, "junk"]})

    def test_movement_list_of_the_wrong_type_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            GetMovementsResponse.model_validate({"M": "junk"})

    def test_a_clean_batch_still_parses(self):
        response = GetMovementsResponse.model_validate({"M": [GOOD_MOVEMENT]})
        assert response.movements[0].movement_id == 1
        assert response.movements[0].source_position.x == 1
        assert response.movements[0].target_position.y == 4

    def test_numeric_strings_are_coerced_rather_than_rejected(self):
        # GGE has sent numbers as strings before; lax coercion is what keeps a
        # whole batch from vanishing when it happens.
        coerced = {**GOOD_MOVEMENT, "MID": "7"}
        assert GetMovementsResponse.model_validate({"M": [coerced]}).movements[0].movement_id == 7


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

    def test_map_area_item_owner_index_depends_on_the_type(self):
        # Type 1 reports the castle id (field 3); capital-likes report the
        # player id (field 4).
        assert MapAreaItem.from_list([MapItemType.CASTLE, 1, 2, 900, 4242]).owner_id == 900
        assert MapAreaItem.from_list([MapItemType.CAPITAL, 1, 2, 900, 4242]).owner_id == 4242

    def test_map_area_item_unknown_type_name_is_labelled(self):
        assert MapAreaItem.from_list([9999, 1, 2, 3]).type_name == "UNKNOWN_9999"

    @pytest.mark.parametrize("data", [["?", "?", "?", "?"], [1, [2], 3, 4], [1, None, 2, 3]])
    def test_map_area_item_rejects_wrong_types_as_validation_errors(self, data):
        # The map scanner relies on this being a ValidationError to skip the
        # row and carry on with the chunk.
        with pytest.raises(ValidationError):
            MapAreaItem.from_list(data)

    @pytest.mark.parametrize("data", [[], [[]], [0], [0, 1], [0, 1, 2], [0, 1, 2, 3]])
    def test_member_castle_tolerates_short_arrays(self, data):
        castle = MemberCastle.from_list(data)
        # A missing type field means "unknown", not "main castle".
        assert castle.castle_type == 0

    def test_member_castle_unwraps_a_doubly_nested_entry(self):
        castle = MemberCastle.from_list([[0, 12345, 640, 655, 1]])
        assert (castle.kingdom, castle.area_id, castle.x, castle.y, castle.castle_type) == (0, 12345, 640, 655, 1)

    @pytest.mark.parametrize("data", [["a", "b", "c", "d", "e"], "abcde"])
    def test_member_castle_rejects_wrong_types(self, data):
        with pytest.raises(ValidationError):
            MemberCastle.from_list(data)

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
    def test_alliance_search_result_degrades_to_unknown(self, data):
        result = AllianceSearchResult.from_list(data)
        assert result.name == "Unknown" or result.alliance_id == 0

    def test_alliance_search_result_rejects_a_non_numeric_id(self):
        with pytest.raises(ValidationError):
            AllianceSearchResult.from_list([1, 2, ["x", "y"]])


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
            entry = RankingEntry(None)
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

    def test_one_bad_building_discards_the_castle(self):
        payload = {"C": {"CID": 1, "B": [{"BID": 1}, {"BID": "not-an-int"}]}}
        with pytest.raises(ValidationError):
            GetDetailedCastleResponse.model_validate(payload)

    def test_drifted_item_array_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            GetDetailedCastleResponse.model_validate({"C": {"CID": 1, "AC": "junk"}})
        with pytest.raises(ValidationError):
            GetDetailedCastleResponse.model_validate({"C": {"CID": 1, "AC": [[201, "x"]]}})

    def test_drifted_defence_array_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            GetSupportDefenseResponse.model_validate({"SCID": 1, "S": "nope"})

    def test_a_missing_alliance_block_is_not_an_error(self):
        response = GetAllianceInfoResponse.model_validate({"A": None})
        assert response.members == []
        assert response.online_members == []

    def test_drifted_map_row_breaks_only_the_item_accessor(self):
        # The payload itself parses; the raw AI rows are validated lazily, so a
        # drifted row surfaces when .items / .get_moving_flags() is read.
        response = GetMapAreaResponse.model_validate({"KID": 0, "AI": [["?", "?", "?", "?"]]})
        assert response.kingdom == Kingdom.GREEN
        with pytest.raises(ValidationError):
            response.get_moving_flags()


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

    def test_drifted_kingdom_entry_is_skipped_rather_than_crashing(self):
        response = GetPlayerInfoResponse.model_validate(
            {
                "gcl": {
                    "C": [
                        {"KID": 0, "AI": [{"AI": [gdi_location_row(1, 1, 2, 3, 4, "Keep", 0)]}]},
                        "unexpected-string-entry",
                    ]
                }
            }
        )
        assert [c.name for c in response.get_castles()] == ["Keep"]

    def test_string_unit_count_does_not_crash_the_defence_total(self):
        response = GetSupportDefenseResponse.model_validate({"SCID": 1, "S": [[[487, 100]], [[488, "20"]]]})
        assert response.get_total_defenders() >= 100

    def test_string_unit_count_does_not_crash_the_per_position_grouping(self):
        response = GetSupportDefenseResponse.model_validate({"SCID": 1, "S": [[[488, "20"]]]})
        assert response.get_units_by_position() == [{488: 20}]

    def test_defence_rows_of_the_wrong_shape_are_already_skipped(self):
        response = GetSupportDefenseResponse.model_validate({"SCID": 1, "S": [[[487]], ["junk"], [[487, 5]]]})
        assert response.get_total_defenders() == 5
