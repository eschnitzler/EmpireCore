"""Founding wire payloads and payment/membership safeguards from the client."""

import pytest

from empire_core.exceptions import CommandError, EmpireTimeoutError, PacketError, ReplyMismatchError
from empire_core.player import BoosterInfoResponse
from tests.alliance.test_membership import membership_state
from tests.service_helpers import conn, make_client, xt_packet


def founding_client(script=None, *, premium_seconds=0):
    state = membership_state()
    state.boosts = BoosterInfoResponse(premium_seconds=premium_seconds)
    return make_client(script, state=state)


def founded_payload():
    return {"A": {"AID": 301, "N": "Guild", "FR": 1}, "gal": {"AID": 301, "R": 0, "AN": "Guild"}}


@pytest.mark.parametrize("open_join", [True, False])
def test_found_sends_normal_client_options_and_applies_membership(open_join):
    client = founding_client({"afo": xt_packet("afo", founded_payload())}, premium_seconds=60)
    result = client.alliance.found("Guild", "  Back\\slash  ", "en", open_join=open_join, timeout=0.2)
    assert result.alliance_id == 301
    assert client.alliance.local_alliance_id == 301
    assert client.alliance.own_alliance is not None and client.alliance.own_alliance.name == "Guild"
    assert conn(client).request_payloads == [
        ("afo", {"N": "Guild", "D": "Back&percnt;5Cslash", "ALL": "en", "PO": -1, "PWR": 0, "IA": int(open_join)})
    ]


@pytest.mark.parametrize("premium_seconds", [0, 0.01])
def test_found_requires_ruby_consent_without_safe_premium_exemption(premium_seconds):
    client = founding_client(premium_seconds=premium_seconds)
    with pytest.raises(ValueError, match="spend_rubies"):
        client.alliance.found("Guild", "Description", "en", timeout=0.2)
    assert conn(client).requested == []


def test_found_explicit_consent_keeps_normal_missing_resource_payment_disabled():
    client = founding_client({"afo": xt_packet("afo", founded_payload())})
    assert client.alliance.found("Guild", "Description", "en", spend_rubies=True).alliance_id == 301
    assert conn(client).request_payloads[0][1]["PWR"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"A": {"AID": 301}},
        {"gal": {"AID": 301}},
        {"A": {"AID": 301}, "gal": {"AID": 401}},
        {"A": {"AID": -1}, "gal": {"AID": -1}},
    ],
)
def test_found_malformed_reply_preserves_membership(payload):
    client = founding_client({"afo": xt_packet("afo", payload)}, premium_seconds=60)
    conn(client).on_packet = lambda packet: client.state.update_from_packet(
        packet.command_id, packet.payload, packet.error_code
    )
    with pytest.raises(PacketError):
        client.alliance.found("Guild", "Description", "en")
    assert client.alliance.local_alliance_id is None and client.alliance.own_alliance is None


@pytest.mark.parametrize("failure", [EmpireTimeoutError("timeout"), CommandError("afo", 1, {})])
def test_found_failure_preserves_state(failure):
    client = founding_client({"afo": failure}, premium_seconds=60)
    with pytest.raises(type(failure)):
        client.alliance.found("Guild", "Description", "en")
    assert client.alliance.local_alliance_id is None and client.alliance.own_alliance is None


def test_found_does_not_replace_a_newer_membership():
    client = founding_client({"afo": xt_packet("afo", founded_payload())}, premium_seconds=60)

    def newer(packet):
        client.state.update_from_packet("gal", {"AID": 401})
        client.state.update_from_packet("ain", {"A": {"AID": 401, "N": "Newer guild"}})
        client.state.update_from_packet(packet.command_id, packet.payload, packet.error_code)

    conn(client).on_packet = newer
    with pytest.raises(ReplyMismatchError):
        client.alliance.found("Guild", "Description", "en")
    assert client.alliance.local_alliance_id == 401
    assert client.alliance.own_alliance is not None and client.alliance.own_alliance.name == "Newer guild"


def test_found_existing_membership_or_invalid_text_sends_nothing():
    client = founding_client(premium_seconds=60)
    for name, description in [("bad!name", ""), ("a", ""), ("a" * 16, ""), ("Guild", "a" * 1001)]:
        with pytest.raises(ValueError):
            client.alliance.found(name, description, "en")
    client.state.update_from_packet("gal", {"AID": 301})
    with pytest.raises(ValueError, match="already"):
        client.alliance.found("Guild", "", "en")
    assert conn(client).requested == []


def test_found_timeout_reply_cannot_later_apply_without_active_request():
    client = founding_client({"afo": EmpireTimeoutError("timeout")}, premium_seconds=60)
    with pytest.raises(EmpireTimeoutError):
        client.alliance.found("Guild", "Description", "en")
    client.state.update_from_packet("afo", founded_payload())
    assert client.alliance.local_alliance_id is None


def test_malformed_created_ids_do_not_turn_into_alliance_zero():
    client = founding_client(
        {"afo": xt_packet("afo", {"A": {"AID": "bad"}, "gal": {"AID": "bad"}})}, premium_seconds=60
    )
    with pytest.raises(PacketError):
        client.alliance.found("Guild", "Description", "en")
    assert client.alliance.local_alliance_id is None


@pytest.mark.parametrize("timeout", [-1.0, float("nan")])
def test_invalid_timeout_cannot_bypass_paid_founding_consent(timeout):
    client = founding_client()
    with pytest.raises(ValueError, match="spend_rubies"):
        client.alliance.found("Guild", "Description", "en", timeout=timeout)
    assert conn(client).requested == []
