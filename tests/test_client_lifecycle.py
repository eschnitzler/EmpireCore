"""Tests for EmpireClient error surfacing and lifecycle (no real socket).

The client is built with ``EmpireClient.__new__`` and hand-wired stubs: the
behaviours under test only touch ``config``, ``connection``, ``state`` and
``_handlers``.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from empire_core.client import client as client_module
from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.exceptions import (
    CommandError,
    EmpireTimeoutError,
    LoginCooldownError,
    LoginError,
    PacketError,
)
from empire_core.network.connection import ResponseWaiter
from empire_core.protocol.models.player import GetPlayerInfoRequest
from empire_core.protocol.packet import Packet


def xt_packet(command: str, payload: str = "{}", error_code: int = 0) -> Packet:
    return Packet.from_bytes(f"%xt%{command}%1%{error_code}%{payload}%".encode())


class StubConnection:
    """Scripted stand-in for Connection.

    ``script`` maps a command id to either a Packet to return or an Exception
    to raise. Unscripted command ids get an empty successful packet.
    """

    def __init__(self, script: dict[str, Packet | Exception] | None = None, events: list[str] | None = None):
        self.script = script or {}
        self.events = events if events is not None else []
        self.connected = False
        self.sent: list[str] = []
        self.requested: list[str] = []
        self.disconnect_count = 0
        self.on_packet = None
        self.on_disconnect = None

    def _resolve(self, cmd_id: str) -> Packet:
        result = self.script.get(cmd_id, xt_packet(cmd_id))
        if isinstance(result, Exception):
            raise result
        return result

    def connect(self, timeout: float = 10.0) -> None:
        self.connected = True
        self.events.append("connect")

    def disconnect(self) -> None:
        self.connected = False
        self.disconnect_count += 1
        self.events.append("disconnect")

    def send(self, data: str) -> None:
        self.sent.append(data)

    def request(self, data: str, cmd_id: str, timeout: float = 5.0) -> Packet:
        self.requested.append(cmd_id)
        return self._resolve(cmd_id)

    def create_waiter(self, cmd_id: str) -> ResponseWaiter:
        return ResponseWaiter()

    def cancel_waiter(self, cmd_id: str, waiter: ResponseWaiter) -> None:
        pass

    def wait_for_result(self, cmd_id: str, waiter: ResponseWaiter, timeout: float = 5.0) -> Packet:
        return self._resolve(cmd_id)


class StubState:
    def __init__(self, movements: list | None = None, events: list[str] | None = None):
        self.movements = movements if movements is not None else []
        self.events = events if events is not None else []
        self.updates: list[tuple[str, object]] = []
        self.shutdown_count = 0

    def update_from_packet(self, cmd_id: str, payload) -> None:
        self.updates.append((cmd_id, payload))

    def get_all_movements(self) -> list:
        self.events.append("get_all_movements")
        return list(self.movements)

    def shutdown(self) -> None:
        self.shutdown_count += 1
        self.events.append("state_shutdown")


def make_client(connection: StubConnection | None = None, state: StubState | None = None) -> EmpireClient:
    client = EmpireClient.__new__(EmpireClient)
    client.config = EmpireConfig(login_timeout=0.1, request_timeout=0.1, connection_timeout=0.1)
    client.username = "tester"
    client.password = "secret"
    client.connection = connection or StubConnection()  # type: ignore[assignment]
    client.state = state or StubState()  # type: ignore[assignment]
    client.is_logged_in = False
    client._handlers = {}
    return client


class TestLoginCleansUpOnFailure:
    def test_version_check_timeout_closes_connection(self):
        conn = StubConnection({"apiOK": EmpireTimeoutError("no apiOK")})
        client = make_client(conn)

        with pytest.raises(EmpireTimeoutError, match="Version check timed out"):
            client.login()

        assert conn.disconnect_count == 1
        assert client.is_logged_in is False

    def test_timeout_keeps_the_original_cause(self):
        cause = EmpireTimeoutError("no apiOK")
        client = make_client(StubConnection({"apiOK": cause}))

        with pytest.raises(EmpireTimeoutError) as exc_info:
            client.login()

        assert exc_info.value.__cause__ is cause

    def test_zone_login_timeout_closes_connection(self):
        conn = StubConnection({"rlu": EmpireTimeoutError("no rlu")})
        client = make_client(conn)

        with pytest.raises(EmpireTimeoutError, match="Zone login timed out"):
            client.login()

        assert conn.disconnect_count == 1

    def test_login_cooldown_closes_connection_and_keeps_cooldown(self):
        conn = StubConnection({"lli": xt_packet("lli", '{"CD": 42}', error_code=453)})
        client = make_client(conn)

        with pytest.raises(LoginCooldownError) as exc_info:
            client.login()

        assert exc_info.value.cooldown == 42
        assert conn.disconnect_count == 1

    def test_auth_failure_closes_connection(self):
        conn = StubConnection({"lli": xt_packet("lli", error_code=21)})
        client = make_client(conn)

        with pytest.raises(LoginError, match="Auth failed with code 21"):
            client.login()

        assert conn.disconnect_count == 1

    def test_xt_login_timeout_closes_connection(self):
        conn = StubConnection({"lli": EmpireTimeoutError("no lli")})
        client = make_client(conn)

        with pytest.raises(EmpireTimeoutError, match="XT login timed out"):
            client.login()

        assert conn.disconnect_count == 1

    def test_missing_credentials_does_not_connect(self):
        conn = StubConnection()
        client = make_client(conn)
        client.password = None

        with pytest.raises(ValueError):
            client.login()

        assert conn.events == []

    def test_successful_login_keeps_the_connection_open(self):
        conn = StubConnection()
        client = make_client(conn)

        assert client.login() is True
        assert conn.disconnect_count == 0
        assert client.is_logged_in is True

    def test_missing_gbd_is_not_fatal(self):
        # gbd is best-effort: a missing one must not close the session.
        conn = StubConnection({"gbd": EmpireTimeoutError("no gbd")})
        client = make_client(conn)

        assert client.login() is True
        assert conn.disconnect_count == 0


class TestGetMovements:
    def test_server_error_raises_command_error(self):
        conn = StubConnection({"gam": xt_packet("gam", error_code=21)})
        state = StubState(movements=["stale"])
        client = make_client(conn, state)

        with pytest.raises(CommandError) as exc_info:
            client.get_movements()

        assert exc_info.value.command == "gam"
        assert exc_info.value.code == 21
        assert "get_all_movements" not in state.events

    def test_successful_response_returns_state_movements(self):
        conn = StubConnection({"gam": xt_packet("gam", '{"M": []}')})
        state = StubState(movements=["m1", "m2"])
        client = make_client(conn, state)

        assert client.get_movements() == ["m1", "m2"]

    def test_fire_and_forget_returns_state_movements(self):
        conn = StubConnection()
        state = StubState(movements=["m1"])
        client = make_client(conn, state)

        assert client.get_movements(wait=False) == ["m1"]
        assert conn.requested == []
        assert len(conn.sent) == 1


class TestOnPacketPayloadTypes:
    def test_list_payload_reaches_state(self):
        # 'sce' inventory pushes arrive as a JSON array; dropping them loses
        # inventory state silently.
        state = StubState()
        client = make_client(state=state)

        client._on_packet(xt_packet("sce", '[["PTT", 123]]'))

        assert state.updates == [("sce", [["PTT", 123]])]

    def test_dict_payload_still_reaches_state(self):
        state = StubState()
        client = make_client(state=state)

        client._on_packet(xt_packet("gam", '{"M": []}'))

        assert state.updates == [("gam", {"M": []})]

    def test_xml_packet_is_ignored(self):
        state = StubState()
        client = make_client(state=state)

        client._on_packet(Packet.from_bytes(b"<msg t='sys'><body action='apiOK' r='0'></body></msg>"))

        assert state.updates == []

    def test_handler_dispatch_survives_a_list_payload(self):
        state = StubState()
        client = make_client(state=state)
        seen: list[object] = []
        client._register_handler("sce", seen.append)

        client._on_packet(xt_packet("sce", '[["PTT", 123]]'))

        assert state.updates == [("sce", [["PTT", 123]])]
        assert seen == []


class TestSendErrorSurfacing:
    def test_validation_error_becomes_packet_error(self, monkeypatch):
        class Strict(BaseModel):
            n: int

        def exploding_parse_response(command, payload):
            return Strict.model_validate({"n": "not-an-int"})

        monkeypatch.setattr(client_module, "parse_response", exploding_parse_response)
        client = make_client(StubConnection({"gdi": xt_packet("gdi", '{"PID": 1}')}))

        with pytest.raises(PacketError) as exc_info:
            client.send(GetPlayerInfoRequest(PID=1), wait=True)

        assert "gdi" in str(exc_info.value)
        assert exc_info.value.__cause__ is not None
        assert type(exc_info.value.__cause__).__name__ == "ValidationError"


class TestCloseAndContextManager:
    def test_close_disconnects_before_shutting_state_down(self):
        # Shutting the state executor down first leaves a window where an
        # in-flight packet lazily recreates a leaked executor.
        events: list[str] = []
        client = make_client(StubConnection(events=events), StubState(events=events))

        client.close()

        assert events == ["disconnect", "state_shutdown"]

    def test_context_manager_closes_on_exit(self):
        conn = StubConnection()
        state = StubState()
        client = make_client(conn, state)

        with client as entered:
            assert entered is client

        assert conn.disconnect_count == 1
        assert state.shutdown_count == 1

    def test_context_manager_closes_on_exception(self):
        conn = StubConnection()
        client = make_client(conn)

        with pytest.raises(RuntimeError, match="boom"):
            with client:
                raise RuntimeError("boom")

        assert conn.disconnect_count == 1
