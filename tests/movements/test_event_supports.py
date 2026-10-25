"""Supports on event maps: alliance battleground towers (tde), daimyo townships (cdd), and the css reply."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.exceptions import CommandError, PremiumCommanderCostError
from empire_core.gamedata import WodAmount
from empire_core.protocol.base import parse_response
from empire_core.protocol.models import (
    SendSupportResponse,
    SendTowerSupportRequest,
    SendTowerSupportResponse,
    SendTownshipSupportRequest,
    SendTownshipSupportResponse,
    SendTroopsResponse,
    SentMovementResponse,
    SiegeMovementResponse,
)
from tests.service_helpers import conn, make_client, xt_packet

ME = 1001


def reply(movement_id: int, x: int = 700, y: int = 710) -> dict[str, Any]:
    """A send reply as the client reads one: gcu, O and the movement under A."""
    return {
        "gcu": {"C1": 100, "C2": 4},
        "O": [{"OID": ME, "N": "me"}, {"N": "no id"}],
        "A": {"M": {"MID": movement_id, "T": 1, "TT": 60, "PT": 0, "OID": ME, "TA": [26, x, y, -1, 1, -1, 0]}},
    }


class TestSentMovementReplies:
    @pytest.mark.parametrize(
        ("command", "model"),
        [
            ("cds", SendSupportResponse),
            ("tde", SendTowerSupportResponse),
            ("cdd", SendTownshipSupportResponse),
            ("cat", SendTroopsResponse),
            ("css", SiegeMovementResponse),
        ],
    )
    def test_the_movement_owners_and_currencies_are_typed(self, command, model):
        parsed = parse_response(command, reply(5))
        assert type(parsed) is model
        assert parsed.movement_id == 5
        assert [owner.player_id for owner in parsed.owners] == [ME]
        assert parsed.currencies is not None and (parsed.currencies.coins, parsed.currencies.rubies) == (100, 4)

    def test_the_shared_base_reads_the_shape_itself(self):
        assert SentMovementResponse.model_validate(reply(3)).movement_id == 3

    def test_an_unreadable_movement_costs_only_itself(self):
        parsed = SendTownshipSupportResponse.model_validate({"A": {"M": "junk"}, "gcu": {"C1": 1}})
        assert (parsed.movement, parsed.movement_id) == (None, None)
        assert parsed.currencies is not None


class TestTowerSupport:
    def test_keys_match_a_support(self):
        request = SendTowerSupportRequest(
            source_castle_id=1, target_x=2, target_y=3, commander_id=4, wait_time=5, units=WodAmount.slots({487: 6})
        )
        # C2SCreateAllianceTowerSupportMovementVO initialises SID..SD, then sets A, as cds does
        assert list(request.to_payload()) == ["SID", "TX", "TY", "LID", "WT", "HBW", "BPC", "PTT", "SD", "A"]

    def test_send_support_sends_tde_to_a_tower(self):
        client = make_client({"tde": xt_packet("tde", reply(8, 30, 40))})

        sent = client.movements.send_support(12345, 30, 40, {487: 10}, commander_id=5, alliance_tower=True)

        command, payload = conn(client).request_payloads[0]
        assert command == "tde"
        assert payload == {
            "SID": 12345, "TX": 30, "TY": 40, "LID": 5, "WT": 12, "HBW": -1, "BPC": 0, "PTT": 0, "SD": 0,
            "A": [[487, 10]],
        }  # fmt: skip
        assert isinstance(sent, SendTowerSupportResponse)
        assert sent.movement_id == 8

    def test_send_support_returns_the_cds_reply(self):
        client = make_client({"cds": xt_packet("cds", reply(9))})

        sent = client.movements.send_support(12345, 700, 710, {487: 10}, commander_id=5)

        assert type(sent) is SendSupportResponse
        assert sent.movement_id == 9

    def test_the_premium_commander_needs_consent(self):
        client = make_client()

        with pytest.raises(PremiumCommanderCostError):
            client.movements.send_support(
                12345, 30, 40, {487: 1}, commander_id=-14, use_premium_commander=True, alliance_tower=True
            )

        assert conn(client).request_payloads == []


class TestTownshipSupport:
    def test_keys_follow_the_client_order(self):
        request = SendTownshipSupportRequest(
            source_castle_id=1, target_x=2, target_y=3, units=WodAmount.slots({487: 6})
        )
        assert list(request.to_payload().items()) == [("SID", 1), ("TX", 2), ("TY", 3), ("A", [[487, 6]])]

    def test_sends_cdd_and_returns_the_movement(self):
        client = make_client({"cdd": xt_packet("cdd", reply(10, 30, 40))})

        sent = client.movements.send_township_support(12345, 30, 40, {487: 10, 488: 2})

        assert conn(client).request_payloads[0] == (
            "cdd",
            {"SID": 12345, "TX": 30, "TY": 40, "A": [[487, 10], [488, 2]]},
        )
        assert sent.movement_id == 10

    def test_no_units_are_refused_before_sending(self):
        client = make_client()

        with pytest.raises(ValueError, match="needs units"):
            client.movements.send_township_support(12345, 30, 40, {})

        assert conn(client).request_payloads == []

    def test_a_refusal_raises(self):
        client = make_client({"cdd": xt_packet("cdd", None, error_code=21)})

        with pytest.raises(CommandError):
            client.movements.send_township_support(12345, 30, 40, {487: 1})

    def test_a_reply_for_another_target_is_not_taken(self):
        request = SendTownshipSupportRequest(
            source_castle_id=1, target_x=30, target_y=40, units=WodAmount.slots({487: 6})
        )
        assert request.accepts_reply(reply(1, 30, 40))
        assert not request.accepts_reply(reply(1, 500, 510))
