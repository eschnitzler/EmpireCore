"""What an EmpireClient does when its session drops (no real socket)."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator

import pytest
import websocket

from empire_core.client.client import EmpireClient
from empire_core.exceptions import ReceiveThreadError
from empire_core.protocol.packet import Packet
from tests.service_helpers import request_payload
from tests.state.state_helpers import arrive, gam_payload, gcl_payload, login, wait_for


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


class RecordingSocket:
    connected = True

    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, data: str) -> None:
        self.sent.append(data)

    def close(self) -> None:
        self.connected = False


def new_session(client: EmpireClient) -> RecordingSocket:
    """Stand up a fresh live session, as a (re)connect does, that records what it sends."""
    socket = RecordingSocket()
    connection = client.connection
    connection.ws = socket  # type: ignore[assignment]
    connection._running = True
    connection._closing = False
    connection._generation += 1
    return socket


def arrive_packet(client: EmpireClient, command: str, payload: object, error_code: int = 0) -> None:
    frame = f"%xt%{command}%1%{error_code}%{json.dumps(payload)}%"
    client.connection._route_packet(Packet.from_bytes(frame.encode()))


def sent_commands(socket: RecordingSocket) -> list[str]:
    return [frame.split("%")[3] for frame in socket.sent]


class TestMovementsAfterLogin:
    """The server pushes gam after the login data; the client asks for it only after an mvf push."""

    def test_the_login_data_asks_for_nothing(self, client):
        socket = new_session(client)
        arrive_packet(client, "gbd", {"gpi": {"PID": 1, "PN": "me"}, "mvf": {}})
        assert socket.sent == []

    def test_an_mvf_push_is_followed_by_a_gam_request(self, client):
        socket = new_session(client)
        arrive_packet(client, "mvf", {})
        assert sent_commands(socket) == ["gam"]
        assert request_payload(socket.sent[0]) == {}

    def test_a_refused_mvf_asks_for_nothing(self, client):
        socket = new_session(client)
        arrive_packet(client, "mvf", {}, error_code=1)
        assert socket.sent == []

    def test_a_reconnect_and_login_list_the_movements_again_from_the_pushed_gam(self, client):
        new_session(client)
        arrive_packet(client, "gbd", {"gpi": {"PID": 1, "PN": "me"}})
        arrive_packet(client, "gam", gam_payload(100))
        drop(client)
        assert client.state.get_all_movements() == []

        socket = new_session(client)
        arrive_packet(client, "gbd", {"gpi": {"PID": 1, "PN": "me"}})
        # The server's own gam push after the login data.
        arrive_packet(client, "gam", gam_payload(100))

        assert socket.sent == []
        assert [m.movement_id for m in client.state.get_all_movements()] == [100]


class TestAttacksAcrossAReconnect:
    def test_an_attack_still_on_its_way_is_announced_once(self, client):
        fired: list[int] = []
        client.state.on_incoming_attack(lambda mov: fired.append(mov.movement_id))
        new_session(client)
        arrive_packet(client, "gbd", {"gpi": {"PID": 1, "PN": "me"}})
        arrive_packet(client, "gam", gam_payload(100))
        assert wait_for(lambda: fired == [100])

        drop(client)
        new_session(client)
        arrive_packet(client, "gbd", {"gpi": {"PID": 1, "PN": "me"}})
        arrive_packet(client, "gam", gam_payload(100))
        arrive_packet(client, "gam", gam_payload(101))

        assert wait_for(lambda: fired == [100, 101])
        assert [m.movement_id for m in client.state.get_all_movements()] == [100, 101]

    def test_a_removed_attack_is_forgotten(self, client):
        fired: list[int] = []
        client.state.on_incoming_attack(lambda mov: fired.append(mov.movement_id))
        login(client.state)
        client.state.update_from_packet("gam", gam_payload(100))
        client.state.update_from_packet("mrm", {"MID": 100})
        client.state.update_from_packet("gam", gam_payload(100))
        assert wait_for(lambda: fired == [100, 100])

    def test_an_arrived_attack_is_forgotten(self, client):
        login(client.state)
        client.state.update_from_packet("gam", gam_payload(100))
        assert 100 in client.state._announced_attacks
        arrive(client.state, 100)
        assert 100 not in client.state._announced_attacks


class TestLateDropReport:
    def test_a_drop_reported_after_a_new_session_started_leaves_it_alone(self, client):
        new_session(client)
        stale = client.connection.generation
        new_session(client)
        client.is_logged_in = True
        login(client.state)

        client._on_disconnect(stale)

        assert client.is_logged_in
        assert client.state.local_player is not None

    def test_a_drop_of_the_current_session_resets_it(self, client):
        new_session(client)
        client.is_logged_in = True
        login(client.state)

        client._on_disconnect(client.connection.generation)

        assert not client.is_logged_in
        assert client.state.local_player is None


class TestBulkLookupOnTheReceiveThread:
    def test_is_refused(self, client):
        socket = new_session(client)
        client.connection._recv_thread = threading.current_thread()
        with pytest.raises(ReceiveThreadError):
            client.player.get_player_details_bulk([1, 2])
        assert socket.sent == []
