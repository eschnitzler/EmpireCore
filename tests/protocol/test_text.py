"""Tests for the client's JSON text encoding."""

import pytest

from empire_core.alliance.models.chat import AllianceChatMessageRequest, AllianceChatMessageResponse
from empire_core.protocol.text import decode_json_text, encode_json_text


class TestChatEncoding:
    """Expectations printed by node running TextValide (dll lines 5817-5833) and C2SAllianceChatVO."""

    @pytest.mark.parametrize(
        ("text", "encoded"),
        [
            (
                "Hello 100% \"friend\" 'quoted'\nnew \\ line",
                "Hello 100&percnt; &quot;friend&quot; &145;quoted&145;<br />new %5C line",
            ),
            ("\\", "%5C"),
            ("give me %5C please", "give me &percnt;5C please"),
            ("a\r\nb\tc", "a<br /><br />b c"),
            ("[b]x[/b]", "[b]x[/b]"),
        ],
    )
    def test_encode(self, text, encoded):
        assert encode_json_text(text) == encoded

    @pytest.mark.parametrize(
        ("wire", "decoded"),
        [
            ("&percnt;5C", "\\"),
            ("a<br />b<br>c", "a\nb<br>c"),
            ("&quot;x&quot; &145;y&145;", "\"x\" 'y'"),
            (" b x /b ", " b x /b "),
            ("[b]x[/b]", " b x /b "),
            ("", ""),
            (None, ""),
        ],
    )
    def test_decode(self, wire, decoded):
        assert decode_json_text(wire) == decoded

    def test_the_client_does_not_round_trip_a_typed_percent_5c(self):
        assert decode_json_text(encode_json_text("give me %5C please")) == "give me \\ please"

    def test_the_chat_request_drops_carriage_returns_first(self):
        assert AllianceChatMessageRequest.create("a\r\nb\tc").to_payload() == {"M": "a<br />b c"}

    def test_a_chat_message_decodes_as_the_client_does(self):
        response = AllianceChatMessageResponse.model_validate({"CM": {"PN": "p", "MT": "[x] &percnt;", "PID": 1}})
        assert response.decoded_text == " x  %"
