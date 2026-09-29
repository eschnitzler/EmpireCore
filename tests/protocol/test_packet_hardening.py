"""Hardening tests for packet framing, parsing and XML."""

import xml.etree.ElementTree as ET

from empire_core.protocol.packet import MALFORMED_STATUS_CODE, MAX_FRAME_SIZE, MAX_XML_SIZE, Packet


class TestFrameDebatching:
    """Finding 3: a WS frame may carry several null-delimited packets."""

    def test_iter_from_bytes_splits_batched_frame(self):
        frame = b'%xt%gam%1%0%{"M": []}%\x00%xt%acm%1%0%{"A": 1}%\x00'
        packets = Packet.iter_from_bytes(frame)
        assert [p.command_id for p in packets] == ["gam", "acm"]
        assert packets[0].payload == {"M": []}
        assert packets[1].payload == {"A": 1}

    def test_iter_from_bytes_single_packet_matches_from_bytes(self):
        frame = b'%xt%gam%1%0%{"M": []}%\x00'
        packets = Packet.iter_from_bytes(frame)
        assert len(packets) == 1
        assert packets[0] == Packet.from_bytes(frame)

    def test_iter_from_bytes_skips_padding_segments(self):
        assert Packet.iter_from_bytes(b"\x00\x00\x00") == []
        assert Packet.iter_from_bytes(b"") == []

    def test_iter_from_bytes_keeps_xml_handshake(self):
        frame = b"<msg t='sys'><body action='verChk' r='0'></body></msg>\x00"
        packets = Packet.iter_from_bytes(frame)
        assert len(packets) == 1
        assert packets[0].is_xml
        assert packets[0].command_id == "verChk"

    def test_from_bytes_unchanged_for_single_packet(self):
        # from_bytes must stay a single-packet parser: the receive loop still
        # calls it, and changing its return type would break every caller.
        packet = Packet.from_bytes(b'%xt%gam%1%0%{"M": []}%\x00')
        assert isinstance(packet, Packet)
        assert packet.command_id == "gam"


class TestPayloadTyping:
    """Finding 4: JSON-array payloads are real and must be typed."""

    def test_array_payload_parses_to_list(self):
        packet = Packet.from_bytes(b"%xt%gam%1%0%[1, 2, 3]%")
        assert packet.payload == [1, 2, 3]

    def test_payload_annotation_admits_list(self):
        annotation = Packet.__dataclass_fields__["payload"].type
        assert "list" in str(annotation)


class TestTotalParsing:
    """Finding 5: parsing never raises; the receive loop has no recovery."""

    def test_hostile_frames_never_raise(self):
        hostile = [
            b"",
            b"\x00",
            b"\x00\x00\x00",
            b"%xt%",
            b"%xt%gam%",
            b"%xt%gam%1%",
            b"%xt%gam%1%0%",
            b"%xt%gam%notanint%notanint%{}%",
            b"%xt%gam%1%0%{unclosed%",
            b"\xff\xfe\xfd",
            b"<msg",
            b"<msg><body\x00></msg>",
            b"garbage",
            b"[" * 5000,
        ]
        for data in hostile:
            packet = Packet.from_bytes(data)
            assert isinstance(packet, Packet)
            assert Packet.iter_from_bytes(data) is not None

    def test_deeply_nested_payload_degrades_to_raw(self):
        packet = Packet.from_bytes(b"%xt%gam%1%0%" + b"[" * 5000 + b"%")
        assert isinstance(packet.payload, dict)
        assert "raw" in packet.payload


class TestMalformedStatus:
    """Finding 6: a garbled status field must not look like success."""

    def test_non_integer_status_is_sentinel(self):
        packet = Packet.from_bytes(b'%xt%gam%1%abc%{"M": []}%')
        assert packet.error_code == MALFORMED_STATUS_CODE
        assert packet.error_code != 0

    def test_sentinel_cannot_collide_with_real_status(self):
        # Real status codes are >= -1 (see GGEError), so the sentinel must sit
        # well below them.
        assert MALFORMED_STATUS_CODE < -1


class TestFrameSizeBound:
    """Finding 7: oversized frames must not reach json.loads."""

    def test_oversized_frame_is_dropped(self, caplog):
        data = b"%xt%gam%1%0%{" + b'"k": 1,' * 8 + b"}%"
        data += b" " * (MAX_FRAME_SIZE + 1 - len(data))
        with caplog.at_level("WARNING"):
            packet = Packet.from_bytes(data)
        assert packet.command_id is None
        assert packet.payload is None
        # The frame must not be retained; that is the point of the bound.
        assert packet.raw_data == ""
        assert "too large" in caplog.text

    def test_frame_at_limit_still_parses(self):
        payload = b'{"pad": "' + b"a" * 1000 + b'"}'
        data = b"%xt%gam%1%0%" + payload + b"%"
        assert len(data) < MAX_FRAME_SIZE
        packet = Packet.from_bytes(data)
        assert packet.command_id == "gam"

    def test_oversized_batched_frame_is_dropped(self):
        frame = b'%xt%gam%1%0%{"M": []}%\x00' + b"x" * MAX_FRAME_SIZE
        assert Packet.iter_from_bytes(frame) == []


class TestXMLHardening:
    """Finding 8: network-controlled XML gets no entity expansion."""

    BILLION_LAUGHS = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE msg [<!ENTITY a "aaaaaaaaaa">'
        b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
        b'<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>'
        b'<msg t="sys"><body action="&c;"/></msg>'
    )

    def test_doctype_payload_is_not_parsed(self, caplog):
        with caplog.at_level("WARNING"):
            packet = Packet.from_bytes(self.BILLION_LAUGHS)
        assert packet.is_xml
        assert packet.payload is None
        assert packet.command_id is None
        assert "doctype" in caplog.text.lower()

    def test_entity_only_payload_is_not_parsed(self):
        packet = Packet.from_bytes(b'<!ENTITY x "y"><msg t="sys"><body action="verChk"/></msg>')
        assert packet.payload is None
        assert packet.command_id is None

    def test_oversized_xml_is_not_parsed(self):
        data = b"<msg t='sys'><body action='verChk' pad='" + b"a" * MAX_XML_SIZE + b"'/></msg>"
        packet = Packet.from_bytes(data)
        assert packet.payload is None
        assert packet.command_id is None

    def test_normal_handshake_xml_still_parses(self):
        packet = Packet.from_bytes(b"<msg t='sys'><body action='verChk' r='0'></body></msg>")
        assert packet.is_xml
        assert packet.command_id == "verChk"
        assert isinstance(packet.payload, ET.Element)

    def test_cross_domain_policy_still_parses(self):
        packet = Packet.from_bytes(b"<cross-domain-policy></cross-domain-policy>")
        assert packet.command_id == "cross-domain-policy"
