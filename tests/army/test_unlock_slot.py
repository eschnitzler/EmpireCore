"""Unlocking a production slot with rubies."""

import pytest

from empire_core.army import ProductionListId
from empire_core.exceptions import CommandError
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

SPL = {"LID": 1, "SC": 0, "QS": [], "PS": [], "RM": 0}


def test_it_needs_consent():
    client = make_client()
    with pytest.raises(ValueError, match="spend_rubies"):
        client.army.unlock_production_slot(ProductionListId.TOOLS)
    assert conn(client).request_payloads == []


def test_it_sends_the_list():
    client = make_client({"ups": xt_packet("ups", {"spl": SPL, "gcu": {"C1": 10, "C2": 25}, "boi": {}})})
    reply = client.army.unlock_production_slot(ProductionListId.TOOLS, spend_rubies=True)
    assert conn(client).request_payloads == [("ups", {"LID": 1})]
    assert reply.currencies is not None and reply.currencies.rubies == 25
    assert reply.production_list is not None


def test_a_refusal_raises():
    client = make_client({"ups": xt_packet("ups", error_code=1)})
    with pytest.raises(CommandError):
        client.army.unlock_production_slot(ProductionListId.SOLDIERS, spend_rubies=True)


def test_the_slots_reach_the_boosts():
    state = logged_in_state()
    state.update_from_packet("ups", {"spl": SPL, "gcu": {"C1": 1, "C2": 2}, "boi": {"BO": [], "SU": [1, 1]}})
    assert state.get_boosts().bought_unit_slots == 2
