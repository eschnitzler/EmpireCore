"""Unlocking a kingdom (ksc), relocating (rst), leaving the joined area (laa) and losing it (gtwara)."""

import pytest

from empire_core.castle import LeaveAreaRequest, RelocateCastleRequest, SelectKingdomCastleRequest
from empire_core.enums import Kingdom, KingdomDirection
from empire_core.exceptions import CommandError
from empire_core.state.manager import GameState
from tests.service_helpers import conn, logged_in_state, make_client, request_payload, xt_packet


def test_select_kingdom_castle_keeps_the_client_key_order_and_int_flags():
    request = SelectKingdomCastleRequest(
        prebuilt_castle_id=5, direction=KingdomDirection.EAST, ruby_castle=True, kingdom_id=Kingdom.ICE
    )
    payload = request.to_payload()
    assert list(payload) == ["ID", "D", "PWR", "OC2", "SID"]
    assert payload == {"ID": 5, "D": 3, "PWR": 0, "OC2": 1, "SID": 2}


def test_unlock_kingdom_sends_the_direction_and_kingdom():
    client = make_client()
    client.castle.unlock_kingdom(Kingdom.SANDS, 8, KingdomDirection.NORTH)
    assert conn(client).request_payloads == [("ksc", {"ID": 8, "D": 1, "PWR": 0, "OC2": 0, "SID": 1})]


def test_storm_islands_go_without_a_direction():
    client = make_client()
    client.castle.unlock_kingdom(Kingdom.STORM, 16)
    assert conn(client).request_payloads == [("ksc", {"ID": 16, "D": 0, "PWR": 0, "OC2": 0, "SID": 4})]


def test_another_kingdom_needs_a_direction():
    client = make_client()
    with pytest.raises(ValueError, match="direction"):
        client.castle.unlock_kingdom(Kingdom.FIRE, 11)
    assert conn(client).request_payloads == []


def test_the_ruby_castle_needs_consent_and_spend_rubies_pays_missing_resources():
    client = make_client()
    with pytest.raises(ValueError, match="spend_rubies"):
        client.castle.unlock_kingdom(Kingdom.ICE, 6, KingdomDirection.WEST, ruby_castle=True)
    client.castle.unlock_kingdom(Kingdom.ICE, 6, KingdomDirection.WEST, ruby_castle=True, spend_rubies=True)
    client.castle.unlock_kingdom(Kingdom.ICE, 5, KingdomDirection.WEST, spend_rubies=True)
    assert [payload for _, payload in conn(client).request_payloads] == [
        {"ID": 6, "D": 2, "PWR": 0, "OC2": 1, "SID": 2},
        {"ID": 5, "D": 2, "PWR": 1, "OC2": 0, "SID": 2},
    ]


def test_a_refused_unlock_raises():
    client = make_client({"ksc": xt_packet("ksc", error_code=1)})
    with pytest.raises(CommandError):
        client.castle.unlock_kingdom(Kingdom.ICE, 4, KingdomDirection.SOUTH)


def test_relocate_sends_the_position():
    assert RelocateCastleRequest(x=300, y=400).to_payload() == {"PX": 300, "PY": 400}


def test_the_first_relocation_is_free():
    client = make_client(state=logged_in_state(gri={"RLC": 0, "RMC": 0, "RD": -1}))
    client.castle.relocate(300, 400)
    assert conn(client).request_payloads == [("rst", {"PX": 300, "PY": 400})]


@pytest.mark.parametrize(("count", "price"), [(1, 5000), (2, 20000), (3, 35000), (9, 35000)])
def test_a_later_relocation_needs_consent(count, price):
    client = make_client(state=logged_in_state(gri={"RLC": count, "RMC": 0, "RD": -1}))
    with pytest.raises(ValueError, match=f"{price} rubies"):
        client.castle.relocate(300, 400)
    assert conn(client).request_payloads == []
    client.castle.relocate(300, 400, spend_rubies=True)
    assert conn(client).request_payloads == [("rst", {"PX": 300, "PY": 400})]


def test_an_unknown_relocation_count_needs_consent():
    client = make_client(state=GameState())
    with pytest.raises(ValueError, match="spend_rubies"):
        client.castle.relocate(1, 2)


def test_a_refused_relocation_raises():
    # RSTCommand: CASTLE_HAS_MOVEMENTS while armies are on the way
    client = make_client({"rst": xt_packet("rst", error_code=212)}, state=logged_in_state(gri={"RLC": 0}))
    with pytest.raises(CommandError):
        client.castle.relocate(1, 2)


def test_leave_area_sends_laa_without_waiting():
    client = make_client()
    client.castle.leave_area()
    assert conn(client).requested == []
    (frame,) = conn(client).sent
    assert "%laa%" in frame and request_payload(frame) == {}
    assert LeaveAreaRequest().to_payload() == {}


def test_losing_the_joined_area_drops_its_mines_as_a_map_read_does():
    state = GameState()
    state.mines = {1: object()}  # type: ignore[dict-item]
    revision = state.area_revision
    state.update_from_packet("gtwara", {})
    assert state.mines == {} and state.area_revision == revision + 1
    state.mines = {1: object()}  # type: ignore[dict-item]
    state.update_from_packet("gtwara", {}, 1)
    assert state.mines != {}
