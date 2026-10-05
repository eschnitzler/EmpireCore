"""Tests for the EmpireClient login handshake (no real socket).

The handshake is six steps over two wire formats (XML for the SmartFox
handshake, XT for the version check and the game login) and it is the one code
path every consumer runs before anything else. What is pinned here:

* the step order and the exact packet each step puts on the wire,
* the gbd waiter being registered *before* the lli request, since gbd arrives
  immediately after a successful login and would otherwise race it,
* the error mapping for the server's login rejections (cooldown 453, ban 27,
  wrong server 368, refused token 409, other codes, and a garbled status field),
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
from empire_core.config import LOGIN_DEFAULTS, EmpireConfig
from empire_core.exceptions import (
    AccountBannedError,
    ClientVersionError,
    EmpireError,
    EmpireTimeoutError,
    LoginCooldownError,
    LoginError,
    WrongServerError,
)
from empire_core.network.connection import ResponseWaiter
from empire_core.protocol.errors import GGEError
from empire_core.protocol.packet import MALFORMED_STATUS_CODE, Packet

# The requests in wire order: XML version check, XML zone login, XML autojoin,
# the XT version check, then the XT auth. The round trip is sent, not
# requested, and gbd is awaited on a waiter, so neither is in this list.
HANDSHAKE_STEPS = ["apiOK", "rlu", "joinOK", "vck", "lli"]

# 453 is the one refusal the login treats as a cooldown. 401 and 440 have
# unrelated meanings in GGEError; they pin that any other code is an ordinary
# rejection.
LOGIN_COOLDOWN_CODE = int(GGEError.LOGIN_COOLDOWN_ACTIVE)
BAD_CREDENTIALS_CODE = 401
SESSION_EXPIRED_CODE = 440
SESSION_ID = "1.5e+300"


def xt_packet(command: str, payload: Any = None, error_code: int = 0) -> Packet:
    body = "{}" if payload is None else json.dumps(payload)
    return Packet.from_bytes(f"%xt%{command}%1%{error_code}%{body}%".encode())


def room_list(room: str, name: str = "Lobby") -> Packet:
    """One rlu message: t[1] the room id, t[5] its name (BasicSmartfoxClient.setRoomList, dll line 7155)."""
    return Packet.from_bytes(f"%xt%rlu%-1%{room}%B%A%A%{name}%".encode())


def join_ok(room: str) -> Packet:
    return Packet.from_bytes(f"<msg t='sys'><body action='joinOK' r='{room}'><pid id='0'/></body></msg>".encode())


def lobby(room: str) -> dict[str, Packet | Exception]:
    return {"rlu": room_list(room), "joinOK": join_ok(room)}


class ScriptedConnection:
    """Scripted stand-in for Connection that records the whole exchange.

    ``script`` maps the command id a step waits for to a Packet to return or an
    Exception to raise. Unscripted steps get an empty successful packet.
    """

    def __init__(self, script: dict[str, Packet | Exception] | None = None, connected: bool = False):
        self.script = {**lobby("1"), **(script or {})}
        self.room_id = -1
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
        self.sent: list[str] = []
        self.subscribers: dict[str, list[Any]] = {}

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
        self.sent.append(data)
        self.events.append("send")
        if "action='roundTrip'" in data and not isinstance(self.script.get("roundTripRes"), Exception):
            answer = Packet.from_bytes(b"<msg t='sys'><body action='roundTripRes' r='1'></body></msg>")
            for callback in list(self.subscribers.get("roundTripRes", [])):
                callback(answer)

    def subscribe(self, cmd_id: str, callback: Any) -> None:
        self.subscribers.setdefault(cmd_id, []).append(callback)
        self.events.append(f"subscribe:{cmd_id}")

    def unsubscribe(self, cmd_id: str, callback: Any) -> None:
        self.subscribers[cmd_id].remove(callback)
        self.events.append(f"unsubscribe:{cmd_id}")

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

    def update_from_packet(self, cmd_id: str, payload: object, error_code: int = 0) -> None:
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
    client.login_token = None
    client.session_id = SESSION_ID
    client.connection = connection or ScriptedConnection()  # type: ignore[assignment]
    client.state = state or StubState()  # type: ignore[assignment]
    client.is_logged_in = False
    client._handlers = {}
    client._handlers_lock = threading.Lock()
    client._streams = set()
    client._streams_lock = threading.Lock()
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
        # Client: the build number, language and distributor id (dll line 7230).
        assert "<pword><![CDATA[1169011%en%0]]></pword>" in rlu

    def test_zone_login_sends_the_configured_client_version(self):
        conn = ScriptedConnection()
        make_client(conn, config=EmpireConfig(client_version="1.2.3")).login()
        assert "<pword><![CDATA[1002003%en%0]]></pword>" in conn.request_data["rlu"]

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

    def test_round_trip_is_sent_in_the_joined_room_before_the_version_check(self):
        conn = ScriptedConnection(lobby("2"))
        client = make_client(conn)

        client.login()

        assert conn.sent == ["<msg t='sys'><body action='roundTrip' r='2'></body></msg>"]
        assert conn.events.index("send") < conn.events.index("request:vck")
        assert conn.subscribers["roundTripRes"] == []

    def test_version_check_frame(self):
        conn = ScriptedConnection(lobby("2"))
        make_client(conn).login()
        # Client: BasicJoinedRoomCommand sends [build, "web-html5", "", sessionId] (dll line 33011).
        assert conn.request_data["vck"] == f"%xt%EmpireEx_21%vck%2%1169011%web-html5%<RoundHouseKick>%{SESSION_ID}%"

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
        assert payload["LT"] is None
        for key, value in LOGIN_DEFAULTS.items():
            assert payload[key] == value

    def test_xt_login_keys_are_in_the_client_order(self):
        conn = ScriptedConnection()
        make_client(conn).login()
        # Client: JSON.stringify of C2SLoginVO (bundle line 131792), checked in node.
        assert list(xt_login_payload(conn)) == [
            "CONM", "RTM", "ID", "PL", "NOM", "PW", "LT", "LANG", "DID", "AID", "KID", "REF", "GCI", "SID", "PLFID",
        ]  # fmt: skip

    def test_name_and_password_are_encoded_as_the_login_screen_does(self):
        conn = ScriptedConnection()
        client = make_client(conn)
        client.username = 'a"b'
        client.password = "p%w'd\\"

        client.login()

        # Layer 1 (encode_json_text), then the frame turns its '%' into '&percnt;'.
        payload = xt_login_payload(conn)
        assert payload["NOM"] == "a&quot;b"
        assert payload["PW"] == "p&percnt;w&145;d&percnt;5C"

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
    def test_missing_round_trip_continues_the_login_with_no_round_trip_time(self):
        conn = ScriptedConnection({"roundTripRes": EmpireTimeoutError("no roundTripRes")})
        client = make_client(conn)

        assert client.login() is True
        assert client.is_logged_in is True
        assert xt_login_payload(conn)["RTM"] == 0

    def test_both_optional_steps_missing_is_still_a_login(self):
        conn = ScriptedConnection(
            {
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
            ("apiOK", "API version check"),
            ("rlu", "Zone login timed out"),
            ("joinOK", "Room join"),
            ("vck", "Version check"),
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

        with pytest.raises(LoginError, match="Username and a password or login token are required"):
            client.login()

        assert conn.events == []


class TestJoinedRoom:
    """joinOK's ``r`` is the room every later command carries (dll line 7232)."""

    def test_the_room_id_from_join_ok_goes_into_lli(self):
        conn = ScriptedConnection(lobby("3"))
        client = make_client(conn)

        client.login()

        assert conn.room_id == 3
        assert conn.request_data["lli"].startswith("%xt%EmpireEx_21%lli%3%")

    @pytest.mark.parametrize(("attribute", "room"), [("3.0", 3), ("", 0), (" 4 ", 4), ("x", -1)])
    def test_the_room_id_is_read_with_number(self, attribute, room):
        conn = ScriptedConnection({"rlu": room_list(str(room)), "joinOK": join_ok(attribute)})
        make_client(conn).login()
        assert conn.room_id == room

    def test_a_missing_join_ok_fails_the_login(self):
        # The client sends vck only from the Lobby join (dll line 7163, 33011).
        conn = ScriptedConnection({"joinOK": EmpireTimeoutError("no joinOK")})

        with pytest.raises(EmpireTimeoutError, match="joinOK"):
            make_client(conn).login()

        assert "vck" not in conn.requested
        assert "disconnect" in conn.events

    def test_a_room_that_is_not_the_lobby_fails_the_login(self):
        conn = ScriptedConnection({"rlu": room_list("1", "Other"), "joinOK": join_ok("1")})

        with pytest.raises(LoginError, match="not the lobby"):
            make_client(conn).login()

        assert conn.sent == []
        assert "vck" not in conn.requested

    def test_a_room_missing_from_the_room_list_fails_the_login(self):
        conn = ScriptedConnection({"joinOK": join_ok("7")})
        with pytest.raises(LoginError, match="not in the room list"):
            make_client(conn).login()

    def test_room_lists_pushed_besides_the_first_are_read(self):
        conn = ScriptedConnection({"rlu": room_list("1", "Other"), "joinOK": join_ok("2")})
        original = conn.request

        def request(data, cmd_id, timeout=5.0):
            result = original(data, cmd_id, timeout)
            if cmd_id == "rlu":
                for callback in list(conn.subscribers.get("rlu", [])):
                    callback(room_list("2"))
            return result

        conn.request = request  # type: ignore[method-assign]
        make_client(conn).login()
        assert conn.room_id == 2
        assert conn.subscribers["rlu"] == []


class TestTokenWithEmptyPassword:
    def test_an_empty_password_is_sent_with_the_token(self):
        # C2SLoginVO nulls LT only for a non-empty password (bundle line 131792).
        conn = ScriptedConnection()
        client = make_client(conn)
        client.password = ""
        client.login_token = "tok"

        client.login()

        payload = xt_login_payload(conn)
        assert payload["PW"] == ""
        assert payload["LT"] == "tok"


class TestTimings:
    """CONM runs from before the socket opens to apiOK, RTM from roundTrip to its answer (dll line 7130-7228)."""

    def test_connection_and_round_trip_times_are_measured(self, monkeypatch):
        ticks = iter([10.0, 10.25, 11.0, 11.5])
        monkeypatch.setattr("empire_core.client.client.time.monotonic", lambda: next(ticks))
        conn = ScriptedConnection()

        make_client(conn).login()

        payload = xt_login_payload(conn)
        assert payload["CONM"] == 250
        assert payload["RTM"] == 500


class TestVersionCheck:
    """The vck reply: 0 goes on, 1 too low, 2 too high (CastleVCKCommand, bundle line 120444)."""

    @pytest.mark.parametrize("status", [1, 2])
    def test_a_version_the_server_refuses_raises_with_its_build(self, status):
        conn = ScriptedConnection({"vck": Packet.from_bytes(f"%xt%vck%1%{status}%1170001%".encode())})

        with pytest.raises(ClientVersionError) as exc_info:
            make_client(conn).login()

        assert exc_info.value.status == status
        assert exc_info.value.server_build == "1170001"
        assert "lli" not in conn.requested
        assert "disconnect" in conn.events

    def test_another_status_is_a_login_error(self):
        conn = ScriptedConnection({"vck": xt_packet("vck", error_code=1000)})
        with pytest.raises(LoginError, match="1000"):
            make_client(conn).login()

    def test_ok_goes_on_to_the_login(self):
        conn = ScriptedConnection({"vck": Packet.from_bytes(b"%xt%vck%1%0%1169011%")})
        assert make_client(conn).login() is True


class TestLoginToken:
    """A persistent login's token (slt, bundle line 120936) logs in without the password."""

    def test_login_by_token_sends_no_password(self):
        conn = ScriptedConnection()
        client = make_client(conn)
        client.password = None
        client.login_token = "tok-123"

        client.login()

        payload = xt_login_payload(conn)
        assert "PW" not in payload
        assert payload["LT"] == "tok-123"

    def test_a_password_nulls_the_token(self):
        conn = ScriptedConnection()
        client = make_client(conn)
        client.login_token = "tok-123"

        client.login()

        assert xt_login_payload(conn)["LT"] is None

    def test_the_pushed_token_is_kept(self):
        client = make_client()
        client._on_packet(xt_packet("slt", {"LT": "fresh-token"}))
        assert client.login_token == "fresh-token"

    def test_a_refused_slt_keeps_the_old_token(self):
        client = make_client()
        client.login_token = "old"
        client._on_packet(xt_packet("slt", {"LT": "x"}, error_code=1))
        assert client.login_token == "old"

    def test_a_refused_token_is_forgotten(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", error_code=int(GGEError.INVALID_LOGIN_TOKEN))})
        client = make_client(conn)
        client.password = None
        client.login_token = "stale"

        with pytest.raises(LoginError, match="token"):
            client.login()

        assert client.login_token is None


class TestRecaptchaToken:
    """The client attaches a reCAPTCHA token as RCT (bundle line 131780)."""

    def test_no_token_sends_no_rct(self):
        conn = ScriptedConnection()
        make_client(conn).login()
        assert "RCT" not in xt_login_payload(conn)

    def test_a_token_is_sent_last(self):
        conn = ScriptedConnection()
        make_client(conn).login(recaptcha_token="captcha")
        payload = xt_login_payload(conn)
        assert list(payload)[-1] == "RCT"
        assert payload["RCT"] == "captcha"

    def test_a_token_function_is_called(self):
        conn = ScriptedConnection()
        make_client(conn).login(recaptcha_token=lambda: "from-callback")
        assert xt_login_payload(conn)["RCT"] == "from-callback"


class TestRefusalDetails:
    """What LLICommand reads off a refused login (bundle line 120651)."""

    def test_a_ban_carries_the_remaining_seconds(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", {"RS": 3600}, error_code=27)})
        with pytest.raises(AccountBannedError) as exc_info:
            make_client(conn).login()
        assert exc_info.value.remaining_seconds == 3600
        assert exc_info.value.deleted is False

    def test_a_deleted_account(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", {"GDPR": 1}, error_code=27)})
        with pytest.raises(AccountBannedError) as exc_info:
            make_client(conn).login()
        assert exc_info.value.deleted is True

    def test_the_wrong_server_names_the_right_instance(self):
        conn = ScriptedConnection({"lli": xt_packet("lli", {"IID": 21}, error_code=368)})
        with pytest.raises(WrongServerError) as exc_info:
            make_client(conn).login()
        assert exc_info.value.instance_id == 21


class TestLoginTokenPushShapes:
    """SLTCommand stores ``JSON.parse(t[1]).LT`` whatever it is (bundle line 120936)."""

    @pytest.mark.parametrize(("value", "stored"), [("abc", "abc"), (1234567890123, "1234567890123")])
    def test_the_token_is_kept_as_the_client_would_send_it_back(self, value, stored):
        client = make_client()
        client._on_packet(Packet.from_bytes(f'%xt%slt%-1%0%{{"LT":{json.dumps(value)}}}%'.encode()))
        assert client.login_token == stored

    def test_a_push_during_the_login_is_kept(self):
        # The server pushes slt between the lli reply and gbd.
        client = make_client()

        class PushingConnection(ScriptedConnection):
            def wait_for_result(self, cmd_id, waiter, timeout=5.0):
                if cmd_id == "gbd":
                    client._on_packet(Packet.from_bytes(b'%xt%slt%-1%0%{"LT":"live-token"}%'))
                return super().wait_for_result(cmd_id, waiter, timeout)

        client.connection = PushingConnection()  # type: ignore[assignment]
        client.login()
        assert client.login_token == "live-token"

    def test_a_push_without_a_token_is_reported(self, caplog):
        client = make_client()
        with caplog.at_level("WARNING", logger="empire_core.client.client"):
            client._on_packet(xt_packet("slt", {}))
        assert client.login_token is None
        assert "slt" in caplog.text
