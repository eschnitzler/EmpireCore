"""Tests for the services layer (no real socket).

Every service goes through ``BaseService.request``/``send``/``execute``, which
all funnel into ``EmpireClient``. The client is built with
``EmpireClient.__new__`` and hand-wired stubs (the same idiom as
tests/test_client_lifecycle.py) and the connection is a scripted stand-in
serving canned response packets (the same idiom as the ``_FakeConnection`` in
tests/test_map_scanner.py).

The payloads below are written in the shape the live server sends -- positional
arrays and all -- because that shape is what drifts when the game updates, and
the services layer is what dreambot consumes in production.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

import pytest
from pydantic import ValidationError

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.exceptions import (
    CommandError,
    ConnectionClosedError,
    EmpireTimeoutError,
    NetworkError,
    PacketError,
)
from empire_core.network.connection import ResponseWaiter
from empire_core.protocol.models import (
    AllianceChatMessageResponse,
    AllianceMember,
    GetAllianceInfoRequest,
    GetAllianceInfoResponse,
    HelpType,
    SelectCastleRequest,
)
from empire_core.protocol.packet import Packet
from empire_core.services import (
    AllianceService,
    ArmyService,
    CastleService,
    LordsService,
    RankingService,
    SpyService,
    get_registered_services,
)
from empire_core.services import spy as spy_module

# =============================================================================
# Harness
# =============================================================================


def xt_packet(command: str, payload: Any = None, error_code: int = 0) -> Packet:
    """Build a response packet the way the wire delivers it."""
    body = "{}" if payload is None else json.dumps(payload)
    return Packet.from_bytes(f"%xt%{command}%1%{error_code}%{body}%".encode())


def request_payload(data: str) -> dict[str, Any]:
    """Recover the JSON payload from a built request packet.

    Split with maxsplit so a '%' inside the payload (encoded chat text uses
    '%5C' for a backslash) cannot truncate it.
    """
    raw = data.split("%", 5)[5]
    if raw.endswith("%"):
        raw = raw[:-1]
    return json.loads(raw)


class ScriptedConnection:
    """Scripted stand-in for Connection.

    ``script`` maps a command id to a Packet to return, an Exception to raise,
    or a list of either consumed one per call. Unscripted command ids get an
    empty successful packet, so an ``execute()`` call needs no scripting to
    succeed.
    """

    def __init__(self, script: dict[str, Any] | None = None):
        self.script = script or {}
        self.connected = True
        self.sent: list[str] = []
        self.requested: list[str] = []
        self.request_payloads: list[tuple[str, dict[str, Any]]] = []
        self.waiters_created: list[str] = []
        self.waiters_cancelled: list[str] = []
        self.waited_for: list[str] = []
        self.events: list[str] = []
        self.on_packet = None
        self.on_disconnect = None

    def _resolve(self, cmd_id: str) -> Packet:
        result = self.script.get(cmd_id, xt_packet(cmd_id))
        if isinstance(result, list):
            result = result.pop(0) if result else xt_packet(cmd_id)
        if isinstance(result, Exception):
            raise result
        return result

    def send(self, data: str) -> None:
        self.sent.append(data)

    def request(self, data: str, cmd_id: str, timeout: float = 5.0) -> Packet:
        self.requested.append(cmd_id)
        self.request_payloads.append((cmd_id, request_payload(data)))
        self.events.append(f"request:{cmd_id}")
        return self._resolve(cmd_id)

    def create_waiter(self, cmd_id: str) -> ResponseWaiter:
        self.waiters_created.append(cmd_id)
        self.events.append(f"create_waiter:{cmd_id}")
        return ResponseWaiter()

    def cancel_waiter(self, cmd_id: str, waiter: ResponseWaiter) -> None:
        self.waiters_cancelled.append(cmd_id)
        self.events.append(f"cancel_waiter:{cmd_id}")

    def wait_for_result(self, cmd_id: str, waiter: ResponseWaiter, timeout: float = 5.0) -> Packet:
        self.waited_for.append(cmd_id)
        self.events.append(f"wait_for_result:{cmd_id}")
        return self._resolve(cmd_id)

    def subscribe(self, cmd_id: str, callback: object) -> None:
        pass

    def unsubscribe(self, cmd_id: str, callback: object) -> None:
        pass

    def disconnect(self) -> None:
        self.connected = False


class StubPlayer:
    def __init__(self, alliance_id: int = 0):
        self.alliance_id = alliance_id


class StubState:
    """Only the members the services actually touch."""

    def __init__(self, local_player: StubPlayer | None = None):
        self.local_player = local_player
        self.updates: list[tuple[str, object]] = []

    def update_from_packet(self, cmd_id: str, payload: object) -> None:
        self.updates.append((cmd_id, payload))


def make_client(script: dict[str, Any] | None = None, state: StubState | None = None) -> EmpireClient:
    """Build a client with every registered service attached, but no socket."""
    client = EmpireClient.__new__(EmpireClient)
    client.config = EmpireConfig()
    client.username = "tester"
    client.password = "secret"
    client.connection = ScriptedConnection(script)  # type: ignore[assignment]
    client.state = state or StubState()  # type: ignore[assignment]
    client.is_logged_in = True
    client._handlers = {}
    client._handlers_lock = threading.Lock()
    client._services = {}
    for name, service_cls in get_registered_services().items():
        service = service_cls(client)
        client._services[name] = service
        setattr(client, name, service)
    return client


def conn(client: EmpireClient) -> ScriptedConnection:
    return client.connection  # type: ignore[return-value]


# =============================================================================
# Golden payloads (shapes captured from the live server)
# =============================================================================

GOLDEN_AIN: dict[str, Any] = {
    "A": {
        "AID": 190426,
        "N": "Knights of HOPE",
        "A": "HOPE",
        "D": "Recruiting active players",
        "MP": 4213377,
        "CF": 12,
        "HF": 47,
        "ML": 50,
        "ALL": "en",
        "STO": {"W": 120000, "S": 98000, "O": 45000, "C1": 3000, "C2": 12, "I": 400, "G": 7},
        "ABL": [{"BT": 1, "L": 5, "CD": -1}, {"BT": 2, "L": 3, "CD": 3600}],
        "M": [
            {
                "OID": 7001,
                "N": "LeaderGuy",
                "L": 70,
                "LL": 812,
                "AR": 8,
                "MP": 1200000,
                "CF": 3,
                "HF": 9,
                "AID": 190426,
                "AN": "Knights of HOPE",
                "RPT": 0,
                "AP": [[0, 12345, 640, 655, 1], [2, 22222, 300, 400, 4]],
                "E": {"BGT": 1, "BGC1": 2, "SPT": 3, "S1": 4, "IS": 1},
            },
            {
                "OID": 7002,
                "N": "OfficerGal",
                "L": 70,
                "AR": 4,
                "MP": 900000,
                "RPT": 7200,
                "AP": [[0, 12346, 641, 656, 1]],
            },
            {"OID": 7003, "N": "AfkDude", "L": 55, "AR": 0, "MP": 100, "AP": []},
        ],
        # Positional activity array: [player_id, ?, ?, ?, activity_tier]
        "AMI": [[7001, 0, 0, 0, 0], [7002, 0, 0, 0, 2], [7003, 0, 0, 0, 4]],
    }
}

GOLDEN_GCL: dict[str, Any] = {
    "C": [
        {"CID": 12345, "CN": "Main Castle", "X": 640, "Y": 655, "KID": 0, "CT": 0, "L": 70},
        {"CID": 55555, "CN": "Outpost North", "X": 700, "Y": 700, "KID": 0, "CT": 1, "L": 12},
    ]
}

GOLDEN_DCL: dict[str, Any] = {
    "C": {
        "CID": 12345,
        "CN": "Main Castle",
        "X": 640,
        "Y": 655,
        "KID": 0,
        "CT": 0,
        "L": 70,
        "B": [
            {"BID": 1, "BT": 12, "L": 5, "X": 3, "Y": 4, "S": 0, "H": 100},
            {"BID": 2, "BT": 40, "L": 1, "X": 8, "Y": 9, "S": 2, "H": 40},
        ],
        "R": {"W": 100000, "S": 90000, "F": 5000, "C": 12345, "R": 300},
        "P": 1200,
        "MP": 1500,
        # Item inventory as positional pairs; the trailing 1-element entry is
        # the kind of short row the server does send.
        "AC": [[201, 5], [305, 2], [999]],
    }
}


# =============================================================================
# Registration / wiring
# =============================================================================


class TestServiceRegistration:
    def test_every_documented_service_is_registered(self):
        registered = get_registered_services()
        assert set(registered) >= {"alliance", "castle", "army", "lords", "spy", "ranking"}

    def test_services_attach_to_the_client_by_name(self):
        client = make_client()
        assert isinstance(client.alliance, AllianceService)
        assert isinstance(client.castle, CastleService)
        assert isinstance(client.army, ArmyService)
        assert isinstance(client.lords, LordsService)
        assert isinstance(client.spy, SpyService)
        assert isinstance(client.ranking, RankingService)

    def test_service_zone_follows_client_config(self):
        client = make_client()
        client.config = EmpireConfig(default_zone="EmpireEx_99")
        assert client.alliance.zone == "EmpireEx_99"
        assert client.castle.zone == "EmpireEx_99"

    def test_requests_are_built_for_the_configured_zone(self):
        client = make_client()
        client.config = EmpireConfig(default_zone="EmpireEx_99")

        client.alliance.send_chat("hi")

        assert conn(client).sent[0].startswith("%xt%EmpireEx_99%acm%")


# =============================================================================
# BaseService contracts (the README's CommandError-vs-bool split)
# =============================================================================


class TestExecuteSemantics:
    """``execute()`` returns False for game-rule rejections and raises for
    transport failures - infrastructure problems must never look like a
    rejected action."""

    def test_accepted_action_returns_true(self):
        client = make_client({"jaa": xt_packet("jaa")})
        assert client.castle.select(12345) is True

    def test_rejected_action_returns_false(self):
        client = make_client({"jaa": xt_packet("jaa", error_code=21)})
        assert client.castle.select(12345) is False

    def test_rejection_is_logged_with_the_command(self, caplog):
        client = make_client({"jaa": xt_packet("jaa", error_code=21)})
        with caplog.at_level(logging.WARNING, logger="empire_core.services.base"):
            client.castle.select(12345)
        assert "jca" in caplog.text

    @pytest.mark.parametrize(
        "failure",
        [
            EmpireTimeoutError("no answer"),
            ConnectionClosedError("socket closed"),
            NetworkError("send failed"),
        ],
    )
    def test_transport_failure_still_raises(self, failure):
        client = make_client({"jaa": failure})
        with pytest.raises(type(failure)):
            client.castle.select(12345)

    def test_malformed_status_is_not_treated_as_acceptance(self):
        # A garbled status field parses to the MALFORMED_STATUS_CODE sentinel,
        # which must read as a rejection rather than a success.
        client = make_client({"jaa": Packet.from_bytes(b"%xt%jaa%1%notanumber%{}%")})
        assert client.castle.select(12345) is False


class TestRequestSemantics:
    def test_server_error_code_raises_command_error(self):
        client = make_client({"ain": xt_packet("ain", error_code=21)})
        with pytest.raises(CommandError) as exc_info:
            client.alliance.get_members(190426)
        assert exc_info.value.command == "ain"
        assert exc_info.value.code == 21

    def test_unparseable_payload_raises_packet_error(self):
        # 'gli' requires an ID per lord; a drifted entry must surface as a
        # library error, not a raw pydantic ValidationError.
        client = make_client({"gli": xt_packet("gli", {"C": [{"N": "no id here"}]})})
        with pytest.raises(PacketError) as exc_info:
            client.lords.get_lords()
        assert "gli" in str(exc_info.value)

    def test_array_payload_raises_packet_error_not_none(self):
        # A JSON-array payload has no response model, so send() returns None;
        # request() must not hand that back as if it were the typed response.
        client = make_client({"gcl": xt_packet("gcl", [1, 2, 3])})
        with pytest.raises(PacketError, match="GetCastlesResponse"):
            client.castle.get_all()

    def test_timeout_propagates(self):
        client = make_client({"gcl": EmpireTimeoutError("no gcl")})
        with pytest.raises(EmpireTimeoutError):
            client.castle.get_all()


# =============================================================================
# AllianceService
# =============================================================================


class TestAllianceMembers:
    def test_golden_ain_payload_parses_into_members(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})

        members = client.alliance.get_members(190426)

        assert [m.name for m in members] == ["LeaderGuy", "OfficerGal", "AfkDude"]
        assert conn(client).request_payloads == [("ain", {"AID": 190426})]

    def test_activity_tiers_come_from_the_ami_array(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})

        by_name = {m.name: m for m in client.alliance.get_members(190426)}

        assert by_name["LeaderGuy"].activity_tier == 0
        assert by_name["LeaderGuy"].is_online is True
        assert by_name["OfficerGal"].activity_tier == 2
        assert by_name["OfficerGal"].is_online is False
        assert by_name["AfkDude"].activity_tier == 4

    def test_online_members_are_filtered(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})
        online = client.alliance.get_online_members(190426)
        assert [m.name for m in online] == ["LeaderGuy"]

    def test_member_profile_fields_survive_the_round_trip(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})
        by_name = {m.name: m for m in client.alliance.get_members(190426)}

        leader = by_name["LeaderGuy"]
        assert leader.player_id == 7001
        assert leader.is_leader is True
        assert leader.might == 1200000
        assert leader.legendary_level == 812
        assert by_name["OfficerGal"].is_officer is True
        assert by_name["OfficerGal"].has_bird is True
        assert by_name["LeaderGuy"].has_bird is False

    def test_member_castle_positions_parse_from_the_ap_array(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})
        by_name = {m.name: m for m in client.alliance.get_members(190426)}

        castles = by_name["LeaderGuy"].castles
        assert [(c.kingdom, c.x, c.y, c.castle_type) for c in castles] == [
            (0, 640, 655, 1),
            (2, 300, 400, 4),
        ]
        assert by_name["AfkDude"].castles == []

    def test_typed_emblem_is_parsed(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})
        leader = client.alliance.get_members(190426)[0]
        assert leader.emblem is not None
        assert leader.emblem.background_type == 1
        assert leader.emblem.symbol1 == 4

    def test_members_are_cached_and_handed_out_as_a_copy(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})
        client.alliance.get_members(190426)

        cached = client.alliance.cached_members
        assert set(cached) == {7001, 7002, 7003}
        cached.clear()
        assert set(client.alliance.cached_members) == {7001, 7002, 7003}

    def test_get_member_reads_the_cache_without_a_request(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})
        client.alliance.get_members(190426)
        conn(client).requested.clear()

        member = client.alliance.get_member(7002)

        assert isinstance(member, AllianceMember)
        assert member.name == "OfficerGal"
        assert conn(client).requested == []

    def test_get_member_no_cache_refreshes_the_cached_alliance(self):
        # Refreshing the *local* alliance would query the wrong id whenever the
        # cache was filled from another alliance.
        state = StubState(local_player=StubPlayer(alliance_id=999))
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)}, state=state)
        client.alliance.get_members(190426)
        conn(client).request_payloads.clear()

        client.alliance.get_member(7001, no_cache=True)

        assert conn(client).request_payloads == [("ain", {"AID": 190426})]

    def test_get_member_no_cache_falls_back_to_the_local_alliance(self):
        state = StubState(local_player=StubPlayer(alliance_id=190426))
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)}, state=state)

        member = client.alliance.get_member(7001, no_cache=True)

        assert conn(client).request_payloads == [("ain", {"AID": 190426})]
        assert member is not None

    def test_unknown_member_is_none(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})
        client.alliance.get_members(190426)
        assert client.alliance.get_member(424242) is None


class TestAllianceLocalHelpers:
    def test_local_alliance_id_comes_from_state(self):
        client = make_client(state=StubState(local_player=StubPlayer(alliance_id=190426)))
        assert client.alliance.local_alliance_id == 190426

    def test_local_alliance_id_is_none_without_a_local_player(self):
        client = make_client(state=StubState(local_player=None))
        assert client.alliance.local_alliance_id is None

    def test_local_members_without_an_alliance_sends_nothing(self):
        client = make_client(state=StubState(local_player=StubPlayer(alliance_id=None)))  # type: ignore[arg-type]
        assert client.alliance.get_local_members() == []
        assert conn(client).requested == []

    def test_local_members_uses_the_local_alliance_id(self):
        state = StubState(local_player=StubPlayer(alliance_id=190426))
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)}, state=state)

        members = client.alliance.get_local_members()

        assert len(members) == 3
        assert conn(client).request_payloads == [("ain", {"AID": 190426})]

    def test_local_online_members_filters(self):
        state = StubState(local_player=StubPlayer(alliance_id=190426))
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)}, state=state)
        assert [m.name for m in client.alliance.get_local_online_members()] == ["LeaderGuy"]

    def test_local_online_members_without_an_alliance_is_empty(self):
        client = make_client(state=StubState(local_player=None))
        assert client.alliance.get_local_online_members() == []
        assert conn(client).requested == []


class TestAllianceSearch:
    GOLDEN_HGH: dict[str, Any] = {"L": [[1, 4213377, [190426, "Knights of HOPE", 47, 4213377]]]}

    def test_search_parses_positional_results(self):
        client = make_client({"hgh": xt_packet("hgh", self.GOLDEN_HGH)})

        results = client.alliance.search_alliances("HOPE")

        assert len(results) == 1
        assert results[0].alliance_id == 190426
        assert results[0].name == "Knights of HOPE"
        assert results[0].member_count == 47
        assert results[0].might == 4213377

    def test_search_sends_the_search_term(self):
        client = make_client({"hgh": xt_packet("hgh", self.GOLDEN_HGH)})
        client.alliance.search_alliances("HOPE")
        command, payload = conn(client).request_payloads[0]
        assert command == "hgh"
        assert payload["SV"] == "HOPE"

    def test_nothing_found_is_an_empty_result_not_an_error(self):
        # 114 is the server's "no match", which is a legitimate empty answer.
        client = make_client({"hgh": xt_packet("hgh", error_code=114)})
        assert client.alliance.search_alliances("nope") == []

    def test_other_error_codes_raise(self):
        client = make_client({"hgh": xt_packet("hgh", error_code=21)})
        with pytest.raises(CommandError) as exc_info:
            client.alliance.search_alliances("HOPE")
        assert exc_info.value.code == 21

    def test_array_payload_is_an_empty_result(self):
        client = make_client({"hgh": xt_packet("hgh", [1, 2, 3])})
        assert client.alliance.search_alliances("HOPE") == []

    def test_drifted_entry_degrades_to_unknown(self):
        client = make_client({"hgh": xt_packet("hgh", {"L": [[1, 2], [1, 2, "not-a-list"]]})})
        results = client.alliance.search_alliances("HOPE")
        assert [r.name for r in results] == ["Unknown", "Unknown"]

    def test_unparseable_payload_raises_packet_error_not_validation_error(self):
        # 'L' of the wrong type fails model_validate; the documented parse
        # failure type of the request contract is PacketError.
        client = make_client({"hgh": xt_packet("hgh", {"L": "junk"})})
        with pytest.raises(PacketError):
            client.alliance.search_alliances("HOPE")

    def test_wrong_typed_entry_is_skipped_not_fatal(self, caplog):
        # Well-shaped but wrong-typed: a non-numeric AID raises ValidationError
        # inside from_list; only that entry may be lost.
        payload = {"L": [[1, 2, ["x", "y"]], self.GOLDEN_HGH["L"][0], 5]}
        client = make_client({"hgh": xt_packet("hgh", payload)})

        with caplog.at_level(logging.WARNING, logger="empire_core.services.alliance"):
            results = client.alliance.search_alliances("HOPE")

        assert [r.name for r in results] == ["Knights of HOPE"]
        assert "Skipped 2/3" in caplog.text


class TestAllianceChat:
    def test_send_chat_encodes_special_characters(self):
        client = make_client()

        client.alliance.send_chat('100% sure, said "go"')

        payload = request_payload(conn(client).sent[0])
        assert payload["M"] == "100&percnt; sure, said &quot;go&quot;"
        assert conn(client).requested == []

    def test_get_chat_log_parses_entries(self):
        payload = {
            "CL": [
                {"PN": "LeaderGuy", "MT": "100&percnt; ready", "PID": 7001, "T": 1712345678},
                {"PN": "OfficerGal", "MT": "on my way", "PID": 7002, "T": 1712345699},
            ]
        }
        client = make_client({"acl": xt_packet("acl", payload)})

        log = client.alliance.get_chat_log()

        assert [e.player_name for e in log] == ["LeaderGuy", "OfficerGal"]
        assert log[0].decoded_text == "100% ready"
        assert log[0].timestamp == 1712345678

    def test_subscribed_callback_receives_a_typed_response(self):
        client = make_client()
        seen: list[AllianceChatMessageResponse] = []
        client.alliance.on_chat_message(seen.append)

        client._on_packet(xt_packet("acm", {"CM": {"PN": "LeaderGuy", "MT": "hi &percnt;", "PID": 7001}}))

        assert len(seen) == 1
        assert isinstance(seen[0], AllianceChatMessageResponse)
        assert seen[0].player_name == "LeaderGuy"
        assert seen[0].decoded_text == "hi %"
        assert seen[0].player_id == 7001

    def test_one_raising_callback_does_not_stop_the_others(self, caplog):
        client = make_client()
        seen: list[str] = []

        def boom(response: AllianceChatMessageResponse) -> None:
            raise RuntimeError("callback bug")

        client.alliance.on_chat_message(boom)
        client.alliance.on_chat_message(lambda r: seen.append(r.player_name))

        with caplog.at_level(logging.ERROR, logger="empire_core.services.alliance"):
            client._on_packet(xt_packet("acm", {"CM": {"PN": "LeaderGuy", "MT": "hi", "PID": 7001}}))

        assert seen == ["LeaderGuy"]
        assert "callback error" in caplog.text.lower()

    def test_chat_handler_is_registered_at_construction(self):
        client = make_client()
        assert client._handlers.get("acm")

    def test_removed_callback_no_longer_receives_messages(self):
        client = make_client()
        seen: list[AllianceChatMessageResponse] = []
        client.alliance.on_chat_message(seen.append)

        client.alliance.remove_chat_message_callback(seen.append)
        client._on_packet(xt_packet("acm", {"CM": {"PN": "LeaderGuy", "MT": "hi", "PID": 7001}}))

        assert seen == []

    def test_removing_an_unregistered_callback_is_a_no_op(self):
        client = make_client()
        client.alliance.remove_chat_message_callback(lambda r: None)


class TestAllianceHelp:
    def test_help_all_reports_the_count(self):
        client = make_client({"aha": xt_packet("aha", {"HC": 7})})
        assert client.alliance.help_all().helped_count == 7

    def test_help_all_error_raises(self):
        client = make_client({"aha": xt_packet("aha", error_code=21)})
        with pytest.raises(CommandError):
            client.alliance.help_all()

    @pytest.mark.parametrize(
        "method,help_type",
        [
            ("help_member_heal", HelpType.HEAL),
            ("help_member_repair", HelpType.REPAIR),
            ("help_member_recruit", HelpType.RECRUIT),
        ],
    )
    def test_help_member_sends_the_right_help_type(self, method, help_type):
        client = make_client()

        getattr(client.alliance, method)(7001, 12345)

        payload = request_payload(conn(client).sent[0])
        assert payload == {"PID": 7001, "CID": 12345, "HT": int(help_type)}

    def test_request_repair_help_carries_the_building_id(self):
        client = make_client()

        client.alliance.request_repair_help(12345, 42)

        payload = request_payload(conn(client).sent[0])
        assert payload == {"CID": 12345, "HT": int(HelpType.REPAIR), "BID": 42}

    def test_request_heal_help_omits_the_building_id(self):
        client = make_client()

        client.alliance.request_heal_help(12345)

        assert request_payload(conn(client).sent[0]) == {"CID": 12345, "HT": int(HelpType.HEAL)}

    def test_bookmarks_expose_their_positions(self):
        payload = {"ABL": [{"N": "Enemy cluster", "OI": {"AP": [[0, 1, 640, 655, 1]]}}]}
        client = make_client({"gbl": xt_packet("gbl", payload)})

        bookmarks = client.alliance.get_bookmarks()

        assert [b.name for b in bookmarks] == ["Enemy cluster"]
        assert bookmarks[0].positions == [[0, 1, 640, 655, 1]]


# =============================================================================
# CastleService
# =============================================================================


class TestCastleQueries:
    def test_golden_gcl_payload_parses(self):
        client = make_client({"gcl": xt_packet("gcl", GOLDEN_GCL)})

        castles = client.castle.get_all()

        assert [(c.castle_id, c.castle_name, c.x, c.y) for c in castles] == [
            (12345, "Main Castle", 640, 655),
            (55555, "Outpost North", 700, 700),
        ]
        assert castles[0].position.x == 640

    def test_golden_dcl_payload_parses_buildings_and_items(self):
        client = make_client({"dcl": xt_packet("dcl", GOLDEN_DCL)})

        details = client.castle.get_details(12345)

        assert details is not None
        assert details.castle_name == "Main Castle"
        assert [b.building_id for b in details.buildings] == [1, 2]
        assert details.buildings[1].status == 2
        assert details.resources is not None
        assert details.resources.wood == 100000
        assert details.population == 1200
        # The short AC row is skipped rather than crashing the parse.
        assert details.items == {201: 5, 305: 2}
        assert conn(client).request_payloads == [("dcl", {"CID": 12345})]

    def test_missing_castle_block_is_none(self):
        client = make_client({"dcl": xt_packet("dcl", {})})
        assert client.castle.get_details(12345) is None

    def test_resources_are_parsed(self):
        payload = {"R": {"W": 1, "S": 2, "F": 3, "C": 4, "R": 5}, "SC": {"W": 10}}
        client = make_client({"grc": xt_packet("grc", payload)})

        resources = client.castle.get_resources(12345)

        assert resources is not None
        assert (resources.wood, resources.stone, resources.food, resources.coins, resources.rubies) == (1, 2, 3, 4, 5)

    def test_missing_resources_are_none(self):
        client = make_client({"grc": xt_packet("grc", {})})
        assert client.castle.get_resources(12345) is None

    def test_production_returns_both_rates(self):
        payload = {"P": {"W": 1200.5, "S": 900.0}, "CO": {"F": 300.25}}
        client = make_client({"gpa": xt_packet("gpa", payload)})

        production, consumption = client.castle.get_production(12345)

        assert production is not None and production.wood == 1200.5
        assert consumption is not None and consumption.food == 300.25

    def test_production_without_rates_is_a_none_pair(self):
        client = make_client({"gpa": xt_packet("gpa", {})})
        assert client.castle.get_production(12345) == (None, None)


class TestCastleActions:
    def test_select_sends_castle_and_kingdom(self):
        client = make_client()

        assert client.castle.select(12345, kingdom_id=2) is True

        assert conn(client).request_payloads == [("jaa", {"CID": 12345, "KID": 2})]

    def test_select_waits_for_the_jaa_acknowledgement(self):
        # The server answers a castle jump with 'jaa', never with 'jca'.
        # Waiting on the request command times out on every single call.
        client = make_client({"jaa": xt_packet("jaa")})

        assert client.castle.select(12345) is True
        assert conn(client).requested == ["jaa"]

    def test_select_reports_a_rejected_jump(self):
        client = make_client({"jaa": xt_packet("jaa", error_code=21)})

        assert client.castle.select(12345) is False

    def test_select_rejection_is_logged_against_the_request_command(self, caplog):
        client = make_client({"jaa": xt_packet("jaa", error_code=21)})

        with caplog.at_level(logging.WARNING, logger="empire_core.services.base"):
            client.castle.select(12345)

        assert "jca" in caplog.text

    def test_rename_sends_the_new_name(self):
        client = make_client()

        assert client.castle.rename(12345, "My Fortress") is True

        assert conn(client).request_payloads == [("arc", {"CID": 12345, "CN": "My Fortress"})]

    def test_rejected_rename_is_false(self):
        client = make_client({"arc": xt_packet("arc", error_code=21)})
        assert client.castle.rename(12345, "nope") is False

    def test_send_support_builds_the_documented_payload(self):
        client = make_client()

        assert client.castle.send_support(12345, 700, 710, [[487, 100]], kingdom_id=2, wait_time=6) is True

        command, payload = conn(client).request_payloads[0]
        assert command == "cds"
        assert payload["SID"] == 12345
        assert (payload["TX"], payload["TY"], payload["KID"]) == (700, 710, 2)
        assert payload["A"] == [[487, 100]]
        assert payload["WT"] == 6
        assert payload["BPC"] == 1
        assert payload["LID"] == -14

    def test_send_support_without_coin_boost(self):
        client = make_client()
        client.castle.send_support(12345, 700, 710, [[487, 1]], boost_with_coins=False)
        assert conn(client).request_payloads[0][1]["BPC"] == 0

    def test_out_of_range_wait_time_is_rejected_before_sending(self):
        client = make_client()

        with pytest.raises(ValidationError):
            client.castle.send_support(12345, 700, 710, [[487, 1]], wait_time=13)

        assert conn(client).requested == []


# =============================================================================
# ArmyService
# =============================================================================


class TestArmyService:
    def test_get_units_merges_units_and_tools(self):
        payload = {"U": [{"UID": 487, "C": 100}, {"UID": 488, "C": 20}], "T": [{"UID": 301, "C": 5}]}
        client = make_client({"gui": xt_packet("gui", payload)})

        units = client.army.get_units(12345)

        assert [(u.unit_id, u.count) for u in units] == [(487, 100), (488, 20), (301, 5)]
        assert conn(client).request_payloads == [("gui", {"CID": 12345})]

    def test_production_queue_parses(self):
        payload = {"Q": [{"QID": 1, "UID": 487, "C": 50, "R": 20, "CT": 1712345678}]}
        client = make_client({"spl": xt_packet("spl", payload)})

        queue = client.army.get_production_queue(12345, 7, list_id=1)

        assert [(q.queue_id, q.unit_id, q.count, q.remaining) for q in queue] == [(1, 487, 50, 20)]
        assert conn(client).request_payloads == [("spl", {"CID": 12345, "BID": 7, "LID": 1})]

    def test_heal_all_reports_the_count(self):
        client = make_client({"hra": xt_packet("hra", {"UH": 314, "CT": 1712345678})})
        assert client.army.heal_all(12345) == 314

    @pytest.mark.parametrize(
        "call,command,expected",
        [
            (lambda s: s.produce_units(1, 2, 3, 4), "bup", {"CID": 1, "BID": 2, "UID": 3, "C": 4, "LID": 0}),
            (lambda s: s.delete_units(1, 2, 3), "dup", {"CID": 1, "UID": 2, "C": 3}),
            (lambda s: s.cancel_production(1, 2, 3), "mcu", {"CID": 1, "BID": 2, "QID": 3}),
            (lambda s: s.double_production_slot(1, 2, 3), "bou", {"CID": 1, "BID": 2, "QID": 3}),
            (lambda s: s.heal_units(1, 2, 3), "hru", {"CID": 1, "UID": 2, "C": 3}),
            (lambda s: s.cancel_heal(1, 2), "hcs", {"CID": 1, "QID": 2}),
            (lambda s: s.skip_heal_time(1, 2), "hss", {"CID": 1, "QID": 2}),
            (lambda s: s.delete_wounded(1, 2, 3), "hdu", {"CID": 1, "UID": 2, "C": 3}),
        ],
    )
    def test_actions_send_the_documented_payload_and_report_acceptance(self, call, command, expected):
        client = make_client()

        assert call(client.army) is True

        assert conn(client).request_payloads == [(command, expected)]

    @pytest.mark.parametrize(
        "call,command",
        [
            (lambda s: s.produce_units(1, 2, 3, 4), "bup"),
            (lambda s: s.heal_units(1, 2, 3), "hru"),
            (lambda s: s.delete_wounded(1, 2, 3), "hdu"),
        ],
    )
    def test_rejected_actions_are_false(self, call, command):
        client = make_client({command: xt_packet(command, error_code=21)})
        assert call(client.army) is False

    def test_heal_all_error_raises(self):
        client = make_client({"hra": xt_packet("hra", error_code=21)})
        with pytest.raises(CommandError):
            client.army.heal_all(12345)


# =============================================================================
# LordsService
# =============================================================================


class TestLordsService:
    def test_lords_parse(self):
        payload = {"C": [{"ID": -14, "N": ""}, {"ID": 91, "N": "Bloodwing"}]}
        client = make_client({"gli": xt_packet("gli", payload)})

        lords = client.lords.get_lords()

        assert [(lord.lord_id, lord.name) for lord in lords] == [(-14, ""), (91, "Bloodwing")]
        assert conn(client).request_payloads == [("gli", {})]

    def test_empty_lord_list(self):
        client = make_client({"gli": xt_packet("gli", {})})
        assert client.lords.get_lords() == []

    def test_error_raises(self):
        client = make_client({"gli": xt_packet("gli", error_code=21)})
        with pytest.raises(CommandError):
            client.lords.get_lords()


# =============================================================================
# RankingService
# =============================================================================


class TestRankingService:
    def test_highscore_dict_details_layout(self):
        payload = {"L": [[1, 999999, {"OID": 7001, "N": "LeaderGuy", "AID": 190426, "AN": "HOPE"}]]}
        client = make_client({"hgh": xt_packet("hgh", payload)})

        entries = client.ranking.get_highscore(list_type=6, search_value="LeaderGuy")

        assert len(entries) == 1
        entry = entries[0]
        assert (entry.rank, entry.score, entry.entity_id) == (1, 999999, 7001)
        assert (entry.name, entry.alliance_id, entry.alliance_name) == ("LeaderGuy", 190426, "HOPE")

    def test_highscore_sends_list_type_and_search_value(self):
        client = make_client({"hgh": xt_packet("hgh", {"L": []})})

        client.ranking.get_highscore(list_type=6, search_value="LeaderGuy", list_id=6)

        command, payload = conn(client).request_payloads[0]
        assert command == "hgh"
        assert (payload["LT"], payload["SV"], payload["LID"]) == (6, "LeaderGuy", 6)

    def test_highscore_omits_an_unset_list_id(self):
        client = make_client({"hgh": xt_packet("hgh", {"L": []})})
        client.ranking.get_highscore(list_type=6, search_value="x")
        assert "LID" not in conn(client).request_payloads[0][1]

    def test_ranking_list_by_position(self):
        payload = {"L": [{"R": 3, "S": 500, "P": "SomePlayer", "A": "SomeAlliance"}], "T": 1000}
        client = make_client({"llsp": xt_packet("llsp", payload)})

        entries = client.ranking.get_ranking_list(list_type=6, rank=3)

        assert (entries[0].rank, entries[0].score) == (3, 500)
        assert (entries[0].name, entries[0].alliance_name) == ("SomePlayer", "SomeAlliance")
        assert conn(client).request_payloads == [("llsp", {"LT": 6, "R": 3})]

    def test_error_raises(self):
        client = make_client({"hgh": xt_packet("hgh", error_code=21)})
        with pytest.raises(CommandError):
            client.ranking.get_highscore(list_type=6, search_value="x")


# =============================================================================
# SpyService
# =============================================================================


@pytest.fixture
def no_sleep(monkeypatch):
    """The spy poll sleeps 2s between attempts; tests must not."""
    monkeypatch.setattr(spy_module.time, "sleep", lambda seconds: None)


def spy_script(
    ssi: Any = None,
    csm: Any = None,
    sne: Any = None,
    bsd: Any = None,
) -> dict[str, Any]:
    return {
        "ssi": ssi if ssi is not None else xt_packet("ssi", {"AS": 46, "GC": 0}),
        "csm": csm if csm is not None else xt_packet("csm", {"MID": 1}),
        "sne": sne
        if sne is not None
        else xt_packet("sne", {"MSG": [[9001, 3, "1+0+4#0+16324240+Enemy Keep", "", -1, 0, 0, 0, 0]]}),
        "bsd": bsd
        if bsd is not None
        else xt_packet(
            "bsd",
            {
                "MID": 9001,
                "S": [[[487, 100]]],
                "B": {"K": 1},
                "AI": {"N": "Enemy Keep", "X": 700, "Y": 710, "K": 0},
            },
        ),
    }


class TestSpySuccessPath:
    def test_successful_mission_returns_the_report(self, no_sleep):
        client = make_client(spy_script())

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True
        assert result.reason is None
        assert result.message_id == 9001
        assert result.spy_data == [[[487, 100]]]
        assert result.battle_data == {"K": 1}
        assert result.target is not None
        assert result.target.castle_name == "Enemy Keep"

    def test_only_the_spies_the_risk_budget_needs_are_sent(self, no_sleep):
        # Sending the whole pool bought nothing: 6 spies already reach the 5%
        # floor against an unguarded castle, and draining the pool made the next
        # mission wait for spies to walk home.
        client = make_client(spy_script(ssi=xt_packet("ssi", {"AS": 46, "GC": 0})))

        client.spy.execute_instant_spy(12345, 700, 710, target_kingdom=2)

        payloads = dict(conn(client).request_payloads)
        assert payloads["ssi"] == {"TX": 700, "TY": 710, "KID": 2}
        assert payloads["csm"]["SC"] == 6
        assert payloads["csm"]["SE"] == 100
        assert payloads["csm"]["PTT"] == 1
        assert payloads["csm"]["SID"] == 12345
        assert payloads["bsd"] == {"MID": 9001}

    def test_a_loose_ceiling_does_not_buy_a_riskier_mission(self, no_sleep):
        client = make_client(spy_script(ssi=xt_packet("ssi", {"AS": 46, "GC": 0})))

        client.spy.execute_instant_spy(12345, 700, 710, risk_tolerance=90)

        assert dict(conn(client).request_payloads)["csm"]["SC"] == 6

    def test_a_guarded_target_costs_more_spies(self, no_sleep):
        client = make_client(spy_script(ssi=xt_packet("ssi", {"AS": 200, "GC": 60})))

        client.spy.execute_instant_spy(12345, 700, 710)

        assert dict(conn(client).request_payloads)["csm"]["SC"] > 6

    def test_a_target_over_the_risk_ceiling_is_not_spied(self, no_sleep):
        # Two spies against an unguarded castle is the best this pool can do,
        # and that sits well above a 10% ceiling.
        client = make_client(spy_script(ssi=xt_packet("ssi", {"AS": 2, "GC": 0})))

        result = client.spy.execute_instant_spy(12345, 700, 710, risk_tolerance=10)

        assert result.success is False
        assert result.reason == "risk_over_budget"
        assert "csm" not in dict(conn(client).request_payloads), "sent a mission over the ceiling"

    def test_a_thin_pool_still_spies_when_no_ceiling_is_set(self, no_sleep):
        client = make_client(spy_script(ssi=xt_packet("ssi", {"AS": 2, "GC": 0})))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True
        assert dict(conn(client).request_payloads)["csm"]["SC"] == 2

    def test_sne_waiter_is_created_before_the_spy_is_sent(self, no_sleep):
        # sne arrives right after csm; registering the waiter afterwards races
        # the notification.
        client = make_client(spy_script())

        client.spy.execute_instant_spy(12345, 700, 710)

        events = conn(client).events
        assert events.index("create_waiter:sne") < events.index("request:csm")

    def test_waiter_is_cancelled_on_success(self, no_sleep):
        client = make_client(spy_script())
        client.spy.execute_instant_spy(12345, 700, 710)
        assert conn(client).waiters_cancelled == ["sne"]


class TestForwardingASpyReport:
    """Forwarding sends the report's message id to chosen players.

    C2SForwardSpyLogVO(playerIDs, messageID) in the client, so the payload is
    the recipient list plus the id of the report being shared.
    """

    def test_the_report_and_recipients_are_sent(self):
        client = make_client()

        assert client.spy.forward_report(9001, [111, 222]) is True

        assert dict(conn(client).request_payloads)["mfs"] == {"PID": [111, 222], "MID": 9001}

    def test_a_rejected_forward_reports_failure(self):
        client = make_client({"mfs": xt_packet("mfs", error_code=21)})

        assert client.spy.forward_report(9001, [111]) is False

    def test_forwarding_to_nobody_sends_nothing(self):
        client = make_client()

        assert client.spy.forward_report(9001, []) is False
        assert "mfs" not in conn(client).requested


class TestSpyNotificationDecoding:
    """sne carries the mission outcome in a '+'-delimited params string.

    Format, from AMessageSpyVO and MessageConst in the client bundle:
        subtypeSpy+subtypeResult+areaType#kingdomID+ownerID+areaName
    with ATTACKER_SUCCESS=0, DEFENDER_SUCCESS=1, ATTACKER_FAILED=2.

    The old check read first_msg[1]/[2]/[3] as ints and compared a string to 2,
    so it could never fire: every caught mission was recorded as a success, and
    its empty report was published as a castle with no troops.
    """

    def _sne(self, params: str) -> Any:
        return xt_packet("sne", {"MSG": [[9001, 3, params, "", -1, 0, 0, 0, 0]]})

    def test_a_caught_mission_is_reported_as_caught(self, no_sleep):
        client = make_client(
            spy_script(sne=self._sne("1+2+12#3+16324240+Inheritor"), bsd=xt_packet("bsd", {"MID": 9001}))
        )

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.reason == "spy_caught"

    def test_a_successful_defence_for_the_target_is_also_a_loss(self, no_sleep):
        client = make_client(spy_script(sne=self._sne("1+1+12#3+16324240+Inheritor")))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.reason == "spy_caught"

    def test_a_successful_mission_still_reads_as_success(self, no_sleep):
        client = make_client(spy_script(sne=self._sne("1+0+4#0+16324240+Sanghelios")))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True

    def test_an_undecodable_params_string_is_not_a_success(self, no_sleep):
        client = make_client(spy_script(sne=self._sne("garbage")))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.reason == "invalid_sne_format"


class TestSpiedCastleDetail:
    """The report's AI block carries the castle's fortifications.

    parseAreaInfoBattleLog in the client reads keep, wall, gate, tower and moat
    levels from it — the inputs any assessment of the castle needs, and the
    numbers a spy goes to look at in the first place.
    """

    def test_fortification_levels_are_parsed(self, no_sleep):
        bsd = xt_packet(
            "bsd",
            {
                "MID": 9001,
                "S": [[[487, 100]]],
                "AI": {
                    "N": "Requiem", "X": 700, "Y": 710, "K": 1, "AT": 12,
                    "KL": 5, "WL": 4, "GL": 3, "TL": 2, "ML": 1,
                },
            },
        )
        client = make_client(spy_script(bsd=bsd))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.target is not None
        assert result.target.keep_level == 5
        assert result.target.wall_level == 4
        assert result.target.gate_level == 3
        assert result.target.tower_level == 2
        assert result.target.moat_level == 1
        assert result.target.area_type == 12

    def test_a_report_without_fortifications_still_parses(self, no_sleep):
        client = make_client(spy_script())

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True
        assert result.target is not None
        assert result.target.keep_level == -1


class TestSpyReportIsCheckedAgainstTheTarget:
    """sne has no correlation id, so an unrelated notification arriving in the
    window would hand us another castle's report to publish as this target's."""

    def test_a_report_for_another_castle_is_rejected(self, no_sleep):
        bsd = xt_packet(
            "bsd",
            {"MID": 9001, "S": [[[487, 100]]], "AI": {"N": "Elsewhere", "X": 111, "Y": 222, "K": 0}},
        )
        client = make_client(spy_script(bsd=bsd))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.reason == "report_target_mismatch"

    def test_the_requested_castle_is_accepted(self, no_sleep):
        bsd = xt_packet(
            "bsd",
            {"MID": 9001, "S": [[[487, 100]]], "AI": {"N": "Keep", "X": 700, "Y": 710, "K": 0}},
        )
        client = make_client(spy_script(bsd=bsd))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True
        assert result.target is not None
        assert (result.target.x, result.target.y) == (700, 710)

    def test_a_report_with_no_army_block_is_not_an_empty_castle(self, no_sleep):
        # The caught mission's report had no S and no B at all. Reporting that
        # as zero troops publishes a castle nobody actually read.
        bsd = xt_packet("bsd", {"MID": 9001, "AI": {"N": "Keep", "X": 700, "Y": 710, "K": 0}})
        client = make_client(spy_script(bsd=bsd))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.reason == "no_spy_data"


class TestSpyFailurePaths:
    def test_no_spies_available_after_polling(self, no_sleep):
        client = make_client(spy_script(ssi=xt_packet("ssi", {"AS": 0})))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.reason == "no_spies_available"
        # Polled several times, then gave up without sending the mission.
        assert conn(client).requested.count("ssi") == 5
        assert "csm" not in conn(client).requested

    def test_spies_returning_are_picked_up_on_a_later_poll(self, no_sleep):
        script = spy_script(ssi=[xt_packet("ssi", {"AS": 0}), xt_packet("ssi", {"AS": 8})])
        client = make_client(script)

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True
        assert conn(client).requested.count("ssi") == 2

    def test_ssi_error_code_is_tagged_with_the_code(self, no_sleep):
        client = make_client(spy_script(ssi=xt_packet("ssi", error_code=21)))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.reason == "ssi_failed_21"

    def test_ssi_timeout_is_tagged_by_type(self, no_sleep):
        client = make_client(spy_script(ssi=EmpireTimeoutError("no ssi")))
        result = client.spy.execute_instant_spy(12345, 700, 710)
        assert result.reason == "ssi_failed_EmpireTimeoutError"

    def test_csm_rejection_is_tagged(self, no_sleep):
        client = make_client(spy_script(csm=xt_packet("csm", error_code=21)))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.reason == "csm_failed_21"

    def test_sne_timeout_is_tagged(self, no_sleep):
        client = make_client(spy_script(sne=EmpireTimeoutError("no sne")))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.reason == "sne_timeout_or_error_EmpireTimeoutError"

    @pytest.mark.parametrize(
        "sne_payload",
        [
            {},  # no MSG at all
            {"MSG": []},  # empty batch
            {"MSG": [[]]},  # empty first message
            {"MSG": "junk"},  # ValidationError inside parse_response
            {"MSG": [123]},  # entries of the wrong type
        ],
    )
    def test_unusable_sne_payloads_are_rejected(self, no_sleep, sne_payload):
        client = make_client(spy_script(sne=xt_packet("sne", sne_payload)))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.reason == "invalid_sne_format"

    def test_array_sne_payload_is_rejected(self, no_sleep):
        client = make_client(spy_script(sne=xt_packet("sne", [1, 2, 3])))
        result = client.spy.execute_instant_spy(12345, 700, 710)
        assert result.reason == "invalid_sne_format"

    def test_caught_spy_is_reported_as_such(self, no_sleep):
        # subtypeResult 2 is ATTACKER_FAILED: the mission was caught.
        client = make_client(
            spy_script(sne=xt_packet("sne", {"MSG": [[9001, 3, "1+2+12#3+16324240+Enemy Keep", "", -1, 0, 0, 0, 0]]}))
        )

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.reason == "spy_caught"
        # No point asking for the report of a mission that never landed.
        assert "bsd" not in conn(client).requested

    def test_bsd_failure_is_tagged(self, no_sleep):
        client = make_client(spy_script(bsd=xt_packet("bsd", error_code=21)))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.reason == "bsd_failed_21"

    def test_failure_defaults_are_empty_containers(self, no_sleep):
        client = make_client(spy_script(csm=xt_packet("csm", error_code=21)))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.spy_data == []
        assert result.battle_data == {}
        assert result.target is None
        assert result.message_id is None

    @pytest.mark.parametrize(
        "script",
        [
            spy_script(csm=xt_packet("csm", error_code=21)),
            spy_script(sne=EmpireTimeoutError("no sne")),
            spy_script(bsd=xt_packet("bsd", error_code=21)),
        ],
    )
    def test_waiter_is_always_cancelled(self, no_sleep, script):
        client = make_client(script)

        client.spy.execute_instant_spy(12345, 700, 710)

        assert conn(client).waiters_cancelled == ["sne"]


# =============================================================================
# Handler registration via on_response
# =============================================================================


class TestOnResponse:
    def test_registered_handler_receives_parsed_responses(self):
        client = make_client()
        seen: list[object] = []
        client.castle.on_response("gcl", seen.append)

        client._on_packet(xt_packet("gcl", GOLDEN_GCL))

        assert len(seen) == 1
        assert [c.castle_id for c in seen[0].castles] == [12345, 55555]  # type: ignore[attr-defined]

    def test_unparseable_push_does_not_reach_the_handler(self, caplog):
        client = make_client()
        seen: list[object] = []
        client.lords.on_response("gli", seen.append)

        with caplog.at_level(logging.ERROR, logger="empire_core.client.client"):
            client._on_packet(xt_packet("gli", {"C": [{"N": "no id"}]}))

        assert seen == []
        assert "gli" in caplog.text

    def test_commands_without_handlers_are_not_parsed(self):
        client = make_client()
        assert "gli" not in client._handlers

        # An unhandled command whose payload no model can parse must not raise
        # on the receive thread: parsing is skipped entirely.
        client._on_packet(xt_packet("gli", {"C": [{"N": "no id"}]}))

        assert client.state.updates == [("gli", {"C": [{"N": "no id"}]})]  # type: ignore[attr-defined]


# =============================================================================
# Request models used by the services
# =============================================================================


class TestRequestBuilding:
    def test_select_castle_request_packet_shape(self):
        packet = SelectCastleRequest(CID=12345, KID=2).to_packet(zone="EmpireEx_21")
        assert packet == '%xt%EmpireEx_21%jca%1%{"CID": 12345, "KID": 2}%'

    def test_alliance_info_request_requires_an_id(self):
        with pytest.raises(ValidationError):
            GetAllianceInfoRequest()  # type: ignore[call-arg]

    def test_response_members_accessor_tolerates_a_missing_alliance(self):
        response = GetAllianceInfoResponse.model_validate({})
        assert response.members == []
        assert response.online_members == []
