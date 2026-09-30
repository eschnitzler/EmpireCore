"""Request frames as BasicSmartfoxClient.sendMessage / sendCommand build them (dll line 7171, 7198)."""

import json

import pytest

from empire_core.alliance.models.chat import AllianceChatMessageRequest
from empire_core.protocol.base import NO_ROOM, BaseRequest, build_command, json_text, smartfox_text
from empire_core.protocol.packet import Packet


class _Named(BaseRequest):
    command = "tst"

    name: str


class TestSmartfoxText:
    def test_percent_becomes_an_entity_and_apostrophes_are_dropped(self):
        assert smartfox_text("100% O'Brien") == "100&percnt; OBrien"

    def test_an_already_escaped_percent_is_left_alone(self):
        assert smartfox_text("&percnt;") == "&percnt;"


class TestBuildCommand:
    def test_fields_and_room_id(self):
        assert build_command("EmpireEx_21", "vck", ["1169011", "web-html5", ""], 4) == (
            "%xt%EmpireEx_21%vck%4%1169011%web-html5%<RoundHouseKick>%"
        )

    @pytest.mark.parametrize(
        ("param", "wire"), [(0, "0"), ("", "<RoundHouseKick>"), (None, "<RoundHouseKick>"), (7, "7")]
    )
    def test_params_the_client_converts(self, param, wire):
        assert build_command("Z", "c", [param]) == f"%xt%Z%c%-1%{wire}%"

    def test_no_room_is_minus_one(self):
        assert NO_ROOM == -1
        assert build_command("Z", "pin", [""]) == "%xt%Z%pin%-1%<RoundHouseKick>%"


class TestJsonCommands:
    def test_json_is_written_as_json_stringify_writes_it(self):
        assert json_text({"A": 1, "B": [1, 2], "N": "ü"}) == '{"A":1,"B":[1,2],"N":"ü"}'

    def test_to_packet_carries_the_room_id(self):
        assert _Named(name="x").to_packet(zone="Z", room_id=12) == '%xt%Z%tst%12%{"name":"x"}%'

    def test_to_packet_defaults_to_no_room(self):
        assert _Named(name="x").to_packet(zone="Z") == '%xt%Z%tst%-1%{"name":"x"}%'

    def test_a_percent_or_apostrophe_in_the_json_is_escaped(self):
        assert _Named(name="50% O'Neil").to_packet(zone="Z") == '%xt%Z%tst%-1%{"name":"50&percnt; ONeil"}%'

    def test_build_xt_escapes_like_to_packet(self):
        assert Packet.build_xt("Z", "tst", {"name": "50% O'Neil"}, room_id=3) == (
            '%xt%Z%tst%3%{"name":"50&percnt; ONeil"}%'
        )

    def test_a_backslash_in_chat_goes_out_as_percnt_5c(self):
        packet = AllianceChatMessageRequest.create("a\\b").to_packet(zone="Z")
        body = packet.split("%", 5)[5][:-1]
        assert "%" not in body
        assert json.loads(body)["M"] == "a&percnt;5Cb"


class TestJsonTextNumbersAndStrings:
    # Expected strings are node's JSON.stringify of the same values.

    @pytest.mark.parametrize(
        ("value", "text"), [(1.0, "1"), (1e-7, "1e-7"), (1e16, "10000000000000000"), (1e21, "1e+21"), (0.1, "0.1")]
    )
    def test_numbers(self, value, text):
        assert json_text({"n": value}) == f'{{"n":{text}}}'

    @pytest.mark.parametrize("value", [float("nan"), float("inf")])
    def test_no_nan(self, value):
        with pytest.raises(ValueError):
            json_text({"n": value})

    def test_a_lone_surrogate_is_escaped(self):
        assert json_text("x\ud800y\U0001f600") == '"x\\ud800y\U0001f600"'


class TestNonStringParams:
    @pytest.mark.parametrize(
        ("param", "wire"),
        [(0.0, "0"), (False, "<RoundHouseKick>"), (True, "true"), (float("nan"), "<RoundHouseKick>"), (1.5, "1.5")],
    )
    def test_as_send_message_converts_them(self, param, wire):
        assert build_command("Z", "c", [param]) == f"%xt%Z%c%-1%{wire}%"


def test_int_enums_and_non_string_keys_are_written_as_numbers():
    from empire_core.enums import Kingdom

    assert json_text({"KID": Kingdom.ICE, 1: [Kingdom.ICE]}) == '{"KID":2,"1":[2]}'
    assert build_command("Z", "c", [Kingdom.ICE]) == "%xt%Z%c%-1%2%"
