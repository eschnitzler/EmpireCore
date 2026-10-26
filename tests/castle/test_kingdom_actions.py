"""Unlocking a kingdom (ksc), relocating (rst), leaving the joined area (laa) and losing it (gtwara)."""

import pytest

from empire_core.castle import LeaveAreaRequest, RelocateCastleRequest, SelectKingdomCastleRequest
from empire_core.enums import Kingdom, KingdomDirection
from empire_core.exceptions import CommandError
from empire_core.gamedata import PrebuiltCastle
from empire_core.state.manager import GameState
from tests.service_helpers import (
    StubPlayer,
    StubState,
    conn,
    logged_in_state,
    make_client,
    request_payload,
    with_prebuilt_castles,
    xt_packet,
)


def test_select_kingdom_castle_keeps_the_client_key_order_and_int_flags():
    request = SelectKingdomCastleRequest(
        prebuilt_castle_id=PrebuiltCastle.ICE_KNIGHTLY_CASTLE,
        direction=KingdomDirection.EAST,
        ruby_castle=True,
        kingdom_id=Kingdom.ICE,
    )
    payload = request.to_payload()
    assert list(payload) == ["ID", "D", "PWR", "OC2", "SID"]
    assert payload == {"ID": 5, "D": 3, "PWR": 0, "OC2": 1, "SID": 2}


def unlock_client(script=None, level: int = 0):
    return with_prebuilt_castles(make_client(script, state=StubState(StubPlayer(level=level))))


def test_unlock_kingdom_sends_the_castle_s_kingdom_and_the_direction():
    client = unlock_client()
    client.castle.unlock_kingdom(PrebuiltCastle.SANDS_KNIGHTLY_CASTLE, KingdomDirection.NORTH)
    assert conn(client).request_payloads == [("ksc", {"ID": 8, "D": 1, "PWR": 0, "OC2": 0, "SID": 1})]


def test_storm_islands_go_without_a_direction_priced_by_their_selection():
    client = unlock_client()
    client.castle.unlock_kingdom(PrebuiltCastle.STORM_TIDE_OUTPOST)
    with pytest.raises(ValueError, match="59000 rubies"):
        client.castle.unlock_kingdom(PrebuiltCastle.STORM_BASTION)
    client.castle.unlock_kingdom(PrebuiltCastle.STORM_BASTION, spend_rubies=True)
    assert [payload for _, payload in conn(client).request_payloads] == [
        {"ID": 16, "D": 0, "PWR": 0, "OC2": 0, "SID": 4},
        {"ID": 18, "D": 0, "PWR": 0, "OC2": 1, "SID": 4},
    ]


def test_storm_islands_refuse_a_direction_and_ask_for_no_level():
    # onConfirmed always sends D 0; the island selection checks no minLevel (35 for these castles)
    client = unlock_client(level=10)
    with pytest.raises(ValueError, match="no direction"):
        client.castle.unlock_kingdom(PrebuiltCastle.STORM_TIDE_OUTPOST, KingdomDirection.NORTH)
    client.castle.unlock_kingdom(PrebuiltCastle.STORM_TIDE_OUTPOST)
    assert conn(client).request_payloads == [("ksc", {"ID": 16, "D": 0, "PWR": 0, "OC2": 0, "SID": 4})]


def test_another_kingdom_needs_a_direction():
    client = unlock_client()
    with pytest.raises(ValueError, match="direction"):
        client.castle.unlock_kingdom(PrebuiltCastle.FIRE_KNIGHTLY_CASTLE)
    assert conn(client).request_payloads == []


def test_the_ruby_only_castle_needs_consent_and_spend_rubies_pays_missing_resources():
    client = unlock_client()
    with pytest.raises(ValueError, match="29000 rubies"):
        client.castle.unlock_kingdom(PrebuiltCastle.ICE_LORDLY_CASTLE, KingdomDirection.WEST)
    client.castle.unlock_kingdom(PrebuiltCastle.ICE_LORDLY_CASTLE, KingdomDirection.WEST, spend_rubies=True)
    client.castle.unlock_kingdom(PrebuiltCastle.ICE_SIMPLE_CASTLE, KingdomDirection.WEST)
    client.castle.unlock_kingdom(PrebuiltCastle.ICE_SIMPLE_CASTLE, KingdomDirection.WEST, spend_rubies=True)
    assert [payload for _, payload in conn(client).request_payloads] == [
        {"ID": 6, "D": 2, "PWR": 0, "OC2": 1, "SID": 2},
        {"ID": 4, "D": 2, "PWR": 0, "OC2": 0, "SID": 2},
        {"ID": 4, "D": 2, "PWR": 1, "OC2": 0, "SID": 2},
    ]


@pytest.mark.parametrize(
    "castle",
    [
        PrebuiltCastle.UNDERWORLD_SIMPLE_CAMP,
        PrebuiltCastle.BERIMOND_SIMPLE_CAMP,
        PrebuiltCastle.OUTER_REALMS_ROYAL_KEEP_32,
    ],
)
def test_a_castle_that_starts_no_kingdom_is_refused(castle):
    client = unlock_client()
    with pytest.raises(ValueError, match="starts no kingdom"):
        client.castle.unlock_kingdom(castle, KingdomDirection.WEST)
    assert conn(client).request_payloads == []


def test_ruby_price_buys_a_castle_priced_in_resources_at_its_ruby_price():
    client = unlock_client()
    with pytest.raises(ValueError, match="10000 rubies"):
        client.castle.unlock_kingdom(PrebuiltCastle.ICE_SIMPLE_CASTLE, KingdomDirection.WEST, ruby_price=True)
    client.castle.unlock_kingdom(
        PrebuiltCastle.ICE_SIMPLE_CASTLE, KingdomDirection.WEST, ruby_price=True, spend_rubies=True
    )
    assert conn(client).request_payloads == [("ksc", {"ID": 4, "D": 2, "PWR": 0, "OC2": 1, "SID": 2})]


def test_ruby_price_on_a_castle_without_one_is_refused():
    client = unlock_client()
    with pytest.raises(ValueError, match="no ruby price"):
        client.castle.unlock_kingdom(PrebuiltCastle.STORM_TIDE_OUTPOST, ruby_price=True, spend_rubies=True)
    assert conn(client).request_payloads == []


def test_a_castle_above_your_level_is_refused():
    client = unlock_client(level=24)
    with pytest.raises(ValueError, match="needs level 25"):
        client.castle.unlock_kingdom(PrebuiltCastle.ICE_SIMPLE_CASTLE, KingdomDirection.WEST)
    assert conn(client).request_payloads == []


def test_a_refused_unlock_raises():
    client = unlock_client({"ksc": xt_packet("ksc", error_code=1)})
    with pytest.raises(CommandError):
        client.castle.unlock_kingdom(PrebuiltCastle.ICE_SIMPLE_CASTLE, KingdomDirection.SOUTH)


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
