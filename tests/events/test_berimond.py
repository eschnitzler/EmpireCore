"""Synthetic Battle for Berimond replies and pushes: afd, fgb, gfp, fsc and fki."""

import pytest

from empire_core.enums import GGEError
from empire_core.exceptions import (
    CommandError,
    ConnectionClosedError,
    EmpireTimeoutError,
    EventNotRunningError,
    PacketError,
)
from empire_core.gamedata import PrebuiltCastle
from empire_core.gamedata.ids.events import Event
from empire_core.state.manager import GameState
from tests.service_helpers import conn, logged_in_state, make_client, with_prebuilt_castles, xt_packet


def berimond_client(script=None):
    client = with_prebuilt_castles(make_client(script or {}, state=logged_in_state()))
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


def test_points_read_both_factions():
    client = berimond_client({"gfp": xt_packet("gfp", {"RFP": 1200, "BFP": "800"})})
    points = client.events.get_berimond_points(timeout=0.2)
    assert (points.red_points, points.blue_points) == (1200, 800)
    assert conn(client).request_payloads == [("gfp", {})]


def test_points_refusal_raises():
    client = berimond_client({"gfp": xt_packet("gfp", error_code=145)})
    with pytest.raises(CommandError):
        client.events.get_berimond_points(timeout=0.1)


def test_join_sends_the_camp_for_berimond():
    client = berimond_client({"fsc": xt_packet("fsc", {})})
    client.events.join_berimond(PrebuiltCastle.BERIMOND_SIMPLE_CAMP, timeout=0.2)
    assert conn(client).request_payloads == [("fsc", {"ID": 1, "PWR": 0, "OC2": 0, "SID": 10})]


def test_the_ruby_only_camp_goes_as_bought_with_rubies():
    client = berimond_client({"fsc": xt_packet("fsc", {})})
    client.events.join_berimond(PrebuiltCastle.BERIMOND_WARLORDS_CAMP, spend_rubies=True, timeout=0.2)
    assert conn(client).request_payloads == [("fsc", {"ID": 3, "PWR": 0, "OC2": 1, "SID": 10})]


def test_spend_rubies_pays_missing_resources():
    client = berimond_client({"fsc": xt_packet("fsc", {})})
    client.events.join_berimond(PrebuiltCastle.BERIMOND_SIMPLE_CAMP, spend_rubies=True, timeout=0.2)
    assert conn(client).request_payloads == [("fsc", {"ID": 1, "PWR": 1, "OC2": 0, "SID": 10})]


def test_the_ruby_only_camp_needs_consent_before_sending():
    client = berimond_client()
    with pytest.raises(ValueError, match="49000 rubies"):
        client.events.join_berimond(PrebuiltCastle.BERIMOND_WARLORDS_CAMP)
    assert conn(client).request_payloads == []


def test_a_camp_of_another_map_is_refused():
    client = berimond_client()
    with pytest.raises(ValueError, match="no Battle for Berimond camp"):
        client.events.join_berimond(PrebuiltCastle.UNDERWORLD_SIMPLE_CAMP)
    assert conn(client).request_payloads == []


def test_join_refused_during_last_man_standing_raises():
    client = berimond_client({"fsc": xt_packet("fsc", error_code=353)})
    with pytest.raises(CommandError) as refused:
        client.events.join_berimond(PrebuiltCastle.BERIMOND_SIMPLE_CAMP, timeout=0.1)
    assert refused.value.error is GGEError.FACTION_LAST_MAN_STANDING_ACTIVE


@pytest.mark.parametrize(
    "method,args", [("get_berimond_points", ()), ("join_berimond", (PrebuiltCastle.BERIMOND_SIMPLE_CAMP,))]
)
def test_points_and_join_need_the_running_event(method, args):
    client = make_client({}, state=GameState())
    with pytest.raises(EventNotRunningError):
        getattr(client.events, method)(*args)
    assert conn(client).request_payloads == []


FKI = {"BFLMS": 1, "RFLMS": 0, "PA": True, "BCR": "1", "RCR": None}


def test_kingdom_status_push_is_kept_on_the_event():
    client = berimond_client()
    assert client.events.berimond_kingdom_status is None
    client._on_packet(xt_packet("fki", FKI))
    status = client.events.berimond_kingdom_status
    assert status is not None
    assert (status.blue_last_man_standing, status.red_last_man_standing, status.active_in_event) == (True, False, True)
    assert (status.blue_capital_reachable, status.red_capital_reachable) == (True, False)


def test_kingdom_status_survives_a_new_event_entry():
    client = berimond_client()
    client._on_packet(xt_packet("fki", FKI))
    client._on_packet(xt_packet("sei", {"E": [{"EID": 3, "RS": 500, "UL": 1}]}))
    status = client.events.berimond_kingdom_status
    assert status is not None and status.blue_last_man_standing


def test_kingdom_status_needs_the_running_event_and_a_success():
    idle = make_client({}, state=GameState())
    idle._on_packet(xt_packet("fki", FKI))
    assert idle.events.berimond_kingdom_status is None

    refused = berimond_client()
    refused._on_packet(xt_packet("fki", FKI, error_code=1))
    assert refused.events.berimond_kingdom_status is None


def test_kingdom_status_inside_the_login_kpi_follows_the_sei():
    state = GameState()
    state.update_from_packet(
        "gbd",
        {"sei": {"E": [{"EID": 3, "RS": 600, "UL": 1}]}, "kpi": {"UL": [{"KID": 10, "U": 1, "C": 0}], "fki": FKI}},
    )
    event = state.get_event(Event.BATTLE_FOR_BERIMOND)
    assert event is not None and event.kingdom_status is not None
    assert event.kingdom_status.blue_capital_reachable
