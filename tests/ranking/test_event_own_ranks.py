"""Client-specific own ranks, Beyond the Horizon timers and player statistics."""

import pytest

from empire_core.exceptions import CommandError, ConnectionClosedError, EmpireTimeoutError
from tests.service_helpers import conn, make_client, xt_packet


def _running(client, event_id):
    from empire_core.state.manager import GameState

    client.state = GameState()
    client._on_packet(xt_packet("sei", {"E": [{"EID": event_id, "RS": 60}]}))


def test_horizon_own_rank_is_alliance_rank_only():
    client = make_client({"abgph": xt_packet("abgph", {"R": 8})})
    _running(client, 113)
    assert client.events.get_horizon_rank(alliance_id=45).alliance_rank == 8
    assert conn(client).request_payloads == [("abgph", {"AID": 45})]


def test_horizon_timers():
    client = make_client({"trt": xt_packet("trt", {"STNL": 41, "STNR": 82})})
    _running(client, 113)
    timers = client.events.get_horizon_timers()
    assert (timers.relink_seconds, timers.revive_seconds) == (41, 82)
    assert conn(client).request_payloads == [("trt", {})]


def test_player_event_performance_has_typed_statistics_and_unknown_ids():
    client = make_client(
        {"gpe": xt_packet("gpe", {"AMT": 123, "PST": [{"PSI": 1, "AMT": 18}, {"PSI": 98765, "AMT": 4}]})}
    )
    _running(client, 113)
    result = client.events.get_player_performance(113, player_id=78)
    assert result.points == 123
    assert [(s.statistic_id, s.amount) for s in result.statistics] == [(1, 18), (98765, 4)]
    assert result.amount(1) == 18 and result.amount(20) == 0
    assert conn(client).request_payloads == [("gpe", {"PID": 78, "EID": 113})]


def test_outer_realms_own_ranks_clamp_unranked_only():
    client = make_client({"tsh": xt_packet("tsh", {"DHS": 123, "DR": -1, "HS": 456, "R": 8})})
    _running(client, 106)
    result = client.events.get_outer_realms_ranks()
    assert (result.daily_points, result.daily_rank, result.overall_points, result.overall_rank) == (123, 0, 456, 8)
    assert conn(client).request_payloads == [("tsh", {})]


@pytest.mark.parametrize(
    "method,args",
    [
        ("get_horizon_rank", {"alliance_id": 45}),
        ("get_horizon_timers", {}),
        ("get_player_performance", {"event": 113, "player_id": 78}),
        ("get_outer_realms_ranks", {}),
    ],
)
def test_event_specific_reads_require_event_context(method, args):
    from empire_core.exceptions import EventNotRunningError

    client = make_client({})
    with pytest.raises(EventNotRunningError):
        getattr(client.events, method)(**args)
    assert conn(client).request_payloads == []


@pytest.mark.parametrize(
    "command,method,args,event",
    [
        ("abgph", "get_horizon_rank", {"alliance_id": 45}, 113),
        ("trt", "get_horizon_timers", {}, 113),
        ("gpe", "get_player_performance", {"event": 113, "player_id": 78}, 113),
        ("tsh", "get_outer_realms_ranks", {}, 106),
    ],
)
@pytest.mark.parametrize("error", [145, EmpireTimeoutError("late"), ConnectionClosedError("gone")])
def test_remaining_board_errors(command, method, args, event, error):
    client = make_client({command: xt_packet(command, error_code=error) if isinstance(error, int) else error})
    _running(client, event)
    expected = CommandError if isinstance(error, int) else type(error)
    with pytest.raises(expected):
        getattr(client.events, method)(**args, timeout=0.1)


def test_bad_performance_statistics_warn_and_missing_list_is_empty(caplog):
    client = make_client({"gpe": [xt_packet("gpe", {"AMT": 0, "PST": [None]}), xt_packet("gpe", {"AMT": 0})]})
    _running(client, 113)
    assert client.events.get_player_performance(113, player_id=1).statistics == ()
    assert "unreadable" in caplog.text
    assert client.events.get_player_performance(113, player_id=1).statistics == ()
