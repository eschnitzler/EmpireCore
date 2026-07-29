"""Tests for the protocol model registry and base behaviors."""

import logging

import pytest
from pydantic import Field, ValidationError

from empire_core.protocol.models import parse_response
from empire_core.protocol.models.alliance import AllianceInfo
from empire_core.protocol.models.base import (
    BaseResponse,
    decode_chat_text,
    encode_chat_text,
    get_response_model,
)


class TestRegistry:
    def test_known_commands_registered(self):
        # Importing the models package must register all command modules,
        # including defense (previously forgotten in __init__).
        for command in ("gam", "gaa", "ain", "acm", "acl", "gdi", "dfc", "sdi", "hgh", "gcl", "dcl"):
            assert get_response_model(command) is not None, f"'{command}' not registered"

    def test_unknown_command_returns_none(self):
        assert get_response_model("nonexistent") is None
        assert parse_response("nonexistent", {}) is None

    def test_duplicate_registration_raises(self):
        class UniqueResponse(BaseResponse):
            command = "test_dup_cmd"

        with pytest.raises(TypeError, match="Duplicate response registration"):

            class ConflictingResponse(BaseResponse):
                command = "test_dup_cmd"

    def test_register_opt_out(self):
        class OptOutResponse(BaseResponse, register=False):
            command = "test_optout_cmd"

        assert get_response_model("test_optout_cmd") is None


class TestBaseResponse:
    def test_error_code_from_payload(self):
        class SomeResponse(BaseResponse, register=False):
            command = "test_some_cmd"

        response = SomeResponse.model_validate({"E": 21})
        assert response.error_code == 21
        assert response.success is False

        ok = SomeResponse.model_validate({})
        assert ok.error_code == 0
        assert ok.success is True

    def test_error_payload_parses_for_registered_models(self):
        # An error-shaped payload ({"E": code} and nothing else) must not
        # raise ValidationError for any registered response model.
        for command in ("ain", "acl", "gam", "gaa", "dfc", "gdi", "gcl"):
            response = parse_response(command, {"E": 21})
            assert response is not None, f"'{command}' has no model"
            assert response.error_code == 21
            assert response.success is False

    def test_to_payload_uses_aliases(self):
        class AliasedResponse(BaseResponse, register=False):
            command = "test_alias_cmd"
            castle_id: int = Field(alias="CID", default=0)

        response = AliasedResponse(CID=5)
        assert response.to_payload()["CID"] == 5


class TestAllianceInfoMemberInfo:
    """AMI is an unvalidated positional server array that has drifted format before.

    model_post_init exceptions are NOT wrapped by pydantic, so anything raised
    here escapes model_validate un-wrapped and defeats `except ValidationError`.
    """

    @pytest.mark.parametrize(
        "ami",
        [
            [5],  # entry is a bare int -> len() fails
            [None],  # entry is None
            [[1, 2]],  # entry too short
            [[[1, 2], 0, 0, 0, 3]],  # unhashable player id
            [{"OID": 1, "AT": 3}],  # drifted to dicts
            "not-a-list",  # whole field drifted
        ],
    )
    def test_malformed_ami_does_not_raise(self, ami):
        try:
            info = AllianceInfo.model_validate({"AID": 1, "AMI": ami})
        except ValidationError:
            # Rejecting the field outright is acceptable; crashing is not.
            return
        assert info.alliance_id == 1

    def test_malformed_ami_entry_is_logged(self, caplog):
        with caplog.at_level(logging.WARNING, logger="empire_core.protocol.models.alliance"):
            AllianceInfo.model_validate({"AID": 1, "AMI": [5]})
        assert [r for r in caplog.records if r.levelno >= logging.WARNING], "malformed AMI logged nothing"

    def test_valid_ami_still_populates_activity_tier(self):
        info = AllianceInfo.model_validate(
            {
                "AID": 1,
                "M": [{"OID": 7, "N": "online_guy"}, {"OID": 8, "N": "afk_guy"}],
                "AMI": [[7, 0, 0, 0, 0], [8, 0, 0, 0, 4]],
            }
        )
        by_name = {m.name: m for m in info.members}
        assert by_name["online_guy"].activity_tier == 0
        assert by_name["online_guy"].is_online
        assert by_name["afk_guy"].activity_tier == 4
        assert not by_name["afk_guy"].is_online
        assert info.online_count == 1

    def test_good_entries_survive_a_bad_neighbour(self):
        info = AllianceInfo.model_validate(
            {
                "AID": 1,
                "M": [{"OID": 7, "N": "good"}],
                "AMI": [5, [7, 0, 0, 0, 2]],
            }
        )
        assert info.members[0].activity_tier == 2


class TestChatEncoding:
    def test_roundtrip_special_characters(self):
        original = "Hello 100% \"friend\" 'quoted'\nnew \\ line"
        assert decode_chat_text(encode_chat_text(original)) == original

    def test_backslash_wire_format(self):
        # Backslash must encode to literal %5C, not &percnt;5C
        assert encode_chat_text("\\") == "%5C"

    def test_literal_percent_5c_text_roundtrip(self):
        # A user literally typing "%5C" must not decode into a backslash
        original = "give me %5C please"
        assert decode_chat_text(encode_chat_text(original)) == original
