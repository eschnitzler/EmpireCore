"""The ruby wishing well: start, finish, collect, upgrade and read it (rww)."""

from __future__ import annotations

import pytest

from empire_core.castle import WishingWellRequest, wishing_well_skip_rubies
from empire_core.enums import GGEError, WishingWellOption
from empire_core.exceptions import CommandError
from empire_core.state.manager import GameState
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

# WishingWellConst.calculateWishingWellSkipCost through the dialog's int(Math.max(0, ...)), run in node
CLIENT_SKIP_PRICES = [
    (0, 0),
    (59, 0),
    (60, 0),
    (119, 0),
    (120, 1),
    (3599, 29),
    (3600, 30),
    (86399, 719),
    (239880, 1999),
    (999999, 1999),
]


def replying(payload: dict, error_code: int = 0):
    return make_client({"rww": xt_packet("rww", payload, error_code=error_code)}, state=GameState())  # type: ignore[arg-type]


def test_the_options_are_the_client_constants():
    assert [option.value for option in WishingWellOption] == ["S", "SK", "C", "U", "UD"]


@pytest.mark.parametrize(("seconds", "rubies"), CLIENT_SKIP_PRICES)
def test_the_skip_price_matches_the_client(seconds, rubies):
    assert wishing_well_skip_rubies(seconds) == rubies


def test_the_request_keys_follow_the_client_order():
    payload = WishingWellRequest(option=WishingWellOption.UPGRADE, pay_with_rubies=True).to_payload()
    assert payload == {"PWR": 1, "_PO": -1, "WOP": "U"}
    assert list(payload) == ["PWR", "_PO", "WOP"]


def test_get_reads_the_well():
    client = replying({"L": 2, "RT": -1})
    well = client.castle.get_wishing_well()
    assert (well.level, well.is_ready_to_start) == (2, True)
    assert conn(client).request_payloads == [("rww", {"PWR": 0, "_PO": -1, "WOP": "UD"})]


def test_a_reply_updates_the_state_and_a_refused_one_does_not():
    state = GameState()
    state.update_from_packet("rww", {"L": 3, "RT": -1}, error_code=GGEError.NOT_ENOUGH_RESOURCES)
    assert state.get_wishing_well() is None
    state.update_from_packet("rww", {"L": 2, "RT": 600})
    well = state.get_wishing_well()
    assert well is not None and (well.level, well.is_running) == (2, True)


def test_start_needs_spend_rubies():
    client = make_client()
    with pytest.raises(ValueError, match="entry rubies"):
        client.castle.start_wishing_well()
    assert conn(client).request_payloads == []


def test_start_sends_s_with_consent():
    client = replying({"L": 2, "RT": 7200})
    assert client.castle.start_wishing_well(spend_rubies=True).is_running
    assert conn(client).request_payloads == [("rww", {"PWR": 0, "_PO": -1, "WOP": "S"})]


def test_finish_names_the_price_of_the_running_well():
    client = make_client(state=logged_in_state(rww={"L": 1, "RT": 3600}))
    with pytest.raises(ValueError, match=r"costs (29|30) rubies"):
        client.castle.finish_wishing_well()
    assert conn(client).request_payloads == []


def test_finish_without_a_known_well_still_needs_consent():
    client = make_client(state=GameState())
    with pytest.raises(ValueError, match="costs rubies"):
        client.castle.finish_wishing_well()
    assert conn(client).request_payloads == []


def test_finish_sends_sk_with_consent():
    client = replying({"L": 1, "RT": 0})
    assert client.castle.finish_wishing_well(spend_rubies=True).is_ready_to_collect
    assert conn(client).request_payloads == [("rww", {"PWR": 0, "_PO": -1, "WOP": "SK"})]


def test_collect_needs_no_consent():
    client = replying({"L": 1, "RT": -1})
    assert client.castle.collect_wishing_well().is_ready_to_start
    assert conn(client).request_payloads == [("rww", {"PWR": 0, "_PO": -1, "WOP": "C"})]


@pytest.mark.parametrize(("spend_rubies", "flag"), [(False, 0), (True, 1)])
def test_upgrade_pays_missing_resources_only_with_consent(spend_rubies, flag):
    client = replying({"L": 3, "RT": -1})
    assert client.castle.upgrade_wishing_well(spend_rubies=spend_rubies).level == 3
    assert conn(client).request_payloads == [("rww", {"PWR": flag, "_PO": -1, "WOP": "U"})]


def test_a_refusal_raises_and_leaves_state():
    client = replying({"W": 10, "S": 10}, error_code=GGEError.NOT_ENOUGH_RESOURCES)
    with pytest.raises(CommandError):
        client.castle.upgrade_wishing_well()
    assert client.castle.wishing_well is None
