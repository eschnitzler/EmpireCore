"""Tests for SmartFox packet parsing and building."""

import json
import logging

import pytest

from empire_core.protocol import packet as packet_module
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


class TestTruncatedFrames:
    """A frame cut short must never come out looking like a valid response."""

    def test_frame_without_a_status_field_is_a_raw_wrapper(self):
        # Fewer than 5 '%'-separated parts: there is no command to trust.
        packet = Packet.from_bytes(b"%xt%gam%")
        assert packet.command_id is None
        assert packet.payload is None
        assert packet.error_code == 0  # the field default, not a parsed status

    def test_frame_cut_off_after_the_request_id_has_no_success_status(self):
        # This one *does* reach the command, so the status is what protects the
        # caller: client.send() only raises on error_code != 0.
        packet = Packet.from_bytes(b"%xt%gam%1%")
        assert packet.command_id == "gam"
        assert packet.request_id == 1
        assert packet.error_code == MALFORMED_STATUS_CODE
        assert packet.payload == {"raw": ""}

    def test_non_numeric_request_id_falls_back_without_losing_the_command(self):
        packet = Packet.from_bytes(b"%xt%gam%abc%0%{}%")
        assert packet.command_id == "gam"
        assert packet.request_id == -1
        # The status is still readable, so this is a usable response.
        assert packet.error_code == 0

    def test_float_status_is_not_silently_truncated(self):
        packet = Packet.from_bytes(b"%xt%gam%1%1.5%{}%")
        assert packet.error_code == MALFORMED_STATUS_CODE

    def test_empty_command_id_is_falsy(self):
        # Consumers gate on `if not packet.command_id`, so an empty command must
        # not be routed as if it named something.
        packet = Packet.from_bytes(b"%xt%%1%0%{}%")
        assert not packet.command_id

    def test_junk_frame_keeps_its_bytes_for_diagnosis(self):
        packet = Packet.from_bytes(b"just some junk")
        assert packet.command_id is None
        assert packet.payload is None
        assert packet.raw_data == "just some junk"


class TestPayloadShapes:
    """``payload`` is a union; each branch is reachable from real traffic."""

    def test_object_payload_is_a_dict(self):
        assert Packet.from_bytes(b'%xt%gam%1%0%{"M": []}%').payload == {"M": []}

    def test_array_payload_stays_a_list(self):
        # 'sce' inventory pushes arrive like this, so consumers must not assume
        # .get() is available after a None-check.
        payload = Packet.from_bytes(b'%xt%sce%1%0%[["PTT", 123]]%').payload
        assert isinstance(payload, list)
        assert payload == [["PTT", 123]]

    def test_empty_payload_field_becomes_an_empty_raw_wrapper(self):
        assert Packet.from_bytes(b"%xt%gam%1%0%%").payload == {"raw": ""}

    def test_bare_scalar_payload_is_wrapped_not_parsed(self):
        # Only '{' / '[' payloads go through json.loads; a bare number is kept
        # verbatim rather than silently becoming an int payload.
        assert Packet.from_bytes(b"%xt%gam%1%0%123%").payload == {"raw": "123"}

    def test_broken_json_object_is_wrapped(self):
        assert Packet.from_bytes(b"%xt%gam%1%0%{unclosed%").payload == {"raw": "{unclosed"}


class TestBatchedFrameHandling:
    """from_bytes is a single-packet parser by contract."""

    def test_from_bytes_swallows_a_second_packet_into_the_payload(self):
        # Pinned deliberately: iter_from_bytes is the batch-aware entry point,
        # and the receive loop still calls from_bytes. If this ever changes,
        # every caller of from_bytes needs revisiting.
        frame = b'%xt%gam%1%0%{"M": []}%\x00%xt%acm%1%0%{"A": 1}%\x00'
        packet = Packet.from_bytes(frame)
        assert packet.command_id == "gam"
        assert isinstance(packet.payload, dict)
        assert "acm" in packet.payload["raw"]

    def test_trailing_null_padding_does_not_affect_a_single_packet(self):
        packet = Packet.from_bytes(b'%xt%gam%1%0%{"M": []}%\x00\x00\x00')
        assert packet.command_id == "gam"
        assert packet.payload == {"M": []}


class TestDegradedFrameWarnings:
    """A frame degrading to command_id=None matches no waiter or subscriber
    and is dropped silently end-to-end, so the degradation itself must be
    visible: one rate-limited warning, with credentials masked."""

    @pytest.fixture(autouse=True)
    def reset_rate_limit(self, monkeypatch):
        monkeypatch.setattr(packet_module, "_degraded_frame_count", 0)
        monkeypatch.setattr(packet_module, "_degraded_frame_warn_at", 0.0)

    @staticmethod
    def _warnings(caplog):
        return [r for r in caplog.records if r.levelno == logging.WARNING and "raw wrapper" in r.getMessage()]

    def test_junk_prefix_is_warned_with_the_frame_prefix(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.protocol.packet"):
            packet = Packet.from_bytes(b"garbage frame")
        assert packet.command_id is None
        warnings = self._warnings(caplog)
        assert len(warnings) == 1
        assert "garbage frame" in warnings[0].getMessage()

    def test_xml_parse_failure_is_warned(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.protocol.packet"):
            packet = Packet.from_bytes(b"<msg t='sys'><unclosed")
        assert packet.command_id is None
        assert len(self._warnings(caplog)) == 1

    def test_truncated_xt_frame_is_warned(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.protocol.packet"):
            packet = Packet.from_bytes(b"%xt%x%")
        assert packet.command_id is None
        assert len(self._warnings(caplog)) == 1

    def test_empty_and_null_only_frames_are_not_warned(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.protocol.packet"):
            Packet.from_bytes(b"")
            Packet.from_bytes(b"\x00\x00")
        assert self._warnings(caplog) == []

    def test_credentials_are_masked_in_the_logged_prefix(self, caplog):
        # The password contains a JSON-escaped quote; the mask must consume
        # it rather than stop there and leak the tail.
        frame = b'junk {"PW": "hun\\"ter2secret"} trailing'
        with caplog.at_level(logging.WARNING, logger="empire_core.protocol.packet"):
            Packet.from_bytes(frame)
        assert "ter2secret" not in caplog.text
        assert "<redacted>" in caplog.text

    def test_logged_prefix_is_truncated(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.protocol.packet"):
            Packet.from_bytes(b"junk " + b"A" * 500)
        assert "A" * 200 not in self._warnings(caplog)[0].getMessage()

    def test_warning_is_rate_limited_and_reports_the_suppressed_count(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="empire_core.protocol.packet"):
            Packet.from_bytes(b"junk one")
            Packet.from_bytes(b"junk two")  # inside the window: debug only
            assert len(self._warnings(caplog)) == 1

            packet_module._degraded_frame_warn_at = 0.0  # window elapses
            Packet.from_bytes(b"junk three")
        warnings = self._warnings(caplog)
        assert len(warnings) == 2
        assert "1 further" in warnings[-1].getMessage()

    def test_malformed_xt_json_payload_is_logged_at_debug(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="empire_core.protocol.packet"):
            packet = Packet.from_bytes(b"%xt%gam%1%0%{broken%")
        assert packet.payload == {"raw": "{broken"}
        assert any(r.levelno == logging.DEBUG and "gam" in r.getMessage() for r in caplog.records)


class TestRoundTrip:
    def test_to_bytes_appends_the_wire_terminator(self):
        packet = Packet.from_bytes(b'%xt%gam%1%0%{"M": []}%')
        assert packet.to_bytes() == b'%xt%gam%1%0%{"M": []}%\x00'

    def test_reparsing_to_bytes_yields_the_same_packet(self):
        original = Packet.from_bytes(b'%xt%acm%1%0%{"CM": {"MT": "100% off"}}%')
        assert Packet.from_bytes(original.to_bytes()) == original

    def test_a_built_request_must_not_be_read_back_as_a_response(self):
        # The two layouts differ: a request carries the zone where a response
        # carries the command, so from_bytes reads a request's zone as the
        # command and its request id as the status. from_bytes is for inbound
        # frames only - this pins why.
        raw = Packet.build_xt("EmpireEx_21", "acm", {"M": "100&percnt; off"}, request_id=1)
        packet = Packet.from_bytes(raw.encode())
        assert packet.command_id == "EmpireEx_21"
        assert packet.error_code == 1
        # The payload does survive the misread, which is what makes the
        # confusion easy to miss.
        assert packet.payload == {"M": "100&percnt; off"}
