"""Sending plague monks (cpm)."""

from __future__ import annotations

import pytest

from empire_core.enums import Kingdom
from empire_core.exceptions import CommandError
from empire_core.protocol.base import parse_response
from empire_core.protocol.models import PlagueMonkInfoResponse, SendPlagueMonksRequest, SendPlagueMonksResponse
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet

ME = 1001
REPLY = {
    "gcu": {"C1": 100, "C2": 4},
    "O": [{"OID": ME, "N": "me"}],
    "A": {"M": {"MID": 12, "T": 5, "TT": 60, "PT": 0, "OID": ME, "TA": [1, 700, 710, 55, 77, 1, 0]}},
    "cpi": {"APM": 3, "TPM": 8},
}


class TestPlagueMonkModels:
    def test_keys_follow_the_client_order(self):
        request = SendPlagueMonksRequest(target_x=7, target_y=8, target_kingdom=Kingdom.ICE, monks=4, damage=30)
        # C2SCreatePlagueMonkMovementVO declares TX, TY, TK, C, E
        assert list(request.to_payload().items()) == [("TX", 7), ("TY", 8), ("TK", 2), ("C", 4), ("E", 30)]

    def test_the_reply_carries_the_movement_and_the_monks_left(self):
        reply = parse_response("cpm", REPLY)
        assert isinstance(reply, SendPlagueMonksResponse)
        assert reply.movement_id == 12
        assert reply.plague_monks == PlagueMonkInfoResponse(available_plague_monks=3, total_plague_monks=8)

    def test_a_falsy_cpi_is_none(self):
        # CastleSpyData.parse_CPI skips a falsy section
        assert SendPlagueMonksResponse.model_validate({"cpi": None}).plague_monks is None


class TestSendPlagueMonks:
    def test_sends_cpm_and_returns_the_reply(self):
        client = make_client({"cpm": xt_packet("cpm", REPLY)}, GameState())

        reply = client.spy.send_plague_monks(700, 710, Kingdom.GREEN, monks=4, damage=30)

        assert conn(client).request_payloads[0] == ("cpm", {"TX": 700, "TY": 710, "TK": 0, "C": 4, "E": 30})
        assert reply.movement_id == 12

    @pytest.mark.parametrize(("monks", "damage"), [(0, 30), (21, 30), (4, 9), (4, 51)])
    def test_what_the_dialog_would_not_send_is_refused(self, monks, damage):
        client = make_client()

        with pytest.raises(ValueError):
            client.spy.send_plague_monks(700, 710, monks=monks, damage=damage)

        assert conn(client).request_payloads == []

    def test_more_monks_than_are_at_home_are_refused(self):
        state = GameState()
        state.update_from_packet("cpi", {"APM": 2, "TPM": 5})
        client = make_client(state=state)

        with pytest.raises(ValueError, match="2 plague monks"):
            client.spy.send_plague_monks(700, 710, monks=3, damage=30)

        assert conn(client).request_payloads == []

    def test_a_refusal_raises(self):
        client = make_client({"cpm": xt_packet("cpm", None, error_code=21)}, GameState())

        with pytest.raises(CommandError):
            client.spy.send_plague_monks(700, 710, monks=1, damage=10)
