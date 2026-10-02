"""Tests for the spy protocol models."""

from __future__ import annotations

import copy

import pytest

from empire_core.enums import Kingdom, MapItemType, SpyLogResult, SpyLogType, SpyType
from empire_core.protocol.base import parse_response
from empire_core.spy.models import (
    AutoSpyRequest,
    AutoSpyResponse,
    MaxSpiesResponse,
    SendSpyRequest,
    SendSpyResponse,
    SpyScreenInfoResponse,
)
from tests.spy.payloads import BSD_NPC_CAMP_REPORT, CSM_REPLY, SSI_NPC_CAMP


class TestSendSpyResponse:
    def test_the_movement_is_read_from_a(self):
        response = SendSpyResponse.model_validate(CSM_REPLY)

        assert response.movement_id == 5001
        assert response.seconds_until_arrival == 38
        assert response.spy_movement is not None
        movement = response.spy_movement.movement
        assert movement.owner_id == 1001
        assert movement.target_area is not None
        assert movement.target_area.area_type == MapItemType.DUNGEON
        assert (movement.target_area.x, movement.target_area.y) == (501, 297)
        assert movement.source_area is not None
        assert movement.source_area.name == "Spy Castle"

    def test_the_spy_details_are_read_from_s(self):
        spy = SendSpyResponse.model_validate(CSM_REPLY).spy

        assert spy is not None
        assert spy.spy_type_enum == SpyType.MILITARY
        assert (spy.spy_count, spy.accuracy_or_damage, spy.risk) == (2, 100, 26)

    def test_the_owner_records_are_read(self):
        response = SendSpyResponse.model_validate(CSM_REPLY)

        assert [owner.name for owner in response.owners] == ["Spy Player"]
        assert response.currencies is None

    def test_csm_parses_to_the_spy_response(self):
        assert isinstance(parse_response("csm", CSM_REPLY), SendSpyResponse)

    def test_a_reply_without_a_movement_has_no_id_or_arrival(self):
        response = SendSpyResponse.model_validate({"O": []})

        assert response.movement_id is None
        assert response.seconds_until_arrival is None
        assert response.spy is None

    def test_an_unreadable_movement_costs_only_itself(self):
        payload = copy.deepcopy(CSM_REPLY)
        payload["A"]["M"] = "junk"

        response = SendSpyResponse.model_validate(payload)

        assert response.spy_movement is None
        assert len(response.owners) == 1

    def test_arrival_is_what_is_left_of_the_trip(self):
        payload = copy.deepcopy(CSM_REPLY)
        payload["A"]["M"]["PT"] = 10

        assert SendSpyResponse.model_validate(payload).seconds_until_arrival == 28

    def test_owner_records_without_an_id_are_skipped(self):
        payload = copy.deepcopy(CSM_REPLY)
        payload["O"].append({"N": "no id"})

        assert len(SendSpyResponse.model_validate(payload).owners) == 1

    def test_the_currencies_are_read_from_gcu(self):
        payload = {**CSM_REPLY, "gcu": {"C1": 1200, "C2": 30}}

        currencies = SendSpyResponse.model_validate(payload).currencies

        assert currencies is not None
        assert (currencies.coins, currencies.rubies) == (1200, 30)


class TestSendSpyRequest:
    def test_the_payload_keeps_the_client_order(self):
        # C2SCreateSpyMovementVO initialises SID, TX, TY, SC, ST, SE, HBW, KID, PTT, SD in that order
        request = SendSpyRequest(
            castle_id=1,
            target_x=2,
            target_y=3,
            spy_count=4,
            spy_type=SpyType.SABOTAGE,
            accuracy_or_damage=30,
            horse_booster_id=1010,
            target_kingdom=Kingdom.ICE,
            feathers=0,
            slowdown=5,
        )

        assert list(request.to_payload().items()) == [
            ("SID", 1),
            ("TX", 2),
            ("TY", 3),
            ("SC", 4),
            ("ST", 2),
            ("SE", 30),
            ("HBW", 1010),
            ("KID", 2),
            ("PTT", 0),
            ("SD", 5),
        ]

    def test_feathers_send_no_horse(self):
        # Client: HBW=int(u?-1:l), PTT=int(u?1:0)
        payload = SendSpyRequest(castle_id=1, target_x=2, target_y=3, horse_booster_id=1010, feathers=1).to_payload()

        assert (payload["HBW"], payload["PTT"]) == (-1, 1)


class TestSpyTypeValues:
    def test_mission_types_are_the_clients(self):
        # ClientConstCastle.SPYTYPE_*
        assert [int(t) for t in (SpyType.MILITARY, SpyType.ECO, SpyType.SABOTAGE, SpyType.PLAGUE)] == [0, 1, 2, 3]

    def test_log_subtypes_differ_from_mission_types(self):
        # MessageConst.SUBTYPE_SPY_*: a military mission's log is DEFENCE (1)
        assert [int(t) for t in (SpyLogType.SABOTAGE, SpyLogType.DEFENCE, SpyLogType.ECO, SpyLogType.PLAGUE_MONK)] == [
            0,
            1,
            2,
            3,
        ]
        assert [int(r) for r in SpyLogResult] == [0, 1, 2, 3]


class TestSpyScreenInfoResponse:
    def test_the_live_reply_for_a_camp(self):
        screen = SpyScreenInfoResponse.model_validate(SSI_NPC_CAMP)

        assert (screen.available_spies, screen.guard_count) == (2, 0)
        assert (screen.available_plague_monks, screen.total_plague_monks) == (0, 0)
        assert (screen.target_x, screen.target_y) == (501, 297)
        area = screen.target_area
        assert area.kingdom_id == 0
        assert area.protection is not None
        assert (area.protection.noob_protection_seconds, area.protection.is_noob_protected) == (-1, False)
        assert area.protection.protection_status == -1
        assert area.owners == []
        row = screen.target_row()
        assert row is not None
        assert (row.item_type, row.x, row.y) == (MapItemType.DUNGEON, 501, 297)
        assert screen.target_owner() is None
        # A dungeon NPC owns it: isDungeon, and no outpost
        assert screen.risk_flags() == (True, True)

    def test_ssi_parses_to_the_screen_reply(self):
        assert isinstance(parse_response("ssi", SSI_NPC_CAMP), SpyScreenInfoResponse)

    def test_the_owner_record_of_a_player_target(self):
        payload = {
            **SSI_NPC_CAMP,
            "gaa": {
                "OI": [{"OID": 1001, "N": "Enemy", "L": 40}],
                "AI": [[1, 501, 297, 2001, 1001, 2, 2, 2, 1, 0, "Keep"]],
            },
        }
        screen = SpyScreenInfoResponse.model_validate(payload)

        owner = screen.target_owner()
        assert owner is not None
        assert (owner.owner_id, owner.level) == (1001, 40)
        assert screen.risk_flags() == (False, True)

    @pytest.mark.parametrize("position", [{"TX": 0, "TY": 297.0}, {}])
    def test_a_position_needs_both_coordinates(self, position):
        # Client: e.TX&&e.TY
        payload = {key: value for key, value in SSI_NPC_CAMP.items() if key not in ("TX", "TY")}

        screen = SpyScreenInfoResponse.model_validate({**payload, **position})

        assert (screen.target_x, screen.target_y) == (None, None)
        # The only row is still the target's
        assert screen.target_row() is not None

    def test_a_reply_without_gaa_still_parses(self):
        screen = SpyScreenInfoResponse.model_validate({"AS": 5, "GC": 3})

        assert (screen.available_spies, screen.guard_count) == (5, 3)
        assert screen.target_row() is None
        assert screen.risk_flags() is None


class TestAutoSpy:
    def test_ssu_sends_only_the_position(self):
        # C2SSpySpyUnits sets TX and TY
        assert AutoSpyRequest(target_x=501, target_y=297).to_payload() == {"TX": 501, "TY": 297}

    def test_the_reply_is_a_spy_report(self):
        report = parse_response("ssu", BSD_NPC_CAMP_REPORT)

        assert isinstance(report, AutoSpyResponse)
        assert (report.spy_count, report.risk) == (2, 26)


class TestMaxSpies:
    def test_gms_is_read(self):
        # CastleSpyData.parse_GMS: int(MS), int(BS)
        response = parse_response("gms", {"MS": 12, "BS": "3"})

        assert isinstance(response, MaxSpiesResponse)
        assert (response.max_spies, response.bonus_spies) == (12, 3)
