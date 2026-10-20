"""
permessage-deflate (RFC 7692) for websocket-client, which has none of its own.

The game servers refuse a WebSocket handshake that offers no compression
extension and compress every message once it is negotiated. The client needs
no code for it: the browser offers the extension on every ``new WebSocket``.

Client: ``BasicSmartfoxClient.executeConnection`` (ggs.dll line 6952) opens the socket.
"""

import zlib

import websocket
from websocket._abnf import frame_buffer

PERMESSAGE_DEFLATE_OFFER = "Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits"
"""The extension offer a browser sends with every WebSocket handshake."""

MAX_MESSAGE_BYTES = 64 * 1024 * 1024
"""Most bytes one message may inflate to; a larger one ends the connection."""

_DEFLATE_TAIL = b"\x00\x00\xff\xff"
_MESSAGE_OPCODES = frozenset({websocket.ABNF.OPCODE_TEXT, websocket.ABNF.OPCODE_BINARY})
_DATA_OPCODES = _MESSAGE_OPCODES | {websocket.ABNF.OPCODE_CONT}


class InflatingFrameBuffer(frame_buffer):
    """A frame buffer that inflates the messages the server sent compressed (RSV1 on their first frame)."""

    def __init__(self, source: frame_buffer, context_takeover: bool) -> None:
        super().__init__(source.recv, source.skip_utf8_validation)
        self.recv_buffer = source.recv_buffer
        self._context_takeover = context_takeover
        self._inflater = zlib.decompressobj(-zlib.MAX_WBITS)
        self._compressed_frame = False
        self._compressed_message = False
        self._inflated = 0

    def recv_header(self) -> None:
        super().recv_header()
        assert self.header is not None
        fin, rsv1, rsv2, rsv3, opcode, *rest = self.header
        self._compressed_frame = bool(rsv1) and opcode in _DATA_OPCODES
        if self._compressed_frame:
            self.header = (fin, 0, rsv2, rsv3, opcode, *rest)

    def recv_frame(self) -> websocket.ABNF:
        frame = super().recv_frame()
        if frame.opcode in _MESSAGE_OPCODES:
            self._compressed_message = self._compressed_frame
            self._inflated = 0
        elif frame.opcode == websocket.ABNF.OPCODE_CONT and self._compressed_frame:
            raise websocket.WebSocketProtocolException("RSV1 set on a continuation frame")
        if frame.opcode in _DATA_OPCODES and self._compressed_message:
            assert isinstance(frame.data, bytes)
            frame.data = self._inflate(frame.data, bool(frame.fin))
        return frame

    def _inflate(self, data: bytes, fin: bool) -> bytes:
        if fin:
            data += _DEFLATE_TAIL
        room = MAX_MESSAGE_BYTES - self._inflated
        try:
            inflated = self._inflater.decompress(data, room + 1)
        except zlib.error as e:
            raise websocket.WebSocketProtocolException(f"Could not inflate a message: {e}") from e
        self._inflated += len(inflated)
        if self._inflated > MAX_MESSAGE_BYTES or self._inflater.unconsumed_tail:
            raise websocket.WebSocketPayloadException(f"A message inflates to more than {MAX_MESSAGE_BYTES} bytes")
        if fin and not self._context_takeover:
            self._inflater = zlib.decompressobj(-zlib.MAX_WBITS)
        return inflated


def accept_permessage_deflate(ws: websocket.WebSocket) -> bool:
    """
    Inflate the messages of a connected ``ws`` if its handshake negotiated permessage-deflate.

    Returns whether it did. A smaller ``server_max_window_bits`` needs no
    setting: an inflater with the largest window reads any smaller one.
    """
    accepted = (ws.getheaders() or {}).get("sec-websocket-extensions", "")
    for extension in accepted.split(","):
        name, *params = (part.strip() for part in extension.split(";"))
        if name == "permessage-deflate":
            context_takeover = "server_no_context_takeover" not in {p.split("=")[0].strip() for p in params}
            ws.frame_buffer = InflatingFrameBuffer(ws.frame_buffer, context_takeover)
            return True
    return False
