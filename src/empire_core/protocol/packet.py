from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# error_code used when an XT frame's status field is not an integer.
# Real status codes are >= -1 (see GGEError), so this sentinel can never be
# confused with a success (0) — a garbled status must not pass client.send()'s
# `error_code != 0` check as if the response were valid.
MALFORMED_STATUS_CODE = -1000


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
    payload: dict[str, Any] | ET.Element | None = None

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

        Args:
            data: Raw frame bytes (may be truncated, padded or non-UTF-8)

        Returns:
            A Packet. Unparseable input yields a raw wrapper whose
            ``command_id`` is None and whose ``payload`` is None.
        """
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
        return cls(raw_data=decoded, is_xml=False)

    @classmethod
    def _parse_xml(cls, data: str) -> "Packet":
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
            return cls(raw_data=data, is_xml=True)

    @classmethod
    def _parse_xt(cls, data: str) -> "Packet":
        # Format: %xt%{Command}%{RequestId}%{Status}%{Payload}%
        # Limit the split so '%' characters inside the payload (chat
        # messages, player names, ...) don't truncate it.
        parts = data.split("%", 5)
        if len(parts) < 5:
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
        payload_data = {}
        if raw_payload.startswith("{") or raw_payload.startswith("["):
            try:
                payload_data = json.loads(raw_payload)
            except (ValueError, RecursionError):
                # ValueError covers JSONDecodeError; RecursionError guards
                # against pathologically nested payloads.
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
