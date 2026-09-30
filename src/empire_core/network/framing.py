"""Splitting the server's message stream into packets."""

import logging
import re

from empire_core.protocol.packet import MAX_FRAME_SIZE

logger = logging.getLogger(__name__)

# Null bytes, the two noncharacters and lone surrogates, as the client strips them.
_STRIPPED_CHARS_RE = re.compile("[\x00￾￿\ud800-\udfff]")

_SYSTEM_MESSAGE_RE = re.compile(r"<msg[\s\S]+?</msg>")
_SYSTEM_MESSAGE_START = "<msg"
_SYSTEM_MESSAGE_END = "</msg>"


def _tail(chunks: list[str], length: int) -> str:
    """The last ``length`` characters of ``chunks`` joined, however many chunks they span."""
    pieces: list[str] = []
    needed = length
    for chunk in reversed(chunks):
        pieces.append(chunk[-needed:])
        needed -= len(pieces[-1])
        if needed <= 0:
            break
    return "".join(reversed(pieces))


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
        # No system message can start before this offset of the pending data: it is
        # the first "<msg" there (opened) or the last characters that could begin one.
        # A closing tag then only needs the data from here on, not a packet still arriving.
        self._scan_from = 0
        self._opened = False

    def feed(self, message: str) -> list[str]:
        """Add one message; return the packets it completes, system messages first, each in wire order.

        Extension packets are returned with their ``%xt`` prefix, as ``Packet.from_bytes`` reads them.
        """
        text = _STRIPPED_CHARS_RE.sub("", message)
        if not text:
            return []
        if not self._chunks and text.endswith("%") and _SYSTEM_MESSAGE_START not in text:
            # Whole extension packets with nothing pending: the common case
            return ["%xt" + piece for piece in text.split("%xt") if piece]
        # A tag may straddle the previous message and this one.
        previous_tail = _tail(self._chunks, len(_SYSTEM_MESSAGE_END) - 1)
        before = self._size
        self._chunks.append(text)
        self._size += len(text)
        if not self._opened:
            self._find_opener(before, previous_tail[-(len(_SYSTEM_MESSAGE_START) - 1) :], text)

        if text.endswith("%"):
            return self._take_all()
        if self._opened and _SYSTEM_MESSAGE_END in previous_tail + text:
            packets = self._take_system_messages()
            if packets:
                return packets
        if self._size > self._limit:
            self._drop()
        return []

    def _find_opener(self, offset: int, tail: str, text: str) -> None:
        """Note where the first "<msg" in ``tail + text`` (starting ``len(tail)`` before ``offset``) is."""
        at = (tail + text).find(_SYSTEM_MESSAGE_START)
        if at >= 0:
            self._scan_from = offset - len(tail) + at
            self._opened = True
        else:
            self._scan_from = max(0, self._size - (len(_SYSTEM_MESSAGE_START) - 1))
            self._opened = False

    def _take_all(self) -> list[str]:
        """The data ends with ``%``: take every system message, then split the rest into packets."""
        buffer = "".join(self._chunks)
        packets = _SYSTEM_MESSAGE_RE.findall(buffer) if self._opened else []
        if packets:
            buffer = _SYSTEM_MESSAGE_RE.sub("", buffer)
        return packets + self._split(buffer)

    def _split(self, buffer: str) -> list[str]:
        """Split data ending with ``%`` into extension packets; keep anything else for the next message."""
        packets = []
        if buffer.endswith("%"):
            packets = ["%xt" + piece for piece in buffer.split("%xt") if piece]
            buffer = ""
        self._chunks = [buffer] if buffer else []
        self._size = len(buffer)
        self._find_opener(0, "", buffer)
        if self._size > self._limit:
            self._drop()
        return packets

    def _take_system_messages(self) -> list[str]:
        """Take the system messages a closing tag completed, reading only the data from ``_scan_from`` on."""
        index = len(self._chunks)
        offset = self._size
        while offset > self._scan_from:
            index -= 1
            offset -= len(self._chunks[index])
        region = "".join(self._chunks[index:])
        cut = self._scan_from - offset
        head_piece, region = region[:cut], region[cut:]
        packets = _SYSTEM_MESSAGE_RE.findall(region)
        if not packets:
            return []
        rest = _SYSTEM_MESSAGE_RE.sub("", region)
        head = self._chunks[:index] + ([head_piece] if head_piece else [])
        last = rest or (head[-1] if head else "")
        if last.endswith("%"):
            return packets + self._split("".join(head) + rest)
        self._chunks = [*head, rest] if rest else head
        self._size = self._scan_from + len(rest)
        self._find_opener(self._scan_from, _tail(head, len(_SYSTEM_MESSAGE_START) - 1), rest)
        if self._size > self._limit:
            self._drop()
        return packets

    def _drop(self) -> None:
        logger.warning(f"Dropping {self._size} buffered characters that never completed a packet (limit {self._limit})")
        self._chunks = []
        self._size = 0
        self._scan_from = 0
        self._opened = False

    @property
    def pending(self) -> str:
        """Data kept for the next message: the start of a packet still arriving."""
        return "".join(self._chunks)
