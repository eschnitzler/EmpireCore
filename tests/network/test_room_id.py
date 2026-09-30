"""The joined room's id on the connection: the ping carries it, and a new socket starts with none."""

import websocket

from empire_core.network import connection as connection_module
from empire_core.network.connection import Connection


def test_the_ping_carries_the_room_id(monkeypatch):
    monkeypatch.setattr(connection_module, "KEEPALIVE_INTERVAL", 0)
    conn = Connection("wss://example.invalid/", keepalive_zone="EmpireEx_21")
    conn._running = True
    conn.room_id = 4
    sent: list[str] = []

    def record(frame: str) -> None:
        sent.append(frame)
        conn._running = False

    monkeypatch.setattr(conn, "send", record)
    conn._keepalive_loop(conn._generation)

    # Client: BasicSmartfoxClient.activatePing sends "pin" with [""] (dll line 7167).
    assert sent == ["%xt%EmpireEx_21%pin%4%<RoundHouseKick>%"]


def test_a_new_connection_has_joined_no_room(monkeypatch):
    class FakeWebSocket:
        connected = True

        def settimeout(self, timeout):
            pass

        def connect(self, url):
            pass

        def recv(self):
            raise websocket.WebSocketTimeoutException()

        def close(self):
            self.connected = False

    monkeypatch.setattr(connection_module.websocket, "WebSocket", FakeWebSocket)
    conn = Connection("wss://example.invalid/")
    assert conn.room_id == -1
    conn.room_id = 9
    conn.connect()
    try:
        assert conn.room_id == -1
    finally:
        conn.disconnect()
