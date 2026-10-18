"""Raid controls return acknowledgements; status comes from bse/bbs."""

import pytest

from empire_core.exceptions import CommandError, EmpireTimeoutError, EventNotRunningError, PacketError
from empire_core.state.manager import GameState
from tests.events.test_alliance_status import raid_payload, status_client
from tests.service_helpers import conn, make_client, xt_packet


@pytest.mark.parametrize(
    "method,command,args,payload",
    [
        ("select_raid_boss", "srb", (98765,), {"BID": 98765}),
        ("abort_raid", "arb", (), {}),
    ],
)
def test_raid_control_payload_and_acknowledgement(method, command, args, payload):
    client = status_client({command: xt_packet(command)})
    before = client.events.running
    result = getattr(client.events, method)(*args)
    assert result.command == command
    assert conn(client).request_payloads == [(command, payload)]
    assert client.events.running == before


@pytest.mark.parametrize("method,args", [("select_raid_boss", (5,)), ("abort_raid", ())])
def test_raid_controls_require_running_event(method, args):
    client = make_client({}, state=GameState())
    with pytest.raises(EventNotRunningError):
        getattr(client.events, method)(*args)
    assert conn(client).request_payloads == []


@pytest.mark.parametrize("command,method,args", [("srb", "select_raid_boss", (5,)), ("arb", "abort_raid", ())])
@pytest.mark.parametrize("error", [145, EmpireTimeoutError("late")])
def test_raid_refusal_or_timeout_keeps_state(command, method, args, error):
    client = status_client({command: xt_packet(command, error_code=error) if isinstance(error, int) else error})
    before = client.events.running
    with pytest.raises(CommandError if isinstance(error, int) else EmpireTimeoutError):
        getattr(client.events, method)(*args)
    assert client.events.running == before


@pytest.mark.parametrize("boss_id", [0, -1])
def test_invalid_boss_id_is_not_sent(boss_id):
    client = status_client()
    with pytest.raises(ValueError):
        client.events.select_raid_boss(boss_id)
    assert conn(client).request_payloads == []


def test_unknown_generated_boss_id_is_selectable_when_server_card_is_available():
    client = status_client({"srb": xt_packet("srb")})
    client._on_packet(xt_packet("bbs", {"BCDS": [{"BID": 98765, "CST": 0, "ULV": 1}]}))
    client.events.select_raid_boss(98765)
    assert conn(client).request_payloads == [("srb", {"BID": 98765})]


@pytest.mark.parametrize("card_status", [1, 2, 3, 4, 98765])
def test_nonselectable_card_is_not_sent(card_status):
    client = status_client()
    client._on_packet(xt_packet("bbs", {"BCDS": [{"BID": 98765, "CST": card_status, "ULV": 1}]}))
    with pytest.raises(ValueError, match="available"):
        client.events.select_raid_boss(98765)
    assert conn(client).request_payloads == []


def test_final_playable_boss_cannot_be_aborted():
    client = status_client()
    client._on_packet(xt_packet("bbs", raid_payload(BCDS=[{"BID": 98765, "CST": 2, "ULV": 1}])))
    with pytest.raises(ValueError, match="last playable"):
        client.events.abort_raid()
    assert conn(client).request_payloads == []


def test_abort_does_not_clear_boss_and_later_broadcast_is_authoritative():
    client = status_client({"arb": xt_packet("arb")})
    client._on_packet(
        xt_packet(
            "bbs",
            raid_payload(
                BCDS=[
                    {"BID": 98765, "CST": 2, "ULV": 1},
                    {"BID": 5, "CST": 0, "ULV": 1},
                ]
            ),
        )
    )
    before = client.events.running[133]
    client.events.abort_raid()
    assert client.events.running[133] is before
    client._on_packet(xt_packet("bbs", {}))
    assert not client.events.running[133].boss_status.active


@pytest.mark.parametrize("command,method,args", [("srb", "select_raid_boss", (5,)), ("arb", "abort_raid", ())])
def test_unreadable_ack_is_not_success(command, method, args):
    client = status_client({command: xt_packet(command, "unreadable")})
    with pytest.raises(PacketError):
        getattr(client.events, method)(*args)
