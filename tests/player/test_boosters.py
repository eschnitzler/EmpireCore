"""Hiring boosters with rubies, and asking for the boosters."""

import pytest

from empire_core.enums import BoosterId
from empire_core.exceptions import CommandError
from empire_core.player import (
    BoosterInfoResponse,
    HireInstructorResponse,
    HireOverseerResponse,
)
from empire_core.protocol.base import parse_response
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

BOI = {"BO": [{"ID": 10, "L": 1, "RT": 86400}], "PA": 0, "SU": [1, -1], "ST": [], "bfs": None}


@pytest.mark.parametrize(
    "booster, command, payload",
    [
        (BoosterId.INSTRUCTOR, "bis", {"PO": -1}),
        (BoosterId.MARAUDER, "bms", {"PO": -1}),
        (BoosterId.CARAVAN_OVERLOADER, "bcs", {"PO": -1}),
        (BoosterId.RETURNING_SPEED, "brs", {"PO": -1}),
        (BoosterId.OVERSEER_WOOD, "ovs", {"T": 0, "PO": -1}),
        (BoosterId.OVERSEER_BEEF, "ovs", {"T": 5, "PO": -1}),
    ],
)
def test_each_hire_sends_its_command(booster, command, payload):
    client = make_client()
    client.player.hire_booster(booster, spend_rubies=True)
    assert conn(client).request_payloads == [(command, payload)]


def test_a_hire_sends_the_booster_sale():
    client = make_client()
    client.player.hire_booster(BoosterId.MARAUDER, spend_rubies=True, private_offer_id=77)
    assert conn(client).request_payloads == [("bms", {"PO": 77})]


def test_a_hire_needs_consent():
    client = make_client()
    with pytest.raises(ValueError, match="spend_rubies"):
        client.player.hire_booster(BoosterId.INSTRUCTOR)
    assert conn(client).request_payloads == []


@pytest.mark.parametrize("booster", [BoosterId.TAX, BoosterId.GLORY])
def test_boosters_not_hired_here_send_nothing(booster):
    client = make_client()
    with pytest.raises(ValueError):
        client.player.hire_booster(booster, spend_rubies=True)
    assert conn(client).request_payloads == []


def test_a_refused_hire_raises():
    client = make_client({"ovs": xt_packet("ovs", error_code=1)})
    with pytest.raises(CommandError):
        client.player.hire_booster(BoosterId.OVERSEER_FOOD, spend_rubies=True)


def test_the_hire_reply_brings_currencies_and_boosters():
    client = make_client({"ovs": xt_packet("ovs", {"gcu": {"C1": 100, "C2": 400}, "boi": BOI})})
    reply = client.player.hire_booster(BoosterId.OVERSEER_STONE, spend_rubies=True)
    assert isinstance(reply, HireOverseerResponse)
    assert reply.currencies is not None and reply.currencies.rubies == 400
    assert reply.boosts is not None and reply.boosts.booster(10) is not None


def test_the_instructor_reply_brings_the_production_area():
    reply = parse_response("bis", {"gcu": {"C1": 1, "C2": 2}, "boi": BOI, "gpa": {"P": 10}})
    assert isinstance(reply, HireInstructorResponse)
    assert reply.production_area is not None


def test_a_falsy_boi_is_skipped():
    reply = parse_response("bms", {"gcu": {"C1": 1, "C2": 2}, "boi": None})
    assert reply is not None and reply.boosts is None  # type: ignore[attr-defined]


def test_a_hire_reaches_the_boosts():
    state = logged_in_state()
    state.update_from_packet("bis", {"gcu": {"C1": 1, "C2": 2}, "boi": BOI})
    booster = state.get_boosts().booster(10)
    assert booster is not None and booster.level == 1


def test_get_boosts_sends_boi():
    client = make_client({"boi": xt_packet("boi", BOI)})
    reply = client.player.get_boosts()
    assert conn(client).request_payloads == [("boi", {})]
    assert isinstance(reply, BoosterInfoResponse) and reply.bought_unit_slots == 1
