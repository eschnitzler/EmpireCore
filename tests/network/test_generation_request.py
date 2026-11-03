"""Generation-bound requests stay on the source socket, without locking reply waits."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
from unittest.mock import Mock

import pytest

from empire_core.exceptions import ConnectionClosedError, EmpireTimeoutError, NetworkError
from empire_core.network.connection import Connection
from tests.network.test_connection import make_packet


@pytest.fixture
def connection():
    connection = Connection("wss://example.invalid/")
    connection.ws = Mock(connected=True)
    connection._running = True
    connection._generation = 1
    return connection


@pytest.mark.parametrize("change", ["generation", "disconnected"])
def test_changed_source_rejected_without_registering_or_sending(connection, change):
    socket = connection.ws
    if change == "generation":
        connection._generation += 1
    else:
        connection._running = False
    with pytest.raises(ConnectionClosedError):
        connection.request("token", "glt", expected_generation=1)
    socket.send.assert_not_called()
    assert not connection._waiters


def test_generation_checked_after_command_lock_queue(connection, monkeypatch):
    @contextmanager
    def lock(*args, **kwargs):
        connection._generation += 1
        yield

    monkeypatch.setattr(connection, "command_lock", lock)
    with pytest.raises(ConnectionClosedError):
        connection.request("token", "glt", expected_generation=1)
    connection.ws.send.assert_not_called()
    assert not connection._waiters


def test_generation_checked_after_settling_owed_reply(connection, monkeypatch):
    connection._owing.add("glt")

    def settle(command):
        assert command == "glt"
        connection._generation += 1
        return 0.0

    monkeypatch.setattr(connection, "_settle_owed_replies", settle)
    with pytest.raises(ConnectionClosedError):
        connection.request("token", "glt", expected_generation=1)
    connection.ws.send.assert_not_called()
    assert not connection._waiters


def test_register_and_send_share_lifecycle_lock(connection, monkeypatch):
    registering = Event()
    release = Event()
    replacement_attempted = Event()
    replaced = Event()
    original = connection.create_waiter
    packet = make_packet("glt")

    def create(*args, **kwargs):
        registering.set()
        assert release.wait(2)
        return original(*args, **kwargs)

    def replace():
        replacement_attempted.set()
        with connection._lifecycle_lock:
            connection._generation += 1
            replaced.set()

    def send(data):
        assert not replaced.is_set()
        assert connection.generation == 1
        connection._route_packet(packet)

    monkeypatch.setattr(connection, "create_waiter", create)
    monkeypatch.setattr(connection, "send", send)
    with ThreadPoolExecutor(max_workers=2) as pool:
        request = pool.submit(connection.request, "token", "glt", expected_generation=1)
        try:
            assert registering.wait(2)
            replacement = pool.submit(replace)
            assert replacement_attempted.wait(2)
            assert not replaced.is_set()
        finally:
            release.set()
        assert request.result(timeout=2) is packet
        replacement.result(timeout=2)
    assert replaced.is_set()
    assert not connection._waiters


def test_reply_wait_releases_lock_so_disconnect_can_cancel(connection, monkeypatch):
    sent = Event()
    monkeypatch.setattr(connection, "send", lambda data: sent.set())
    with ThreadPoolExecutor(max_workers=2) as pool:
        request = pool.submit(connection.request, "token", "glt", timeout=5, expected_generation=1)
        assert sent.wait(2)
        disconnect = pool.submit(connection.disconnect)
        disconnect.result(timeout=2)
        with pytest.raises(ConnectionClosedError):
            request.result(timeout=2)
    assert not connection._waiters


def test_send_failure_removes_generation_bound_waiter(connection):
    connection.ws.send.side_effect = OSError("offline")
    with pytest.raises(NetworkError):
        connection.request("token", "glt", expected_generation=1)
    assert not connection._waiters


def test_generation_bound_timeout_retains_late_reply_handling(connection):
    with pytest.raises(EmpireTimeoutError):
        connection.request("token", "glt", timeout=0.01, expected_generation=1)
    assert "glt" in connection._owing
    assert len(connection._waiters["glt"]) == 1
    assert connection._waiters["glt"][0].owed_until is not None
    connection._route_packet(make_packet("glt"))
    assert not connection._waiters
