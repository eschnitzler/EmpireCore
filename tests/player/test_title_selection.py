"""Choosing the titles shown with your name: ste, as CastleTitleSelectDialog sends it and parseSTE reads it."""

import pytest

from empire_core.enums import GGEError, TitleSystem
from empire_core.exceptions import CommandError
from empire_core.player import SelectTitleRequest, SelectTitleResponse
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet


def _client(reply):
    return make_client({"ste": reply}, state=logged_in_state())  # type: ignore[arg-type]


def test_the_request():
    assert SelectTitleRequest(prefix=TitleSystem.FACTION).to_payload() == {"PRE": "FACTION", "SUF": ""}
    request = SelectTitleRequest(prefix=TitleSystem.GLORY, suffix=TitleSystem.ISLAND)
    assert request.to_payload() == {"PRE": "FAME", "SUF": "ISLE"}


def test_the_reply_may_be_empty():
    reply = SelectTitleResponse.model_validate({})
    assert (reply.prefix_system, reply.suffix_system) == (None, None)


def test_the_reply_updates_the_displayed_systems():
    client = _client(xt_packet("ste", {"PFX": "FACTION", "SFX": "ISLE"}))

    selected = client.player.select_titles(TitleSystem.FACTION, TitleSystem.ISLAND)

    assert conn(client).request_payloads == [("ste", {"PRE": "FACTION", "SUF": "ISLE"})]
    assert (selected.prefix_system, selected.suffix_system) == (TitleSystem.FACTION, TitleSystem.ISLAND)
    ranks = client.player.title_ranks
    assert (ranks.prefix_system, ranks.suffix_system) == (TitleSystem.FACTION, TitleSystem.ISLAND)


def test_a_system_the_reply_leaves_out_keeps_its_value():
    # parseSTE sets each only when it is truthy
    client = _client(xt_packet("ste", {"PFX": "FACTION", "SFX": ""}))

    client.player.select_titles(TitleSystem.FACTION)

    ranks = client.player.title_ranks
    assert (ranks.prefix_system, ranks.suffix_system) == (TitleSystem.FACTION, TitleSystem.GLORY)


def test_a_refusal_raises():
    client = _client(xt_packet("ste", {}, error_code=GGEError.TITLE_ON_COOLDOWN))

    with pytest.raises(CommandError) as raised:
        client.player.select_titles(TitleSystem.FACTION)

    assert raised.value.error is GGEError.TITLE_ON_COOLDOWN
    assert client.player.title_ranks.prefix_system is TitleSystem.GLORY
