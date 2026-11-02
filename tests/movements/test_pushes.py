"""The movement pushes: abr and asr, mrm, mfc, mvf, and the castle lists of a taken castle (mir)."""

from typing import Any

import pytest

from empire_core.castle.models.castles import NameCastleInvitationResponse
from empire_core.enums import MovementFilter
from empire_core.movements.models import (
    ArmyInBigRadiusResponse,
    ArmyInSmallRadiusResponse,
    MovementFilterResponse,
    MovementForceCancelableResponse,
    MovementRemovedResponse,
)
from empire_core.protocol.models import parse_response

WRAPPER = {"M": {"MID": 500, "T": 0, "PT": 0, "TT": 600, "D": 0, "OID": 999, "TID": 1}}


class TestArmyRadiusPushes:
    def test_the_owner_is_one_record_and_the_movement_a_gam_entry(self):
        push = parse_response("abr", {"O": {"OID": 999, "N": "Attacker", "AN": "Clan"}, "A": WRAPPER})
        assert isinstance(push, ArmyInBigRadiusResponse)
        assert push.owner is not None and (push.owner.player_id, push.owner.name) == (999, "Attacker")
        assert push.movement is not None and push.movement.movement.movement_id == 500

    @pytest.mark.parametrize("owner", [None, [], {}, {"N": "no id"}, {"OID": 0}])
    def test_no_owner_without_an_object_carrying_an_oid(self, owner):
        # parseOwnerInfo: !e || !e.OID returns null
        push = ArmyInSmallRadiusResponse.model_validate({"O": owner, "A": WRAPPER})
        assert push.owner is None and push.movement is not None

    def test_no_movement_when_a_is_no_object(self):
        assert ArmyInSmallRadiusResponse.model_validate({"A": []}).movement is None


class TestMovementIds:
    @pytest.mark.parametrize(
        ("value", "expected"), [(150, 150), (150.0, 150), ("150", None), (1.5, None), (None, None)]
    )
    def test_a_removed_movement_is_named_as_sent(self, value, expected):
        # parse_MRM: _mapMovements.get(MID), no int(), so only a number finds the movement
        assert MovementRemovedResponse.model_validate({"MID": value}).movement_id == expected
        assert MovementForceCancelableResponse.model_validate({"MID": value}).movement_id == expected


class TestMovementFilter:
    def test_filters_are_read_by_membership(self):
        filters = parse_response("mvf", {"AFS": [0, 2, "1", True]})
        assert isinstance(filters, MovementFilterResponse)
        assert filters.active_filters == (MovementFilter.PVP_ATTACKS, MovementFilter.MARKET_BARROWS)
        assert filters.shows(MovementFilter.PVP_ATTACKS) and not filters.shows(MovementFilter.ALLIANCE_PVP_ATTACKS)

    def test_no_list_is_no_filter(self):
        assert MovementFilterResponse.model_validate({}).active_filters == ()


class TestNameCastleInvitation:
    def test_the_lists_and_the_castle_to_name(self):
        body: dict[str, Any] = {
            "gcl": {"PID": 7, "C": []},
            "gkl": None,
            "gml": [],
            "CID": 42,
            "KID": 2.0,
        }
        mir = parse_response("mir", body)
        assert isinstance(mir, NameCastleInvitationResponse)
        assert mir.castles is not None and mir.castles.player_id == 7
        assert (mir.kings_towers, mir.monuments, mir.laboratories) == (None, None, None)
        assert (mir.castle_id, mir.kingdom_id) == (42, 2)

    def test_ids_that_are_no_whole_numbers_name_nothing(self):
        mir = NameCastleInvitationResponse.model_validate({"CID": "42", "KID": None})
        assert (mir.castle_id, mir.kingdom_id) == (None, None)


class TestMovementFilterState:
    def test_the_login_section_and_the_push_are_kept(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "mvf": {"AFS": [0]}})
        filters = state.get_movement_filter()
        assert filters is not None and filters.active_filters == (0,)

        state.update_from_packet("mvf", {"AFS": [1, 2]})
        filters = state.get_movement_filter()
        assert filters is not None and filters.active_filters == (1, 2)
        assert state.get_last_packet_time("mvf") is not None

    def test_a_falsy_section_keeps_the_filters(self, state):
        state.update_from_packet("mvf", {"AFS": [2]})
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "mvf": None})
        filters = state.get_movement_filter()
        assert filters is not None and filters.active_filters == (2,)

    def test_the_service_fronts_it(self):
        from tests.service_helpers import logged_in_state, make_client

        client = make_client(state=logged_in_state())
        client.state.update_from_packet("mvf", {"AFS": [0, 1]})
        filters = client.movements.map_filter
        assert filters is not None and filters.shows(MovementFilter.ALLIANCE_PVP_ATTACKS)
