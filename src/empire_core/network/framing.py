"""Splitting the server's message stream into packets."""

import logging
import re

from empire_core.protocol.packet import MAX_FRAME_SIZE

logger = logging.getLogger(__name__)

# Null bytes, the two noncharacters and lone surrogates, as the client strips them.
_STRIPPED_CHARS_RE = re.compile("[\x00￾￿\ud800-\udfff]")

_SYSTEM_MESSAGE_RE = re.compile(r"<msg[\s\S]+?</msg>")


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
        self._buffer = ""
        self._limit = limit

    def feed(self, message: str) -> list[str]:
        """Add one message; return the packets it completes, system messages first, each in wire order.

        Extension packets are returned with their ``%xt`` prefix, as ``Packet.from_bytes`` reads them.
        """
        self._buffer += _STRIPPED_CHARS_RE.sub("", message)
        packets = _SYSTEM_MESSAGE_RE.findall(self._buffer)
        if packets:
            self._buffer = _SYSTEM_MESSAGE_RE.sub("", self._buffer)
        if self._buffer.endswith("%"):
            pieces = self._buffer.split("%xt")
            self._buffer = ""
            packets.extend("%xt" + piece for piece in pieces if piece)
        elif len(self._buffer) > self._limit:
            logger.warning(
                f"Dropping {len(self._buffer)} buffered characters that never completed a packet (limit {self._limit})"
            )
            self._buffer = ""
        return packets

    @property
    def pending(self) -> str:
        """Data kept for the next message: the start of a packet still arriving."""
        return self._buffer
