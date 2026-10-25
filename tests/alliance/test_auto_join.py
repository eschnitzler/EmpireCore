"""Joining automatically and the alliances to join, from AASCommand, AJACommand and SALCommand."""

import pytest

from empire_core.alliance.models.search import AllianceSearchListResponse, AutoAllianceSearchRequest
from empire_core.enums import AllianceRank
from empire_core.exceptions import CommandError
from empire_core.state.manager import GameState
from empire_core.state.models import Player
from tests.service_helpers import conn, make_client, xt_packet

ROW = {"AID": "301", "N": "Guild", "D": 12.5, "M": "9", "AH": 300, "AL": 4, "ALL": "de"}


def player_state(alliance_id: int | None = None) -> GameState:
    state = GameState()
    state.local_player = Player(PID=7, PN="Player")
    if alliance_id is not None:
        state.update_from_packet("gal", {"AID": alliance_id, "R": 0})
    return state


def wired(script, state):
    client = make_client(script, state=state)
    conn(client).on_packet = lambda packet: state.update_from_packet(
        packet.command_id, packet.payload, packet.error_code
    )
    return client


def test_request_sends_name_description_and_language():
    assert AutoAllianceSearchRequest(name="Alliance", language="de").to_payload() == {
        "N": "Alliance",
        "D": "",
        "ALL": "de",
    }


def test_auto_join_lists_alliances_when_none_was_joined():
    state = player_state()
    client = wired({"aas": xt_packet("aas", {"AL": [ROW, None, "bad"]})}, state)
    result = client.alliance.auto_join("Alliance", timeout=0.2)
    assert result.membership is None
    (row,) = result.alliances
    assert (row.alliance_id, row.name, row.distance, row.member_count, row.honor, row.level, row.language) == (
        301,
        "Guild",
        12.5,
        9,
        300,
        4,
        "de",
    )
    assert conn(client).request_payloads == [("aas", {"N": "Alliance", "D": "", "ALL": ""})]
    assert state.get_local_player().alliance_id is None


def test_auto_join_applies_membership_and_movements():
    state = player_state()
    reply = {"gal": {"AID": 301, "R": 9, "AN": "Guild"}, "gam": {"M": [], "O": []}}
    client = wired({"aas": xt_packet("aas", reply)}, state)
    result = client.alliance.auto_join("Alliance", timeout=0.2)
    assert result.membership is not None and result.membership.alliance_id == 301
    assert result.alliances == []
    assert state.get_local_player().alliance_id == 301


def test_auto_join_is_not_sent_inside_an_alliance():
    client = make_client(state=player_state(201))
    with pytest.raises(ValueError, match="already"):
        client.alliance.auto_join("Alliance")
    assert conn(client).request_payloads == []


def test_auto_join_refusal_raises_and_keeps_state():
    state = player_state()
    client = wired({"aas": xt_packet("aas", {"gal": {"AID": 301}}, error_code=1)}, state)
    with pytest.raises(CommandError):
        client.alliance.auto_join("Alliance", timeout=0.2)
    assert state.get_local_player().alliance_id is None


def test_aja_push_applies_membership_then_alliance():
    state = player_state(201)
    state.update_from_packet("ain", {"A": {"AID": 201, "N": "Old"}})
    state.update_from_packet("aja", {"gal": {"AID": 301, "R": 0, "AN": "Guild"}, "A": {"AID": 301, "N": "Guild"}})
    assert state.get_local_player().alliance_id == 301
    own = state.get_own_alliance()
    assert own is not None and own.alliance_id == 301 and own.name == "Guild"
    assert state.local_player is not None and state.local_player.alliance is not None
    assert state.local_player.alliance.rank == AllianceRank.LEADER


def test_aja_push_refused_or_malformed_changes_nothing():
    state = player_state(201)
    state.update_from_packet("aja", {"gal": {"AID": 301}, "A": {"AID": 301}}, 1)
    state.update_from_packet("aja", {"gal": {"AID": 301}, "A": {}})
    assert state.get_local_player().alliance_id == 201


def test_sal_push_lists_alliances():
    assert [row.alliance_id for row in AllianceSearchListResponse.model_validate({"AL": [ROW, ROW]}).alliances] == [
        301,
        301,
    ]
    assert AllianceSearchListResponse.model_validate({}).alliances == []
