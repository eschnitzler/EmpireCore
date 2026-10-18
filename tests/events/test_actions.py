"""Source-derived event action contracts."""

import pytest

from empire_core.exceptions import CommandError, EmpireTimeoutError, PacketError, ReplyMismatchError
from tests.events.test_alliance_status import status_client
from tests.service_helpers import conn, xt_packet


@pytest.mark.parametrize(
    "method,command,args,consent",
    [
        ("start_grand_tournament_quest", "saq", (2, 98765), {}),
        ("complete_grand_tournament_quest", "caq", (), {}),
        ("cancel_grand_tournament_quest", "caaq", (), {"spend_rubies": True}),
        ("reroll_grand_tournament_quest", "raq", (2, 98765), {}),
        ("skip_grand_tournament_cooldown", "scq", (2, 98765), {"spend_rubies": True}),
    ],
)
def test_quest_action_payload_and_nested_reply(method, command, args, consent):
    payload = {"aqs": {"EID": 129, "AQS": [{"QID": 98765, "PID": -1, "RS": 10}]}}
    client = status_client({command: xt_packet(command, payload)})
    before = client.events.running[129]
    result = getattr(client.events, method)(*args, **consent)
    expected = {"EID": 129, **({"S": 2, "QID": 98765} if args else {})}
    assert conn(client).request_payloads == [(command, expected)]
    assert result.status.slots[0].alliance_quest_id == 98765
    assert result.status.event_id == 129
    assert client.events.running[129].quest_status.slots == result.status.slots
    assert before.quest_status is None


@pytest.mark.parametrize(
    "method,args",
    [
        ("cancel_grand_tournament_quest", ()),
        ("skip_grand_tournament_cooldown", (0, 4)),
    ],
)
def test_premium_actions_require_explicit_consent(method, args):
    client = status_client()
    with pytest.raises(ValueError, match="spend_rubies=True"):
        getattr(client.events, method)(*args)
    assert conn(client).request_payloads == []


@pytest.mark.parametrize("payload", [{}, {"aqs": {}}, {"aqs": {"EID": 129, "AQS": {}}}])
def test_malformed_action_reply_keeps_status(payload):
    client = status_client({"caq": xt_packet("caq", payload)})
    before = client.events.running[129]
    with pytest.raises(PacketError):
        client.events.complete_grand_tournament_quest()
    assert client.events.running[129] is before


@pytest.mark.parametrize("error", [145, EmpireTimeoutError("late")])
def test_quest_action_failure_preserves_state(error):
    client = status_client({"caq": xt_packet("caq", error_code=error) if isinstance(error, int) else error})
    before = client.events.running[129]
    with pytest.raises(CommandError if isinstance(error, int) else EmpireTimeoutError):
        client.events.complete_grand_tournament_quest()
    assert client.events.running[129] is before


def test_wrong_event_action_reply_is_not_accepted():
    client = status_client({"caq": xt_packet("caq", {"aqs": {"EID": 133, "AQS": []}})})
    before = client.events.running
    with pytest.raises(EmpireTimeoutError):
        client.events.complete_grand_tournament_quest(timeout=0.1)
    assert client.events.running == before


@pytest.mark.parametrize("slot,quest", [(-1, 4), (0, -1)])
def test_invalid_slot_or_quest_is_not_sent(slot, quest):
    client = status_client()
    with pytest.raises(ValueError):
        client.events.start_grand_tournament_quest(slot, quest)
    assert conn(client).request_payloads == []


@pytest.mark.parametrize("change", ["event", "alliance", "same_alliance"])
def test_context_change_during_action_does_not_update_new_context(monkeypatch, change):
    client = status_client({"caq": xt_packet("caq", {"aqs": {"EID": 129, "AQS": []}})})
    from empire_core.state.models import Player

    client.state.local_player = Player.model_validate({"PID": 4, "AID": 77})
    connection = conn(client)
    resolve = connection._resolve

    def change_context(command):
        if change == "event":
            client._on_packet(xt_packet("see", {"EID": 129}))
            client._on_packet(xt_packet("sei", {"E": [{"EID": 129, "RS": 700, "A": {}, "SP": {}}]}))
        elif change == "same_alliance":
            client._on_packet(xt_packet("gbd", {"gal": {"AID": -1}}))
            client._on_packet(xt_packet("gbd", {"gal": {"AID": 77}}))
        else:
            from empire_core.state.models import Player

            client.state.local_player = Player.model_validate({"PID": 4, "AID": 88})
        return resolve(command)

    monkeypatch.setattr(connection, "_resolve", change_context)
    with pytest.raises(ReplyMismatchError):
        client.events.complete_grand_tournament_quest()
    assert client.events.running[129].quest_status is None


def test_action_receipt_does_not_overwrite_later_status_push():
    client = status_client({"caq": xt_packet("caq", {"aqs": {"EID": 129, "AQS": []}})})

    def apply_then_broadcast(packet):
        client._on_packet(packet)
        client._on_packet(xt_packet("aqs", {"EID": 129, "APC": 9, "AQS": [{"QID": 8, "PID": -1, "RS": 0}]}))

    conn(client).on_packet = apply_then_broadcast
    result = client.events.complete_grand_tournament_quest()
    assert result.status.slots == ()
    assert client.events.running[129].quest_status.slots[0].alliance_quest_id == 8


def test_action_with_string_event_id_does_not_update_numeric_event():
    client = status_client()
    client.state._begin_quest_action()
    try:
        client._on_packet(xt_packet("caq", {"aqs": {"EID": "129", "AQS": []}}))
    finally:
        client.state._end_quest_action()
    assert client.events.running[129].quest_status is None


def test_ordinary_event_refresh_keeps_pending_quest_action_context(monkeypatch):
    client = status_client({"caq": xt_packet("caq", {"aqs": {"EID": 129, "AQS": []}})})
    connection = conn(client)
    resolve = connection._resolve

    def refresh_event(command):
        client._on_packet(xt_packet("sei", {"E": [{"EID": 129, "RS": 590, "A": {}, "SP": {}}]}))
        return resolve(command)

    monkeypatch.setattr(connection, "_resolve", refresh_event)
    result = client.events.complete_grand_tournament_quest()
    assert result.status.slots == ()
    assert client.events.running[129].quest_status.slots == ()


def test_ranking_uses_grand_tournament_name():
    from empire_core.enums import RankingType

    assert RankingType.GRAND_TOURNAMENT == 84
    assert "ALLIANCE_MOBILISATION_EVENT" not in RankingType.__members__


def test_readded_event_with_identical_end_time_has_new_action_context(monkeypatch):
    monkeypatch.setattr("empire_core.state.events._clock", lambda: 1000.0)
    client = status_client({"caq": xt_packet("caq", {"aqs": {"EID": 129, "AQS": []}})})
    connection = conn(client)
    resolve = connection._resolve

    def replace_event(command):
        client._on_packet(xt_packet("see", {"EID": 129}))
        client._on_packet(xt_packet("sei", {"E": [{"EID": 129, "RS": 600, "A": {}, "SP": {}}]}))
        return resolve(command)

    monkeypatch.setattr(connection, "_resolve", replace_event)
    with pytest.raises(ReplyMismatchError):
        client.events.complete_grand_tournament_quest()
    assert client.events.running[129].quest_status is None
