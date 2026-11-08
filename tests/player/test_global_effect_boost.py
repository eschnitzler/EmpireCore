"""The global-effect ruby purchase and its separate bie state push."""

import pytest

from empire_core.exceptions import CommandError, ConnectionClosedError, EmpireTimeoutError
from empire_core.gamedata import GlobalEffect
from empire_core.player import ActivateGlobalEffectBoostRequest, ActivateGlobalEffectBoostResponse
from empire_core.protocol.base import parse_response
from tests.service_helpers import conn, global_effect_state, make_client, xt_packet


def test_requires_ruby_consent_before_sending():
    client = make_client(state=global_effect_state())
    with pytest.raises(ValueError, match="spend_rubies"):
        client.player.activate_global_effect_boost(GlobalEffect.SPEED_BOOST_2)
    assert conn(client).request_payloads == []


def test_purchase_acknowledgement_does_not_invent_boosted_state():
    client = make_client(state=global_effect_state())
    client.player.activate_global_effect_boost(GlobalEffect.SPEED_BOOST_2, spend_rubies=True)
    assert conn(client).request_payloads == [("agb", {"GEID": 2})]
    assert client.player.boosted_global_effects is None


def test_boosted_state_comes_from_bie_push():
    state = global_effect_state()
    client = make_client(state=state)
    client.player.activate_global_effect_boost(GlobalEffect.SPEED_BOOST_2, spend_rubies=True)
    state.update_from_packet("bie", {"GE": [2]})
    boosted = client.player.boosted_global_effects
    assert boosted is not None
    assert boosted.global_effect_ids == (GlobalEffect.SPEED_BOOST_2,)


@pytest.mark.parametrize(
    "reply, error_type",
    [
        (xt_packet("agb", error_code=1), CommandError),
        (EmpireTimeoutError("no acknowledgement"), EmpireTimeoutError),
        (ConnectionClosedError("disconnected"), ConnectionClosedError),
    ],
)
def test_purchase_failures_raise_without_retry(reply, error_type):
    client = make_client({"agb": reply}, state=global_effect_state())
    with pytest.raises(error_type):
        client.player.activate_global_effect_boost(GlobalEffect.SPEED_BOOST_2, spend_rubies=True)
    assert conn(client).request_payloads == [("agb", {"GEID": 2})]
    assert client.player.boosted_global_effects is None


def test_public_models_match_the_client_command():
    request = ActivateGlobalEffectBoostRequest(effect_id=GlobalEffect.SPEED_BOOST_2)
    assert request.command == "agb"
    assert request.to_payload() == {"GEID": 2}
    assert isinstance(parse_response("agb", {}), ActivateGlobalEffectBoostResponse)


def test_purchase_requires_a_running_booster_event():
    from empire_core.exceptions import EventNotRunningError
    from tests.service_helpers import logged_in_state

    client = make_client(state=logged_in_state())
    with pytest.raises(EventNotRunningError):
        client.player.activate_global_effect_boost(2, spend_rubies=True)
    assert conn(client).request_payloads == []


def test_purchase_requires_an_offered_effect():
    client = make_client(state=global_effect_state())
    with pytest.raises(ValueError, match="not offered"):
        client.player.activate_global_effect_boost(11, spend_rubies=True)
    assert conn(client).request_payloads == []


def test_ruby_consent_error_names_the_current_offer_price():
    client = make_client(state=global_effect_state())
    with pytest.raises(ValueError, match="2500"):
        client.player.activate_global_effect_boost(2)
    assert conn(client).request_payloads == []
