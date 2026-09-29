"""Tests for the response registry and BaseResponse."""

import pytest
from pydantic import Field

from empire_core.protocol.base import BaseResponse, get_response_model
from empire_core.protocol.models import parse_response


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
