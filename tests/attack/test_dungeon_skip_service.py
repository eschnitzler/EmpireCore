"""Dungeon skip calls, using the client's msd/sdc payloads and AI replies."""

import pytest

from empire_core.enums import GGEError, Kingdom
from empire_core.exceptions import CommandError, ConnectionClosedError, EmpireTimeoutError, PacketError
from empire_core.gamedata import Currency
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet


@pytest.mark.parametrize("currency, key", [(Currency.SKIP_5_MINUTES, "MS2"), ("MS2", "MS2"), ("MS8", "MS8")])
def test_minute_skip_sends_inventory_key_and_returns_updated_camp(currency, key):
    client = make_client({"msd": xt_packet("msd", {"AI": [2, 100, 200, -1, 3, 540, 2]})})
    result = client.attack.minute_skip_dungeon(100, 200, currency, Kingdom.ICE)
    assert conn(client).request_payloads == [
        ("msd", {"X": 100, "Y": 200, "MID": -1, "NID": -1, "MST": key, "KID": "2"})
    ]
    assert (result.x, result.y, result.kingdom, result.attack_cooldown_seconds) == (100, 200, Kingdom.ICE, 540)


def test_full_skip_requires_ruby_consent_before_sending():
    client = make_client({"sdc": xt_packet("sdc", {"AI": [2, 100, 200, -1, 3, 0, 0]})})
    with pytest.raises(ValueError, match="spend_rubies=True"):
        client.attack.skip_dungeon_cooldown(100, 200)
    assert conn(client).request_payloads == []
    result = client.attack.skip_dungeon_cooldown(100, 200, spend_rubies=True)
    assert result.attack_cooldown_seconds == 0
    assert conn(client).request_payloads == [("sdc", {"X": 100, "Y": 200, "KID": 0, "MID": -1, "NID": -1})]


@pytest.mark.parametrize("command", ["msd", "sdc"])
def test_treasure_node_ids_are_explicit_and_paired(command):
    client = make_client({command: xt_packet(command, {"AI": [7, 5, 6, -1, 3, 0, 0]})})
    if command == "msd":
        result = client.attack.minute_skip_dungeon(5, 6, Currency.SKIP_1_MINUTE, map_id=3, node_id=12)
    else:
        result = client.attack.skip_dungeon_cooldown(5, 6, map_id=3, node_id=12, spend_rubies=True)
    assert (result.x, result.y) == (5, 6)
    payload = conn(client).request_payloads[0][1]
    assert (payload["MID"], payload["NID"]) == (3, 12)


@pytest.mark.parametrize("ids", [{"map_id": 3}, {"node_id": 12}, {"map_id": -2, "node_id": -2}])
@pytest.mark.parametrize("command", ["msd", "sdc"])
def test_incomplete_treasure_identity_does_not_send(command, ids):
    client = make_client()
    with pytest.raises(ValueError, match="map_id.*node_id"):
        if command == "msd":
            client.attack.minute_skip_dungeon(5, 6, "MS1", **ids)
        else:
            client.attack.skip_dungeon_cooldown(5, 6, spend_rubies=True, **ids)
    assert conn(client).request_payloads == []


def test_minute_skip_checks_currency_kind_and_known_holdings():
    state = GameState()
    state.update_from_packet("gbd", {"gpi": {"PID": 1, "PN": "Player"}})
    client = make_client(state=state)
    with pytest.raises(ValueError, match="minute skip"):
        client.attack.minute_skip_dungeon(1, 2, "C2")
    client.state.update_from_packet("sce", [["MS1", 0]])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="hold no"):
        client.attack.minute_skip_dungeon(1, 2, Currency.SKIP_1_MINUTE)
    assert conn(client).request_payloads == []


@pytest.mark.parametrize(
    "payload", [{}, {"AI": None}, {"AI": "broken"}, {"AI": []}, {"AI": [2, 100, 200]}, {"raw": "broken"}]
)
@pytest.mark.parametrize("command", ["msd", "sdc"])
def test_malformed_success_does_not_fabricate_a_camp(command, payload):
    client = make_client({command: xt_packet(command, payload)})
    with pytest.raises(PacketError):
        if command == "msd":
            client.attack.minute_skip_dungeon(100, 200, "MS1")
        else:
            client.attack.skip_dungeon_cooldown(100, 200, spend_rubies=True)


@pytest.mark.parametrize("command", ["msd", "sdc"])
@pytest.mark.parametrize("row", [[2, 101, 200, -1, 3, 0, 2], [2, 100, 200, -1, 3, 0, 1]])
def test_other_position_or_kingdom_does_not_satisfy_waiter(command, row):
    client = make_client({command: xt_packet(command, {"AI": row})})
    with pytest.raises(EmpireTimeoutError):
        if command == "msd":
            client.attack.minute_skip_dungeon(100, 200, "MS1", Kingdom.ICE)
        else:
            client.attack.skip_dungeon_cooldown(100, 200, Kingdom.ICE, spend_rubies=True)


@pytest.mark.parametrize("command", ["msd", "sdc"])
def test_refusal_keeps_typed_game_error(command):
    client = make_client({command: xt_packet(command, {}, error_code=int(GGEError.NOT_ENOUGH_RUBIES))})
    with pytest.raises(CommandError) as caught:
        if command == "msd":
            client.attack.minute_skip_dungeon(100, 200, "MS1")
        else:
            client.attack.skip_dungeon_cooldown(100, 200, spend_rubies=True)
    assert caught.value.error is GGEError.NOT_ENOUGH_RUBIES


@pytest.mark.parametrize("error", [EmpireTimeoutError("late"), ConnectionClosedError("closed")])
@pytest.mark.parametrize("command", ["msd", "sdc"])
def test_transport_error_identity_is_preserved(command, error):
    client = make_client({command: error})
    with pytest.raises(type(error)) as caught:
        if command == "msd":
            client.attack.minute_skip_dungeon(100, 200, "MS1")
        else:
            client.attack.skip_dungeon_cooldown(100, 200, spend_rubies=True)
    assert caught.value is error


@pytest.mark.parametrize("command", ["msd", "sdc"])
@pytest.mark.parametrize(
    "row", [[2, 100, 200, -1, 3, 0], [2, 100, 200, -1, 3, 0, None], [2, 100, 200, -1, 3, 0, "broken"]]
)
def test_missing_or_unreadable_wire_kingdom_cannot_be_fabricated(command, row):
    client = make_client({command: xt_packet(command, {"AI": row})})
    with pytest.raises(PacketError):
        if command == "msd":
            client.attack.minute_skip_dungeon(100, 200, "MS1", Kingdom.ICE)
        else:
            client.attack.skip_dungeon_cooldown(100, 200, Kingdom.ICE, spend_rubies=True)


@pytest.mark.parametrize("command", ["msd", "sdc"])
def test_numeric_string_kingdom_is_compared_before_accepting(command):
    client = make_client({command: xt_packet(command, {"AI": [2, 100, 200, -1, 3, 0, "1"]})})
    with pytest.raises(EmpireTimeoutError):
        if command == "msd":
            client.attack.minute_skip_dungeon(100, 200, "MS1", Kingdom.ICE)
        else:
            client.attack.skip_dungeon_cooldown(100, 200, Kingdom.ICE, spend_rubies=True)


@pytest.mark.parametrize("command", ["msd", "sdc"])
def test_matching_numeric_string_kingdom_returns_canonical_kingdom(command):
    client = make_client({command: xt_packet(command, {"AI": [2, 100, 200, -1, 3, 0, "2"]})})
    if command == "msd":
        result = client.attack.minute_skip_dungeon(100, 200, "MS1", Kingdom.ICE)
    else:
        result = client.attack.skip_dungeon_cooldown(100, 200, Kingdom.ICE, spend_rubies=True)
    assert result.kingdom is Kingdom.ICE
