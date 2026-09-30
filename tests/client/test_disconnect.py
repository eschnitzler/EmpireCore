"""What an EmpireClient does when its session drops (no real socket)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import websocket

from empire_core.client.client import EmpireClient
from tests.state.state_helpers import gam_payload, gcl_payload, login, wait_for


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


class TestStateAfterADrop:
    """The game client forgets the lost session's data; the next login rebuilds it."""

    def test_the_lost_sessions_data_is_forgotten(self, client):
        login(client.state)
        client.state.update_from_packet("gbd", {"gcl": gcl_payload([(5, "Home")], owner_id=1)})
        client.state.update_from_packet("gam", gam_payload(100))
        assert client.state.movements and client.state.castles

        drop(client)

        assert client.state.local_player is None
        assert client.state.castles == {}
        assert client.state.get_all_movements() == []
        assert client.state.get_packet_times() == {}

    def test_callbacks_survive_and_the_drop_fires_none(self, client):
        fired: list[int] = []
        removed: list[int] = []
        client.state.on_incoming_attack(lambda mov: fired.append(mov.movement_id))
        client.state.on_movement_removed(lambda mid: removed.append(mid))
        login(client.state)
        client.state.update_from_packet("gam", gam_payload(100))
        assert wait_for(lambda: fired == [100])

        drop(client)
        # A re-login's movement list: nothing from before the drop is left to merge into.
        login(client.state)
        client.state.update_from_packet("gam", gam_payload(101))

        assert wait_for(lambda: fired == [100, 101])
        assert removed == []
        assert [m.movement_id for m in client.state.get_all_movements()] == [101]

    def test_close_forgets_the_session_too(self, client):
        login(client.state)
        client.close()
        assert client.state.local_player is None
