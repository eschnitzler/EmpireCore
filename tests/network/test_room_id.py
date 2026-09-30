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

        def __init__(self, **_options):
            pass

        def settimeout(self, timeout):
            pass

        def connect(self, url):
            pass

        def recv_data(self):
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


def test_handled_login_refusals_are_not_logged_as_errors(caplog):
    from empire_core.protocol.packet import Packet

    conn = Connection("wss://example.invalid/")
    with caplog.at_level("DEBUG", logger="empire_core.network.connection"):
        conn._route_packet(Packet.from_bytes(b'%xt%lli%1%27%{"RS":5}%'))
        conn._route_packet(Packet.from_bytes(b"%xt%vck%1%1%1170001%"))
        conn._route_packet(Packet.from_bytes(b"%xt%gam%1%5%{}%"))
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert errors == ["Server error: INVALID_OBJECT_ID (5) for command 'gam'"]
