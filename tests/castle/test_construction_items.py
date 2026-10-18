"""Construction inventory fixtures follow ConstructionItemData.updateInventory (bundle 22947)."""

from typing import Any

import pytest
from pydantic import ValidationError

from empire_core.castle.service import CastleService
from empire_core.exceptions import CommandError, EmpireTimeoutError
from empire_core.state.manager import GameState
from tests.service_helpers import conn, gcl_castles, make_client, xt_packet


def test_inventory_request_preserves_stacks_and_unknown_ids():
    client = make_client({"gii": xt_packet("gii", {"CI": [[1, 2], [99999999, 3]]})})
    inventory = client.castle.get_construction_items(timeout=1.25)
    assert [(s.construction_item_id, s.amount) for s in inventory.items] == [(1, 2), (99999999, 3)]
    assert conn(client).request_payloads == [("gii", {})]


def test_empty_inventory_is_typed_and_read_only():
    client = make_client({"gii": xt_packet("gii", {"CI": []})})
    inventory = client.castle.get_construction_items()
    assert inventory.items == ()
    with pytest.raises(ValidationError):
        inventory.__setattr__("items", ())


def test_malformed_inventory_entries_warn_and_cost_only_themselves(caplog):
    client = make_client({"gii": xt_packet("gii", {"CI": [[1, 2], None, [2], [3, "bad"], [99999999, 4]]})})
    inventory = client.castle.get_construction_items()
    assert [(s.construction_item_id, s.amount) for s in inventory.items] == [(1, 2), (99999999, 4)]
    assert "construction item" in caplog.text.lower()


@pytest.mark.parametrize("body", [{}, {"CI": None}, {"CI": {}}])
def test_missing_or_wrong_inventory_is_not_an_empty_success(body):
    from empire_core.exceptions import PacketError

    client = make_client({"gii": xt_packet("gii", body)})
    with pytest.raises(PacketError):
        client.castle.get_construction_items()


@pytest.mark.parametrize(
    "reply, error", [(xt_packet("gii", error_code=1), CommandError), (EmpireTimeoutError("late"), EmpireTimeoutError)]
)
def test_inventory_failures_propagate(reply, error):
    client = make_client({"gii": reply})
    with pytest.raises(error):
        client.castle.get_construction_items()


def test_inventory_state_only_changes_on_success_and_resets():
    state = GameState()
    try:
        service = CastleService(make_client(state=state))
        assert service.construction_items is None
        state.update_from_packet("gii", {"CI": [[1, 2]]})
        snapshot = service.construction_items
        assert snapshot is not None
        assert snapshot.items[0].amount == 2
        state.update_from_packet("gii", {"CI": [[1, 9]]}, error_code=1)
        assert service.construction_items is snapshot
        state.update_from_packet("gii", {"CI": None})
        assert service.construction_items is snapshot
        state.update_from_packet("gii", {"CI": []})
        empty = service.construction_items
        assert empty is not None and empty.items == ()
        assert snapshot.items[0].amount == 2
        state.reset()
        assert service.construction_items is None
    finally:
        state.shutdown()


# Action fixtures follow C2SReplace/Remove/DisassembleConstructionItemVO
# (bundle 79223-79285), and RPCCommand/CRICommand (123313/123255).
JOIN: dict[str, Any] = {
    "KID": 2,
    "gca": {"A": [1, 10, 20, 2001, 1001, 1, 1, 1, 0, 0, "Castle"], "CI": [{"OID": 55, "CIL": [{"CID": 1, "S": 0}]}]},
}
PLACED = {"CI": [{"OID": 55, "CIL": [{"CID": 99999999, "S": 0, "RS": 60}]}]}


@pytest.fixture
def action_client():
    from empire_core.enums import Kingdom
    from empire_core.gamedata import GameData

    state = GameState()
    client = make_client(
        {
            "jaa": xt_packet("jaa", JOIN),
            "rpc": xt_packet("rpc", PLACED),
            "cri": xt_packet("cri", {"CI": []}),
            "gii": xt_packet("gii", {"CI": [[1, 1]]}),
            "dci": xt_packet("dci", {"AMT": 2, "RIDS": [77, 99999999]}),
        },
        state=state,
    )
    state.castles = {castle.id: castle for castle in gcl_castles((2001, Kingdom.ICE))}
    client.game_data = GameData.parse("test", {"rewards": [{"rewardID": "77", "addC2": "15"}]})
    conn(client).on_packet = client._on_packet
    yield client
    state.shutdown()


@pytest.mark.parametrize("mode, wire", [("ADD", 0), ("REPLACE", 1), ("OVERWRITE", 2)])
def test_equip_modes_exact_context_and_reply_driven_state(action_client, mode, wire):
    from empire_core.castle import ConstructionItemMode

    client = action_client
    result = client.castle.equip_construction_item(2001, 55, 99999999, 0, mode=ConstructionItemMode[mode])
    assert result.items[0].items[0].construction_item_id == 99999999
    assert result.items[0].items[0].remaining_seconds == 60
    assert client.castle.placed_construction_items == result.items
    assert client.castle.construction_items.items[0].amount == 1
    assert conn(client).request_payloads == [
        ("jaa", {"CID": 2001, "KID": 2}),
        ("rpc", {"OID": 55, "CID": 99999999, "SID": 0, "M": wire, "KID": 2, "AID": 2001}),
        ("gii", {}),
    ]


def test_remove_uses_item_and_slot_and_replaces_entire_ci_list(action_client):
    client = action_client
    result = client.castle.remove_construction_item(2001, 55, 1, 0)
    assert result.items == ()
    assert client.castle.placed_construction_items == ()
    assert conn(client).request_payloads[1] == ("cri", {"OID": 55, "CID": 1, "SID": 0, "KID": 2, "AID": 2001})


def test_disassembly_resolves_rewards_and_refreshes_inventory(action_client):
    from empire_core.enums import CollectableKind

    client = action_client
    result = client.castle.disassemble_construction_item(2001, 1, amount=2)
    assert result.amount == 2
    assert result.reward_ids == (77, 99999999)
    assert [(reward.kind, reward.amount) for reward in result.rewards] == [(CollectableKind.RUBIES, 15)]
    assert conn(client).request_payloads == [
        ("jaa", {"CID": 2001, "KID": 2}),
        ("dci", {"CID": 1, "KID": 2, "AID": 2001, "LFID": -1, "AMT": 2}),
        ("gii", {}),
    ]
    assert client.castle.placed_construction_items[0].items[0].construction_item_id == 1


@pytest.mark.parametrize(
    "method, command, args",
    [
        ("equip_construction_item", "rpc", (2001, 55, 1, 0)),
        ("remove_construction_item", "cri", (2001, 55, 1, 0)),
        ("disassemble_construction_item", "dci", (2001, 1)),
    ],
)
@pytest.mark.parametrize("failure, error", [(1, CommandError), ("timeout", EmpireTimeoutError)])
def test_action_refusal_or_transport_does_not_mutate_or_refresh(action_client, method, command, args, failure, error):
    client = action_client
    conn(client).script[command] = xt_packet(command, error_code=1) if failure == 1 else EmpireTimeoutError("late")
    with pytest.raises(error):
        getattr(client.castle, method)(*args)
    assert client.castle.placed_construction_items[0].items[0].construction_item_id == 1
    assert client.castle.construction_items is None
    assert conn(client).requested == ["jaa", command]


def test_refresh_failure_keeps_successful_placement_and_invalidates_inventory(action_client, caplog):
    client = action_client
    client.state.update_from_packet("gii", {"CI": [[1, 9]]})
    conn(client).script["gii"] = EmpireTimeoutError("late refresh")
    result = client.castle.equip_construction_item(2001, 55, 99999999, 0)
    assert result.items[0].items[0].construction_item_id == 99999999
    assert client.castle.placed_construction_items == result.items
    assert client.castle.construction_items is None
    assert "inventory" in caplog.text.lower()


@pytest.mark.parametrize("switch", ["other_castle", "rejoin", "map"])
def test_concurrent_area_change_rejects_untagged_action_response(action_client, switch):
    from empire_core.exceptions import ReplyMismatchError

    client = action_client
    normal = conn(client).on_packet

    def change_area(packet):
        if packet.command_id == "rpc":
            if switch == "map":
                client.state.update_from_packet("gaa", {})
            else:
                joined = JOIN if switch == "rejoin" else {**JOIN, "gca": {**JOIN["gca"], "A": [1, 11, 21, 2002, 1001]}}
                client.state.update_from_packet("jaa", joined)
        normal(packet)

    conn(client).on_packet = change_area
    with pytest.raises(ReplyMismatchError):
        client.castle.equip_construction_item(2001, 55, 99999999, 0)
    if switch == "map":
        assert client.castle.placed_construction_items is None
    else:
        assert client.castle.placed_construction_items[0].items[0].construction_item_id == 1
    assert "gii" not in conn(client).requested


def test_delayed_bare_action_reply_cannot_change_joined_castle(action_client):
    client = action_client
    client.castle.join(2001)
    old = client.castle.placed_construction_items
    client.state.update_from_packet("rpc", PLACED)
    assert client.castle.placed_construction_items == old
    client.state.update_from_packet("nec", {"NCRS": 60, "LECT": 0, "CI": []})
    assert client.castle.placed_construction_items == ()
    assert old[0].items[0].construction_item_id == 1
    client.state.reset()
    assert client.castle.placed_construction_items is None


@pytest.mark.parametrize(
    "method, args, kwargs",
    [
        ("equip_construction_item", (2001, 55, 1, -1), {}),
        ("equip_construction_item", (2001, 55, 1, 0), {"mode": 3}),
        ("remove_construction_item", (2001, 55, 1, -1), {}),
        ("disassemble_construction_item", (2001, 1), {"amount": 0}),
    ],
)
def test_invalid_action_arguments_send_nothing(action_client, method, args, kwargs):
    client = action_client
    with pytest.raises(ValueError):
        getattr(client.castle, method)(*args, **kwargs)
    assert conn(client).requested == []


def test_malformed_placed_items_warn_instead_of_silently_disappearing(action_client, caplog):
    client = action_client
    conn(client).script["rpc"] = xt_packet("rpc", {"CI": [{"OID": 55, "CIL": [{"CID": 1}, {"CID": []}]}]})
    result = client.castle.equip_construction_item(2001, 55, 1, 0)
    assert len(result.items[0].items) == 1
    assert "placed construction item" in caplog.text.lower()


@pytest.mark.parametrize("method, command", [("equip_construction_item", "rpc"), ("remove_construction_item", "cri")])
@pytest.mark.parametrize("body", [{}, {"CI": None}, {"CI": {}}])
def test_malformed_action_result_is_not_empty_placement(action_client, method, command, body):
    from empire_core.exceptions import PacketError

    client = action_client
    conn(client).script[command] = xt_packet(command, body)
    with pytest.raises(PacketError):
        getattr(client.castle, method)(2001, 55, 1, 0)
    assert client.castle.placed_construction_items is None
    assert "gii" not in conn(client).requested


def test_failed_action_then_delayed_packet_keeps_placement(action_client):
    client = action_client
    conn(client).script["rpc"] = EmpireTimeoutError("late")
    with pytest.raises(EmpireTimeoutError):
        client.castle.equip_construction_item(2001, 55, 1, 0)
    client.state.update_from_packet("rpc", PLACED)
    assert client.castle.placed_construction_items[0].items[0].construction_item_id == 1


def test_placement_snapshots_cannot_mutate_state(action_client):
    client = action_client
    result = client.castle.equip_construction_item(2001, 55, 99999999, 0)
    snapshot = client.castle.placed_construction_items
    snapshot[0].items[0].slot = 9
    result.items[0].items[0].slot = 8
    assert client.castle.placed_construction_items[0].items[0].slot == 0


def test_disassembly_lost_and_found_and_default_amount(action_client):
    client = action_client
    client.castle.disassemble_construction_item(2001, 1, lost_and_found_id=42)
    assert conn(client).request_payloads[1] == ("dci", {"CID": 1, "KID": 2, "AID": 2001, "LFID": 42, "AMT": 1})


def test_expiry_bad_ci_and_refusals_preserve_placement(action_client):
    client = action_client
    client.castle.join(2001)
    before = client.castle.placed_construction_items
    client.state.update_from_packet("nec", {"NCRS": 30, "CI": None})
    assert client.castle.placed_construction_items == before
    client.state.update_from_packet("nec", {"NCRS": 30, "CI": []}, error_code=1)
    assert client.castle.placed_construction_items == before


@pytest.mark.parametrize(
    "method, args",
    [
        ("equip_construction_item", (2001, 55, 1, 0)),
        ("remove_construction_item", (2001, 55, 1, 0)),
        ("disassemble_construction_item", (2001, 1)),
    ],
)
@pytest.mark.parametrize("wrong", ["castle", "kingdom"])
def test_wrong_join_response_prevents_the_action(action_client, method, args, wrong):
    from empire_core.exceptions import ReplyMismatchError

    client = action_client
    joined = {**JOIN, "KID": 0} if wrong == "kingdom" else {**JOIN, "gca": {"A": [1, 10, 20, 2002, 1001], "CI": []}}
    conn(client).script["jaa"] = xt_packet("jaa", joined)
    with pytest.raises(ReplyMismatchError):
        getattr(client.castle, method)(*args)
    assert conn(client).requested == ["jaa"]


@pytest.mark.parametrize("bad", [{"OID": 55}, {"OID": 55, "CIL": None}, {"OID": 55, "CIL": {}}])
def test_wrong_nested_placement_container_is_dropped_with_warning(action_client, caplog, bad):
    client = action_client
    conn(client).script["rpc"] = xt_packet("rpc", {"CI": [bad, {"OID": 56, "CIL": [{"CID": 1}]}]})
    result = client.castle.equip_construction_item(2001, 56, 1, 0)
    assert [entry.object_id for entry in result.items] == [56]
    assert "placed construction item" in caplog.text.lower()


def test_inventory_amount_uses_collectable_floor_and_keeps_duplicate_rows():
    # ACollectableItemVO.amount (bundle 3575); addItem combines only with its optional flag (1740).
    client = make_client({"gii": xt_packet("gii", {"CI": [[1, 2.9], [1, -1.1]]})})
    inventory = client.castle.get_construction_items()
    assert [(stack.construction_item_id, stack.amount) for stack in inventory.items] == [(1, 2), (1, -2)]


@pytest.mark.parametrize("area_command", ["jaa", "gaa"])
def test_construction_waits_for_concurrent_area_commands(action_client, monkeypatch, area_command):
    from concurrent.futures import ThreadPoolExecutor

    from empire_core.network.connection import Connection

    client = action_client
    locking = Connection("wss://example.invalid/")
    monkeypatch.setattr(conn(client), "command_lock", locking.command_lock)
    with locking.command_lock(area_command), ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(client.castle.equip_construction_item, 2001, 55, 1, 0, timeout=0.01)
        with pytest.raises(EmpireTimeoutError):
            future.result(timeout=1)
    assert conn(client).requested == []


@pytest.mark.parametrize("method, command", [("equip_construction_item", "rpc"), ("remove_construction_item", "cri")])
@pytest.mark.parametrize("expiry_after_reply", [True, False])
def test_placement_follows_receive_order_with_expiry_push(action_client, method, command, expiry_after_reply):
    client = action_client
    conn(client).script[command] = xt_packet(
        command, {"CI": [{"OID": 55, "CIL": [{"CID": 99999999, "S": 0, "RS": 1}]}]}
    )
    normal = conn(client).on_packet

    def with_expiry(packet):
        if packet.command_id == command and not expiry_after_reply:
            normal(xt_packet("nec", {"NCRS": 60, "LECT": 0, "CI": []}))
        normal(packet)
        if packet.command_id == command and expiry_after_reply:
            normal(xt_packet("nec", {"NCRS": 60, "LECT": 0, "CI": []}))

    conn(client).on_packet = with_expiry
    result = getattr(client.castle, method)(2001, 55, 99999999, 0)
    assert result.items[0].items[0].construction_item_id == 99999999
    snapshot = client.castle.placed_construction_items
    assert snapshot is not None
    if expiry_after_reply:
        assert snapshot == ()
    else:
        assert snapshot[0].items[0].construction_item_id == 99999999


@pytest.mark.parametrize(
    "method, command, args, body",
    [
        ("equip_construction_item", "rpc", (2001, 55, 1, 0), {"CI": None}),
        ("remove_construction_item", "cri", (2001, 55, 1, 0), {}),
        ("disassemble_construction_item", "dci", (2001, 1), {"RIDS": None}),
    ],
)
def test_accepted_malformed_action_invalidates_known_inventory(action_client, method, command, args, body):
    from empire_core.exceptions import PacketError

    client = action_client
    client.state.update_from_packet("gii", {"CI": [[1, 5]]})
    conn(client).script[command] = xt_packet(command, body)
    with pytest.raises(PacketError):
        getattr(client.castle, method)(*args)
    assert client.castle.construction_items is None
    if command == "dci":
        assert client.castle.placed_construction_items[0].items[0].construction_item_id == 1
    else:
        assert client.castle.placed_construction_items is None
    assert conn(client).requested == ["jaa", command]
    recovered = client.castle.get_construction_items()
    assert recovered.items[0].amount == 1
    assert client.castle.construction_items is recovered or client.castle.construction_items == recovered


@pytest.mark.parametrize(
    "method, command, args",
    [
        ("equip_construction_item", "rpc", (2001, 55, 1, 0)),
        ("remove_construction_item", "cri", (2001, 55, 1, 0)),
        ("disassemble_construction_item", "dci", (2001, 1)),
    ],
)
def test_refused_action_preserves_known_inventory(action_client, method, command, args):
    client = action_client
    client.state.update_from_packet("gii", {"CI": [[1, 5]]})
    before = client.castle.construction_items
    conn(client).script[command] = xt_packet(command, error_code=1)
    with pytest.raises(CommandError):
        getattr(client.castle, method)(*args)
    assert client.castle.construction_items is before


@pytest.mark.parametrize("method, command", [("equip_construction_item", "rpc"), ("remove_construction_item", "cri")])
@pytest.mark.parametrize("expiry_after_reply", [True, False])
def test_accepted_malformed_placement_is_unknown_unless_newer_expiry_arrived(
    action_client, method, command, expiry_after_reply
):
    from empire_core.exceptions import PacketError

    client = action_client
    conn(client).script[command] = xt_packet(command, {"CI": None})
    normal = conn(client).on_packet

    def with_expiry(packet):
        if packet.command_id == command and not expiry_after_reply:
            normal(xt_packet("nec", {"NCRS": 60, "LECT": 0, "CI": []}))
        normal(packet)
        if packet.command_id == command and expiry_after_reply:
            normal(xt_packet("nec", {"NCRS": 60, "LECT": 0, "CI": []}))

    conn(client).on_packet = with_expiry
    with pytest.raises(PacketError):
        getattr(client.castle, method)(2001, 55, 1, 0)
    assert client.castle.placed_construction_items == (() if expiry_after_reply else None)


@pytest.mark.parametrize("method, command", [("equip_construction_item", "rpc"), ("remove_construction_item", "cri")])
def test_accepted_malformed_placement_preserves_newer_join(action_client, method, command):
    from empire_core.exceptions import PacketError

    client = action_client
    conn(client).script[command] = xt_packet(command, {"CI": None})
    normal = conn(client).on_packet

    def with_join(packet):
        normal(packet)
        if packet.command_id == command:
            normal(xt_packet("jaa", JOIN))

    conn(client).on_packet = with_join
    with pytest.raises(PacketError):
        getattr(client.castle, method)(2001, 55, 1, 0)
    assert client.castle.placed_construction_items[0].items[0].construction_item_id == 1


def test_construction_space_push_and_inventory_capacity():
    state = GameState()
    try:
        service = CastleService(make_client(state=state))
        assert service.construction_item_space is None
        state.update_from_packet("csp", {"C": -4})
        snapshot = service.construction_item_space
        assert snapshot is not None and snapshot.space_left == -4
        state.update_from_packet("csp", {"C": "bad"})
        state.update_from_packet("csp", {"C": 90}, error_code=1)
        snapshot = service.construction_item_space
        assert snapshot is not None and snapshot.space_left == -4
        state.update_from_packet("gii", {"CI": [[1, 3]]})
        snapshot = service.construction_item_space
        assert snapshot is not None and snapshot.space_left == 4997
    finally:
        state.shutdown()


def test_expired_items_exact_list_payload_and_seen_request(action_client):
    client = action_client
    conn(client).script["aec"] = xt_packet(
        "aec", [{"AID": 2001, "KID": 2, "CIL": [{"CID": 99999999, "B": 17, "OID": 55}]}]
    )
    result = client.castle.get_expired_construction_items()
    assert result.areas[0].items[0].construction_item_id == 99999999
    assert client.castle.expired_construction_items == result
    client.castle.mark_expired_construction_items_seen(2001)
    assert conn(client).request_payloads == [("aec", {}), ("mec", {"AID": 2001})]
    # Viewing the list does not remove its expired records in the client.
    assert client.castle.expired_construction_items == result


@pytest.mark.parametrize("payload", [{}, {"CIL": []}, [None], [{"AID": 2001, "KID": 2, "CIL": [{}]}]])
def test_expired_malformed_is_not_fabricated_empty(action_client, payload):
    from empire_core.exceptions import PacketError

    client = action_client
    conn(client).script["aec"] = xt_packet("aec", payload)
    with pytest.raises(PacketError):
        client.castle.get_expired_construction_items()
    assert client.castle.expired_construction_items is None


def test_move_construction_slot_reorders_build_queue(action_client):
    client = action_client
    conn(client).script["scl"] = [
        xt_packet("scl", {"OIDL": [55, 66, -1, -2], "SSC": 1}),
        xt_packet("scl", {"OIDL": [66, 55, -1, -2], "SSC": 1}),
    ]
    result = client.castle.move_construction_slot(2001, 0, 1)
    assert result.building_object_ids == [66, 55]
    assert ("mci", {"OID": 55, "NS": 1}) in conn(client).request_payloads


@pytest.mark.parametrize("old,new", [(-1, 1), (0, -1), (5, 0), (0, 2), (0, 3), (2, 0), (3, 0)])
def test_move_rejects_free_locked_and_invalid_slots(action_client, old, new):
    client = action_client
    conn(client).script["scl"] = xt_packet("scl", {"OIDL": [55, 66, -1, -2], "SSC": 1})
    with pytest.raises(ValueError):
        client.castle.move_construction_slot(2001, old, new)
    assert "mci" not in conn(client).requested


def setup_booster(client, *, duration=3600, rarity=1, stock=1, seconds=120):
    from empire_core.gamedata import GameData
    from empire_core.state.models import Player

    client.game_data = GameData.parse(
        "test",
        {
            "constructionItems": [
                {"constructionItemID": "1", "duration": str(duration), "rarenessID": str(rarity)},
                {"constructionItemID": "2", "duration": "3600", "rarenessID": "2"},
            ],
            "currencies": [{"currencyID": "2000", "JSONKey": "TESTBOOST"}],
        },
    )
    client.state.local_player = Player(special_currencies={"TESTBOOST": stock})
    import copy

    join = copy.deepcopy(JOIN)
    join["gca"]["CI"][0]["CIL"][0]["RS"] = seconds
    conn(client).script["jaa"] = xt_packet("jaa", join)
    conn(client).script["ubc"] = xt_packet("ubc", {"CI": [{"OID": 55, "CIL": [{"CID": 2, "S": 0, "RS": 120}]}]})


def test_booster_uses_explicit_inventory_selection_and_placement(action_client):
    from empire_core.enums import CurrencyId

    client = action_client
    setup_booster(client)
    result = client.castle.boost_construction_item(2001, 55, 1, 0, consumable=CurrencyId(2000))
    assert result.items[0].items[0].construction_item_id == 2
    assert client.castle.placed_construction_items == result.items
    assert conn(client).request_payloads[-1] == (
        "ubc",
        {"OID": 55, "SUC": 2000, "SID": 0, "KID": 2, "AID": 2001, "CID": 1},
    )


@pytest.mark.parametrize("changes", [{"duration": 0}, {"rarity": 2}, {"stock": 0}, {"seconds": 0}])
def test_booster_refuses_ineligible_item_or_missing_inventory(action_client, changes):
    from empire_core.enums import CurrencyId

    setup_booster(action_client, **changes)
    with pytest.raises(ValueError):
        action_client.castle.boost_construction_item(2001, 55, 1, 0, consumable=CurrencyId(2000))
    assert "ubc" not in conn(action_client).requested


@pytest.mark.parametrize("consumable", [0, 1, 999999])
def test_booster_rejects_other_currencies_without_sending(action_client, consumable):
    with pytest.raises(ValueError):
        action_client.castle.boost_construction_item(2001, 55, 1, 0, consumable=consumable)
    assert conn(action_client).requested == []


@pytest.mark.parametrize("item,slot,object_id", [(99999999, 0, 55), (1, -1, 55), (1, 1, 55), (1, 0, 56)])
def test_booster_requires_exact_equipped_item(action_client, item, slot, object_id):
    from empire_core.enums import CurrencyId

    setup_booster(action_client)
    with pytest.raises(ValueError):
        action_client.castle.boost_construction_item(2001, object_id, item, slot, consumable=CurrencyId(2000))
    assert "ubc" not in conn(action_client).requested


@pytest.mark.parametrize("body", [{}, {"CI": None}, {"CI": [None]}, {"CI": [{"OID": 55, "CIL": [{}]}]}])
def test_booster_malformed_reply_never_fabricates_placement(action_client, body):
    from empire_core.enums import CurrencyId
    from empire_core.exceptions import PacketError

    setup_booster(action_client)
    conn(action_client).script["ubc"] = xt_packet("ubc", body)
    with pytest.raises(PacketError):
        action_client.castle.boost_construction_item(2001, 55, 1, 0, consumable=CurrencyId(2000))
    assert action_client.castle.placed_construction_items is None


@pytest.mark.parametrize(
    "reply,error", [(xt_packet("ubc", error_code=1), CommandError), (EmpireTimeoutError("late"), EmpireTimeoutError)]
)
def test_booster_failure_and_delayed_reply_keep_existing_placement(action_client, reply, error):
    from empire_core.enums import CurrencyId

    setup_booster(action_client)
    conn(action_client).script["ubc"] = reply
    with pytest.raises(error):
        action_client.castle.boost_construction_item(2001, 55, 1, 0, consumable=CurrencyId(2000))
    action_client.state.update_from_packet("ubc", PLACED)
    assert action_client.castle.placed_construction_items[0].items[0].construction_item_id == 1


@pytest.mark.parametrize("wrong", ["castle", "kingdom"])
def test_booster_wrong_join_refuses_mutation(action_client, wrong):
    from empire_core.enums import CurrencyId
    from empire_core.exceptions import ReplyMismatchError

    setup_booster(action_client)
    joined = {**JOIN, "KID": 0} if wrong == "kingdom" else {**JOIN, "gca": {"A": [1, 10, 20, 2002, 1001], "CI": []}}
    conn(action_client).script["jaa"] = xt_packet("jaa", joined)
    with pytest.raises(ReplyMismatchError):
        action_client.castle.boost_construction_item(2001, 55, 1, 0, consumable=CurrencyId(2000))
    assert conn(action_client).requested == ["jaa"]


@pytest.mark.parametrize("expiry_after_reply", [True, False])
def test_booster_placement_respects_receive_order(action_client, expiry_after_reply):
    from empire_core.enums import CurrencyId

    setup_booster(action_client)
    normal = conn(action_client).on_packet

    def with_expiry(packet):
        if packet.command_id == "ubc" and not expiry_after_reply:
            normal(xt_packet("nec", {"NCRS": 60, "LECT": 0, "CI": []}))
        normal(packet)
        if packet.command_id == "ubc" and expiry_after_reply:
            normal(xt_packet("nec", {"NCRS": 60, "LECT": 0, "CI": []}))

    conn(action_client).on_packet = with_expiry
    action_client.castle.boost_construction_item(2001, 55, 1, 0, consumable=CurrencyId(2000))
    if expiry_after_reply:
        assert action_client.castle.placed_construction_items == ()
    else:
        assert action_client.castle.placed_construction_items[0].items[0].construction_item_id == 2


@pytest.mark.parametrize("rows,expected", [([[1, 2.9], [1, -1.1]], 4998), ([[1, "2"], [2, 3]], 4977)])
def test_inventory_capacity_uses_client_raw_sum_before_truncation(rows, expected):
    state = GameState()
    try:
        state.update_from_packet("gii", {"CI": rows})
        capacity = state.get_construction_item_space()
        assert capacity is not None and capacity.space_left == expected
    finally:
        state.shutdown()


@pytest.mark.parametrize("stage", ["before", "after"])
def test_queue_move_rejects_malformed_queue_read(action_client, stage):
    from empire_core.exceptions import PacketError

    good = xt_packet("scl", {"OIDL": [55, 66], "SSC": 1})
    conn(action_client).script["scl"] = [xt_packet("scl", {})] if stage == "before" else [good, xt_packet("scl", {})]
    with pytest.raises(PacketError):
        action_client.castle.move_construction_slot(2001, 0, 1)
    assert ("mci" in conn(action_client).requested) == (stage == "after")


@pytest.mark.parametrize("switch", ["other_castle", "rejoin", "map"])
def test_booster_reply_cannot_overwrite_a_changed_castle_context(action_client, switch):
    from empire_core.enums import CurrencyId
    from empire_core.exceptions import ReplyMismatchError

    setup_booster(action_client)
    normal = conn(action_client).on_packet

    def change_area(packet):
        if packet.command_id == "ubc":
            if switch == "map":
                normal(xt_packet("gaa", {}))
            else:
                joined = JOIN if switch == "rejoin" else {**JOIN, "gca": {**JOIN["gca"], "A": [1, 11, 21, 2002, 1001]}}
                normal(xt_packet("jaa", joined))
        normal(packet)

    conn(action_client).on_packet = change_area
    with pytest.raises(ReplyMismatchError):
        action_client.castle.boost_construction_item(2001, 55, 1, 0, consumable=CurrencyId(2000))
    if switch == "map":
        assert action_client.castle.placed_construction_items is None
    else:
        assert action_client.castle.placed_construction_items[0].items[0].construction_item_id == 1


@pytest.mark.parametrize("command", ["aec", "mec", "mci"])
@pytest.mark.parametrize("failure", ["refused", "timeout"])
def test_remaining_construction_failures_propagate(action_client, command, failure):
    client = action_client
    conn(client).script[command] = (
        xt_packet(command, error_code=1) if failure == "refused" else EmpireTimeoutError("late")
    )
    conn(client).script["scl"] = xt_packet("scl", {"OIDL": [55, 66]})
    with pytest.raises(CommandError if failure == "refused" else EmpireTimeoutError):
        if command == "aec":
            client.castle.get_expired_construction_items()
        elif command == "mec":
            client.castle.mark_expired_construction_items_seen(2001)
        else:
            client.castle.move_construction_slot(2001, 0, 1)
    assert client.castle.expired_construction_items is None
