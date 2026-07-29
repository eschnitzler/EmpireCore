"""Tests for SmartFox packet parsing and building."""

import json

from empire_core.protocol.packet import MALFORMED_STATUS_CODE, Packet


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


class TestStatusField:
    def test_non_integer_status_is_not_success(self):
        # A garbled status field must not be indistinguishable from success:
        # client.send() only raises when error_code != 0.
        packet = Packet.from_bytes(b"%xt%gcl%1%notanumber%{}%")
        assert packet.command_id == "gcl"
        assert packet.error_code == MALFORMED_STATUS_CODE
        assert packet.error_code != 0

    def test_empty_status_is_not_success(self):
        packet = Packet.from_bytes(b"%xt%gcl%1%%{}%")
        assert packet.error_code == MALFORMED_STATUS_CODE


class TestTotality:
    """from_bytes must be total: the recv loop tears down the connection on any raise."""

    def test_null_only_frame_returns_raw_wrapper(self):
        # `if not data: continue` in the recv loop does not catch b"\x00"
        packet = Packet.from_bytes(b"\x00\x00\x00")
        assert packet.command_id is None
        assert packet.payload is None
        assert packet.is_xml is False
        assert packet.raw_data == ""

    def test_empty_frame_returns_raw_wrapper(self):
        packet = Packet.from_bytes(b"")
        assert packet.command_id is None
        assert packet.raw_data == ""

    def test_invalid_utf8_xt_payload_is_replaced_not_raised(self):
        # Latin-1 bytes in a player name / chat message must not kill the loop
        packet = Packet.from_bytes(b'%xt%acm%1%0%{"PN": "caf\xe9"}%')
        assert packet.command_id == "acm"
        assert packet.error_code == 0
        assert isinstance(packet.payload, dict)
        assert packet.payload["PN"].startswith("caf")

    def test_invalid_utf8_xml_does_not_raise(self):
        packet = Packet.from_bytes(b"<msg t='sys'><body action='verChk' r='\xff'></body></msg>")
        assert packet.is_xml
        assert packet.command_id == "verChk"

    def test_invalid_utf8_junk_does_not_raise(self):
        packet = Packet.from_bytes(b"\xff\xfe\xfd")
        assert packet.command_id is None
        assert packet.raw_data != ""


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
