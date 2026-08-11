"""Hardening tests for the protocol layer (untrusted server bytes).

Every test here maps to a reviewed finding on the `ec-protocol` list. The
protocol layer parses bytes we do not control, so each case is written as
"hostile or drifted input must not crash, mislead, or silently vanish".
"""

import xml.etree.ElementTree as ET

import pytest
from pydantic import ValidationError

from empire_core.network.connection import _summarise_frame
from empire_core.protocol.models.alliance import AllianceInfo
from empire_core.protocol.models.map import GetMapAreaResponse, MapAreaItem, MapItemType
from empire_core.protocol.packet import (
    MALFORMED_STATUS_CODE,
    MAX_FRAME_SIZE,
    MAX_XML_SIZE,
    Packet,
)


def _castle_entry(
    x: int,
    y: int,
    castle_id: int = 900,
    player_id: int = 4242,
    relocating: int = 0,
) -> list:
    """A 20-field gaa type-1 (CASTLE) entry as the live server sends it.

    Layout (reverse-engineered, confirmed against the live server):
        [type, x, y, castle_id, player_id, lvl, lvl, lvl, ?, ?, name,
         0, 0, -1, -1, -1, 0, alliance_id, [], relocating_flag]
    """
    return [
        MapItemType.CASTLE,
        x,
        y,
        castle_id,
        player_id,
        1,
        1,
        1,
        0,
        0,
        "SomeCastle",
        0,
        0,
        -1,
        -1,
        -1,
        0,
        77,
        [],
        relocating,
    ]


class TestAllianceMemberInfoGuard:
    """Finding 1: model_post_init must not raise on drifted AMI entries."""

    def test_scalar_ami_entry_does_not_raise_typeerror(self):
        # pydantic does not wrap model_post_init exceptions in ValidationError,
        # so a raw TypeError here would escape model_validate and crash callers
        # that correctly catch only ValidationError.
        info = AllianceInfo.model_validate({"AID": 1, "AMI": [5]})
        assert info.member_info == [5]

    def test_mixed_malformed_ami_entries_are_skipped(self, caplog):
        payload = {
            "AID": 7,
            "AMI": [
                5,  # scalar
                None,
                ["not-an-int", 0, 0, 0, 2],  # unparseable player id
                [11, 0, 0, 0],  # too short
                [12, 0, 0, 0, "x"],  # unparseable tier
                [13, 0, 0, 0, 3],  # valid
            ],
        }
        with caplog.at_level("WARNING"):
            info = AllianceInfo.model_validate(payload)
        assert info.alliance_id == 7
        assert "malformed AMI entries" in caplog.text

    def test_non_list_ami_still_fails_validation(self):
        # Shape drift inside the array is tolerated; a wholly wrong AMI type is
        # still a validation error, which callers already handle.
        try:
            AllianceInfo.model_validate({"AID": 1, "AMI": "nope"})
        except ValidationError:
            pass
        else:
            raise AssertionError("expected ValidationError for non-list AMI")


class TestMovingFlags:
    """Finding 2: relocation detection and player-id keying."""

    def test_player_id_is_field_four(self):
        item = MapAreaItem.from_list(_castle_entry(10, 20, castle_id=900, player_id=4242))
        assert item.player_id == 4242
        # owner_id keeps its historical meaning (field 3 for type 1) because
        # the map scanner filters on it.
        assert item.owner_id == 900

    def test_is_relocating_reads_field_nineteen(self):
        settled = MapAreaItem.from_list(_castle_entry(10, 20, relocating=0))
        moving = MapAreaItem.from_list(_castle_entry(10, 20, relocating=1))
        assert settled.is_relocating is False
        assert moving.is_relocating is True

    def test_is_moving_flag_matches_is_relocating_and_warns(self):
        settled = MapAreaItem.from_list(_castle_entry(1, 2, relocating=0))
        moving = MapAreaItem.from_list(_castle_entry(1, 2, relocating=1))
        with pytest.warns(DeprecationWarning, match="is_relocating"):
            assert settled.is_moving_flag is False
        with pytest.warns(DeprecationWarning, match="is_relocating"):
            assert moving.is_moving_flag is True

    def test_short_entry_has_no_relocation_data(self):
        item = MapAreaItem.from_list([MapItemType.CASTLE, 5, 6, 900])
        assert item.player_id == -1
        assert item.is_relocating is False

    def test_non_castle_entry_is_never_relocating(self):
        outpost = MapAreaItem.from_list([MapItemType.OUTPOST, 5, 6, 900, 4242] + [0] * 14 + [1])
        assert outpost.is_relocating is False

    def test_get_moving_flags_keys_by_player_id(self):
        response = GetMapAreaResponse.model_validate(
            {
                "KID": 0,
                "AI": [
                    _castle_entry(100, 200, castle_id=901, player_id=111, relocating=1),
                    _castle_entry(300, 400, castle_id=902, player_id=222, relocating=0),
                ],
            }
        )
        assert response.get_moving_flags() == {111: (100, 200)}

    def test_get_moving_flags_ignores_invalid_player_ids(self):
        response = GetMapAreaResponse.model_validate(
            {
                "KID": 0,
                "AI": [
                    _castle_entry(1, 2, player_id=0, relocating=1),
                    _castle_entry(3, 4, player_id=-1, relocating=1),
                    _castle_entry(5, 6, player_id="nope", relocating=1),
                ],
            }
        )
        assert response.get_moving_flags() == {}

    def test_settled_castles_are_not_reported_as_moving(self):
        # The old heuristic (owned type-1) reported every castle in the area.
        response = GetMapAreaResponse.model_validate(
            {"KID": 0, "AI": [_castle_entry(i, i, castle_id=900 + i, player_id=1000 + i) for i in range(5)]}
        )
        assert response.get_moving_flags() == {}


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


class TestFrameRedactionEscapedQuotes:
    """Finding: a JSON-escaped quote inside a credential value must not stop
    the mask early and leak the tail of the secret."""

    def test_escaped_quote_does_not_leak_the_password_tail(self):
        summary = _summarise_frame('%xt%z%unk%1%{"PW": "hun\\"ter2secret"}%')
        assert "ter2secret" not in summary
        assert '"<redacted>"' in summary

    def test_escaped_backslash_before_the_closing_quote(self):
        summary = _summarise_frame('%xt%z%unk%1%{"PW": "hunter2\\\\"}%')
        assert "hunter2" not in summary
        assert '"<redacted>"' in summary

    def test_plain_password_is_still_masked(self):
        summary = _summarise_frame('%xt%z%unk%1%{"PW": "hunter2", "NM": "user"}%')
        assert "hunter2" not in summary
        assert '"NM": "user"' in summary
