"""Tests for client.events.get_own_points and the pep models."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.events import POINT_EVENTS, GetEventPointsRequest, GetEventPointsResponse
from empire_core.exceptions import CommandError, EmpireTimeoutError, EventHasNoPointsError, EventNotRunningError
from empire_core.gamedata.ids import Event
from empire_core.protocol.base import get_response_model
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet


def _running(script: dict[str, Any], *entries: dict[str, Any]):
    client = make_client(script, state=GameState())  # type: ignore[arg-type]
    client._on_packet(xt_packet("sei", {"E": [{"RS": 3600, **entry} for entry in entries]}))
    conn(client).on_packet = client._on_packet
    return client


class TestModels:
    def test_the_request(self):
        request = GetEventPointsRequest(event_id=3)

        assert request.get_command() == "pep"
        assert request.to_payload() == {"EID": 3}

    def test_a_reply_for_another_event_is_not_this_one(self):
        request = GetEventPointsRequest(event_id=80)

        assert request.accepts_reply({"EID": 80.0, "OR": [1], "OP": [2]})
        assert not request.accepts_reply({"EID": 3, "OR": [1], "OP": [2]})
        assert request.accepts_reply({})

    def test_the_reply_is_registered_for_pep(self):
        assert get_response_model("pep") is GetEventPointsResponse

    def test_the_lists_and_the_raid_boss_points(self):
        reply = GetEventPointsResponse.model_validate({"EID": 133, "OR": [8, "2"], "OP": [50.0, 700], "BLPP": 40})

        assert (reply.event_id, reply.own_ranks, reply.own_points) == (133, [8, 2], [50, 700])
        assert (reply.max_points, reply.boss_level_points) == (None, 40)

    def test_a_reply_without_scores(self):
        reply = GetEventPointsResponse.model_validate({"EID": 46})

        assert (reply.own_ranks, reply.own_points, reply.max_points, reply.boss_level_points) == ([], [], None, None)


class TestGetOwnPoints:
    def test_a_score_event(self):
        reply = {"EID": 60, "OR": [12], "OP": [3400], "PT": [9000]}
        client = _running({"pep": xt_packet("pep", reply)}, {"EID": 60, "LID": 2})

        points = client.events.get_own_points(Event.POINT_EVENT)

        assert conn(client).request_payloads == [("pep", {"EID": 60})]
        assert (points.own_ranks, points.own_points, points.max_points) == ([12], [3400], [9000])
        event = client.state.get_event(Event.POINT_EVENT)
        assert (event.own_rank, event.own_points, event.max_points) == (12, 3400, 9000)  # type: ignore[union-attr]

    def test_berimond_invasion_reads_a_value_per_part(self):
        reply = {"EID": 85, "OR": [1, 2, 3], "OP": [10, 20, 30], "PT": [7, 8, 9]}
        parts = {"FB": {"OP": 0}, "FR": {"OP": 0}, "A": {"OP": 0}}
        client = _running({"pep": xt_packet("pep", reply)}, {"EID": 85, **parts})

        points = client.events.get_own_points(Event.FACTION_INVASION)

        assert points.own_points == [10, 20, 30]
        event = client.state.get_event(Event.FACTION_INVASION)
        assert [(p.own_rank, p.own_points, p.max_points) for p in event.parts.values()] == [  # type: ignore[union-attr]
            (1, 10, 7),
            (2, 20, 8),
            (3, 30, 9),
        ]

    def test_an_event_without_a_scoreboard(self):
        reply = {"EID": 89, "OR": [4], "OP": [15]}
        client = _running({"pep": xt_packet("pep", reply)}, {"EID": 89})

        points = client.events.get_own_points(Event.SALE_DAYS_LUCKY_WHEEL)

        assert (points.own_ranks, points.own_points) == ([4], [15])

    def test_the_point_events_are_the_clients_classes_with_points(self):
        ids = {int(event) for event in POINT_EVENTS}
        assert ids == {3, 15, 36, 60, 62, 71, 72, 80, 83, 85, 89, 103, *range(126, 136)}

    def test_an_event_without_points_is_refused_unsent(self):
        client = _running({}, {"EID": 138}, {"EID": 125})

        with pytest.raises(EventHasNoPointsError, match=r"event 138 \(RAIDBOSS_SHOP_EVENT\)") as raised:
            client.events.get_own_points(Event.RAIDBOSS_SHOP_EVENT)
        with pytest.raises(EventHasNoPointsError, match="event 9999 keeps"):
            client.events.get_own_points(9999)
        assert raised.value.event_id == 138
        assert conn(client).request_payloads == []

    def test_an_event_that_is_not_running(self):
        client = _running({}, {"EID": 60})

        with pytest.raises(EventNotRunningError):
            client.events.get_own_points(Event.FACTION)
        assert conn(client).request_payloads == []

    def test_a_reply_for_another_event_is_left_to_its_waiter(self):
        client = _running({"pep": xt_packet("pep", {"EID": 3, "OR": [1], "OP": [5]})}, {"EID": 60})

        with pytest.raises(EmpireTimeoutError):
            client.events.get_own_points(Event.POINT_EVENT)

    def test_a_refusal_raises(self):
        client = _running({"pep": xt_packet("pep", {}, error_code=1)}, {"EID": 60})

        with pytest.raises(CommandError):
            client.events.get_own_points(Event.POINT_EVENT)
