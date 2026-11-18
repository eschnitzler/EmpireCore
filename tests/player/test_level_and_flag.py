"""Buying the next level and the premium flag with rubies: blv and gbp."""

import pytest

from empire_core.exceptions import CommandError
from empire_core.player import BuyLevelRequest, BuyLevelResponse, BuyPremiumFlagRequest, BuyPremiumFlagResponse
from empire_core.protocol.base import parse_response
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet


def at_level(level: int):
    return logged_in_state(gxp={"XP": 0, "LVL": level})


def test_the_models():
    assert BuyLevelRequest(new_level=21).to_payload() == {"NL": 21}
    assert BuyPremiumFlagRequest().to_payload() == {}
    assert isinstance(parse_response("blv", {}), BuyLevelResponse)
    assert isinstance(parse_response("gbp", {}), BuyPremiumFlagResponse)


def test_buying_a_level_sends_the_next_one():
    client = make_client(state=at_level(20))
    client.player.buy_level(spend_rubies=True)
    assert conn(client).request_payloads == [("blv", {"NL": 21})]


def test_buying_a_level_needs_consent():
    client = make_client(state=at_level(20))
    with pytest.raises(ValueError, match="spend_rubies"):
        client.player.buy_level()
    assert conn(client).request_payloads == []


@pytest.mark.parametrize("level", [9, 70])
def test_no_level_is_bought_outside_the_offered_range(level):
    client = make_client(state=at_level(level))
    with pytest.raises(ValueError, match="no level to buy"):
        client.player.buy_level(spend_rubies=True)
    assert conn(client).request_payloads == []


def test_a_refused_level_raises():
    client = make_client({"blv": xt_packet("blv", error_code=1)}, state=at_level(10))
    with pytest.raises(CommandError):
        client.player.buy_level(spend_rubies=True)


def test_the_premium_flag_needs_consent():
    client = make_client()
    with pytest.raises(ValueError, match="4900"):
        client.player.buy_premium_flag()
    assert conn(client).request_payloads == []


def test_the_premium_flag_sends_gbp():
    client = make_client()
    client.player.buy_premium_flag(spend_rubies=True)
    assert conn(client).request_payloads == [("gbp", {})]
