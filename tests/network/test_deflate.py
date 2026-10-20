import zlib

import pytest
import websocket

from empire_core.network import deflate
from empire_core.network.deflate import InflatingFrameBuffer, accept_permessage_deflate

BINARY = websocket.ABNF.OPCODE_BINARY
CONT = websocket.ABNF.OPCODE_CONT
PING = websocket.ABNF.OPCODE_PING


class _ByteSocket:
    def __init__(self, data: bytes):
        self.data = data

    def recv(self, n):
        chunk, self.data = self.data[:n], self.data[n:]
        return chunk

    def send(self, data):
        return len(data)

    def gettimeout(self):
        return None

    def settimeout(self, _timeout):
        pass


class _Handshake:
    def __init__(self, extensions: str | None):
        self.headers = {} if extensions is None else {"sec-websocket-extensions": extensions}


def _frame(opcode: int, payload: bytes, *, fin: bool = True, rsv1: bool = False) -> bytes:
    assert len(payload) < 126
    return bytes([fin << 7 | rsv1 << 6 | opcode, len(payload)]) + payload


def _compress(compressor, data: bytes) -> bytes:
    out = compressor.compress(data) + compressor.flush(zlib.Z_SYNC_FLUSH)
    assert out.endswith(b"\x00\x00\xff\xff")
    return out[:-4]


def _socket(data: bytes, extensions: str | None = "permessage-deflate") -> websocket.WebSocket:
    ws = websocket.WebSocket(skip_utf8_validation=True)
    ws.sock = _ByteSocket(data)  # type: ignore[assignment]
    ws.connected = True
    ws.handshake_response = _Handshake(extensions)  # type: ignore[assignment]
    return ws


def _messages(ws: websocket.WebSocket, count: int) -> list[bytes]:
    return [ws.recv_data()[1] for _ in range(count)]


def test_messages_are_inflated_with_one_context_across_messages():
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    first, second = b"%xt%gbd%1%0%{}%", b"%xt%gbd%1%0%{}%"
    data = _frame(BINARY, _compress(compressor, first), rsv1=True)
    data += _frame(BINARY, _compress(compressor, second), rsv1=True)
    ws = _socket(data)

    assert accept_permessage_deflate(ws)
    assert _messages(ws, 2) == [first, second]


def test_a_fragmented_message_is_inflated_whole():
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    message = b"%xt%gam%1%0%" + b"x" * 300 + b"%"
    compressed = _compress(compressor, message)
    half = len(compressed) // 2
    data = _frame(BINARY, compressed[:half], fin=False, rsv1=True)
    data += _frame(PING, b"")
    data += _frame(CONT, compressed[half:])
    ws = _socket(data)
    accept_permessage_deflate(ws)

    assert _messages(ws, 1) == [message]


def test_uncompressed_messages_pass_through():
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    data = _frame(BINARY, b"plain")
    data += _frame(BINARY, _compress(compressor, b"packed"), rsv1=True)
    data += _frame(BINARY, b"plain again")
    ws = _socket(data)
    accept_permessage_deflate(ws)

    assert _messages(ws, 3) == [b"plain", b"packed", b"plain again"]


def test_server_no_context_takeover_inflates_each_message_alone():
    data = b""
    for message in (b"same words", b"same words"):
        data += _frame(BINARY, _compress(zlib.compressobj(wbits=-zlib.MAX_WBITS), message), rsv1=True)
    ws = _socket(data, "permessage-deflate; server_no_context_takeover")
    accept_permessage_deflate(ws)

    assert _messages(ws, 2) == [b"same words", b"same words"]


def test_rsv1_on_a_continuation_frame_is_refused():
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    compressed = _compress(compressor, b"split message")
    data = _frame(BINARY, compressed[:3], fin=False, rsv1=True) + _frame(CONT, compressed[3:], rsv1=True)
    ws = _socket(data)
    accept_permessage_deflate(ws)

    with pytest.raises(websocket.WebSocketProtocolException):
        ws.recv_data()


def test_a_message_inflating_past_the_limit_is_refused(monkeypatch):
    monkeypatch.setattr(deflate, "MAX_MESSAGE_BYTES", 100)
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    ws = _socket(_frame(BINARY, _compress(compressor, b"y" * 101), rsv1=True))
    accept_permessage_deflate(ws)

    with pytest.raises(websocket.WebSocketPayloadException):
        ws.recv_data()


def test_without_the_extension_compressed_frames_stay_refused():
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    ws = _socket(_frame(BINARY, _compress(compressor, b"packed"), rsv1=True), extensions=None)

    assert not accept_permessage_deflate(ws)
    assert not isinstance(ws.frame_buffer, InflatingFrameBuffer)
    with pytest.raises(websocket.WebSocketProtocolException):
        ws.recv_data()


def test_connect_offers_the_extension(monkeypatch):
    from empire_core.network import connection as connection_module

    calls: list[dict] = []

    class RecordingWS:
        connected = True

        def __init__(self, **_options):
            pass

        def settimeout(self, _timeout):
            pass

        def connect(self, url, **options):
            calls.append(options)

        def getheaders(self):
            return {}

        def recv_data(self):
            raise websocket.WebSocketTimeoutException()

        def close(self):
            self.connected = False

    monkeypatch.setattr(connection_module.websocket, "WebSocket", RecordingWS)
    conn = connection_module.Connection("wss://example.invalid/")
    conn.connect()
    conn.disconnect()

    assert calls == [{"header": [deflate.PERMESSAGE_DEFLATE_OFFER]}]
