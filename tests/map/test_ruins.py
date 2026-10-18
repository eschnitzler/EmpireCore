"""Ruins: the time left on one, and the reminder for when it frees."""

from __future__ import annotations

import pytest

from empire_core.exceptions import CommandError
from empire_core.map import RememberRuinRequest, RuinInfoRequest, RuinInfoResponse
from empire_core.protocol.base import parse_response
from tests.service_helpers import conn, make_client, request_payload, xt_packet


def test_the_requests_send_the_position():
    assert RuinInfoRequest(x=12, y=34).to_payload() == {"PX": 12, "PY": 34}
    assert RememberRuinRequest(x=12, y=34).to_payload() == {"PX": 12, "PY": 34}


def test_the_reply_reads_through_int():
    reply = parse_response("rui", {"ART": "3600", "PX": "12", "PY": 34})

    assert isinstance(reply, RuinInfoResponse)
    assert (reply.x, reply.y, reply.remaining_seconds) == (12, 34, 3600)


def test_get_ruin_info():
    client = make_client({"rui": xt_packet("rui", {"ART": 3600, "PX": 12, "PY": 34})})

    info = client.map.get_ruin_info(12, 34)

    assert conn(client).request_payloads == [("rui", {"PX": 12, "PY": 34})]
    assert info.remaining_seconds == 3600


def test_a_refused_ruin_info_raises():
    client = make_client({"rui": xt_packet("rui", error_code=21)})

    with pytest.raises(CommandError):
        client.map.get_ruin_info(12, 34)


def test_remember_ruin_does_not_wait():
    client = make_client()

    client.map.remember_ruin(12, 34)

    assert [request_payload(p) for p in conn(client).sent] == [{"PX": 12, "PY": 34}]
    assert conn(client).requested == []
