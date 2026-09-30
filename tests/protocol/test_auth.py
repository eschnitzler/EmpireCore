"""Auth models against the client's VOs and reply handlers."""

from typing import Any

import pytest

from empire_core.protocol.auth import (
    CheckUsernameAvailableRequest,
    CheckUsernameAvailableResponse,
    CheckUsernameExistsRequest,
    LoginRequest,
    LoginResponse,
    LoginTokenResponse,
    PasswordRecoveryRequest,
    RegisterRequest,
    RegisterResponse,
    build_version_check,
)
from empire_core.protocol.base import json_text

LOGIN_FIELDS: dict[str, Any] = {
    "CONM": 812,
    "RTM": 37,
    "PL": 1,
    "LANG": "en",
    "DID": "0",
    "AID": "17000000000001234",
    "REF": "https://ref",
}


class TestLoginRequest:
    # Expected strings are JSON.stringify of the client's C2SLoginVO, run in node.

    def test_password_login(self):
        request = LoginRequest.create("name", "pass", LT="tok", RCT="captcha", **LOGIN_FIELDS)
        assert json_text(request.to_payload()) == (
            '{"CONM":812,"RTM":37,"ID":0,"PL":1,"NOM":"name","PW":"pass","LT":null,"LANG":"en","DID":"0",'
            '"AID":"17000000000001234","KID":"","REF":"https://ref","GCI":"","SID":9,"PLFID":1,"RCT":"captcha"}'
        )

    def test_token_login(self):
        request = LoginRequest.create("name", LT="tok", **LOGIN_FIELDS)
        assert json_text(request.to_payload()) == (
            '{"CONM":812,"RTM":37,"ID":0,"PL":1,"NOM":"name","LT":"tok","LANG":"en","DID":"0",'
            '"AID":"17000000000001234","KID":"","REF":"https://ref","GCI":"","SID":9,"PLFID":1}'
        )

    def test_create_encodes_the_name_and_password(self):
        request = LoginRequest.create('O"Neil', "a'b\n", AID="1")
        assert request.username == "O&quot;Neil"
        assert request.password == "a&145;b<br />"

    def test_the_packet_is_a_json_command(self):
        packet = LoginRequest.create("n", "p", AID="1").to_packet(zone="Z", room_id=2)
        assert packet.startswith('%xt%Z%lli%2%{"CONM":0,"RTM":0,"ID":0,"PL":0,"NOM":"n","PW":"p","LT":null,')


class TestLoginResponse:
    def test_the_refusal_details(self):
        response = LoginResponse.model_validate({"GDPR": 1, "RS": "90", "IID": 21, "CD": 30, "PID": 5})
        assert response.account_deleted is True
        assert response.remaining_ban_seconds == 90
        assert response.instance_id == 21
        assert response.remaining_cooldown_seconds == 30
        assert response.player_id == 5

    def test_a_successful_login_has_no_details(self):
        response = LoginResponse.model_validate({})
        assert response.account_deleted is False
        assert response.remaining_ban_seconds is None

    def test_the_guessed_player_block_is_gone(self):
        assert "player" not in LoginResponse.model_fields
        assert "session_id" not in LoginResponse.model_fields


def test_login_token_push():
    assert LoginTokenResponse.model_validate({"LT": "abc"}).login_token == "abc"


def test_version_check_frame():
    assert build_version_check("Z", "1169011", "1e+300", 4) == "%xt%Z%vck%4%1169011%web-html5%<RoundHouseKick>%1e+300%"


class TestNameChecks:
    def test_vpn_sends_pn(self):
        assert CheckUsernameAvailableRequest(PN="x").to_payload() == {"PN": "x"}

    def test_vln_sends_nom(self):
        assert CheckUsernameExistsRequest(NOM="x").to_payload() == {"NOM": "x"}

    def test_a_refused_name_suggests_others(self):
        response = CheckUsernameAvailableResponse.model_validate({"NS": ["a1", 2, "a3"]})
        assert response.suggested_names == ["a1", "a3"]

    @pytest.mark.parametrize("attr", ["available", "exists"])
    def test_the_inverted_booleans_are_gone(self, attr):
        assert not hasattr(CheckUsernameAvailableResponse(), attr)


class TestRegister:
    def test_keys_in_the_client_order(self):
        # C2SRegisterWithNameVO: the constructor's keys first, then initialize()'s.
        request = RegisterRequest(PN="new", PW="pw", AID="1", NID=1, RCT="c")
        assert list(request.to_payload()) == [
            "DID", "CONM", "RTM", "campainPId", "campainCr", "campainLP", "adID", "timeZone",
            "PN", "PW", "REF", "LANG", "AID", "GCI", "SID", "PLFID", "NID", "RCT",
        ]  # fmt: skip

    def test_no_email(self):
        assert "EM" not in RegisterRequest(PN="new", AID="1", NID=1).to_payload()

    def test_reply(self):
        response = RegisterResponse.model_validate({"PID": 7, "NS": ["x"]})
        assert response.player_id == 7
        assert response.suggested_names == ["x"]


def test_password_recovery_sends_the_email_as_mail():
    # Client: BasicLostPasswordCommand.sendMessage builds {MAIL: text} (dll line 33056).
    assert PasswordRecoveryRequest(MAIL="a@example.com").to_payload() == {"MAIL": "a@example.com"}
