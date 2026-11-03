"""Offline source-session introduction regression tests for issue #596."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any
from unittest.mock import Mock

import pytest

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.enums import GGEError, ServerType
from empire_core.exceptions import (
    CommandError,
    ConnectionClosedError,
    EmpireTimeoutError,
    LoginError,
    NetworkError,
    PacketError,
)
from empire_core.network.connection import Connection
from tests.client.test_login_sequence import xt_packet
from tests.client.test_special_server import TOKEN_REPLY

ISSUE_ROW = [5023387889, 95, "12#106", "", -1, 6771, 0, 0, 0]


@pytest.fixture
def source(monkeypatch):
    """Real client, state and waiter router; only socket I/O and target login are fake."""
    client = EmpireClient(config=EmpireConfig(request_timeout=0.1, login_timeout=0.1))
    client.connection.ws = Mock(connected=True)
    client.connection._running = True
    client.is_logged_in = True
    calls: list[tuple[str, Any]] = []
    targets: list[EmpireClient] = []

    def send(frame):
        fields = frame.split("%")
        calls.append((fields[3], json.loads(fields[5])))

    def request(frame, command, timeout=5.0, *, expected_generation=None):
        assert expected_generation == client.connection.generation
        send(frame)
        return xt_packet(command, TOKEN_REPLY)

    close = client.close

    def recorded_close():
        calls.append(("close", None))
        close()

    def login(target):
        targets.append(target)
        calls.append(("login", None))

    monkeypatch.setattr(client.connection, "send", send)
    monkeypatch.setattr(client.connection, "request", request)
    monkeypatch.setattr(client, "close", recorded_close)
    monkeypatch.setattr(EmpireClient, "login", login)
    yield client, calls
    close()
    for target in targets:
        target.close()


def push(client, command, payload, error_code=0):
    client.connection._route_packet(xt_packet(command, payload, error_code))


def seed(client, quests=None, rows=None):
    push(client, "qli", {"QL": [{"QID": 3490}] if quests is None else quests})
    push(client, "sne", {"MSG": [ISSUE_ROW.copy()] if rows is None else rows})


def commands(calls):
    return [command for command, _ in calls]


def transfer(client, server_type=ServerType.OUTER_REALMS):
    return client.connect_to_special_server(server_type, timeout=0.2)


def refuse_token(client, monkeypatch):
    def refuse(*args, **kwargs):
        raise CommandError("glt", GGEError.NO_EVENT, {})

    monkeypatch.setattr(client.connection, "request", refuse)


def test_exact_issue_row_precedes_token_close_and_login(source):
    client, calls = source
    seed(client)
    transfer(client)
    assert calls == [
        ("qsc", {"QID": 3490}),
        ("mmr", {"MID": 5023387889}),
        ("glt", {"GST": 2}),
        ("close", None),
        ("login", None),
    ]
    assert not client.is_logged_in
    assert not client.connection.connected


@pytest.mark.parametrize(
    "quests",
    [
        [],
        [{"QID": 3491}],
        [{"QID": 3490, "S": 1}],
        [{"QID": 3490, "S": 0}],
        [{"QID": 3490, "QCS": "N"}],
        [{"QID": 3490, "RS": 0}],
    ],
    ids=["absent", "join-objective", "completed", "failed", "locked", "expired"],
)
def test_only_active_3490_is_acknowledged(source, quests):
    client, calls = source
    seed(client, quests=quests)
    transfer(client)
    assert commands(calls) == ["mmr", "glt", "close", "login"]


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [[1, 95, "12#106", "", -1, 0, 1]],
        [[1, 95, "garbage"]],
        [[1, 95, "12#no-event"]],
        [[1, 95, "12#113"]],
        [[1, 94, "12#106"]],
        [[1, 95, "11#106"]],
    ],
    ids=["missing", "read", "malformed", "invalid-event", "other-event", "other-type", "other-subtype"],
)
def test_nonmatching_or_read_mail_does_not_send_mmr(source, rows):
    client, calls = source
    seed(client, rows=rows)
    transfer(client)
    assert commands(calls) == ["qsc", "glt", "close", "login"]


@pytest.mark.parametrize("read", [0, 1])
def test_first_matching_archived_teaser_wins_over_later_unread(source, read):
    client, calls = source
    seed(client, rows=[[1, 95, "12#106", "", -1, 0, read, 1], [2, 95, "12#106"]])
    transfer(client)
    assert [payload for command, payload in calls if command == "mmr"] == ([] if read else [{"MID": 1}])


def test_horizon_needs_no_qli_and_never_invents_a_starter(source):
    client, calls = source
    push(client, "qst", {"QIDS": [3490, 3491]})
    push(client, "sne", {"MSG": [ISSUE_ROW, [2, 95, "12#113"]]})
    transfer(client, ServerType.HORIZON)
    assert calls[:2] == [("mmr", {"MID": 2}), ("glt", {"GST": 3})]
    assert commands(calls) == ["mmr", "glt", "close", "login"]


@pytest.mark.parametrize("quests", [[], [{"QID": 3490}]])
def test_delayed_qli_is_applied_before_waiter_wakes(source, monkeypatch, quests):
    client, calls = source
    registered = Event()
    original = client.connection.create_waiter

    def create(command, accepts=None):
        waiter = original(command, accepts)
        registered.set()
        return waiter

    monkeypatch.setattr(client.connection, "create_waiter", create)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(transfer, client)
        assert registered.wait(1)
        assert calls == []
        push(client, "qli", {"QL": quests})
        future.result(timeout=1)
    assert commands(calls) == (["qsc"] if quests else []) + ["glt", "close", "login"]
    assert not client.connection._waiters


def test_qli_between_initial_check_and_registration_is_not_lost(source, monkeypatch):
    client, calls = source
    original = client.connection.create_waiter

    def create(command, accepts=None):
        push(client, "qli", {"QL": [{"QID": 3490}]})
        return original(command, accepts)

    monkeypatch.setattr(client.connection, "create_waiter", create)
    transfer(client)
    assert commands(calls) == ["qsc", "glt", "close", "login"]
    assert not client.connection._waiters


def test_missing_qli_times_out_and_cancels_waiter_without_side_effects(source):
    client, calls = source
    with pytest.raises(EmpireTimeoutError):
        client.connect_to_special_server(ServerType.OUTER_REALMS, timeout=0.01)
    assert calls == []
    assert not client.connection._waiters
    assert client.is_logged_in and client.connection.connected


@pytest.mark.parametrize("malformed", [{"raw": "broken json"}, []])
def test_malformed_qli_does_not_satisfy_readiness(source, monkeypatch, malformed):
    client, calls = source
    original = client.connection.create_waiter
    count = 0

    def create(command, accepts=None):
        nonlocal count
        waiter = original(command, accepts)
        count += 1
        if count == 1:
            push(client, "qli", malformed)
        return waiter

    monkeypatch.setattr(client.connection, "create_waiter", create)
    with pytest.raises(EmpireTimeoutError):
        client.connect_to_special_server(ServerType.OUTER_REALMS, timeout=0.01)
    assert count == 2
    assert client.state.get_last_packet_time("qli") is None
    assert calls == []
    assert not client.connection._waiters


def test_error_qli_raises_command_error_without_transfer(source, monkeypatch):
    client, calls = source
    original = client.connection.create_waiter

    def create(command, accepts=None):
        waiter = original(command, accepts)
        push(client, "qli", {"QL": [{"QID": 3490}]}, GGEError.NO_EVENT)
        return waiter

    monkeypatch.setattr(client.connection, "create_waiter", create)
    with pytest.raises(CommandError) as caught:
        transfer(client)
    assert caught.value.error is GGEError.NO_EVENT
    assert calls == []
    assert client.state.get_last_packet_time("qli") is None
    assert not client.connection._waiters


@pytest.mark.parametrize("reconnect", [False, True])
def test_session_ending_while_waiting_never_transfers(source, monkeypatch, reconnect):
    client, calls = source
    registered = Event()
    original = client.connection.create_waiter

    def create(command, accepts=None):
        waiter = original(command, accepts)
        registered.set()
        return waiter

    monkeypatch.setattr(client.connection, "create_waiter", create)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(transfer, client)
        assert registered.wait(1)
        client.connection.disconnect()
        if reconnect:
            client.connection._generation += 1
            client.connection.ws = Mock(connected=True)
            client.connection._running = True
            push(client, "qli", {"QL": [{"QID": 3490}]})
        with pytest.raises(ConnectionClosedError):
            future.result(timeout=1)
    assert calls == []
    assert not client.connection._waiters


@pytest.mark.parametrize("change", ["logout", "disconnect", "reconnect"])
def test_source_is_checked_after_glt_before_close_or_target_login(source, monkeypatch, change):
    client, calls = source
    seed(client)
    original = client.connection.request

    def request(*args, **kwargs):
        token = original(*args, **kwargs)
        if change == "logout":
            client.is_logged_in = False
        elif change == "disconnect":
            client.connection.disconnect()
        else:
            client.connection._generation += 1
        return token

    monkeypatch.setattr(client.connection, "request", request)
    with pytest.raises(ConnectionClosedError):
        transfer(client)
    assert commands(calls) == ["qsc", "mmr", "glt"]


@pytest.mark.parametrize("failed_command", ["qsc", "mmr"])
def test_send_failure_stops_transfer_and_retry_keeps_successful_progress(source, monkeypatch, failed_command):
    client, calls = source
    seed(client)
    original = client.connection.send

    def send(frame):
        if frame.split("%")[3] == failed_command:
            raise NetworkError("offline send failure")
        original(frame)

    monkeypatch.setattr(client.connection, "send", send)
    with pytest.raises(NetworkError):
        transfer(client)
    assert commands(calls) == (["qsc"] if failed_command == "mmr" else [])
    assert not client.messages.mailbox[0].is_read
    assert client.is_logged_in and client.connection.connected
    monkeypatch.setattr(client.connection, "send", original)
    transfer(client)
    assert commands(calls) == ["qsc", "mmr", "glt", "close", "login"]


@pytest.mark.parametrize("replacement", ["same", "qli", "session"])
def test_token_retry_deduplicates_only_same_quest_in_same_session(source, monkeypatch, replacement):
    client, calls = source
    seed(client)
    quest = client.state.get_quest(3490)
    refuse_token(client, monkeypatch)
    with pytest.raises(CommandError):
        transfer(client)
    assert client.state.get_quest(3490) is quest
    assert client.messages.mailbox[0].is_read
    if replacement == "qli":
        push(client, "qli", {"QL": [{"QID": 3490}]})
    elif replacement == "session":
        client.connection._generation += 1
    with pytest.raises(CommandError):
        transfer(client)
    assert commands(calls) == ["qsc", "mmr"] + ([] if replacement == "same" else ["qsc"])
    assert client.is_logged_in and client.connection.connected


def test_failed_target_login_leaves_source_closed(source, monkeypatch):
    client, calls = source
    seed(client)

    def login(target):
        calls.append(("login", None))
        raise LoginError("target rejected login")

    monkeypatch.setattr(EmpireClient, "login", login)
    with pytest.raises(LoginError):
        transfer(client)
    assert commands(calls) == ["qsc", "mmr", "glt", "close", "login"]
    assert not client.is_logged_in and not client.connection.connected


@pytest.mark.parametrize("finish_first", [False, True])
def test_qst_only_resets_dedup_when_it_creates_a_new_quest(source, monkeypatch, finish_first):
    client, calls = source
    seed(client)
    refuse_token(client, monkeypatch)
    with pytest.raises(CommandError):
        transfer(client)
    quest = client.state.get_quest(3490)
    if finish_first:
        push(client, "qfi", {"QID": 3490})
    push(client, "qst", {"QIDS": [3490]})
    assert (client.state.get_quest(3490) is quest) is (not finish_first)
    with pytest.raises(CommandError):
        transfer(client)
    assert commands(calls) == ["qsc", "mmr"] + (["qsc"] if finish_first else [])


@pytest.mark.parametrize("logged_in,connected", [(False, True), (True, False), (False, False)])
def test_source_must_be_logged_in_and_connected(source, logged_in, connected):
    client, calls = source
    seed(client)
    client.is_logged_in = logged_in
    client.connection._running = connected
    with pytest.raises(ConnectionClosedError):
        transfer(client)
    assert calls == []
    assert not client.connection._waiters


def test_session_replaced_after_qli_before_acknowledgments(source, monkeypatch):
    client, calls = source
    seed(client)
    original = client.connection.run_if_current

    def run(generation, action):
        client.connection._generation += 1
        return original(generation, action)

    monkeypatch.setattr(client.connection, "run_if_current", run)
    with pytest.raises(ConnectionClosedError):
        transfer(client)
    assert calls == []


def test_malformed_then_valid_qli_can_recover_within_deadline(source, monkeypatch):
    client, calls = source
    original = client.connection.create_waiter
    count = 0

    def create(command, accepts=None):
        nonlocal count
        waiter = original(command, accepts)
        count += 1
        push(client, "qli", {"raw": "broken"} if count == 1 else {"QL": [{"QID": 3490}]})
        return waiter

    monkeypatch.setattr(client.connection, "create_waiter", create)
    transfer(client)
    assert count == 2
    assert commands(calls) == ["qsc", "glt", "close", "login"]
    assert not client.connection._waiters


def test_concurrent_transfers_serialize_preparation_and_token(source, monkeypatch):
    client, calls = source
    seed(client)
    token_started = Event()
    second_attempted = Event()
    release_token = Event()
    original_request = client.connection.request
    original_lock = client.connection.command_lock
    lock_count = 0

    def lock(command, timeout=5.0):
        nonlocal lock_count
        lock_count += 1
        if lock_count == 2:
            second_attempted.set()
        return original_lock(command, timeout=timeout)

    def request(*args, **kwargs):
        token_started.set()
        assert release_token.wait(1)
        return original_request(*args, **kwargs)

    monkeypatch.setattr(client.connection, "command_lock", lock)
    monkeypatch.setattr(client.connection, "request", request)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(transfer, client)
        try:
            assert token_started.wait(1)
            second = pool.submit(transfer, client)
            assert second_attempted.wait(1)
            assert commands(calls) == ["qsc", "mmr"]
        finally:
            release_token.set()
        first.result(timeout=1)
        with pytest.raises(ConnectionClosedError):
            second.result(timeout=1)
    assert commands(calls) == ["qsc", "mmr", "glt", "close", "login"]


def test_reconnect_after_preparation_prevents_glt_on_real_request_path(source, monkeypatch):
    client, calls = source
    seed(client)
    original = client._special_server_preparation.prepare

    def prepare(*args):
        generation = original(*args)
        client.connection._generation += 1
        return generation

    monkeypatch.setattr(client._special_server_preparation, "prepare", prepare)
    monkeypatch.setattr(client.connection, "request", Connection.request.__get__(client.connection))
    with pytest.raises(ConnectionClosedError):
        transfer(client)
    assert commands(calls) == ["qsc", "mmr"]
    assert client.connection.connected
    assert not client.connection._waiters


def test_generation_change_during_config_creation_never_closes_new_session(source, monkeypatch):
    client, calls = source
    seed(client)
    original = EmpireConfig.for_instance

    def config(*args, **kwargs):
        result = original(*args, **kwargs)
        client.connection._generation += 1
        return result

    monkeypatch.setattr(EmpireConfig, "for_instance", config)
    with pytest.raises(ConnectionClosedError):
        transfer(client)
    assert commands(calls) == ["qsc", "mmr", "glt"]
    assert client.is_logged_in and client.connection.connected
    assert not client._session._closed.is_set()


def test_drop_after_reserved_transfer_cannot_restart_keep_session(source, monkeypatch):
    client, calls = source
    seed(client)
    client.keep_session = True
    original = client.close
    restore = Mock()
    monkeypatch.setattr(client._session, "_restore", restore)

    def close():
        assert client._session._closed.is_set()
        generation = client.connection.generation
        client.connection.disconnect()
        client._session.dropped(generation)
        assert client._session._dropped_logged_in == generation
        client._session.after_drop(generation)
        assert not client._session._relogin_running
        assert client._session._relogin_thread is None
        original()

    monkeypatch.setattr(client, "close", close)
    transfer(client)
    restore.assert_not_called()
    assert commands(calls) == ["qsc", "mmr", "glt", "close", "login"]
    assert not client.is_logged_in and not client.connection.connected


@pytest.mark.parametrize("payload", [{}, {"TLT": "token-only"}, []])
def test_malformed_token_reply_raises_packet_error_and_preserves_source(source, monkeypatch, payload):
    client, calls = source
    seed(client)

    def request(frame, command, **kwargs):
        return xt_packet(command, payload)

    monkeypatch.setattr(client.connection, "request", request)
    with pytest.raises(PacketError):
        transfer(client)
    assert commands(calls) == ["qsc", "mmr"]
    assert client.is_logged_in and client.connection.connected


def test_token_error_packet_raises_command_error_and_preserves_source(source, monkeypatch):
    client, calls = source
    seed(client)

    def request(frame, command, **kwargs):
        return xt_packet(command, {}, GGEError.NO_EVENT)

    monkeypatch.setattr(client.connection, "request", request)
    with pytest.raises(CommandError) as caught:
        transfer(client)
    assert caught.value.error is GGEError.NO_EVENT
    assert commands(calls) == ["qsc", "mmr"]
    assert client.is_logged_in and client.connection.connected


def test_real_token_request_routes_reply_before_close(source, monkeypatch):
    client, calls = source
    seed(client)
    original = client.connection.send

    def send(frame):
        original(frame)
        if frame.split("%")[3] == "glt":
            push(client, "glt", TOKEN_REPLY)

    monkeypatch.setattr(client.connection, "send", send)
    monkeypatch.setattr(client.connection, "request", Connection.request.__get__(client.connection))
    transfer(client)
    assert commands(calls) == ["qsc", "mmr", "glt", "close", "login"]
    assert not client.connection._waiters


def test_earlier_qli_observer_cannot_hide_ready_state_at_timeout(source, monkeypatch):
    client, calls = source
    original = client.connection.create_waiter
    earlier = original("qli")
    current = []

    def create(command, accepts=None):
        waiter = original(command, accepts)
        current.append(waiter)
        push(client, "qli", {"QL": [{"QID": 3490}]})
        assert earlier.event.is_set()
        assert not waiter.event.is_set()
        return waiter

    monkeypatch.setattr(client.connection, "create_waiter", create)
    client.connect_to_special_server(ServerType.OUTER_REALMS, timeout=0.01)
    assert len(current) == 1
    assert commands(calls) == ["qsc", "glt", "close", "login"]
    assert not client.connection._waiters
