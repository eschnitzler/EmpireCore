"""What an EmpireClient does when its session drops (no real socket)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import websocket

from empire_core.client.client import EmpireClient


class ClosingSocket:
    """A connected socket whose next recv() finds the server gone."""

    connected = True

    def recv(self):
        raise websocket.WebSocketConnectionClosedException("closed by server")

    def send(self, _data):
        pass

    def close(self):
        self.connected = False


@pytest.fixture
def client() -> Iterator[EmpireClient]:
    client = EmpireClient(username="user", password="pass")
    yield client
    client.close()


def drop(client: EmpireClient) -> None:
    """Run the receive loop of a live session until the server closes it."""
    connection = client.connection
    connection.ws = ClosingSocket()  # type: ignore[assignment]
    connection._running = True
    connection._closing = False
    connection._generation += 1
    connection._recv_loop(connection.ws, connection._generation)  # type: ignore[arg-type]


class TestDisconnectCallbacks:
    def test_fires_once_on_an_unexpected_drop_after_the_client_marks_itself_logged_out(self, client):
        seen: list[bool] = []
        client.is_logged_in = True
        client.on_disconnect(lambda: seen.append(client.is_logged_in))

        drop(client)

        assert seen == [False]

    def test_does_not_fire_on_close(self, client):
        calls: list[str] = []
        client.on_disconnect(lambda: calls.append("fired"))
        client.connection._running = True
        client.connection.ws = ClosingSocket()  # type: ignore[assignment]

        client.close()
        # The receive loop then ends on the closed socket without reporting it.
        client.connection._running = True
        client.connection._recv_loop(ClosingSocket(), client.connection._generation)  # type: ignore[arg-type]

        assert calls == []

    def test_a_removed_callback_no_longer_fires(self, client):
        calls: list[str] = []

        def callback() -> None:
            calls.append("fired")

        client.on_disconnect(callback)
        client.on_disconnect(callback)
        drop(client)
        client.remove_disconnect_callback(callback)
        client.remove_disconnect_callback(callback)
        drop(client)

        assert calls == ["fired"]
