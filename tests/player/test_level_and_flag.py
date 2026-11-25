"""Buying the next level and the premium flag with rubies (blv and gbp), the level's price and the next might rank."""

import pytest

from empire_core.exceptions import CommandError
from empire_core.gamedata import GameData
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
    client = make_client(state=logged_in_state())
    with pytest.raises(ValueError, match="4900"):
        client.player.buy_premium_flag()
    assert conn(client).request_payloads == []


@pytest.mark.parametrize("gpf", [None, {"PF": 0}])
def test_the_premium_flag_sends_gbp_unless_you_own_it(gpf):
    client = make_client(state=logged_in_state(gpf=gpf))
    client.player.buy_premium_flag(spend_rubies=True)
    assert conn(client).request_payloads == [("gbp", {})]


def test_an_owned_premium_flag_is_not_bought_again():
    client = make_client(state=logged_in_state(gpf={"PF": 1}))
    with pytest.raises(ValueError, match="own the premium flag"):
        client.player.buy_premium_flag(spend_rubies=True)
    assert conn(client).request_payloads == []


def test_a_refused_premium_flag_raises():
    client = make_client({"gbp": xt_packet("gbp", error_code=1)}, state=logged_in_state())
    with pytest.raises(CommandError):
        client.player.buy_premium_flag(spend_rubies=True)


def test_the_level_price_comes_from_the_game_data():
    client = make_client(state=at_level(20))
    client.game_data = GameData.parse(
        "test", {"levelUpPrices": [{"levelUpPriceID": "20", "fromLevel": "20", "toLevel": "21", "c2Cost": "1490"}]}
    )

    assert client.player.buy_level_cost == 1490
    assert conn(client).request_payloads == []


def test_an_unpriced_level_costs_nothing_as_the_client_shows_it():
    client = make_client(state=at_level(20))
    client.game_data = GameData.parse("test", {})

    assert client.player.buy_level_cost == 0


MIGHT_RANKS = {"mightranks": [{"mightID": "1", "threshold": "500"}, {"mightID": "2", "threshold": "1000"}]}


@pytest.mark.parametrize(
    ("gmu", "rank", "to_go"),
    [
        ({"MP": 400, "TSBM": 0, "HMP": 600}, 2, 600),
        ({"MP": 400, "TSBM": 0, "HMP": 400}, 1, 100),
        ({"MP": 900, "TSBM": 0, "HMP": 1000}, None, 0),
    ],
)
def test_the_next_might_rank_follows_the_highest_might(gmu, rank, to_go):
    client = make_client(state=logged_in_state(gmu=gmu))
    client.game_data = GameData.parse("test", MIGHT_RANKS)

    next_rank = client.player.next_might_rank

    assert (next_rank.might_rank_id if next_rank else None, client.player.might_to_next_rank) == (rank, to_go)
    assert conn(client).request_payloads == []


def test_unreadable_might_has_no_distance_to_the_next_rank():
    client = make_client(state=logged_in_state(gmu={"MP": "x", "TSBM": 0, "HMP": 0}))
    client.game_data = GameData.parse("test", MIGHT_RANKS)

    assert client.player.might_to_next_rank is None
