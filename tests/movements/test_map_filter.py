"""Showing or hiding a kind of movement on the map: mvf."""

import pytest

from empire_core.enums import MovementFilter
from empire_core.exceptions import CommandError
from empire_core.movements import SetMovementFilterRequest
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet


@pytest.mark.parametrize(
    ("kind", "show", "payload"),
    [
        (MovementFilter.PLAYER_ATTACKS, True, {"FID": 0, "ACT": 1}),
        (MovementFilter.ALLIANCE_MEMBER_PLAYER_ATTACKS, False, {"FID": 1, "ACT": 0}),
        (MovementFilter.MARKET_BARROWS, True, {"FID": 2, "ACT": 1}),
    ],
)
def test_the_payload(kind, show, payload):
    assert SetMovementFilterRequest(kind=kind, show=show).to_payload() == payload


def test_the_reply_is_returned_and_kept():
    state = logged_in_state(mvf={"AFS": [0, 1, 2]})
    client = make_client({"mvf": xt_packet("mvf", {"AFS": [0, 1]})}, state=state)
    conn(client).on_packet = lambda packet: state.update_from_packet(
        packet.command_id, packet.payload, packet.error_code
    )

    filters = client.movements.set_map_filter(MovementFilter.MARKET_BARROWS, False)

    assert conn(client).request_payloads == [("mvf", {"FID": 2, "ACT": 0})]
    assert filters.active_filters == (0, 1)
    kept = client.movements.map_filter
    assert kept is not None and not kept.shows(MovementFilter.MARKET_BARROWS)


def test_a_refused_change_raises_and_keeps_the_filters():
    state = logged_in_state(mvf={"AFS": [2]})
    client = make_client({"mvf": xt_packet("mvf", error_code=1)}, state=state)
    conn(client).on_packet = lambda packet: state.update_from_packet(
        packet.command_id, packet.payload, packet.error_code
    )
    with pytest.raises(CommandError):
        client.movements.set_map_filter(MovementFilter.MARKET_BARROWS, False)
    kept = client.movements.map_filter
    assert kept is not None and kept.active_filters == (2,)
