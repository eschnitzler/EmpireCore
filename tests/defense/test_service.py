"""Tests for the defense service."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from empire_core.defense.models import GetSupportDefenseResponse
from tests.service_helpers import StubState, conn, make_client, xt_packet


class _CastleState(StubState):
    def __init__(self, castles: list[SimpleNamespace]):
        super().__init__()
        self.castles = castles

    def get_castles(self) -> list[SimpleNamespace]:
        return self.castles


class TestGetCastleDefense:
    def test_source_defaults_to_the_first_own_castle(self):
        state = _CastleState([SimpleNamespace(x=100, y=200), SimpleNamespace(x=300, y=400)])
        client = make_client({"sdi": xt_packet("sdi", {"S": []})}, state)

        response = client.defense.get_castle_defense(640, 655)

        assert isinstance(response, GetSupportDefenseResponse)
        assert conn(client).request_payloads == [("sdi", {"TX": 640, "TY": 655, "SX": 100, "SY": 200})]

    def test_explicit_source_is_sent_as_given(self):
        client = make_client({"sdi": xt_packet("sdi", {"S": []})}, _CastleState([]))

        client.defense.get_castle_defense(640, 655, source_x=1, source_y=2)

        assert conn(client).request_payloads == [("sdi", {"TX": 640, "TY": 655, "SX": 1, "SY": 2})]

    def test_no_source_and_no_castle_raises(self):
        client = make_client(state=_CastleState([]))

        with pytest.raises(ValueError):
            client.defense.get_castle_defense(640, 655)
