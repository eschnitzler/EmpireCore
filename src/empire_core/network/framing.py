"""Splitting the server's message stream into packets."""

import logging
import re

from empire_core.protocol.packet import MAX_FRAME_SIZE

logger = logging.getLogger(__name__)

# Null bytes, the two noncharacters and lone surrogates, as the client strips them.
_STRIPPED_CHARS_RE = re.compile("[\x00￾￿\ud800-\udfff]")

_SYSTEM_MESSAGE_RE = re.compile(r"<msg[\s\S]+?</msg>")
_SYSTEM_MESSAGE_END = "</msg>"


class FrameBuffer:
    """Turns WebSocket messages into packets, however the server batches or splits them.

    A message may hold several packets, or only part of one. Every ``<msg>...</msg>``
    system message in the buffer is taken out first; the rest is kept until it ends
    with ``%``, then split on ``%xt`` into extension packets. Partial data waits for
    the next message.

    The client's system-message pattern is greedy, so two XML messages in one buffer
    reach it as one; here each is its own packet. The buffer is also capped at
    ``MAX_FRAME_SIZE``, which the client does not do.

    Client: ``BasicSmartfoxClient.onDataReady`` and ``handleExtMessage`` (ggs.dll lines 7211-7224).
    """

    def __init__(self, limit: int = MAX_FRAME_SIZE):
        # Pending data as the messages it came in, joined only when one of them
        # can complete a packet, so a packet split over many messages costs linear time.
        self._chunks: list[str] = []
        self._size = 0
        self._limit = limit

    def feed(self, message: str) -> list[str]:
        """Add one message; return the packets it completes, system messages first, each in wire order.

        Extension packets are returned with their ``%xt`` prefix, as ``Packet.from_bytes`` reads them.
        """
        text = _STRIPPED_CHARS_RE.sub("", message)
        if not text:
            return []
        # A closing tag may straddle the previous message and this one.
        previous_tail = self._chunks[-1][-(len(_SYSTEM_MESSAGE_END) - 1) :] if self._chunks else ""
        self._chunks.append(text)
        self._size += len(text)
        if not text.endswith("%") and _SYSTEM_MESSAGE_END not in previous_tail + text:
            if self._size > self._limit:
                self._drop()
            return []

        buffer = "".join(self._chunks)
        packets = _SYSTEM_MESSAGE_RE.findall(buffer)
        if packets:
            buffer = _SYSTEM_MESSAGE_RE.sub("", buffer)
        if buffer.endswith("%"):
            packets.extend("%xt" + piece for piece in buffer.split("%xt") if piece)
            buffer = ""
        self._chunks = [buffer] if buffer else []
        self._size = len(buffer)
        if self._size > self._limit:
            self._drop()
        return packets

    def _drop(self) -> None:
        logger.warning(f"Dropping {self._size} buffered characters that never completed a packet (limit {self._limit})")
        self._chunks = []
        self._size = 0

    @property
    def pending(self) -> str:
        """Data kept for the next message: the start of a packet still arriving."""
        return "".join(self._chunks)
