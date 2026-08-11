from __future__ import annotations

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# error_code used when an XT frame's status field is not an integer.
# Real status codes are >= -1 (see GGEError), so this sentinel can never be
# confused with a success (0) — a garbled status must not pass client.send()'s
# `error_code != 0` check as if the response were valid.
MALFORMED_STATUS_CODE = -1000

# Largest inbound frame we are willing to look at. A full-kingdom `gaa` chunk
# is a few hundred KB, so this is orders of magnitude of headroom; the point is
# that a misbehaving (or hostile) server cannot stall the single receive thread
# inside json.loads, blocking every request() waiter until timeout.
MAX_FRAME_SIZE = 16 * 1024 * 1024

# XML is only used for the handshake phase (verChk, cross-domain-policy), all
# of which is well under a kilobyte.
MAX_XML_SIZE = 1024 * 1024

# A frame that degrades to a raw wrapper (command_id=None) matches no waiter
# or subscriber, so it is dropped silently end-to-end - the degradation itself
# must be visible. Schema drift can degrade every frame, so the warning is
# rate-limited and the suppressed count reported with the next one (same
# pattern as GameState._log_movement_parse_failure).
DEGRADED_FRAME_WARN_INTERVAL = 60.0

_degraded_frame_count = 0
_degraded_frame_warn_at = 0.0

# Credential shapes to mask before any part of a frame is logged - packet.py
# must never log raw credentials. Mirrors _SECRET_PATTERNS in
# network/connection.py (which cannot be imported here: the network layer
# already imports the protocol layer).
_SECRET_JSON_RE = re.compile(
    r'("(?:PW|PWD|PASS|PASSWORD|TOKEN|SECRET|AUTH)"\s*:\s*)"(?:\\.|[^"\\])*"',
    re.IGNORECASE,
)
_SECRET_XML_RE = re.compile(r"(<pword>).*?(</pword>)", re.IGNORECASE | re.DOTALL)

# Longest frame prefix we are willing to log, as defence in depth on top of
# the redaction above.
_LOG_PREFIX_CHARS = 80


def _redacted_prefix(frame: str) -> str:
    """A short, credential-masked prefix of ``frame`` that is safe to log."""
    safe = _SECRET_JSON_RE.sub(r'\1"<redacted>"', frame)
    safe = _SECRET_XML_RE.sub(r"\1<redacted>\2", safe)
    if len(safe) > _LOG_PREFIX_CHARS:
        safe = safe[:_LOG_PREFIX_CHARS] + "..."
    return safe


def _warn_degraded_frame(reason: str, frame: str) -> None:
    """Report a non-empty frame degrading to a raw wrapper, rate-limited."""
    global _degraded_frame_count, _degraded_frame_warn_at
    _degraded_frame_count += 1
    now = time.time()
    if now < _degraded_frame_warn_at:
        logger.debug(f"Frame degraded to raw wrapper ({reason}; warning rate-limited): {_redacted_prefix(frame)}")
        return

    suppressed = _degraded_frame_count - 1
    _degraded_frame_count = 0
    _degraded_frame_warn_at = now + DEGRADED_FRAME_WARN_INTERVAL
    extra = f" ({suppressed} further degraded frames suppressed)" if suppressed else ""
    logger.warning(
        f"Frame degraded to raw wrapper ({reason}) - it matches no waiter or subscriber "
        f"and will be dropped{extra}: {_redacted_prefix(frame)}"
    )


@dataclass
class Packet:
    """
    Base representation of a SmartFoxServer packet.
    Can be either XML (Handshake) or XT (Extended/JSON).
    """

    raw_data: str
    is_xml: bool

    command_id: str | None = None
    request_id: int = -1
    error_code: int = 0  # New field for XT status/error code
    # list: some XT commands answer with a bare JSON array, which _parse_xt
    # deliberately keeps as a list rather than wrapping it -- so consumers must
    # not assume `.get()` is available after a None-check.
    payload: dict[str, Any] | list[Any] | ET.Element | None = None

    @staticmethod
    def build_xt(zone: str, command: str, payload: dict[str, Any], request_id: int = 1) -> str:
        """
        Build an XT (Extended) packet string.

        Args:
            zone: Game zone (e.g., "EmpireEx_21")
            command: Command ID (e.g., "att", "tra", "bui")
            payload: Dictionary payload to JSON encode
            request_id: Request ID (default 1)

        Returns:
            Formatted XT packet string
        """
        return f"%xt%{zone}%{command}%{request_id}%{json.dumps(payload)}%"

    @classmethod
    def from_bytes(cls, data: bytes) -> "Packet":
        """
        Parse a frame received from the server.

        Total by design: the receive loop has no per-packet recovery, so a
        frame it cannot make sense of must degrade to a raw wrapper rather
        than raise and tear down the whole connection.

        A frame carrying several null-delimited packets is *not* split here --
        only the trailing terminator is stripped, so a batched frame parses as
        one packet whose payload is the concatenation. Use
        :meth:`iter_from_bytes` when the caller can handle several packets.

        Args:
            data: Raw frame bytes (may be truncated, padded or non-UTF-8)

        Returns:
            A Packet. Unparseable input yields a raw wrapper whose
            ``command_id`` is None and whose ``payload`` is None.
        """
        if len(data) > MAX_FRAME_SIZE:
            # Drop it without decoding or JSON-parsing: this runs on the single
            # receive thread, so time and memory spent here stall every waiter.
            logger.warning(f"Dropping inbound frame: {len(data)} bytes is too large (limit {MAX_FRAME_SIZE})")
            return cls(raw_data="", is_xml=False)

        # errors="replace": one bad byte in a chat message or player name must
        # not kill the connection.
        decoded = data.decode("utf-8", errors="replace").rstrip("\x00")
        if not decoded:
            # Empty or null-only padding frames. The receive loop's
            # `if not data: continue` does not catch b"\x00".
            return cls(raw_data="", is_xml=False)

        if decoded.startswith("<"):
            return cls._parse_xml(decoded)
        elif decoded.startswith("%xt%"):
            return cls._parse_xt(decoded)

        # Unknown or junk, return raw wrapper
        _warn_degraded_frame("unrecognised prefix", decoded)
        return cls(raw_data=decoded, is_xml=False)

    @classmethod
    def iter_from_bytes(cls, data: bytes) -> list["Packet"]:
        """
        Split a frame into its packets and parse each one.

        SmartFoxServer's wire protocol is null-delimited, and a single
        WebSocket frame may carry more than one packet. :meth:`from_bytes`
        assumes exactly one, so a batched frame corrupts the first packet
        (the rest of the frame is swallowed into its payload) and silently
        drops the others. This is the total, batch-aware alternative.

        Whether the live game server actually batches is unconfirmed; this
        helper is additive, and the receive loop still calls
        :meth:`from_bytes`. To find out, log any received frame where
        ``data.rstrip(b"\\x00").find(b"\\x00") != -1``.

        Args:
            data: Raw frame bytes, one or more null-terminated packets

        Returns:
            One Packet per non-empty segment, in wire order. Empty and
            null-padding frames yield an empty list.
        """
        if len(data) > MAX_FRAME_SIZE:
            logger.warning(f"Dropping inbound frame: {len(data)} bytes is too large (limit {MAX_FRAME_SIZE})")
            return []

        return [cls.from_bytes(segment) for segment in data.split(b"\x00") if segment]

    @classmethod
    def _parse_xml(cls, data: str) -> "Packet":
        if len(data) > MAX_XML_SIZE:
            # XML only carries the handshake, so anything this big is either
            # broken or an attempt to make the parser chew on it.
            logger.warning(f"Refusing to parse XML frame of {len(data)} chars (limit {MAX_XML_SIZE})")
            return cls(raw_data=data, is_xml=True)

        # stdlib ElementTree expands internal entity definitions, so a
        # billion-laughs / quadratic-blowup document would hang or OOM the
        # receive thread. The handshake XML has no DTD, so refusing one costs
        # nothing. (defusedxml would be the other option, but the client
        # deliberately ships with no XML dependency.)
        lowered = data.lower()
        if "<!doctype" in lowered or "<!entity" in lowered:
            logger.warning("Refusing to parse XML frame containing a DOCTYPE/ENTITY declaration")
            return cls(raw_data=data, is_xml=True)

        try:
            root = ET.fromstring(data)
            # Structure: <msg t='sys'><body action='verChk' ...>
            body = root.find("body")
            cmd = body.get("action") if body is not None else None

            # Fallback: Use root tag if no action (e.g. <cross-domain-policy>)
            if cmd is None:
                cmd = root.tag

            return cls(raw_data=data, is_xml=True, command_id=cmd, payload=root)
        except (ET.ParseError, ValueError):
            # ValueError: embedded null bytes and similar illegal XML content
            _warn_degraded_frame("XML parse failure", data)
            return cls(raw_data=data, is_xml=True)

    @classmethod
    def _parse_xt(cls, data: str) -> "Packet":
        # Format: %xt%{Command}%{RequestId}%{Status}%{Payload}%
        # Limit the split so '%' characters inside the payload (chat
        # messages, player names, ...) don't truncate it.
        parts = data.split("%", 5)
        if len(parts) < 5:
            _warn_degraded_frame("truncated XT frame", data)
            return cls(raw_data=data, is_xml=False)

        cmd = parts[2]
        try:
            req_id = int(parts[3])
        except ValueError:
            req_id = -1

        try:
            error_code = int(parts[4])
        except ValueError:
            # A status field we can't read must not look like success. Some
            # frames (rlu, core_pol) carry data in this field by design — see
            # NON_ERROR_COMMANDS in the network layer — so this stays quiet.
            logger.debug(f"Non-integer XT status {parts[4]!r} for command {cmd!r}")
            error_code = MALFORMED_STATUS_CODE

        raw_payload = parts[5] if len(parts) > 5 else ""
        # Strip the trailing packet delimiter
        if raw_payload.endswith("%"):
            raw_payload = raw_payload[:-1]

        # Optimization: Only parse JSON if it looks like JSON
        payload_data: dict[str, Any] | list[Any] = {}
        if raw_payload.startswith("{") or raw_payload.startswith("["):
            try:
                payload_data = json.loads(raw_payload)
            except (ValueError, RecursionError):
                # ValueError covers JSONDecodeError; RecursionError guards
                # against pathologically nested payloads.
                logger.debug(f"Unparseable JSON payload for command {cmd!r}, kept raw: {_redacted_prefix(raw_payload)}")
                payload_data = {"raw": raw_payload}
        else:
            payload_data = {"raw": raw_payload}

        return cls(
            raw_data=data,
            is_xml=False,
            command_id=cmd,
            request_id=req_id,
            error_code=error_code,
            payload=payload_data,
        )

    def to_bytes(self) -> bytes:
        return (self.raw_data + "\x00").encode("utf-8")
