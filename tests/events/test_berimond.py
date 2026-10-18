"""Synthetic reads from FactionEventVO.parse_AFD/parse_FGB."""

import pytest

from empire_core.exceptions import (
    CommandError,
    ConnectionClosedError,
    EmpireTimeoutError,
    EventNotRunningError,
    PacketError,
)
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet


def berimond_client(script=None):
    client = make_client(script or {}, state=GameState())
    client._on_packet(xt_packet("sei", {"E": [{"EID": 3, "RS": 600, "UL": 1}]}))
    conn(client).on_packet = client._on_packet
    return client


def test_targets_preserve_special_camp_ids_order_duplicates_and_unknowns():
    client = berimond_client({"afd": xt_packet("afd", {"AC": [12, 987654, 12]})})
    before = client.events.running
    targets = client.events.get_berimond_targets(timeout=0.2)
    assert [target.special_camp_id for target in targets] == [12, 987654, 12]
    assert conn(client).request_payloads == [("afd", {})]
    assert client.events.running == before


def test_empty_targets_are_a_valid_success():
    client = berimond_client({"afd": xt_packet("afd", {"AC": []})})
    assert client.events.get_berimond_targets() == ()


def test_balance_returns_both_player_counts():
    client = berimond_client({"fgb": xt_packet("fgb", {"RP": 13, "BP": 7})})
    balance = client.events.get_berimond_balance(timeout=0.2)
    assert (balance.red_players, balance.blue_players) == (13, 7)
    assert conn(client).request_payloads == [("fgb", {})]


@pytest.mark.parametrize("red,blue,expected", [(0, 0, (0, 0)), (-2, 3, (0, 3))])
def test_balance_clamps_negative_counts_like_client(red, blue, expected):
    client = berimond_client({"fgb": xt_packet("fgb", {"RP": red, "BP": blue})})
    balance = client.events.get_berimond_balance()
    assert (balance.red_players, balance.blue_players) == expected


@pytest.mark.parametrize(
    "command,method,payload",
    [
        ("afd", "get_berimond_targets", {}),
        ("afd", "get_berimond_targets", {"AC": None}),
        ("afd", "get_berimond_targets", {"AC": {}}),
        ("afd", "get_berimond_targets", {"AC": [None]}),
        ("afd", "get_berimond_targets", {"AC": [[1, 2]]}),
        ("fgb", "get_berimond_balance", {}),
        ("fgb", "get_berimond_balance", {"RP": 2}),
        ("fgb", "get_berimond_balance", {"RP": None, "BP": 2}),
        ("fgb", "get_berimond_balance", {"RP": "bad", "BP": 2}),
    ],
)
def test_malformed_success_does_not_fabricate_data(command, method, payload):
    client = berimond_client({command: xt_packet(command, payload)})
    before = client.events.running
    with pytest.raises(PacketError):
        getattr(client.events, method)()
    assert client.events.running == before


@pytest.mark.parametrize("command,method", [("afd", "get_berimond_targets"), ("fgb", "get_berimond_balance")])
@pytest.mark.parametrize("error", [145, EmpireTimeoutError("late"), ConnectionClosedError("gone")])
def test_read_failures_keep_their_typed_error_and_event(command, method, error):
    client = berimond_client({command: xt_packet(command, error_code=error) if isinstance(error, int) else error})
    before = client.events.running
    with pytest.raises(CommandError if isinstance(error, int) else type(error)):
        getattr(client.events, method)(timeout=0.1)
    assert client.events.running == before


@pytest.mark.parametrize("method", ["get_berimond_targets", "get_berimond_balance"])
def test_inactive_event_refuses_read_before_sending(method):
    client = make_client({}, state=GameState())
    with pytest.raises(EventNotRunningError):
        getattr(client.events, method)()
    assert conn(client).request_payloads == []
