"""Tests for SmartFox packet parsing and building."""

import json

from empire_core.protocol.packet import Packet


class TestXTParsing:
    def test_basic_xt_packet(self):
        packet = Packet.from_bytes(b'%xt%gam%1%0%{"M": []}%')
        assert packet.command_id == "gam"
        assert packet.request_id == 1
        assert packet.error_code == 0
        assert packet.payload == {"M": []}

    def test_error_code_parsed(self):
        packet = Packet.from_bytes(b"%xt%lli%1%453%{}%")
        assert packet.error_code == 453

    def test_negative_error_code(self):
        packet = Packet.from_bytes(b"%xt%foo%1%-1%{}%")
        assert packet.error_code == -1

    def test_negative_request_id(self):
        packet = Packet.from_bytes(b"%xt%foo%-1%0%{}%")
        assert packet.request_id == -1

    def test_percent_inside_payload_not_truncated(self):
        # A '%' inside the JSON payload (chat message, player name) must not
        # split the payload.
        payload = {"CM": {"MT": "100% sure & 50% off", "PN": "a%b"}}
        raw = f"%xt%acm%1%0%{json.dumps(payload)}%"
        packet = Packet.from_bytes(raw.encode())
        assert packet.command_id == "acm"
        assert packet.payload == payload

    def test_non_json_payload_wrapped_as_raw(self):
        packet = Packet.from_bytes(b"%xt%pin%1%0%<RoundHouseKick>%")
        assert packet.payload == {"raw": "<RoundHouseKick>"}

    def test_short_packet_returns_raw_wrapper(self):
        packet = Packet.from_bytes(b"%xt%x%")
        assert packet.command_id is None

    def test_null_terminator_stripped(self):
        packet = Packet.from_bytes(b"%xt%gam%1%0%{}%\x00")
        assert packet.command_id == "gam"

    def test_build_xt_request_format(self):
        # Requests use %xt%{zone}%{command}%{request_id}%{json}% — a
        # different field layout than responses.
        raw = Packet.build_xt("EmpireEx_21", "att", {"X": 1}, request_id=7)
        assert raw == '%xt%EmpireEx_21%att%7%{"X": 1}%'


class TestXMLParsing:
    def test_sys_body_action(self):
        packet = Packet.from_bytes(b"<msg t='sys'><body action='verChk' r='0'></body></msg>")
        assert packet.is_xml
        assert packet.command_id == "verChk"

    def test_root_tag_fallback(self):
        packet = Packet.from_bytes(b"<cross-domain-policy></cross-domain-policy>")
        assert packet.command_id == "cross-domain-policy"

    def test_malformed_xml_no_crash(self):
        packet = Packet.from_bytes(b"<msg t='sys'><body")
        assert packet.is_xml
        assert packet.command_id is None
