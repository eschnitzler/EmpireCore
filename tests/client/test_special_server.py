"""Going from the main server to a special server: the glt token, the main session's logout, and the tlep login.

Client: ``CastleConnectToSpecialServerCommand`` (bundle lines 58784-58800).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import SecretStr

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.enums import GGEError, ServerType
from empire_core.exceptions import CommandError, LoginError, SpecialServerUnavailableError
from empire_core.protocol.auth import (
    GetSpecialServerTokenRequest,
    SpecialServerLoginRequest,
    SpecialServerTokenResponse,
)
from empire_core.protocol.base import parse_response
from tests.client.test_login_sequence import ScriptedConnection, make_client, xt_packet

TOKEN_REPLY = {
    "TLT": "token-1",
    "TSIP": "special.example.invalid",
    "TSP": 443,
    "TSZ": "EmpireEx_Special",
    "ZID": 61,
    "IID": 9,
}


def _tlep_payload(conn: ScriptedConnection) -> dict[str, Any]:
    return json.loads(conn.request_data["tlep"].split("%", 5)[5].rstrip("%"))


class TestModels:
    def test_glt_sends_the_server_type(self):
        assert GetSpecialServerTokenRequest(server_type=ServerType.TEMPORARY).to_payload() == {"GST": 2}
        assert GetSpecialServerTokenRequest(server_type=ServerType.ALLIANCE_BATTLEGROUND).to_payload() == {"GST": 3}

    def test_the_glt_reply_is_read(self):
        reply = parse_response("glt", TOKEN_REPLY)
        assert isinstance(reply, SpecialServerTokenResponse)
        assert (reply.login_token, reply.server, reply.zone, reply.zone_id, reply.instance_id) == (
            "token-1",
            "special.example.invalid",
            "EmpireEx_Special",
            61,
            9,
        )
        assert "token-1" not in repr(reply)

    def test_tlep_sends_the_token(self):
        assert SpecialServerLoginRequest(login_token="t").to_payload() == {"TLT": "t"}


class TestTokenLogin:
    def _client(self, script: dict | None = None) -> tuple[EmpireClient, ScriptedConnection]:
        connection = ScriptedConnection(script)
        client = make_client(connection)
        client.password = None
        client.special_server_token = "token-1"
        return client, connection

    def test_tlep_replaces_lli_after_the_same_handshake(self):
        client, connection = self._client()

        client.login()

        assert connection.requested == ["apiOK", "rlu", "joinOK", "vck", "tlep"]
        assert _tlep_payload(connection) == {"TLT": "token-1"}
        assert connection.waited_for == ["gbd"]
        assert connection.events.index("create_waiter:gbd") < connection.events.index("request:tlep")
        assert client.is_logged_in

    def test_the_zone_is_the_special_servers(self):
        client, connection = self._client()
        client.config = EmpireConfig(default_zone="EmpireEx_Special", request_timeout=0.1, login_timeout=0.1)

        client.login()

        assert "<login z='EmpireEx_Special'>" in connection.request_data["rlu"]
        assert connection.request_data["tlep"].startswith("%xt%EmpireEx_Special%tlep%")

    def test_no_name_or_password_is_needed(self):
        client, connection = self._client()
        client.username = None

        client.login()

        assert client.is_logged_in

    def test_a_closed_server_raises_its_own_error(self):
        client, connection = self._client({"tlep": xt_packet("tlep", error_code=GGEError.NO_EVENT)})

        with pytest.raises(SpecialServerUnavailableError) as caught:
            client.login()

        assert caught.value.error is GGEError.NO_EVENT
        assert isinstance(caught.value, LoginError)
        assert not client.is_logged_in and not connection.connected

    def test_another_refusal_is_a_login_error(self):
        client, _ = self._client({"tlep": xt_packet("tlep", error_code=401)})

        with pytest.raises(LoginError) as caught:
            client.login()

        assert caught.value.code == 401
        assert not isinstance(caught.value, SpecialServerUnavailableError)


class TestConnectToSpecialServer:
    @pytest.fixture
    def main(self, monkeypatch: pytest.MonkeyPatch) -> tuple[EmpireClient, list[Any]]:
        calls: list[Any] = []
        config = EmpireConfig(username="tester", password=SecretStr("pw"), request_timeout=2.5, client_version="1.2.3")
        main = EmpireClient(config=config, keep_session=True)

        def request(request: Any, response_type: Any, timeout: float = 5.0) -> Any:
            calls.append(("request", request.to_payload(), timeout))
            return response_type.model_validate(TOKEN_REPLY)

        def login(client: EmpireClient, *args: Any, **kwargs: Any) -> None:
            calls.append(("login", client))

        monkeypatch.setattr(main, "request", request)
        monkeypatch.setattr(main, "close", lambda: calls.append("close"))
        monkeypatch.setattr(EmpireClient, "login", login)
        return main, calls

    def test_token_then_logout_then_token_login(self, main):
        client, calls = main

        special = client.connect_to_special_server(ServerType.TEMPORARY, timeout=3.0)

        assert calls[0] == ("request", {"GST": 2}, 3.0)
        assert calls[1] == "close"
        assert calls[2] == ("login", special)
        assert special is not client

    def test_the_new_client_is_set_up_for_the_special_server(self, main):
        client, _ = main

        special = client.connect_to_special_server(ServerType.ALLIANCE_BATTLEGROUND)

        assert special.special_server_token == "token-1"
        assert special.config.game_url == "wss://special.example.invalid:443"
        assert special.config.default_zone == "EmpireEx_Special"
        assert (special.config.request_timeout, special.config.client_version) == (2.5, "1.2.3")
        assert special.username == "tester"
        assert special.password is None
        assert special.keep_session is False
        assert client.config.default_zone != "EmpireEx_Special"

    def test_a_refused_token_leaves_the_main_session(self, main, monkeypatch: pytest.MonkeyPatch):
        client, calls = main

        def refuse(*args: Any, **kwargs: Any) -> Any:
            raise CommandError("glt", 145, {})

        monkeypatch.setattr(client, "request", refuse)

        with pytest.raises(CommandError):
            client.connect_to_special_server(ServerType.TEMPORARY)
        assert calls == []

    def test_the_normal_server_is_refused(self, main):
        client, calls = main

        with pytest.raises(ValueError):
            client.connect_to_special_server(ServerType.NORMAL)
        assert calls == []
