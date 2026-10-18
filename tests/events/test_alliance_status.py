"""Alliance event read fixtures follow AQS/AQPC and raid-boss client parsers."""

import pytest

from empire_core.exceptions import (
    CommandError,
    ConnectionClosedError,
    EmpireTimeoutError,
    EventNotRunningError,
    PacketError,
)
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet


def status_client(script=None):
    client = make_client(script or {}, state=GameState())
    client._on_packet(
        xt_packet(
            "sei",
            {
                "E": [
                    {"EID": 129, "RS": 600, "A": {"LID": 1}, "SP": {}},
                    {"EID": 133, "RS": 600, "A": {"LID": 1}, "SP": {}},
                ]
            },
        )
    )
    conn(client).on_packet = client._on_packet
    return client


def test_grand_tournament_status_and_quest_progress_are_typed():
    client = status_client(
        {
            "aqs": xt_packet(
                "aqs",
                {
                    "EID": 129,
                    "APC": 4,
                    "AQS": [
                        {
                            "QID": 98765,
                            "PID": 23,
                            "PN": "Member",
                            "RS": 100,
                            "QL": [{"P": [2, 4], "QCS": "C", "RS": 30, "CQID": 4, "ST": 100}],
                        },
                        {"QID": -1, "PID": -1, "RS": 0, "QL": []},
                    ],
                },
            )
        }
    )
    before = client.events.running[129]
    result = client.events.get_grand_tournament_status()
    assert (result.event_id, result.participants) == (129, 4)
    slot, empty = result.slots
    assert (slot.slot_id, slot.alliance_quest_id, slot.player_id, slot.player_name, slot.remaining_seconds) == (
        0,
        98765,
        23,
        "Member",
        100,
    )
    assert slot.progress.counters == (2, 4) and slot.progress.completed
    assert (slot.progress.remaining_seconds, slot.progress.campaign_quest_id, slot.progress.campaign_timestamp) == (
        30,
        4,
        100,
    )
    assert empty.slot_id == 1 and empty.player_name == "" and empty.progress is None
    assert before.quest_status is None
    assert client.events.running[129].quest_status == result
    assert client.events.running[133] is not None
    assert conn(client).request_payloads == [("aqs", {"EID": 129})]


def test_empty_grand_tournament_slots_are_a_success():
    client = status_client({"aqs": xt_packet("aqs", {"EID": 129, "APC": 0, "AQS": []})})
    assert client.events.get_grand_tournament_status().slots == ()


def test_grand_tournament_skips_bad_slots_without_renumbering(caplog):
    client = status_client(
        {"aqs": xt_packet("aqs", {"EID": 129, "APC": 0, "AQS": [None, {"QID": 4, "PID": -1, "RS": 9}]})}
    )
    result = client.events.get_grand_tournament_status()
    assert result.slots[0].slot_id == 1
    assert "unreadable" in caplog.text


def test_grand_tournament_contributions():
    client = status_client({"aqpc": xt_packet("aqpc", {"AQPC": [{"R": 1, "PN": "Member", "OP": 44}]})})
    (row,) = client.events.get_grand_tournament_contributions()
    assert (row.rank, row.player_name, row.points) == (1, "Member", 44)
    assert conn(client).request_payloads == [("aqpc", {"EID": 129})]


@pytest.mark.parametrize("payload", [{"EID": 129, "APC": 0}, {"EID": 129, "APC": 0, "AQS": {}}])
def test_missing_or_wrong_shape_status_raises_and_keeps_prior_event(payload):
    client = status_client({"aqs": xt_packet("aqs", payload)})
    before = client.events.running[129]
    with pytest.raises(PacketError):
        client.events.get_grand_tournament_status()
    assert client.events.running[129] is before


def test_grand_tournament_different_event_reply_is_not_accepted_or_cached():
    client = status_client({"aqs": xt_packet("aqs", {"EID": 133, "APC": 4, "AQS": []})})
    before = client.events.running
    with pytest.raises(EmpireTimeoutError):
        client.events.get_grand_tournament_status(timeout=0.1)
    assert client.events.running == before
    client._on_packet(xt_packet("aqs", {"EID": 133, "APC": 4, "AQS": []}))
    assert client.events.running == before


@pytest.mark.parametrize(
    "command,method", [("aqs", "get_grand_tournament_status"), ("aqpc", "get_grand_tournament_contributions")]
)
@pytest.mark.parametrize("error", [145, EmpireTimeoutError("late"), ConnectionClosedError("gone")])
def test_grand_tournament_failures_do_not_mutate(command, method, error):
    client = status_client({command: xt_packet(command, error_code=error) if isinstance(error, int) else error})
    before = client.events.running
    with pytest.raises(CommandError if isinstance(error, int) else type(error)):
        getattr(client.events, method)(timeout=0.1)
    assert client.events.running == before


@pytest.mark.parametrize("method", ["get_grand_tournament_status", "get_grand_tournament_contributions"])
def test_inactive_grand_tournament_does_not_send(method):
    client = make_client({}, state=GameState())
    with pytest.raises(EventNotRunningError):
        getattr(client.events, method)()
    assert conn(client).request_payloads == []


def raid_payload(**updates):
    return {
        "BID": 98765,
        "BLID": 7,
        "HP": 55.001,
        "RUP": 20,
        "BS": 3,
        "BCDS": [{"BID": 98765, "CST": 2, "ULV": 4}],
        "WI": {
            "L": {"RT": 5, "PL": 10},
            "M": {"RT": 6, "PL": 20},
            "R": {"RT": 7, "PL": 30},
        },
        **updates,
    }


def test_raid_status_reads_current_boss_cards_health_and_walls():
    client = status_client({"bse": xt_packet("bse", raid_payload())})
    before = client.events.running[133]
    result = client.events.get_raid_boss_status()
    assert result.active and result.boss_id == 98765 and result.level_id == 7
    assert (result.health, result.revive_unit_percent, result.stage_id) == (55.01, 20, 3)
    assert (result.cards[0].boss_id, result.cards[0].status, result.cards[0].unlocked_level) == (98765, 2, 4)
    assert (result.walls.left.regeneration_seconds, result.walls.right.percent_left) == (5, 30)
    assert before.boss_status is None
    assert client.events.running[133].boss_status == result
    assert conn(client).request_payloads == [("bse", {})]


def test_raid_broadcast_preserves_identity_stage_and_walls_when_omitted():
    client = status_client()
    client._on_packet(xt_packet("bbs", raid_payload()))
    first = client.events.running[133]
    client._on_packet(xt_packet("bbs", {"BLID": 8, "HP": 44, "RUP": 30}))
    second = client.events.running[133]
    assert second is not first
    assert (second.boss_status.boss_id, second.boss_status.level_id, second.boss_status.stage_id) == (98765, 8, 3)
    assert second.boss_status.walls == first.boss_status.walls
    assert second.boss_status.cards == ()
    assert first.boss_status.health == 55.01
    assert client.events.running[129].quest_status is None


def test_raid_request_preserves_boss_identity_in_return_value():
    client = status_client({"bse": xt_packet("bse", {"BLID": 8, "HP": 44, "RUP": 30})})
    client._on_packet(xt_packet("bbs", raid_payload()))
    assert client.events.get_raid_boss_status().boss_id == 98765


def test_inactive_raid_clears_active_block_but_retains_walls_and_cards():
    client = status_client({"bse": xt_packet("bse", {"BCDS": [{"BID": 4, "CST": 0, "ULV": 2}]})})
    client._on_packet(xt_packet("bbs", raid_payload()))
    result = client.events.get_raid_boss_status()
    assert not result.active
    assert (result.boss_id, result.level_id, result.health, result.revive_unit_percent, result.stage_id) == (
        0,
        0,
        0,
        0,
        0,
    )
    assert result.cards[0].boss_id == 4 and result.walls is not None


def test_embedded_raid_status_in_sei_uses_same_model():
    client = status_client()
    client._on_packet(xt_packet("sei", {"E": [{"EID": 133, "RS": 600, "A": {}, "SP": {}, "BSE": raid_payload()}]}))
    assert client.events.running[133].boss_status.boss_id == 98765


@pytest.mark.parametrize("payload", [{"BID": 1}, raid_payload(WI=[]), raid_payload(BCDS={})])
def test_malformed_raid_preserves_event_and_raises(payload):
    client = status_client({"bse": xt_packet("bse", payload)})
    before = client.events.running[133]
    with pytest.raises(PacketError):
        client.events.get_raid_boss_status()
    assert client.events.running[133] is before


@pytest.mark.parametrize("command", ["bbs", "bse"])
def test_raid_status_error_pushes_and_no_event_are_ignored(command):
    client = status_client()
    before = client.events.running
    client._on_packet(xt_packet(command, raid_payload(), error_code=145))
    assert client.events.running == before
    client._on_packet(xt_packet("see", {"EID": 133}))
    client._on_packet(xt_packet(command, raid_payload()))
    assert 133 not in client.events.running and 129 in client.events.running


@pytest.mark.parametrize("error", [145, EmpireTimeoutError("late"), ConnectionClosedError("gone")])
def test_raid_failures_propagate_without_state_change(error):
    client = status_client({"bse": xt_packet("bse", error_code=error) if isinstance(error, int) else error})
    before = client.events.running
    with pytest.raises(CommandError if isinstance(error, int) else type(error)):
        client.events.get_raid_boss_status(timeout=0.1)
    assert client.events.running == before


def test_raid_without_event_does_not_send():
    client = make_client({}, state=GameState())
    with pytest.raises(EventNotRunningError):
        client.events.get_raid_boss_status()
    assert conn(client).request_payloads == []


def test_nonfinite_raid_health_raises_packet_error_and_keeps_event():
    client = status_client({"bse": xt_packet("bse", raid_payload(HP=float("inf")))})
    before = client.events.running[133]
    with pytest.raises(PacketError):
        client.events.get_raid_boss_status()
    assert client.events.running[133] is before


def test_bad_contributions_and_cards_warn_once_per_response(caplog):
    client = status_client(
        {
            "aqpc": xt_packet("aqpc", {"AQPC": [None, {}, {"R": 2, "PN": "B", "OP": 3}]}),
            "bse": xt_packet("bse", raid_payload(BCDS=[None, {}, {"BID": 1, "CST": 98765, "ULV": 2}])),
        }
    )
    assert len(client.events.get_grand_tournament_contributions()) == 1
    messages = [r.message for r in caplog.records if "unreadable Grand Tournament contributions" in r.message]
    assert len(messages) == 1 and "2/3" in messages[0]
    from empire_core.events import GetRaidBossStatusResponse

    result = GetRaidBossStatusResponse.model_validate(
        raid_payload(BCDS=[None, {}, {"BID": 1, "CST": 98765, "ULV": 2}])
    ).status
    assert result.cards[0].status == 98765
    messages = [r.message for r in caplog.records if "unreadable raid boss cards" in r.message]
    assert len(messages) == 1 and "2/3" in messages[0]


def test_empty_contributions_and_missing_contributions_differ():
    client = status_client({"aqpc": [xt_packet("aqpc", {"AQPC": []}), xt_packet("aqpc", {})]})
    assert client.events.get_grand_tournament_contributions() == ()
    with pytest.raises(PacketError):
        client.events.get_grand_tournament_contributions()


def test_unparseable_raid_packet_cannot_clear_active_boss():
    client = status_client({"bse": xt_packet("bse", "unreadable")})
    client._on_packet(xt_packet("bbs", raid_payload()))
    before = client.events.running[133]
    with pytest.raises(PacketError):
        client.events.get_raid_boss_status()
    assert client.events.running[133] is before


@pytest.mark.parametrize("later_broadcast", [False, True])
def test_raid_reply_uses_its_receipt_context_not_a_pre_request_or_later_snapshot(monkeypatch, later_broadcast):
    client = status_client({"bse": xt_packet("bse", {"BLID": 8, "HP": 44, "RUP": 30})})
    connection = conn(client)
    client._on_packet(xt_packet("bbs", raid_payload(BID=101, BS=3)))
    resolve = connection._resolve

    def resolve_after_broadcast(command):
        client._on_packet(xt_packet("bbs", raid_payload(BID=202, BS=4)))
        return resolve(command)

    def apply_reply(packet):
        client._on_packet(packet)
        if later_broadcast:
            client._on_packet(xt_packet("bbs", raid_payload(BID=303, BS=5, HP=66)))

    monkeypatch.setattr(connection, "_resolve", resolve_after_broadcast)
    connection.on_packet = apply_reply
    result = client.events.get_raid_boss_status()

    assert (result.boss_id, result.stage_id, result.level_id, result.health) == (202, 4, 8, 44)
    cached = client.events.running[133].boss_status
    assert (cached.boss_id, cached.stage_id) == ((303, 5) if later_broadcast else (202, 4))


@pytest.mark.parametrize(
    "walls",
    [
        {side: {"RT": 99, "PL": 99} for side in ("L", "M", "R")},
        {"unreadable": True},
        [],
        "unreadable",
    ],
)
def test_inactive_raid_ignores_supplied_walls_even_when_they_are_malformed(walls):
    client = status_client({"bse": xt_packet("bse", {"WI": walls})})
    client._on_packet(xt_packet("bbs", raid_payload()))
    previous = client.events.running[133].boss_status

    result = client.events.get_raid_boss_status()

    assert not result.active
    assert result.walls is previous.walls
    assert result.walls.left.percent_left == 10
    assert client.events.running[133].boss_status == result


@pytest.mark.parametrize("falsy", [None, False, 0, ""])
def test_raid_falsy_optional_walls_and_cards_follow_client_branches(falsy):
    client = status_client({"bse": xt_packet("bse", raid_payload(WI=falsy, BCDS=falsy, HP=44))})
    client._on_packet(xt_packet("bbs", raid_payload()))
    previous = client.events.running[133].boss_status

    result = client.events.get_raid_boss_status()

    assert result.active and result.health == 44
    assert result.walls is previous.walls
    assert result.cards == ()
    assert client.events.running[133].boss_status == result


def test_raid_timeout_drains_late_reply_before_next_request_with_real_connection(monkeypatch):
    import threading

    from empire_core.network.connection import Connection
    from tests.network.test_connection import RecordingSocket

    second_sent = threading.Event()

    class StatusSocket(RecordingSocket):
        def send(self, data):
            super().send(data)
            if len(self.sent) == 2:
                second_sent.set()

    client = status_client()
    connection = Connection("wss://example.invalid/")
    socket = StatusSocket()
    monkeypatch.setattr(connection, "ws", socket)
    connection._running = True
    connection.on_packet = client._on_packet
    client.connection = connection
    results = []
    failures = []
    started = threading.Event()

    def next_request():
        started.set()
        try:
            results.append(client.events.get_raid_boss_status(timeout=1))
        except Exception as error:
            failures.append(error)

    caller = threading.Thread(target=next_request)
    try:
        with pytest.raises(EmpireTimeoutError):
            client.events.get_raid_boss_status(timeout=0.3)
        caller.start()
        assert started.wait(1)
        sent_before_late_reply = second_sent.wait(0.04)
        connection._route_packet(xt_packet("bse", raid_payload(HP=11)))
        assert second_sent.wait(1)
        connection._route_packet(xt_packet("bse", raid_payload(HP=22)))
        caller.join(1)

        assert not sent_before_late_reply
        assert not caller.is_alive() and failures == []
        assert len(results) == 1 and results[0].health == 22
    finally:
        connection.disconnect()
        if caller.ident is not None:
            caller.join(2)
