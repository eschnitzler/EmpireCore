"""Tests for the castle models."""

from empire_core.castle.models.actions import RenameCastleRequest, RenameCastleResponse
from empire_core.castle.models.castles import GetCastlesRequest, GetCastlesResponse, PlayerCastle
from empire_core.castle.models.details import CastleProductionArea, DetailedCastleInfo, GetDetailedCastleResponse
from empire_core.enums import Kingdom, MapItemType
from empire_core.protocol.models import parse_response
from tests.model_helpers import gdi_location_row

GOLDEN_DCL = {
    "PID": 1001,
    "C": [
        {
            "KID": 0,
            "AI": [
                {
                    "AID": 2001,
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
                {"AID": 2002, "W": 800.0, "S": 800.0, "F": 800.0, "AC": [[649, 18]], "B": 0},
            ],
        }
    ],
}


GOLDEN_GCL = {
    "PID": 1001,
    "C": [
        {
            "KID": 0,
            "AI": [
                {"AI": gdi_location_row(1, 512, 256, 2001, 1001, "Château Nord", 0), "AOT": -1, "TA": -1},
                {"AI": gdi_location_row(4, 510, 257, 2002, 1001, "OP1", 0), "TA": 0},
            ],
        },
        {"KID": 2, "AI": [{"AI": gdi_location_row(12, 100, 200, 2004, 1001, "Sands", 2)}]},
    ],
}


class TestGoldenCastlePayloads:
    def test_gcl_rows_are_flattened_across_kingdoms(self):
        response = GetCastlesResponse.model_validate(GOLDEN_GCL)
        assert response.player_id == 1001
        assert [(c.castle_id, c.castle_name, c.x, c.y, c.kingdom_id, c.castle_type) for c in response.castles] == [
            (2001, "Château Nord", 512, 256, 0, 1),
            (2002, "OP1", 510, 257, 0, 4),
            (2004, "Sands", 100, 200, 2, 12),
        ]
        assert response.castles[0].owner_id == 1001
        assert response.castles[2].position.kingdom == 2
        main, outpost = response.castles[0], response.castles[1]
        assert (main.keep_level, main.wall_level, main.gate_level, main.tower_level, main.moat_level) == (1, 1, 1, 0, 0)
        assert (main.abandon_outpost_seconds, main.no_abandon_seconds, main.open_gate_seconds) == (-1, -1, 0)
        # The client reads an absent AOT through int(), so as 0
        assert (outpost.no_abandon_seconds, outpost.abandon_outpost_seconds) == (0, 0)
        assert outpost.occupier_id == -1

    def test_a_rows_own_kingdom_wins_over_its_block(self):
        # InteractiveMapobjectVO.parseAreaInfo (bundle line 3637) reads field 16
        payload = {"C": [{"KID": 0, "AI": [{"AI": gdi_location_row(1, 1, 2, 5, 9, "Ice", 2)}]}]}
        assert GetCastlesResponse.model_validate(payload).castles[0].kingdom_id is Kingdom.ICE

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
        assert response.player_id == 1001
        assert [c.castle_id for c in response.castles] == [2001, 2002]
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
        outpost = response.castle(2002)
        assert outpost is not None
        assert outpost.units == {649: 18}
        assert response.castle(1) is None


class TestRenameCastle:
    def test_a_rename_sends_p_1(self):
        request = RenameCastleRequest(
            castle_id=1, castle_name="Keep", castle_type=MapItemType.CASTLE, kingdom_id=Kingdom.ICE
        )
        assert request.to_payload() == {"CID": 1, "N": "Keep", "AT": 1, "KID": 2, "P": 1}

    def test_the_reply_reads_p(self):
        assert RenameCastleResponse.model_validate({"CID": 1, "KID": 2, "P": 0}).is_rename == 0


def test_rename_castle_sends_the_client_keys_and_encodes_the_name():
    from empire_core.castle.models.actions import RenameCastleRequest

    payload = RenameCastleRequest(
        castle_id=5, castle_name="100% 'mine'\tnow", castle_type=MapItemType.CASTLE, kingdom_id=Kingdom.ICE, is_rename=1
    ).to_payload()
    # C2SRenameCastleVO: CID, P, KID and AT are initialised before N
    assert list(payload) == ["CID", "P", "KID", "AT", "N"]
    assert payload["N"] == "100&percnt; &145;mine&145; now"


# =============================================================================
# gcl row fields 11 to 19
# =============================================================================


def _castle_row(area_type: int, **at: object) -> list:
    """A 20-field castle list row; ``at`` overrides fields by index, as ``i11=...``."""
    row: list = [area_type, 10, 20, 555, 42, 3, 2, 2, 1, 0, "Keep", 0, 0, -1, 0, -1, 0, 0, [], 0]
    for key, value in at.items():
        row[int(key[1:])] = value
    return row


class TestCastleListRowTimers:
    def test_a_castle_row_reads_cooldowns_spy_age_outpost_type_skin_and_protection(self):
        # InteractiveMapobjectVO.parseAreaInfo: 11 to 17 through int(), 19 on when 1
        row = _castle_row(4, i11="120", i12=30, i13=3600, i14=2, i15=77, i17=301, i19=1)
        castle = PlayerCastle.from_list(row)
        assert (castle.attack_cooldown_seconds, castle.sabotage_cooldown_seconds, castle.seconds_since_spy) == (
            120,
            30,
            3600,
        )
        assert (castle.outpost_type, castle.occupier_id, castle.equipment_skin_id) == (2, 77, 301)
        assert castle.has_sabotage_protection is True

    def test_a_main_castle_reads_its_occupier_from_15(self):
        castle = PlayerCastle.from_list(_castle_row(1, i15=77))
        assert (castle.occupier_id, castle.is_occupied) == (77, True)

    def test_protection_is_off_unless_19_is_1(self):
        assert PlayerCastle.from_list(_castle_row(1, i19=2)).has_sabotage_protection is False
        assert PlayerCastle.from_list(_castle_row(1)[:19]).has_sabotage_protection is False

    def test_a_row_that_ends_early_reads_the_missing_timers_as_0(self):
        castle = PlayerCastle.from_list(_castle_row(1)[:17])
        assert (castle.equipment_skin_id, castle.has_sabotage_protection) == (0, False)
        castle = PlayerCastle.from_list(_castle_row(1)[:11])
        assert (castle.attack_cooldown_seconds, castle.seconds_since_spy, castle.outpost_type) == (0, 0, 0)

    def test_a_capital_row_shifts_occupier_and_skin(self):
        # CapitalMapobjectVO.parseAreaInfo: occupier 14, skin 15, no outpost type
        row = _castle_row(3, i11=5, i12=6, i13=7, i14=88, i15=301, i19=1)
        capital = PlayerCastle.from_list(row)
        assert (capital.occupier_id, capital.equipment_skin_id, capital.outpost_type) == (88, 301, None)
        assert (capital.attack_cooldown_seconds, capital.seconds_since_spy, capital.has_sabotage_protection) == (
            5,
            7,
            True,
        )

    def test_landmarks_read_their_spy_age(self):
        assert PlayerCastle.from_list([23, 50, 60, 888, 4242, 2, 900, "Tower"]).seconds_since_spy == 900
        monument = PlayerCastle.from_list([26, 50, 60, 889, 4242, 3, 5, 0, 800, "Monument"])
        assert (monument.monument_type, monument.landmark_level, monument.seconds_since_spy) == (3, 5, 800)
        assert PlayerCastle.from_list([28, 50, 60, 890, 4242, 3, 1, 700, "Lab"]).seconds_since_spy == 700

    def test_castle_info_carries_the_row_fields(self):
        payload = {"C": [{"KID": 0, "AI": [{"AI": _castle_row(1, i11=9, i15=77, i17=5), "AOT": "12"}]}]}
        castle = GetCastlesResponse.model_validate(payload).castles[0]
        assert (castle.attack_cooldown_seconds, castle.occupier_id, castle.equipment_skin_id) == (9, 77, 5)
        assert castle.abandon_outpost_seconds == 12

    def test_castle_info_dumps_no_placeholder_keys(self):
        castle = GetCastlesResponse.model_validate(GOLDEN_GCL).castles[0]
        dumped = castle.model_dump(by_alias=True)
        assert not [key for key in dumped if "[" in key]
        assert {"KID", "OGT", "OGC", "AOT", "CAT", "TA"} <= set(dumped)


class TestCastleListRequest:
    def test_sends_the_player_id(self):
        # C2SGetCastleListVO sends PID
        assert GetCastlesRequest(player_id=777).to_payload() == {"PID": 777}

    def test_without_a_player_id_sends_nothing(self):
        assert GetCastlesRequest().to_payload() == {}


# =============================================================================
# dcl / gpa
# =============================================================================


class TestProductionArea:
    def test_the_faction_buff_is_read(self):
        # AreaDataMorality.parseGPA: RFPPA as sent, a 0 to 1 balance
        assert CastleProductionArea.model_validate({"RFPPA": 0.25}).faction_buff == 0.25
        assert CastleProductionArea.model_validate({}).faction_buff == 0.0

    def test_whole_numbers_go_through_int(self):
        area = CastleProductionArea.model_validate({"P": "80", "R": 5.9, "GRD": None})
        assert (area.population, area.riot, area.guards) == (80, 5, 0)

    def test_dcl_flags_go_through_boolean(self):
        info = DetailedCastleInfo.model_validate({"AID": "7", "B": 2, "WS": 0, "D": "57.5"})
        assert (info.castle_id, info.has_barracks, info.has_siege_workshop, info.defense_value) == (7, True, False, 57)
