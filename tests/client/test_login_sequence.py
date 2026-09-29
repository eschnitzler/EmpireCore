"""Tests for the EmpireClient login handshake (no real socket).

The handshake is six steps over two wire formats (XML for the SmartFox
handshake, XT for the game login) and it is the one code path every consumer
runs before anything else. What is pinned here:

* the step order and the exact packet each step puts on the wire,
* the gbd waiter being registered *before* the lli request, since gbd arrives
  immediately after a successful login and would otherwise race it,
* the error mapping for the server's login rejections (cooldown 453, bad
  credentials 401, session 440, and a garbled status field),
* which steps are fatal and which are best-effort,
* and that every failure path closes the connection and releases the state
  executor, so a failed login leaks neither a socket nor threads.

The client is built with ``EmpireClient.__new__`` and hand-wired stubs; only
``config``, ``connection`` and ``state`` are touched by the code under test.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import pytest

from empire_core.client.client import EmpireClient
from empire_core.config import LOGIN_DEFAULTS, EmpireConfig, ServerError
from empire_core.exceptions import (
    EmpireError,
    EmpireTimeoutError,
    LoginCooldownError,
    LoginError,
)
from empire_core.network.connection import ResponseWaiter
from empire_core.protocol.packet import MALFORMED_STATUS_CODE, Packet

# The full handshake in wire order: XML version check, XML zone login, XML
# autojoin, XML round trip, then the XT auth. gbd is awaited on a waiter, not
# requested, so it is not in this list.
HANDSHAKE_STEPS = ["apiOK", "rlu", "joinOK", "roundTripRes", "lli"]

# 453 comes from the config table (the login code branches on it). 401 and 440
# are deliberately *not* named in ServerError - see its docstring: both collide
# with unrelated GGEError codes, so the login path treats them as ordinary
# rejections. These literals are here to pin that generic handling, not to
# re-assert a meaning for them.
LOGIN_COOLDOWN_CODE = int(ServerError.LOGIN_COOLDOWN)
BAD_CREDENTIALS_CODE = 401
SESSION_EXPIRED_CODE = 440


def xt_packet(command: str, payload: Any = None, error_code: int = 0) -> Packet:
    body = "{}" if payload is None else json.dumps(payload)
    return Packet.from_bytes(f"%xt%{command}%1%{error_code}%{body}%".encode())


class ScriptedConnection:
    """Scripted stand-in for Connection that records the whole exchange.

    ``script`` maps the command id a step waits for to a Packet to return or an
    Exception to raise. Unscripted steps get an empty successful packet.
    """

    def __init__(self, script: dict[str, Packet | Exception] | None = None, connected: bool = False):
        self.script = script or {}
        self.connected = connected
        self.requested: list[str] = []
        self.request_data: dict[str, str] = {}
        self.waited_for: list[str] = []
        self.waiters_created: list[str] = []
        self.waiters_canceled: list[str] = []
        self.connect_timeouts: list[float] = []
        self.events: list[str] = []
        self.on_packet = None
        self.on_disconnect = None

    def _resolve(self, cmd_id: str) -> Packet:
        result = self.script.get(cmd_id, xt_packet(cmd_id))
        if isinstance(result, Exception):
            raise result
        return result

    def connect(self, timeout: float = 10.0) -> None:
        self.connected = True
        self.connect_timeouts.append(timeout)
        self.events.append("connect")

    def disconnect(self) -> None:
        self.connected = False
        self.events.append("disconnect")

    def send(self, data: str) -> None:
        self.events.append("send")

    def request(self, data: str, cmd_id: str, timeout: float = 5.0) -> Packet:
        self.requested.append(cmd_id)
        self.request_data[cmd_id] = data
        self.events.append(f"request:{cmd_id}")
        return self._resolve(cmd_id)

    def create_waiter(self, cmd_id: str) -> ResponseWaiter:
        self.waiters_created.append(cmd_id)
        self.events.append(f"create_waiter:{cmd_id}")
        return ResponseWaiter()

    def cancel_waiter(self, cmd_id: str, waiter: ResponseWaiter) -> None:
        self.waiters_canceled.append(cmd_id)
        self.events.append(f"cancel_waiter:{cmd_id}")

    def wait_for_result(self, cmd_id: str, waiter: ResponseWaiter, timeout: float = 5.0) -> Packet:
        self.waited_for.append(cmd_id)
        self.events.append(f"wait_for_result:{cmd_id}")
        return self._resolve(cmd_id)


class StubState:
    def __init__(self, events: list[str] | None = None):
        self.events = events if events is not None else []
        self.shutdown_count = 0

    def update_from_packet(self, cmd_id: str, payload: object) -> None:
        pass

    def shutdown(self) -> None:
        self.shutdown_count += 1
        self.events.append("state_shutdown")


def make_client(
    connection: ScriptedConnection | None = None,
    state: StubState | None = None,
    config: EmpireConfig | None = None,
) -> EmpireClient:
    client = EmpireClient.__new__(EmpireClient)
    client.config = config or EmpireConfig(login_timeout=0.1, request_timeout=0.1, connection_timeout=0.1)
    client.username = "tester"
    client.password = "s3cr3t-pw"
    client.connection = connection or ScriptedConnection()  # type: ignore[assignment]
    client.state = state or StubState()  # type: ignore[assignment]
    client.is_logged_in = False
    client._handlers = {}
    client._handlers_lock = threading.Lock()
    return client


def xt_login_payload(conn: ScriptedConnection) -> dict[str, Any]:
    """The JSON body of the lli packet that went on the wire."""
    return json.loads(conn.request_data["lli"].split("%", 5)[5].rstrip("%"))


# =============================================================================
# Step order and wire format
# =============================================================================


class TestHandshakeSequence:
    def test_steps_run_in_wire_order(self):
        conn = ScriptedConnection()
        client = make_client(conn)

        client.login()

        assert conn.requested == HANDSHAKE_STEPS
        assert conn.waited_for == ["gbd"]

    def test_connects_before_the_first_step(self):
        conn = ScriptedConnection()
        client = make_client(conn)

        client.login()

        assert conn.events[0] == "connect"
        assert conn.connect_timeouts == [client.config.connection_timeout]

    def test_already_connected_socket_is_reused(self):
        conn = ScriptedConnection(connected=True)
        client = make_client(conn)

        client.login()

        assert "connect" not in conn.events
        assert conn.requested == HANDSHAKE_STEPS

    def test_version_check_advertises_the_configured_game_version(self):
        conn = ScriptedConnection()
        client = make_client(conn, config=EmpireConfig(game_version="777"))

        client.login()

        assert conn.request_data["apiOK"] == ("<msg t='sys'><body action='verChk' r='0'><ver v='777' /></body></msg>")

    def test_zone_login_uses_the_configured_zone(self):
        conn = ScriptedConnection()
        client = make_client(conn, config=EmpireConfig(default_zone="EmpireEx_99"))

        client.login()

        assert "<login z='EmpireEx_99'>" in conn.request_data["rlu"]

    def test_zone_login_sends_an_empty_nick_and_the_client_fingerprint(self):
        conn = ScriptedConnection()
        client = make_client(conn)

        client.login()

        rlu = conn.request_data["rlu"]
        assert "<nick><![CDATA[]]></nick>" in rlu
        assert f"<pword><![CDATA[{LOGIN_DEFAULTS['CONM']}%en%0]]></pword>" in rlu

    def test_zone_login_never_carries_the_account_password(self):
        # The real password belongs to the XT login only; leaking it into the
        # zone-login frame would put it on the wire twice.
        conn = ScriptedConnection()
        client = make_client(conn)

        client.login()

        assert client.password is not None
        assert client.password not in conn.request_data["rlu"]
        assert client.password in conn.request_data["lli"]

    def test_autojoin_uses_the_documented_room_request(self):
        conn = ScriptedConnection()
        client = make_client(conn)

        client.login()

        assert conn.request_data["joinOK"] == "<msg t='sys'><body action='autoJoin' r='-1'></body></msg>"

    def test_round_trip_step_is_sent(self):
        conn = ScriptedConnection()
        client = make_client(conn)

        client.login()

        assert conn.request_data["roundTripRes"] == "<msg t='sys'><body action='roundTrip' r='1'></body></msg>"

    def test_xt_login_packet_shape(self):
        conn = ScriptedConnection()
        client = make_client(conn, config=EmpireConfig(default_zone="EmpireEx_99"))

        client.login()

        assert conn.request_data["lli"].startswith("%xt%EmpireEx_99%lli%1%")
        assert conn.request_data["lli"].endswith("%")

    def test_xt_login_carries_credentials_and_the_login_defaults(self):
        conn = ScriptedConnection()
        client = make_client(conn)

        client.login()

        payload = xt_login_payload(conn)
        assert payload["NOM"] == "tester"
        assert payload["PW"] == "s3cr3t-pw"
        for key, value in LOGIN_DEFAULTS.items():
            assert payload[key] == value

    def test_login_defaults_are_not_mutated_by_a_login(self):
        # The XT payload is built from LOGIN_DEFAULTS; writing the credentials
        # into that module-level dict would leak them into every later login.
        before = dict(LOGIN_DEFAULTS)
        client = make_client()

        client.login()

        assert LOGIN_DEFAULTS == before
        assert "NOM" not in LOGIN_DEFAULTS
        assert "PW" not in LOGIN_DEFAULTS


class TestGbdWaiterRace:
    """gbd arrives immediately after a successful lli."""

    def test_waiter_is_registered_before_the_lli_request(self):
        conn = ScriptedConnection()
        client = make_client(conn)

        client.login()

        assert conn.events.index("create_waiter:gbd") < conn.events.index("request:lli")

    def test_waiter_is_awaited_after_lli_succeeds(self):
        conn = ScriptedConnection()
        client = make_client(conn)

        client.login()

        assert conn.events.index("request:lli") < conn.events.index("wait_for_result:gbd")

    def test_waiter_is_canceled_on_success(self):
        conn = ScriptedConnection()
        client = make_client(conn)

        client.login()

        assert conn.waiters_canceled == ["gbd"]

    @pytest.mark.parametrize(
        "lli_result",
        [
            xt_packet("lli", error_code=BAD_CREDENTIALS_CODE),
            xt_packet("lli", {"CD": 30}, error_code=LOGIN_COOLDOWN_CODE),
            EmpireTimeoutError("no lli"),
        ],
    )
    def test_waiter_is_canceled_when_auth_fails(self, lli_result):
        # An abandoned waiter stays registered on the connection forever and
        # will swallow a later gbd push.
        conn = ScriptedConnection({"lli": lli_result})
        client = make_client(conn)

        with pytest.raises(EmpireError):
            client.login()

        assert conn.waiters_canceled == ["gbd"]

    def test_waiter_is_canceled_when_gbd_never_arrives(self):
        conn = ScriptedConnection({"gbd": EmpireTimeoutError("no gbd")})
        client = make_client(conn)

        client.login()

        assert conn.waiters_canceled == ["gbd"]


# =============================================================================
# Best-effort vs fatal steps
# =============================================================================


class TestNonFatalSteps:
    def test_missing_join_ok_continues_the_login(self):
        # The server does not always answer autoJoin.
        conn = ScriptedConnection({"joinOK": EmpireTimeoutError("no joinOK")})
        client = make_client(conn)

        assert client.login() is True
        assert conn.requested == HANDSHAKE_STEPS
        assert "disconnect" not in conn.events

    def test_missing_round_trip_continues_the_login(self):
        conn = ScriptedConnection({"roundTripRes": EmpireTimeoutError("no roundTripRes")})
        client = make_client(conn)

        assert client.login() is True
        assert client.is_logged_in is True

    def test_both_optional_steps_missing_is_still_a_login(self):
        conn = ScriptedConnection(
            {
                "joinOK": EmpireTimeoutError("no joinOK"),
                "roundTripRes": EmpireTimeoutError("no roundTripRes"),
                "gbd": EmpireTimeoutError("no gbd"),
            }
        )
        client = make_client(conn)

        assert client.login() is True
        assert "disconnect" not in conn.events

    def test_missing_gbd_is_warned_about(self, caplog):
        conn = ScriptedConnection({"gbd": EmpireTimeoutError("no gbd")})
        client = make_client(conn)

        with caplog.at_level("WARNING", logger="empire_core.client.client"):
            client.login()

        assert "gbd" in caplog.text


class TestFatalSteps:
    @pytest.mark.parametrize(
        "step,message",
        [
            ("apiOK", "Version check timed out"),
            ("rlu", "Zone login timed out"),
            ("lli", "XT login timed out"),
        ],
    )
    def test_required_step_timeouts_are_labeled_and_fatal(self, step, message):
        conn = ScriptedConnection({step: EmpireTimeoutError("silence")})
        client = make_client(conn)

        with pytest.raises(EmpireTimeoutError, match=message):
            client.login()

        assert "disconnect" in conn.events

    def test_a_failed_step_stops_the_sequence(self):
        conn = ScriptedConnection({"rlu": EmpireTimeoutError("no rlu")})
        client = make_client(conn)

        with pytest.raises(EmpireTimeoutError):
            client.login()

        # Nothing past the zone login went on the wire.
        assert conn.requested == ["apiOK", "rlu"]
        assert conn.waiters_created == []


# =============================================================================
# Server rejection mapping
# =============================================================================


class TestAuthRejections:
    def test_invalid_credentials_raise_login_error_with_the_code(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", error_code=BAD_CREDENTIALS_CODE)})
        client = make_client(conn)

        with pytest.raises(LoginError, match="401"):
            client.login()

        assert client.is_logged_in is False
        assert "disconnect" in conn.events

    def test_invalid_credentials_are_not_reported_as_a_cooldown(self):
        # Callers retry after a LoginCooldownError; retrying bad credentials
        # just burns login attempts.
        conn = ScriptedConnection({"lli": xt_packet("lli", error_code=BAD_CREDENTIALS_CODE)})
        client = make_client(conn)

        with pytest.raises(LoginError) as exc_info:
            client.login()

        assert not isinstance(exc_info.value, LoginCooldownError)

    def test_session_expired_is_a_login_error(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", error_code=SESSION_EXPIRED_CODE)})
        client = make_client(conn)

        with pytest.raises(LoginError, match="440"):
            client.login()

    def test_unknown_rejection_code_still_raises_a_typed_error(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", error_code=12345)})
        client = make_client(conn)

        with pytest.raises(LoginError, match="12345"):
            client.login()

    def test_garbled_status_is_not_treated_as_a_successful_login(self):
        # A status field the parser cannot read becomes MALFORMED_STATUS_CODE;
        # treating it as 0 would report a login that never happened.
        conn = ScriptedConnection({"lli": Packet.from_bytes(b"%xt%lli%1%notanumber%{}%")})
        client = make_client(conn)

        with pytest.raises(LoginError, match=str(MALFORMED_STATUS_CODE)):
            client.login()

        assert client.is_logged_in is False

    def test_rejection_message_does_not_echo_the_password(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", error_code=BAD_CREDENTIALS_CODE)})
        client = make_client(conn)

        with pytest.raises(LoginError) as exc_info:
            client.login()

        assert "s3cr3t-pw" not in str(exc_info.value)


class TestCooldownReporting:
    def test_cooldown_seconds_are_surfaced(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", {"CD": 42}, error_code=LOGIN_COOLDOWN_CODE)})
        client = make_client(conn)

        with pytest.raises(LoginCooldownError) as exc_info:
            client.login()

        assert exc_info.value.cooldown == 42
        assert "42" in str(exc_info.value)

    def test_cooldown_without_a_cd_field_reports_zero(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", {}, error_code=LOGIN_COOLDOWN_CODE)})
        client = make_client(conn)

        with pytest.raises(LoginCooldownError) as exc_info:
            client.login()

        assert exc_info.value.cooldown == 0

    def test_string_cooldown_is_coerced(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", {"CD": "42"}, error_code=LOGIN_COOLDOWN_CODE)})
        client = make_client(conn)

        with pytest.raises(LoginCooldownError) as exc_info:
            client.login()

        assert exc_info.value.cooldown == 42

    def test_array_payload_cooldown_reports_zero(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", [1, 2, 3], error_code=LOGIN_COOLDOWN_CODE)})
        client = make_client(conn)

        with pytest.raises(LoginCooldownError) as exc_info:
            client.login()

        assert exc_info.value.cooldown == 0

    def test_cooldown_is_catchable_as_a_login_error(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", {"CD": 5}, error_code=LOGIN_COOLDOWN_CODE)})
        client = make_client(conn)

        with pytest.raises(LoginError):
            client.login()


# =============================================================================
# Cleanup after a failed login
# =============================================================================


class TestFailedLoginReleasesResources:
    def test_failure_disconnects_and_shuts_the_state_executor_down(self):
        # close() runs on the raising path, and in that order: shutting the
        # state executor down first lets a late packet recreate a leaked one.
        events: list[str] = []
        conn = ScriptedConnection({"lli": xt_packet("lli", error_code=BAD_CREDENTIALS_CODE)})
        conn.events = events
        state = StubState(events=events)
        client = make_client(conn, state)

        with pytest.raises(LoginError):
            client.login()

        assert events[-2:] == ["disconnect", "state_shutdown"]
        assert state.shutdown_count == 1

    def test_failure_at_the_first_step_closes_the_socket(self):
        conn = ScriptedConnection({"apiOK": EmpireTimeoutError("no apiOK")})
        client = make_client(conn)

        with pytest.raises(EmpireTimeoutError):
            client.login()

        assert conn.connected is False

    def test_cleanup_failure_does_not_mask_the_original_error(self, caplog):
        conn = ScriptedConnection({"lli": xt_packet("lli", error_code=BAD_CREDENTIALS_CODE)})
        client = make_client(conn)

        def exploding_disconnect() -> None:
            raise RuntimeError("disconnect blew up")

        conn.disconnect = exploding_disconnect  # type: ignore[method-assign]

        with caplog.at_level("ERROR", logger="empire_core.client.client"):
            with pytest.raises(LoginError, match="401"):
                client.login()

        assert "Cleanup after failed login raised" in caplog.text

    def test_a_failed_relogin_clears_the_logged_in_flag(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", error_code=BAD_CREDENTIALS_CODE)})
        client = make_client(conn)
        client.is_logged_in = True

        with pytest.raises(LoginError):
            client.login()

        assert client.is_logged_in is False

    def test_every_login_failure_is_an_empire_error(self):
        # The documented catch-all: `except EmpireError` must cover the lot.
        failures: list[dict[str, Packet | Exception]] = [
            {"apiOK": EmpireTimeoutError("x")},
            {"rlu": EmpireTimeoutError("x")},
            {"lli": EmpireTimeoutError("x")},
            {"lli": xt_packet("lli", error_code=BAD_CREDENTIALS_CODE)},
            {"lli": xt_packet("lli", {"CD": 1}, error_code=LOGIN_COOLDOWN_CODE)},
        ]
        for script in failures:
            client = make_client(ScriptedConnection(script))
            with pytest.raises(EmpireError):
                client.login()


class TestSuccessfulLogin:
    def test_returns_true_and_marks_the_session_logged_in(self):
        client = make_client()

        assert client.login() is True
        assert client.is_logged_in is True

    def test_success_keeps_the_connection_open(self):
        conn = ScriptedConnection()
        client = make_client(conn)

        client.login()

        assert conn.connected is True
        assert "disconnect" not in conn.events

    def test_zero_error_code_payload_is_accepted(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", {"E": 0, "PID": 4242})})
        client = make_client(conn)

        assert client.login() is True

    def test_missing_credentials_never_touch_the_socket(self):
        conn = ScriptedConnection()
        client = make_client(conn)
        client.password = None

        with pytest.raises(LoginError, match="Username and password are required"):
            client.login()

        assert conn.events == []
