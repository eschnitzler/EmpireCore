"""The full ruby skip of a transfer to another kingdom: kst, C2SKingdomSkipTransferVO and KSTCommand."""

import pytest

from empire_core.enums import Kingdom, KingdomTransferType
from empire_core.exceptions import CommandError
from empire_core.movements import KingdomSkipTransferRequest, KingdomSkipTransferResponse
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

KPI = {"UL": [{"KID": 2, "U": 1}], "UT": [{"KID": 2, "RS": 600, "I": [[1, 5]]}], "RT": []}


def test_the_request_sends_numbers_in_the_client_order():
    payload = KingdomSkipTransferRequest(kingdom_id=Kingdom.ICE, transfer_type=KingdomTransferType.GOODS).to_payload()
    assert list(payload) == ["KID", "TT"] and payload == {"KID": 2, "TT": 2}


def test_the_reply_reads_coins_and_resources():
    reply = KingdomSkipTransferResponse.model_validate({"gcu": {"C1": 10, "C2": 20}, "grc": {"W": 5}, "kpi": KPI})
    assert reply.currencies is not None and reply.resources is not None


def test_the_skip_needs_consent():
    client = make_client(state=logged_in_state(kpi=KPI))
    with pytest.raises(ValueError, match="spend_rubies"):
        client.movements.skip_kingdom_transfer(Kingdom.ICE, KingdomTransferType.UNITS)
    assert conn(client).request_payloads == []


def test_the_skip_sends_kst_and_its_reply_updates_the_kingdoms():
    reply = {"gcu": {"C1": 10, "C2": 20}, "kpi": {"UL": [], "UT": [], "RT": []}}
    client = make_client({"kst": xt_packet("kst", reply)}, state=logged_in_state(kpi=KPI))
    conn(client).on_packet = client._on_packet
    client.movements.skip_kingdom_transfer(Kingdom.ICE, KingdomTransferType.UNITS, spend_rubies=True)
    assert conn(client).request_payloads == [("kst", {"KID": 2, "TT": 1})]
    kingdoms = client.castle.kingdoms
    assert kingdoms is not None and kingdoms.unit_transfers == ()


def test_no_transfer_on_its_way_is_refused_before_sending():
    client = make_client(state=logged_in_state(kpi=KPI))
    with pytest.raises(ValueError, match="no goods transfer"):
        client.movements.skip_kingdom_transfer(Kingdom.ICE, KingdomTransferType.GOODS, spend_rubies=True)
    with pytest.raises(ValueError, match="FIRE"):
        client.movements.skip_kingdom_transfer(Kingdom.FIRE, KingdomTransferType.UNITS, spend_rubies=True)
    assert conn(client).request_payloads == []


def test_a_refused_skip_raises():
    client = make_client({"kst": xt_packet("kst", error_code=1)}, state=logged_in_state(kpi=KPI))
    with pytest.raises(CommandError):
        client.movements.skip_kingdom_transfer(Kingdom.ICE, KingdomTransferType.UNITS, spend_rubies=True)
