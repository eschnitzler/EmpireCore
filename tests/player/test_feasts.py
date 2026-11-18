"""Holding a feast (bfs): what the client offers, the ruby consent and the reply reaching the boosts."""

from typing import Any

import pytest

from empire_core.enums import GGEError, Kingdom
from empire_core.exceptions import CommandError, UnknownCastleError
from empire_core.gamedata import Feast, GameData
from empire_core.player import HoldFeastRequest, HoldFeastResponse
from empire_core.protocol.base import parse_response
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

# The feasts rows as items 790.02 has them, trimmed to three
FEASTS = [
    {"feastID": "0", "productionBoost": "80", "duration": "3600", "costFood": "4000", "minLevel": 10,
     "maxLevel": "69", "type": "small", "sortOrder": "1"},
    {"feastID": "4", "productionBoost": "500", "duration": "900", "costC2": "1750", "minLevel": 10,
     "maxLevel": "69", "type": "ruby", "sortOrder": "2"},
    {"feastID": "5", "productionBoost": "150", "duration": "21600", "costFood": "25000", "minLevel": 70,
     "maxLevel": "1020", "type": "smallLevel2", "sortOrder": "1"},
]  # fmt: skip


def gcl(*castles: tuple[int, Kingdom]) -> dict[str, Any]:
    """A castle list of (castle id, kingdom) owned by the logged-in player."""
    blocks: dict[int, list[dict[str, Any]]] = {}
    for castle_id, kingdom in castles:
        row = [1, 10, 20, castle_id, 1001, 1, 1, 1, 0, 0, f"Castle {castle_id}"]
        blocks.setdefault(int(kingdom), []).append({"AI": row})
    return {"C": [{"KID": kid, "AI": rows} for kid, rows in blocks.items()]}


def client_with(*, level: int = 20, feast: dict[str, Any] | None = None, script: Any = None):
    state = logged_in_state(
        gcl=gcl((5, Kingdom.GREEN), (9, Kingdom.BERIMOND)),
        gxp={"LVL": level},
        boi={"BO": [], "PA": 0, "PT": -1, "bfs": feast},
    )
    client = make_client(script, state=state)
    client.game_data = GameData.parse("790.02", {"feasts": FEASTS})
    return client


def test_the_request_keys_follow_the_client():
    request = HoldFeastRequest(feast_id=Feast.COUNTRY_FEAST, castle_id=5, kingdom=Kingdom.ICE)
    assert request.to_payload() == {"T": 0, "CID": 5, "KID": 2, "PO": -1, "PWR": 0}


def test_a_food_feast_is_paid_from_the_castle():
    client = client_with()
    client.player.hold_feast(Feast.COUNTRY_FEAST, 5)
    assert conn(client).request_payloads == [("bfs", {"T": 0, "CID": 5, "KID": 0, "PO": -1, "PWR": 0})]


def test_consent_on_a_food_feast_pays_the_missing_food_with_rubies():
    client = client_with()
    client.player.hold_feast(Feast.COUNTRY_FEAST, 5, spend_rubies=True, private_offer_id=12)
    assert conn(client).request_payloads == [("bfs", {"T": 0, "CID": 5, "KID": 0, "PO": 12, "PWR": 1})]


def test_a_ruby_feast_needs_consent_and_sends_no_pwr():
    client = client_with()
    with pytest.raises(ValueError, match="1750 rubies"):
        client.player.hold_feast(Feast.IMPERIAL_BANQUET, 5)
    assert conn(client).request_payloads == []

    client.player.hold_feast(Feast.IMPERIAL_BANQUET, 5, spend_rubies=True)
    assert conn(client).request_payloads == [("bfs", {"T": 4, "CID": 5, "KID": 0, "PO": -1, "PWR": 0})]


@pytest.mark.parametrize("level, feast", [(9, Feast.COUNTRY_FEAST), (70, Feast.COUNTRY_FEAST), (69, Feast(5))])
def test_a_feast_outside_your_level_is_not_offered(level, feast):
    client = client_with(level=level)
    with pytest.raises(ValueError, match="offered from level"):
        client.player.hold_feast(feast, 5)
    assert conn(client).request_payloads == []


def test_a_castle_in_berimond_does_not_pay_for_a_feast():
    client = client_with()
    with pytest.raises(ValueError, match="Berimond"):
        client.player.hold_feast(Feast.COUNTRY_FEAST, 9)
    with pytest.raises(UnknownCastleError):
        client.player.hold_feast(Feast.COUNTRY_FEAST, 77)
    assert conn(client).request_payloads == []


def test_while_a_feast_runs_only_that_one_is_extended():
    client = client_with(feast={"T": 0, "RT": 600})
    with pytest.raises(ValueError, match="COUNTRY_FEAST: 0> runs"):
        client.player.hold_feast(Feast.IMPERIAL_BANQUET, 5, spend_rubies=True)

    client.player.hold_feast(Feast.COUNTRY_FEAST, 5)
    assert conn(client).request_payloads == [("bfs", {"T": 0, "CID": 5, "KID": 0, "PO": -1, "PWR": 0})]


def test_an_ended_feast_does_not_hold_back_another():
    client = client_with(feast={"T": 0, "RT": 0})
    client.player.hold_feast(Feast.IMPERIAL_BANQUET, 5, spend_rubies=True)
    assert [command for command, _ in conn(client).request_payloads] == ["bfs"]


def test_a_feast_outgrown_is_not_extended():
    client = client_with(level=70, feast={"T": 0, "RT": 600})
    with pytest.raises(ValueError, match="not at 70"):
        client.player.hold_feast(Feast.COUNTRY_FEAST, 5)
    assert conn(client).request_payloads == []


def test_a_refusal_raises():
    client = client_with(script={"bfs": xt_packet("bfs", error_code=GGEError.NOT_ENOUGH_RESOURCES)})
    with pytest.raises(CommandError) as refused:
        client.player.hold_feast(Feast.COUNTRY_FEAST, 5)
    assert refused.value.error is GGEError.NOT_ENOUGH_RESOURCES


def test_the_reply_is_the_feast_you_hold():
    client = client_with(script={"bfs": xt_packet("bfs", {"T": 0, "RT": 3600})})
    reply = client.player.hold_feast(Feast.COUNTRY_FEAST, 5)
    assert isinstance(reply, HoldFeastResponse)
    assert reply.feast_id is Feast.COUNTRY_FEAST and reply.is_active()


def test_the_reply_reaches_the_boosts():
    state = logged_in_state()
    state.update_from_packet("bfs", {"T": "4", "RT": 900})
    feast = state.get_boosts().feast
    assert feast is not None and feast.feast_id is Feast.IMPERIAL_BANQUET and feast.is_active()


def test_an_unknown_feast_id_is_kept():
    reply = parse_response("bfs", {"T": 99, "RT": 10})
    assert isinstance(reply, HoldFeastResponse) and reply.feast_id == 99
