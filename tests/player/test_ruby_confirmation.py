"""Server-driven confirmation of an explicitly authorized ruby purchase."""

import pytest

from empire_core.enums import GGEError
from empire_core.exceptions import CommandError, ConnectionClosedError, EmpireTimeoutError, PacketError
from empire_core.player import ActivateGlobalEffectBoostRequest
from tests.service_helpers import conn, global_effect_state, make_client, xt_packet


def challenge(payload):
    return xt_packet("agb", payload, error_code=GGEError.RUBY_CONFIRMATION_REQUIRED)


def test_authorized_purchase_confirms_server_price_once():
    client = make_client({"agb": [challenge({"GEID": 2, "CC2T": 2500}), xt_packet("agb")]}, state=global_effect_state())
    client.player.activate_global_effect_boost(2, spend_rubies=True)
    assert conn(client).request_payloads == [
        ("agb", {"GEID": 2}),
        ("agb", {"cmdID": "agb", "GEID": 2, "CC2T": 2500}),
    ]


def test_low_level_requests_do_not_confirm_without_consent():
    client = make_client({"agb": challenge({"GEID": 2, "CC2T": 2500})}, state=global_effect_state())
    with pytest.raises(CommandError) as caught:
        client.send(ActivateGlobalEffectBoostRequest(effect_id=2), wait=True)
    assert caught.value.error is GGEError.RUBY_CONFIRMATION_REQUIRED
    assert len(conn(client).request_payloads) == 1


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"GEID": 2},
        {"GEID": 2, "CC2T": "2500"},
        {"GEID": 2, "CC2T": True},
        {"GEID": 2, "CC2T": -1},
        {"GEID": 3, "CC2T": 2500},
        {"GEID": 2, "CC2T": 2500, "cmdID": "mps"},
    ],
)
def test_bad_confirmation_payload_never_spends(payload):
    client = make_client({"agb": challenge(payload)}, state=global_effect_state())
    with pytest.raises(PacketError):
        client.player.activate_global_effect_boost(2, spend_rubies=True)
    assert len(conn(client).request_payloads) == 1


@pytest.mark.parametrize(
    "reply, error",
    [
        (challenge({"GEID": 2, "CC2T": 2500}), CommandError),
        (xt_packet("agb", error_code=GGEError.NOT_ENOUGH_RUBIES), CommandError),
        (EmpireTimeoutError("uncertain purchase"), EmpireTimeoutError),
        (ConnectionClosedError("disconnected"), ConnectionClosedError),
    ],
)
def test_confirmation_failures_never_repeat(reply, error):
    client = make_client({"agb": [challenge({"GEID": 2, "CC2T": 2500}), reply]}, state=global_effect_state())
    with pytest.raises(error):
        client.player.activate_global_effect_boost(2, spend_rubies=True)
    assert len(conn(client).request_payloads) == 2


def test_other_purchase_services_use_shared_confirmation():
    from empire_core.enums import PeaceModeDuration

    client = make_client(
        {
            "mps": [
                xt_packet("mps", {"CD": 0, "CC2T": 5000}, error_code=GGEError.RUBY_CONFIRMATION_REQUIRED),
                xt_packet("mps"),
            ]
        },
        state=global_effect_state(),
    )
    client.player.start_peace_mode(PeaceModeDuration.DAYS_7, spend_rubies=True)
    assert conn(client).request_payloads[-1] == ("mps", {"CD": 0, "CC2T": 5000, "cmdID": "mps"})


def test_typed_response_and_server_extra_fields_are_preserved():
    from empire_core.player import ActivateGlobalEffectBoostResponse

    client = make_client(
        {
            "agb": [
                challenge({"GEID": 2, "CC2T": 2500, "proof": "server-value"}),
                xt_packet("agb"),
            ]
        },
        state=global_effect_state(),
    )
    result = client.request(
        ActivateGlobalEffectBoostRequest(effect_id=2),
        ActivateGlobalEffectBoostResponse,
        spend_rubies=True,
    )
    assert isinstance(result, ActivateGlobalEffectBoostResponse)
    assert conn(client).request_payloads[-1][1]["proof"] == "server-value"


def test_initial_request_and_confirmation_share_timeout_budget(monkeypatch):
    from types import SimpleNamespace

    from empire_core.client import client as client_module

    client = make_client({"agb": challenge({"GEID": 2, "CC2T": 2500})}, state=global_effect_state())
    times = iter([100.0, 101.0, 106.0])
    monkeypatch.setattr(client_module, "time", SimpleNamespace(monotonic=lambda: next(times)))
    with pytest.raises(EmpireTimeoutError):
        client.player.activate_global_effect_boost(2, spend_rubies=True, timeout=5)
    assert conn(client).request_payloads == [("agb", {"GEID": 2})]


def test_confirmation_is_never_sent_on_a_new_session(monkeypatch):
    client = make_client({"agb": challenge({"GEID": 2, "CC2T": 2500})}, state=global_effect_state())
    connection = conn(client)
    resolve = connection._resolve

    def reconnect(command):
        packet = resolve(command)
        connection.generation += 1
        return packet

    monkeypatch.setattr(connection, "_resolve", reconnect)
    with pytest.raises(ConnectionClosedError):
        client.player.activate_global_effect_boost(2, spend_rubies=True)
    assert connection.request_payloads == [("agb", {"GEID": 2})]


def test_server_null_fields_are_preserved_in_confirmation():
    client = make_client(
        {
            "agb": [
                challenge({"GEID": 2, "CC2T": 2500, "optional": None}),
                xt_packet("agb"),
            ]
        },
        state=global_effect_state(),
    )
    client.player.activate_global_effect_boost(2, spend_rubies=True)
    assert "optional" in conn(client).request_payloads[-1][1]
    assert conn(client).request_payloads[-1][1]["optional"] is None


def test_raw_packet_path_can_confirm_a_purchase():
    client = make_client(
        {
            "agb": [
                challenge({"GEID": 2, "CC2T": 2500}),
                xt_packet("agb"),
            ]
        },
        state=global_effect_state(),
    )
    reply = client.request_packet(
        ActivateGlobalEffectBoostRequest(effect_id=2),
        "agb",
        spend_rubies=True,
    )
    assert reply.error_code == 0
    assert conn(client).request_payloads[-1][1]["CC2T"] == 2500


def test_fire_and_forget_cannot_authorize_confirmation():
    client = make_client(state=global_effect_state())
    with pytest.raises(ValueError, match="wait=True"):
        client.send(ActivateGlobalEffectBoostRequest(effect_id=2), spend_rubies=True)
    assert conn(client).sent == []
    assert conn(client).request_payloads == []
