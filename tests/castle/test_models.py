"""Tests for the castle models."""

from empire_core.castle.models.actions import RenameCastleRequest, RenameCastleResponse
from empire_core.castle.models.castles import GetCastlesResponse
from empire_core.castle.models.details import GetDetailedCastleResponse
from empire_core.enums import Kingdom, MapItemType
from empire_core.protocol.models import parse_response
from tests.model_helpers import gdi_location_row

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

    def test_gcl_skips_rows_too_short_for_their_type(self):
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


class TestRenameCastle:
    def test_a_rename_sends_p_1(self):
        request = RenameCastleRequest(CID=1, N="Keep", AT=MapItemType.CASTLE, KID=Kingdom.ICE)
        assert request.to_payload() == {"CID": 1, "N": "Keep", "AT": 1, "KID": 2, "P": 1}

    def test_the_reply_reads_p(self):
        assert RenameCastleResponse.model_validate({"CID": 1, "KID": 2, "P": 0}).is_rename == 0


def test_rename_castle_sends_the_client_keys_and_encodes_the_name():
    from empire_core.castle.models.actions import RenameCastleRequest

    payload = RenameCastleRequest(CID=5, N="100% 'mine'\tnow", AT=MapItemType.CASTLE, KID=Kingdom.ICE, P=1).to_payload()
    # C2SRenameCastleVO: CID, P, KID and AT are initialised before N
    assert list(payload) == ["CID", "P", "KID", "AT", "N"]
    assert payload["N"] == "100&percnt; &145;mine&145; now"
