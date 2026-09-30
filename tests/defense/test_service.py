"""Tests for the defense service."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from empire_core.defense.models import GetDefenseResponse, GetSupportDefenseResponse
from empire_core.enums import Kingdom
from empire_core.exceptions import CommandError
from tests.defense.test_models import LIVE_DFC
from tests.service_helpers import StubState, conn, make_client, xt_packet


class _CastleState(StubState):
    def __init__(self, castles: list[SimpleNamespace]):
        super().__init__()
        self.castles = castles

    def get_castles(self) -> list[SimpleNamespace]:
        return self.castles


class TestGetSupportDefenseInfo:
    def test_source_defaults_to_the_first_own_castle(self):
        state = _CastleState([SimpleNamespace(x=100, y=200), SimpleNamespace(x=300, y=400)])
        client = make_client({"sdi": xt_packet("sdi", {"S": []})}, state)

        response = client.defense.get_support_defense_info(640, 655)

        assert isinstance(response, GetSupportDefenseResponse)
        assert conn(client).request_payloads == [("sdi", {"TX": 640, "TY": 655, "SX": 100, "SY": 200})]

    def test_explicit_source_is_sent_as_given(self):
        client = make_client({"sdi": xt_packet("sdi", {"S": []})}, _CastleState([]))

        client.defense.get_support_defense_info(640, 655, source_x=1, source_y=2)

        assert conn(client).request_payloads == [("sdi", {"TX": 640, "TY": 655, "SX": 1, "SY": 2})]

    def test_no_source_and_no_castle_raises(self):
        client = make_client(state=_CastleState([]))

        with pytest.raises(ValueError):
            client.defense.get_support_defense_info(640, 655)


class TestGetOwnDefense:
    def test_dfc_is_sent_for_the_castle_with_no_kingdom(self):
        client = make_client({"dfc": xt_packet("dfc", LIVE_DFC)})

        response = client.defense.get_own_defense(635, 242, 16655114)

        assert isinstance(response, GetDefenseResponse)
        assert conn(client).request_payloads == [("dfc", {"CX": 635, "CY": 242, "AID": 16655114, "KID": -1})]
        assert response.wall is not None
        assert response.keep is not None

    def test_a_given_kingdom_is_sent(self):
        client = make_client({"dfc": xt_packet("dfc", LIVE_DFC)})

        client.defense.get_own_defense(635, 242, 16655114, kingdom=Kingdom.ICE)

        assert conn(client).request_payloads == [("dfc", {"CX": 635, "CY": 242, "AID": 16655114, "KID": 2})]

    def test_a_rejection_raises(self):
        client = make_client({"dfc": xt_packet("dfc", error_code=92)})

        with pytest.raises(CommandError):
            client.defense.get_own_defense(635, 242, 16655114)
