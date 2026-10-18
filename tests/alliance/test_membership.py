"""Membership requests and alliance identity changes from client handlers."""

import pytest

from empire_core.exceptions import CommandError, EmpireTimeoutError, PacketError
from empire_core.state.manager import GameState
from empire_core.state.models import Player
from tests.service_helpers import conn, xt_packet
from tests.service_helpers import make_client as service_client


def membership_state():
    state = GameState()
    state.local_player = Player(PID=7, PN="Player")
    return state


def make_client(script=None, state=None):
    return service_client(script, state=state if state is not None else membership_state())


def test_application_uses_alliance_id_and_single_text_encoding():
    client = make_client()
    client.alliance.apply(301, "  A%\\'\"\t\n  ", timeout=0.2)
    assert conn(client).request_payloads == [("saa", {"AID": 301, "AT": "  A&percnt;&percnt;5C&145;&quot; <br />  "})]


def test_join_applies_gal_before_alliance_details_and_resets_old_context():
    state = membership_state()
    state.update_from_packet("gal", {"AID": 201, "R": 8, "AN": "Old"})
    state.update_from_packet("ain", {"A": {"AID": 201, "N": "Old"}})
    state.update_from_packet("acm", {"CM": {"PID": 1, "PN": "Old member", "T": "hello"}})
    client = make_client(
        {"joa": xt_packet("joa", {"gal": {"AID": 301, "R": 8, "AN": "New"}, "A": {"AID": 301, "N": "New"}})},
        state=state,
    )
    conn(client).on_packet = lambda packet: state.update_from_packet(
        packet.command_id, packet.payload, packet.error_code
    )
    joined = client.alliance.join_open(301, timeout=0.2)
    assert joined.alliance_id == 301
    own = client.alliance.own_alliance
    assert own is not None and own.alliance_id == 301
    assert state.get_local_player().alliance_id == 301
    assert client.alliance.chat == []
    state.update_from_packet("ain", {"A": {"AID": 201, "N": "Late"}})
    own = client.alliance.own_alliance
    assert own is not None and own.alliance_id == 301
    assert conn(client).request_payloads == [("joa", {"AID": 301})]


def test_join_refusal_does_not_change_state():
    state = membership_state()
    state.update_from_packet("gal", {"AID": 201, "R": 8, "AN": "Old"})
    client = make_client({"joa": xt_packet("joa", {"gal": {"AID": 301}, "A": {"AID": 301}}, error_code=1)}, state=state)
    conn(client).on_packet = lambda packet: state.update_from_packet(
        packet.command_id, packet.payload, packet.error_code
    )
    with pytest.raises(CommandError):
        client.alliance.join_open(301)
    assert state.get_local_player().alliance_id == 201


def test_join_missing_or_wrong_alliance_is_malformed():
    for payload in [{}, {"gal": {"AID": 999}, "A": {"AID": 301}}]:
        client = make_client({"joa": xt_packet("joa", payload)})
        with pytest.raises(PacketError):
            client.alliance.join_open(301)


def test_positive_identity_change_forgets_old_alliance_until_details_arrive():
    state = membership_state()
    state.update_from_packet("gal", {"AID": 201, "R": 8})
    state.update_from_packet("ain", {"A": {"AID": 201, "N": "Old"}})
    state.update_from_packet("gal", {"AID": 301, "R": 8})
    assert state.get_own_alliance() is None
    state.update_from_packet("ain", {"A": {"AID": 201, "N": "Late old"}})
    assert state.get_own_alliance() is None


@pytest.mark.parametrize("command,method,args", [("saa", "apply", (301, "Application")), ("joa", "join_open", (301,))])
def test_membership_transport_failure(command, method, args):
    client = make_client({command: EmpireTimeoutError("timeout")})
    with pytest.raises(EmpireTimeoutError):
        getattr(client.alliance, method)(*args, timeout=0.1)


def test_join_does_not_accept_another_alliance_reply():
    client = make_client({"joa": xt_packet("joa", {"gal": {"AID": 999}, "A": {"AID": 999}})})
    with pytest.raises(EmpireTimeoutError):
        client.alliance.join_open(301)


def test_application_constructor_encodes_once_before_frame_escaping():
    from empire_core.alliance.models.membership import ApplyToAllianceRequest

    assert ApplyToAllianceRequest(alliance_id=301, text="\\").to_payload() == {"AID": 301, "AT": "%5C"}


def test_invitation_reads_by_message_id_and_decodes_alliance():
    client = make_client({"bai": xt_packet("bai", {"A": {"AID": 301, "N": "Guild", "D": "Hi &quot;there&quot;"}})})
    result = client.alliance.get_invitation(77, timeout=0.2)
    assert result.alliance_id == 301
    assert result.description == 'Hi "there"'
    assert conn(client).request_payloads == [("bai", {"MID": 77})]


def test_accept_invitation_uses_message_id_decision_and_updates_state():
    state = membership_state()
    client = make_client(
        {"aai": xt_packet("aai", {"gal": {"AID": 301, "R": 8}, "A": {"AID": 301, "N": "Guild"}})}, state=state
    )
    conn(client).on_packet = lambda packet: state.update_from_packet(
        packet.command_id, packet.payload, packet.error_code
    )
    result = client.alliance.accept_invitation(77, timeout=0.2)
    assert result is not None and result.alliance_id == 301
    assert state.get_local_player().alliance_id == 301
    own = client.alliance.own_alliance
    assert own is not None and own.alliance_id == 301
    assert conn(client).request_payloads == [("aai", {"MID": 77, "D": 1})]


def test_refuse_invitation_is_an_explicit_decision():
    client = make_client()
    assert client.alliance.accept_invitation(77, accept=False) is None
    assert conn(client).request_payloads == [("aai", {"MID": 77, "D": 0})]


def test_recruits_are_typed_sorted_and_resolve_owner_records(caplog):
    from tests.alliance.test_service import member_client

    client = member_client(
        {
            "sml": xt_packet(
                "sml",
                {
                    "PL": [{"PID": 8, "D": 10}, [], {"PID": 7, "D": 2}],
                    "OI": [{"OID": 7, "N": "Recruit", "L": 42, "SA": 1}, [], {"OID": 0}],
                },
            )
        }
    )
    result = client.alliance.find_recruits()
    assert [r.player_id for r in result.recruits] == [7, 8]
    owner = result.owner_of(result.recruits[0])
    assert owner is not None and owner.name == "Recruit" and owner.is_searching_alliance
    assert result.owner_of(result.recruits[1]) is None
    assert caplog.records
    assert conn(client).request_payloads == [("sml", {})]


def test_empty_recruits_and_wrong_shape():
    from tests.alliance.test_service import member_client

    client = member_client({"sml": [xt_packet("sml", {"PL": [], "OI": []}), xt_packet("sml", {"PL": {}})]})
    assert client.alliance.find_recruits().recruits == []
    with pytest.raises(PacketError):
        client.alliance.find_recruits()


def test_search_flags_are_exact_and_independent():
    from tests.alliance.test_service import member_client

    client = member_client()
    client.alliance.set_looking_for_members(True, open_join=False)
    client.alliance.set_looking_for_alliance(True)
    assert conn(client).request_payloads == [("asm", {"IS": 1, "IA": 0}), ("asa", {"IS": 1})]


@pytest.mark.parametrize(
    "command,method,args,kwargs",
    [
        ("bai", "get_invitation", (77,), {}),
        ("aai", "accept_invitation", (77,), {}),
        ("sml", "find_recruits", (), {}),
        ("asm", "set_looking_for_members", (True,), {"open_join": True}),
        ("asa", "set_looking_for_alliance", (True,), {}),
    ],
)
def test_other_membership_failures(command, method, args, kwargs):
    from empire_core.exceptions import ConnectionClosedError

    for response, error in [
        (xt_packet(command, error_code=1), CommandError),
        (EmpireTimeoutError("timeout"), EmpireTimeoutError),
        (ConnectionClosedError("closed"), ConnectionClosedError),
    ]:
        state = membership_state()
        state.update_from_packet("gal", {"AID": 201})
        client = make_client({command: response}, state=state)
        with pytest.raises(error):
            getattr(client.alliance, method)(*args, **kwargs, timeout=0.1)


def test_identity_change_clears_chat_even_before_alliance_details_loaded():
    state = membership_state()
    state.update_from_packet("gal", {"AID": 201})
    state.update_from_packet("acl", {"CM": [{"PID": 2, "PN": "Old", "T": "hello"}]})
    assert state.get_alliance_chat()
    state.update_from_packet("gal", {"AID": 301})
    assert state.get_alliance_chat() == []


def test_inconsistent_invitation_response_leaves_state_unchanged():
    state = membership_state()
    state.update_from_packet("gal", {"AID": 201})
    state.update_from_packet("aai", {"gal": {"AID": 301}, "A": {"AID": 999}})
    assert state.get_local_player().alliance_id == 201


def test_join_requires_an_explicit_alliance_id_in_details():
    client = make_client({"joa": xt_packet("joa", {"gal": {"AID": 0}, "A": {}})})
    with pytest.raises(PacketError):
        client.alliance.join_open(301)


def test_missing_invitation_alliance_is_malformed():
    client = make_client()
    with pytest.raises(PacketError):
        client.alliance.get_invitation(77)


def dispatch_client(state):
    from empire_core.network.connection import Connection

    client = make_client(state=state)
    connection = Connection("wss://example.invalid/")
    connection.on_packet = client._on_packet
    client.connection = connection
    return client, connection


def test_real_dispatch_rejected_join_does_not_mutate_membership():
    from empire_core.alliance.models.membership import JoinOpenAllianceRequest

    state = membership_state()
    state.update_from_packet("gal", {"AID": 201})
    state.update_from_packet("ain", {"A": {"AID": 201, "N": "Current"}})
    client, connection = dispatch_client(state)
    request = JoinOpenAllianceRequest(alliance_id=301)
    waiter = connection.create_waiter("joa", lambda packet: request.accepts_reply(packet.payload))
    connection._route_packet(xt_packet("joa", {"gal": {"AID": 999}, "A": {"AID": 999, "N": "Other"}}))
    assert not waiter.event.is_set()
    assert state.get_local_player().alliance_id == 201
    own = client.alliance.own_alliance
    assert own is not None and own.alliance_id == 201
    connection.cancel_waiter("joa", waiter)


@pytest.mark.parametrize("command,method", [("joa", "join_open"), ("aai", "accept_invitation")])
def test_real_dispatch_applies_only_accepted_service_reply(command, method, monkeypatch):
    state = membership_state()
    client, connection = dispatch_client(state)
    reply = xt_packet(command, {"gal": {"AID": 301, "R": 8}, "A": {"AID": 301, "N": "Joined"}})
    monkeypatch.setattr(connection, "send", lambda frame: connection._route_packet(reply))
    result = getattr(client.alliance, method)(301, timeout=0.1)
    assert result.alliance_id == 301
    assert state.get_local_player().alliance_id == 301
    own = client.alliance.own_alliance
    assert own is not None and own.alliance_id == 301


@pytest.mark.parametrize("command,method", [("joa", "join_open"), ("aai", "accept_invitation")])
def test_newer_gal_after_receipt_cannot_be_overwritten(command, method, monkeypatch):
    from empire_core.exceptions import ReplyMismatchError

    state = membership_state()
    client, connection = dispatch_client(state)

    def receive_then_newer_membership(frame):
        connection._route_packet(xt_packet(command, {"gal": {"AID": 301}, "A": {"AID": 301, "N": "Old reply"}}))
        connection._route_packet(xt_packet("gal", {"AID": 777, "AN": "Newer"}))
        connection._route_packet(xt_packet("ain", {"A": {"AID": 777, "N": "Newer"}}))

    monkeypatch.setattr(connection, "send", receive_then_newer_membership)
    with pytest.raises(ReplyMismatchError):
        getattr(client.alliance, method)(301, timeout=0.1)
    assert state.get_local_player().alliance_id == 777
    own = client.alliance.own_alliance
    assert own is not None and own.alliance_id == 777


@pytest.mark.parametrize("command,method", [("joa", "join_open"), ("aai", "accept_invitation")])
def test_timed_out_membership_reply_cannot_mutate_later_state(command, method, monkeypatch):
    state = membership_state()
    state.update_from_packet("gal", {"AID": 201})
    client, connection = dispatch_client(state)
    monkeypatch.setattr(connection, "send", lambda frame: None)
    with pytest.raises(EmpireTimeoutError):
        getattr(client.alliance, method)(301, timeout=0.001)
    connection._route_packet(xt_packet("gal", {"AID": 777}))
    connection._route_packet(xt_packet(command, {"gal": {"AID": 301}, "A": {"AID": 301}}))
    assert state.get_local_player().alliance_id == 777


def test_unsolicited_gal_stays_authoritative_under_real_dispatch():
    state = membership_state()
    client, connection = dispatch_client(state)
    connection._route_packet(xt_packet("gal", {"AID": 777, "AN": "Joined elsewhere"}))
    connection._route_packet(xt_packet("ain", {"A": {"AID": 777, "N": "Joined elsewhere"}}))
    assert state.get_local_player().alliance_id == 777
    own = client.alliance.own_alliance
    assert own is not None and own.alliance_id == 777


@pytest.mark.parametrize("command,method", [("joa", "join_open"), ("aai", "accept_invitation")])
def test_membership_revision_rejects_return_to_same_identity(command, method, monkeypatch):
    from empire_core.exceptions import ReplyMismatchError

    state = membership_state()
    state.update_from_packet("gal", {"AID": 201})
    client, connection = dispatch_client(state)

    def receive_then_leave_and_return(frame):
        connection._route_packet(xt_packet(command, {"gal": {"AID": 301}, "A": {"AID": 301}}))
        connection._route_packet(xt_packet("gal", {"AID": 777}))
        connection._route_packet(xt_packet("gal", {"AID": 201, "R": 9}))

    monkeypatch.setattr(connection, "send", receive_then_leave_and_return)
    with pytest.raises(ReplyMismatchError):
        getattr(client.alliance, method)(301, timeout=0.1)
    assert state.get_local_player().alliance_id == 201
    assert state.get_local_player().alliance.rank == 9


@pytest.mark.parametrize("command,method", [("joa", "join_open"), ("aai", "accept_invitation")])
def test_session_reset_invalidates_membership_reply(command, method, monkeypatch):
    from empire_core.exceptions import ReplyMismatchError

    state = membership_state()
    client, connection = dispatch_client(state)

    def receive_then_disconnect(frame):
        connection._route_packet(xt_packet(command, {"gal": {"AID": 301}, "A": {"AID": 301}}))
        state.reset()

    monkeypatch.setattr(connection, "send", receive_then_disconnect)
    with pytest.raises(ReplyMismatchError):
        getattr(client.alliance, method)(301, timeout=0.1)
    assert state.local_player is None and state.get_own_alliance() is None


def test_scoped_membership_update_preserves_omitted_alliance_fields(monkeypatch):
    state = membership_state()
    state.update_from_packet("gal", {"AID": 301})
    state.update_from_packet("ain", {"A": {"AID": 301, "N": "Current", "AW": 1, "AA": 3}})
    client, connection = dispatch_client(state)
    monkeypatch.setattr(
        connection,
        "send",
        lambda frame: connection._route_packet(
            xt_packet("joa", {"gal": {"AID": 301}, "A": {"AID": 301, "N": "Current"}})
        ),
    )
    client.alliance.join_open(301, timeout=0.1)
    own = client.alliance.own_alliance
    assert own is not None and own.auto_war and own.application_count == 3


@pytest.mark.parametrize("command,method", [("joa", "join_open"), ("aai", "accept_invitation")])
def test_scoped_membership_keeps_raw_boolean_and_text_semantics(command, method, monkeypatch):
    from empire_core.protocol.text import decode_json_text

    state = membership_state()
    client, connection = dispatch_client(state)
    text = "Literal &percnt;5C &quot;quote&quot; [plan]"
    monkeypatch.setattr(
        connection,
        "send",
        lambda frame: connection._route_packet(
            xt_packet(command, {"gal": {"AID": 301, "SA": 1}, "A": {"AID": 301, "N": "Guild", "D": text}})
        ),
    )
    result = getattr(client.alliance, method)(301, timeout=0.1)
    membership = state.get_local_player().alliance
    assert membership is not None and membership.is_searching
    own = client.alliance.own_alliance
    assert own is not None and own.description == result.description == decode_json_text(text)


def test_accepted_leave_without_gal_invalidates_pending_join(monkeypatch):
    from empire_core.exceptions import ReplyMismatchError

    state = membership_state()
    state.update_from_packet("gal", {"AID": 201})
    state.update_from_packet("ain", {"A": {"AID": 201, "N": "Current"}})
    client, connection = dispatch_client(state)

    def receive_then_leave(frame):
        connection._route_packet(xt_packet("joa", {"gal": {"AID": 301}, "A": {"AID": 301}}))
        connection._route_packet(xt_packet("aqi", {}))

    monkeypatch.setattr(connection, "send", receive_then_leave)
    with pytest.raises(ReplyMismatchError):
        client.alliance.join_open(301, timeout=0.1)
    assert state.get_own_alliance() is None and state.get_alliance_chat() == []
    assert state.get_local_player().alliance_id == 201
