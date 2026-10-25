"""Trade reports: mmn reads a market carriage's report."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.exceptions import CommandError
from empire_core.messages import GetTradeReportRequest, TradeReportResponse
from empire_core.protocol.base import parse_response
from tests.service_helpers import conn, make_client, xt_packet

# MMNCommand reads O; CastleTradeMessageDialog.onGetTradeData reads gaa.AI[0], gaa.AI[1] and R
MMN: dict[str, Any] = {
    "O": [{"OID": 1001, "N": "me"}, {"OID": 2002, "N": "friend"}],
    "gaa": {"AI": [[1, 100, 200, 11, 1001], [1, 300, 400, 22, 2002]]},
    "R": [["W", 500], ["S", 250]],
}


class TestModels:
    def test_the_request_sends_the_message(self):
        assert GetTradeReportRequest(message_id=77).to_payload() == {"MID": 77}

    def test_the_reply_reads_both_areas_and_the_goods(self):
        reply = parse_response("mmn", MMN)
        assert isinstance(reply, TradeReportResponse)
        assert [owner.owner_id for owner in reply.owners] == [1001, 2002]
        assert reply.owner_area is not None and (reply.owner_area.x, reply.owner_area.y) == (100, 200)
        assert reply.target_area is not None and (reply.target_area.x, reply.target_area.y) == (300, 400)
        assert [good.amount for good in reply.goods] == [500, 250]

    def test_a_reply_without_rows_has_no_areas(self):
        reply = TradeReportResponse.model_validate({"gaa": None})
        assert reply.owner_area is None and reply.target_area is None and reply.goods == ()


class TestService:
    def test_get_trade_report(self):
        client = make_client({"mmn": xt_packet("mmn", MMN)})
        reply = client.messages.get_trade_report(77)
        assert conn(client).request_payloads == [("mmn", {"MID": 77})]
        assert len(reply.goods) == 2

    def test_a_refused_read_raises(self):
        client = make_client({"mmn": xt_packet("mmn", error_code=66)})
        with pytest.raises(CommandError):
            client.messages.get_trade_report(77)
