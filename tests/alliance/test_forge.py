"""The alliance forge, from C2SRequestForgeCraftVO, FRCCommand and AllianceForgeConst."""

import pytest

from empire_core.alliance.models.forge import (
    ForgeCraftRequest,
    ForgeCraftResponse,
    relic_forge_coin_cost,
    relic_forge_ruby_cost,
)
from empire_core.exceptions import CommandError
from empire_core.state.manager import GameState
from empire_core.state.models import Player
from tests.service_helpers import conn, make_client, xt_packet

ALLIANCE = {"AID": 301, "N": "Guild", "MF": 1, "IF": 0, "SRFU": 2, "HRFU": 1}
RELIC_GEM = [5001, 1, 2, 300, [[10, 5, [1]]], 0]
ESL = {"E": 4, "TE": 50, "G": 10, "TG": 20}


def forge_state(*, legend_level: int = 0, able: int = 1) -> GameState:
    state = GameState()
    state.local_player = Player(PID=7, PN="Player", legendary_level=legend_level)
    state.update_from_packet("gal", {"AID": 301, "R": 0})
    state.update_from_packet("ain", {"A": {**ALLIANCE, "MF": able}})
    return state


def forge_client(reply, **kwargs):
    state = forge_state(**kwargs)
    client = make_client(
        {"frc": xt_packet("frc", reply[0], reply[1]) if isinstance(reply, tuple) else reply}, state=state
    )
    conn(client).on_packet = lambda packet: state.update_from_packet(
        packet.command_id, packet.payload, packet.error_code
    )
    return client, state


def test_request_flag_is_sent_as_number():
    assert ForgeCraftRequest().to_payload() == {"UPRAF": 0}
    assert ForgeCraftRequest(pay_with_rubies=True).to_payload() == {"UPRAF": 1}


def test_relic_forge_prices_follow_the_client_formulas():
    assert [relic_forge_coin_cost(n) for n in range(3)] == [60000, 90000, 135000]
    assert [relic_forge_ruby_cost(n) for n in range(3)] == [10000, 12500, 15625]


def test_reply_reads_the_item_branch_the_client_reads():
    ain = {"A": {**ALLIANCE, "SRFU": 3}}
    with_item = ForgeCraftResponse.model_validate({"ain": ain, "E": [1, 2, 1, 3], "GEM": 7, "esl": ESL})
    assert with_item.equipment is not None and with_item.gem_id is None and with_item.relic_gem is None
    relic = ForgeCraftResponse.model_validate({"ain": ain, "RGEM": RELIC_GEM, "GEM": 7})
    assert relic.relic_gem is not None and relic.relic_gem.gem_id == 5001 and relic.gem_id is None
    gem = ForgeCraftResponse.model_validate({"ain": ain, "GEM": "7"})
    assert gem.gem_id == 7 and gem.alliance.soft_relic_forge_uses == 3


def test_forge_crafts_and_applies_alliance_gem_and_space():
    client, state = forge_client(({"ain": {"A": {**ALLIANCE, "MF": 0}}, "GEM": 7, "esl": ESL}, 0))
    result = client.alliance.forge(timeout=0.2)
    assert result.gem_id == 7
    assert conn(client).request_payloads == [("frc", {"UPRAF": 0})]
    own = client.alliance.own_alliance
    assert own is not None and own.is_able_to_forge is False
    gems = state.get_gems()
    assert gems is not None and gems.amount(7) == 1
    space = state.get_inventory_space()
    assert space is not None and space.equipment_space == 4


def test_forge_relic_gem_joins_the_relic_gems():
    client, state = forge_client(({"ain": {"A": ALLIANCE}, "RGEM": RELIC_GEM}, 0), legend_level=1, able=0)
    client.alliance.forge(timeout=0.2)
    gems = state.get_gems()
    assert gems is not None and [gem.gem_id for gem in gems.relic_gems] == [5001]


def test_alliance_forge_needs_its_flag_and_takes_no_rubies():
    client, _ = forge_client(({"ain": {"A": ALLIANCE}}, 0), able=0)
    with pytest.raises(ValueError, match="cannot craft"):
        client.alliance.forge()
    with pytest.raises(ValueError, match="legend level"):
        client.alliance.forge(pay_with_rubies=True, spend_rubies=True)
    assert conn(client).request_payloads == []


def test_relic_forge_rubies_need_consent():
    client, _ = forge_client(({"ain": {"A": ALLIANCE}, "GEM": 7}, 0), legend_level=3, able=0)
    with pytest.raises(ValueError, match="12500 rubies"):
        client.alliance.forge(pay_with_rubies=True)
    assert conn(client).request_payloads == []
    client.alliance.forge(pay_with_rubies=True, spend_rubies=True, timeout=0.2)
    assert conn(client).request_payloads == [("frc", {"UPRAF": 1})]


def test_forge_refusal_raises_and_keeps_gems():
    client, state = forge_client(({"ain": {"A": ALLIANCE}, "GEM": 7}, 1))
    with pytest.raises(CommandError):
        client.alliance.forge(timeout=0.2)
    assert state.get_gems() is None
