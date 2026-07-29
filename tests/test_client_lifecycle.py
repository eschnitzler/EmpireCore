"""Tests for EmpireClient error surfacing and lifecycle (no real socket).

The client is built with ``EmpireClient.__new__`` and hand-wired stubs: the
behaviours under test only touch ``config``, ``connection``, ``state`` and
``_handlers``.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import get_type_hints

import pytest
from pydantic import BaseModel

from empire_core.client import client as client_module
from empire_core.client.client import EmpireClient
from empire_core.client.map_scanner import ScanResult
from empire_core.config import EmpireConfig
from empire_core.exceptions import (
    CommandError,
    EmpireError,
    EmpireTimeoutError,
    LoginCooldownError,
    LoginError,
    PacketError,
)
from empire_core.network.connection import ResponseWaiter
from empire_core.protocol.models import BaseResponse
from empire_core.protocol.models.player import GetPlayerInfoRequest, GetPlayerInfoResponse
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
        self.request_data: dict[str, str] = {}
        self.subscriptions: list[tuple[str, object]] = []
        self.unsubscriptions: list[tuple[str, object]] = []
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
        self.request_data[cmd_id] = data
        return self._resolve(cmd_id)

    def subscribe(self, cmd_id: str, callback: object) -> None:
        self.subscriptions.append((cmd_id, callback))

    def unsubscribe(self, cmd_id: str, callback: object) -> None:
        self.unsubscriptions.append((cmd_id, callback))

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
    client._handlers_lock = threading.Lock()
    return client


class RecordingLock:
    """Real lock that counts how many times it was held.

    Used to assert the handler registry is actually guarded rather than
    relying on CPython's GIL making the individual dict ops atomic.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.acquisitions = 0

    def __enter__(self) -> None:
        self._lock.acquire()
        self.acquisitions += 1

    def __exit__(self, *exc_info: object) -> None:
        self._lock.release()


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

    def test_missing_credentials_raises_a_typed_error(self):
        # The advertised catch-all is EmpireError; a builtin ValueError here
        # escapes every `except EmpireError` a caller writes.
        conn = StubConnection()
        client = make_client(conn)
        client.password = None

        with pytest.raises(LoginError, match="Username and password are required"):
            client.login()

        assert conn.events == []

    def test_missing_credentials_error_is_an_empire_error(self):
        client = make_client()
        client.username = None

        with pytest.raises(EmpireError):
            client.login()

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


class TestLoginClientVersion:
    """Both login steps must advertise the same client-version fingerprint."""

    def test_zone_login_and_xt_login_share_one_conm(self, monkeypatch):
        # Patch the single source of truth: if the zone login hardcodes its
        # own copy, the two steps drift apart on the next game-client bump.
        monkeypatch.setitem(client_module.LOGIN_DEFAULTS, "CONM", 4242)
        conn = StubConnection()
        client = make_client(conn)

        client.login()

        assert "4242%en%0" in conn.request_data["rlu"]
        xt_payload = json.loads(conn.request_data["lli"].split("%")[5])
        assert xt_payload["CONM"] == 4242


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


class TestHandlerRegistryIsLocked:
    """_handlers is written from user threads and read by the recv thread."""

    def test_register_holds_the_lock(self):
        client = make_client()
        lock = RecordingLock()
        client._handlers_lock = lock  # type: ignore[assignment]

        client._register_handler("gdi", lambda response: None)

        assert lock.acquisitions == 1
        assert client._handlers["gdi"]

    def test_unregister_holds_the_lock_and_removes_the_handler(self):
        client = make_client()

        def handler(response: BaseResponse) -> None:
            pass

        client._register_handler("gdi", handler)
        lock = RecordingLock()
        client._handlers_lock = lock  # type: ignore[assignment]

        client._unregister_handler("gdi", handler)

        assert lock.acquisitions == 1
        assert "gdi" not in client._handlers

    def test_unregister_leaves_other_handlers_alone(self):
        client = make_client()
        kept: list[object] = []

        def handler(response: BaseResponse) -> None:
            pass

        client._register_handler("gdi", handler)
        client._register_handler("gdi", kept.append)
        client._unregister_handler("gdi", handler)

        assert client._handlers["gdi"] == [kept.append]

    def test_unregister_of_unknown_handler_is_a_noop(self):
        client = make_client()

        client._unregister_handler("gdi", lambda response: None)
        client._register_handler("gdi", print)
        client._unregister_handler("gdi", lambda response: None)

        assert client._handlers["gdi"] == [print]

    def test_dispatch_snapshots_handlers_under_the_lock(self):
        client = make_client()
        client._register_handler("gam", lambda response: None)
        lock = RecordingLock()
        client._handlers_lock = lock  # type: ignore[assignment]

        client._on_packet(xt_packet("gam", '{"M": []}'))

        assert lock.acquisitions >= 1

    def test_handler_can_unregister_itself_during_dispatch(self):
        client = make_client()
        calls: list[str] = []

        def self_removing(response: BaseResponse) -> None:
            calls.append("called")
            client._unregister_handler("gam", self_removing)

        client._register_handler("gam", self_removing)

        client._on_packet(xt_packet("gam", '{"M": []}'))
        client._on_packet(xt_packet("gam", '{"M": []}'))

        assert calls == ["called"]


class TestRawChatSubscriptionIsDeprecated:
    """The typed API lives on client.alliance.on_chat_message."""

    def test_subscribe_warns_and_points_at_the_typed_api(self):
        conn = StubConnection()
        client = make_client(conn)

        def callback(packet: Packet) -> None:
            pass

        with pytest.deprecated_call(match=r"alliance\.on_chat_message"):
            client.subscribe_alliance_chat(callback)

        assert conn.subscriptions == [("acm", callback)]

    def test_unsubscribe_warns_and_still_unsubscribes(self):
        conn = StubConnection()
        client = make_client(conn)

        def callback(packet: Packet) -> None:
            pass

        with pytest.deprecated_call(match=r"alliance\.on_chat_message"):
            client.unsubscribe_alliance_chat(callback)

        assert conn.unsubscriptions == [("acm", callback)]


class TestPublicSurfaceIsTyped:
    """The README advertises a fully typed client."""

    def test_scan_methods_return_scan_result(self):
        assert get_type_hints(EmpireClient.scan_kingdom)["return"] is ScanResult
        assert get_type_hints(EmpireClient.scan_chunks)["return"] is ScanResult

    def test_chat_subscription_callbacks_are_typed(self):
        expected = Callable[[Packet], None]
        assert get_type_hints(EmpireClient.subscribe_alliance_chat)["callback"] == expected
        assert get_type_hints(EmpireClient.unsubscribe_alliance_chat)["callback"] == expected


class TestBulkPlayerDetailsPacing:
    """The server drops connections that sustain high request rates."""

    def test_sends_are_paced(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(client_module.time, "sleep", sleeps.append)
        conn = StubConnection()
        client = make_client(conn)

        client.get_player_details_bulk([1, 2, 3], timeout=0.0, send_delay=0.05)

        assert len(conn.sent) == 3
        # Paced between sends only - no leading or trailing sleep.
        assert sleeps == [0.05, 0.05]

    def test_zero_delay_keeps_the_old_burst_behaviour(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(client_module.time, "sleep", sleeps.append)
        client = make_client()

        client.get_player_details_bulk([1, 2, 3], timeout=0.0, send_delay=0.0)

        assert sleeps == []

    def test_single_id_is_not_delayed(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(client_module.time, "sleep", sleeps.append)
        client = make_client()

        client.get_player_details_bulk([7], timeout=0.0)

        assert sleeps == []

    def test_handler_is_removed_afterwards(self):
        client = make_client()

        client.get_player_details_bulk([1, 2], timeout=0.0, send_delay=0.0)

        assert client._handlers.get("gdi", []) == []

    def test_pacing_does_not_break_response_collection(self):
        client = make_client()
        original_send = client.send

        def send_and_answer(request, wait=False, timeout=5.0):
            result = original_send(request, wait=wait, timeout=timeout)
            # Simulate the server answering immediately on the recv thread.
            payload = json.dumps({"O": {"OID": request.player_id, "N": "p"}})
            client._on_packet(xt_packet("gdi", payload))
            return result

        client.send = send_and_answer  # type: ignore[method-assign]
        collected: dict[int, GetPlayerInfoResponse] = client.get_player_details_bulk(
            [1, 2], timeout=1.0, send_delay=0.01
        )

        assert sorted(collected) == [1, 2]
        assert all(isinstance(r, GetPlayerInfoResponse) for r in collected.values())
