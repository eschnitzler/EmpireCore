"""Asking for your VIP status: vip."""

import pytest

from empire_core.exceptions import CommandError
from empire_core.player import VipStatusRequest, VipStatusResponse
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet


def test_the_request_is_empty():
    assert VipStatusRequest().to_payload() == {}


def test_the_reply_is_returned_and_applied_to_your_player():
    state = logged_in_state(vip={"VP": 2, "VRL": 3, "VRS": 0, "UPG": 0})
    client = make_client({"vip": xt_packet("vip", {"VP": 9000, "VRL": 5, "VRS": 3500, "UPG": 1})}, state=state)
    conn(client).on_packet = lambda packet: state.update_from_packet(
        packet.command_id, packet.payload, packet.error_code
    )

    status = client.player.get_vip_status()

    assert conn(client).request_payloads == [("vip", {})]
    assert isinstance(status, VipStatusResponse)
    assert (status.vip_points, status.vip_level, status.vip_seconds_left) == (9000, 5, 3500)
    player = state.get_local_player()
    assert (player.vip_points, player.vip_level, player.used_premium_commanders) == (9000, 5, 1)


def test_a_refused_request_raises():
    client = make_client({"vip": xt_packet("vip", error_code=1)})
    with pytest.raises(CommandError):
        client.player.get_vip_status()
