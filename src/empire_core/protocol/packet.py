import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union


@dataclass
class Packet:
    """
    Base representation of a SmartFoxServer packet.
    Can be either XML (Handshake) or XT (Extended/JSON).
    """

    raw_data: str
    is_xml: bool

    command_id: Optional[str] = None
    request_id: int = -1
    error_code: int = 0  # New field for XT status/error code
    payload: Union[Dict[str, Any], ET.Element, None] = None

    @staticmethod
    def build_xt(zone: str, command: str, payload: Dict[str, Any], request_id: int = 1) -> str:
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
        decoded = data.decode("utf-8").rstrip("\x00")
        if not decoded:
            raise ValueError("Empty packet")

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
        except ET.ParseError:
            return cls(raw_data=data, is_xml=True)

    @classmethod
    def _parse_xt(cls, data: str) -> "Packet":
        # Format: %xt%{Command}%{RequestId}%{Status}%{Payload}%
        parts = data.split("%")
        if len(parts) < 5:
            return cls(raw_data=data, is_xml=False)

        cmd = parts[2]
        req_id = int(parts[3]) if parts[3].isdigit() else -1

        error_code = 0
        if parts[4].isdigit() or (parts[4].startswith("-") and parts[4][1:].isdigit()):
            error_code = int(parts[4])

        raw_payload = parts[5] if len(parts) > 5 else ""

        # Optimization: Only parse JSON if it looks like JSON
        payload_data = {}
        if raw_payload.startswith("{") or raw_payload.startswith("["):
            try:
                payload_data = json.loads(raw_payload)
            except json.JSONDecodeError:
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
