"""Tests for the spy protocol models."""

from __future__ import annotations

import copy

from empire_core.enums import MapItemType, SpyType
from empire_core.protocol.base import parse_response
from empire_core.spy.models import SendSpyResponse
from tests.spy.payloads import CSM_REPLY


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
