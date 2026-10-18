"""Alliance settings and gift actions from the client command handlers."""

import pytest

from empire_core.exceptions import CommandError, EmpireTimeoutError, PacketError, ReplyMismatchError
from tests.alliance.test_pushes import alliance_state
from tests.service_helpers import conn, make_client, xt_packet


@pytest.mark.parametrize(
    "method,command,key,value",
    [
        ("set_description", "acd", "D", "  Text%  "),
        ("set_announcement", "acd", "A", "Text"),
        ("rename", "acn", "N", "New Guild"),
        ("set_language", "cal", "ALL", "de"),
    ],
)
def test_settings_return_echoed_alliance(method, command, key, value):
    state = alliance_state()
    block = {"A": {"AID": 301, key: value}}
    payload = {"ain": block} if command == "acd" else block
    client = make_client({command: xt_packet(command, payload)}, state=state)
    kwargs = {"spend_rubies": True} if command == "acn" else {}
    result = getattr(client.alliance, method)(value, **kwargs, timeout=0.2)
    assert result.alliance_id == 301
    expected = (
        {"TXT": "Text&percnt;", "T": 1}
        if method == "set_description"
        else {"TXT": "Text", "T": 0}
        if command == "acd"
        else {"AN": value}
        if command == "acn"
        else {"ALL": value}
    )
    assert conn(client).request_payloads == [(command, expected)]


def test_rename_requires_ruby_consent_unless_fresh_free_rename():
    state = alliance_state()
    client = make_client({"ain": xt_packet("ain", {"A": {"AID": 301, "FR": 0}})}, state=state)
    with pytest.raises(ValueError, match="spend_rubies"):
        client.alliance.rename("New Guild")
    assert conn(client).requested == ["ain"]
    client = make_client(
        {
            "ain": xt_packet("ain", {"A": {"AID": 301, "FR": 1}}),
            "acn": xt_packet("acn", {"A": {"AID": 301, "N": "New Guild"}}),
        },
        state=state,
    )
    assert client.alliance.rename("New Guild").name == "New Guild"


@pytest.mark.parametrize("payload", [{}, {"ain": {}}, {"ain": {"A": {"AID": 401}}}])
def test_invalid_settings_reply_preserves_state(payload):
    state = alliance_state()
    before = state.get_own_alliance()
    client = make_client({"acd": xt_packet("acd", payload)}, state=state)
    conn(client).on_packet = lambda packet: state.update_from_packet(
        packet.command_id, packet.payload, packet.error_code
    )
    with pytest.raises((PacketError, EmpireTimeoutError)):
        client.alliance.set_description("Text")
    assert state.get_own_alliance() == before


@pytest.mark.parametrize("failure", [CommandError("acd", 1, {}), EmpireTimeoutError("timeout")])
def test_settings_failure_preserves_state(failure):
    state = alliance_state()
    client = make_client({"acd": failure}, state=state)
    before = state.get_own_alliance()
    with pytest.raises(type(failure)):
        client.alliance.set_description("Text")
    assert state.get_own_alliance() == before


def test_settings_cannot_apply_reply_after_leave_and_rejoin_same_id():
    state = alliance_state()
    client = make_client({"acd": xt_packet("acd", {"ain": {"A": {"AID": 301, "N": "Late"}}})}, state=state)

    def newer(packet):
        state.update_from_packet("gal", {"AID": -1})
        state.update_from_packet("gal", {"AID": 301})
        state.update_from_packet("ain", {"A": {"AID": 301, "N": "New membership"}})
        state.update_from_packet(packet.command_id, packet.payload, packet.error_code)

    conn(client).on_packet = newer
    with pytest.raises(ReplyMismatchError):
        client.alliance.set_description("Text")
    current = state.get_own_alliance()
    assert current is not None and current.name == "New membership"


def test_gift_push_read_and_collection_are_typed_and_context_safe():
    state = alliance_state()
    client = make_client({"agc": xt_packet("agc", {"ID": 17, "R": [["C1", 50]]})}, state=state)
    state.update_from_packet("agr", {"G": ["AG", "gift", 60, 17]})
    gifts = client.alliance.gifts
    assert len(gifts) == 1 and gifts[0].gift_id == 17 and gifts[0].remaining_seconds() > 0
    result = client.alliance.collect_gift(17)
    assert result.gift_id == 17 and result.rewards[0].amount == 50
    assert client.alliance.gifts == []
    assert conn(client).request_payloads == [("agc", {"ID": 17})]


def test_gift_invalid_or_failed_collection_keeps_gift():
    for payload, code in [({}, 0), ({"ID": 17}, 0), ({"ID": 17, "R": "bad"}, 0), ({"ID": 17, "R": []}, 1)]:
        state = alliance_state()
        state.update_from_packet("agr", {"G": ["AG", "gift", 60, 17]})
        client = make_client({"agc": xt_packet("agc", payload, code)}, state=state)
        with pytest.raises((PacketError, CommandError)):
            client.alliance.collect_gift(17)
        assert len(client.alliance.gifts) == 1


def test_newer_push_is_preserved_when_settings_reply_wakes_caller():
    state = alliance_state()
    client = make_client(
        {"acd": xt_packet("acd", {"ain": {"A": {"AID": 301, "D": "New description", "CF": 2, "HF": 3, "ABL": []}}})},
        state=state,
    )

    def received(packet):
        state.update_from_packet(packet.command_id, packet.payload, packet.error_code)
        state.update_from_packet("afa", {"CF": 77, "HF": 88})
        state.update_from_packet("abl", {"ABL": [{"BT": 1, "L": 4, "CD": -1}]})

    conn(client).on_packet = received
    client.alliance.set_description("New description")
    current = state.get_own_alliance()
    assert current is not None and current.description == "New description"
    assert current.fame_points == 77 and current.highest_fame_points == 88
    assert current.buildings[0].level == 4


def emblem_client(script=None):
    from empire_core.gamedata import GameData

    client = make_client(script, state=alliance_state())
    client.game_data = GameData.parse(
        "synthetic",
        {
            "allianceCoatLayouts": [
                {"allianceCoatLayoutID": 900001, "noofColors": 2, "maxDuration": 0},
                {"allianceCoatLayoutID": 900002, "noofColors": 1, "maxDuration": 60},
            ],
            "allianceCoatColors": [{"allianceCoatColorID": 900003}, {"allianceCoatColorID": 900004}],
        },
    )
    return client


def test_emblem_uses_client_game_data_and_acknowledges_without_fabricated_push():
    client = emblem_client()
    result = client.alliance.set_emblem(900001, [900003, 900004], timeout=0.2)
    assert result.layout_id == 900001 and result.color_ids == [900003, 900004]
    assert conn(client).request_payloads == [("sae", {"ACLI": 900001, "ACCS": [900003, 900004]})]
    assert client.alliance.own_alliance is not None and client.alliance.own_alliance.crests is None


def test_emblem_validates_available_layout_and_colors():
    client = emblem_client({"ain": xt_packet("ain", {"A": {"AID": 301, "ACLS": []}})})
    for layout_id, colors in [(900001, [900003]), (999999, [900003]), (900001, [900003, 999999]), (900002, [900003])]:
        with pytest.raises(ValueError):
            client.alliance.set_emblem(layout_id, colors)
    assert "sae" not in conn(client).requested


def test_gift_reads_filter_expiry_and_membership_switch_clears_gifts():
    state = alliance_state()
    state.update_from_packet("agr", {"G": ["AG", "gift", 0, 16]})
    state.update_from_packet("agr", {"G": ["AG", "gift", 60, 17]})
    state.update_from_packet("agr", {"G": "bad"})
    client = make_client(state=state)
    assert [gift.gift_id for gift in client.alliance.gifts] == [17]
    state.update_from_packet("gal", {"AID": 401})
    assert client.alliance.gifts == []


def test_gift_collection_does_not_remove_same_id_after_membership_switch():
    state = alliance_state()
    state.update_from_packet("agr", {"G": ["AG", "gift", 60, 17]})
    client = make_client({"agc": xt_packet("agc", {"ID": 17, "R": []})}, state=state)

    def newer(packet):
        state.update_from_packet("gal", {"AID": 401})
        state.update_from_packet("ain", {"A": {"AID": 401}})
        state.update_from_packet("agr", {"G": ["AG", "new gift", 60, 17]})

    conn(client).on_packet = newer
    with pytest.raises(ReplyMismatchError):
        client.alliance.collect_gift(17)
    assert [gift.gift_id for gift in client.alliance.gifts] == [17]


def test_rename_preflight_cannot_overwrite_new_same_id_membership():
    state = alliance_state()
    client = make_client({"ain": xt_packet("ain", {"A": {"AID": 301, "N": "Late details", "FR": 1}})}, state=state)

    def newer(packet):
        state.update_from_packet("gal", {"AID": -1})
        state.update_from_packet("gal", {"AID": 301})
        state.update_from_packet("gbd", {"ain": {"A": {"AID": 301, "N": "New membership"}}})
        state.update_from_packet(packet.command_id, packet.payload, packet.error_code)

    conn(client).on_packet = newer
    with pytest.raises(ReplyMismatchError):
        client.alliance.rename("New Name")
    current = state.get_own_alliance()
    assert current is not None and current.name == "New membership"
    assert conn(client).requested == ["ain"]


def test_settings_text_matches_distinct_client_description_and_announcement_paths():
    from empire_core.alliance.models.settings import ChangeAllianceDescriptionRequest

    assert ChangeAllianceDescriptionRequest(text=" \\ ", text_type=1).to_payload() == {"TXT": "&percnt;5C", "T": 1}
    assert ChangeAllianceDescriptionRequest(text="\\", text_type=0).to_payload() == {"TXT": "%5C", "T": 0}
    assert ChangeAllianceDescriptionRequest(text="😀" * 501, text_type=1).to_payload()["TXT"] == "😀" * 500


@pytest.mark.parametrize("newer_members", [False, True])
def test_settings_keep_newer_or_omitted_member_protection_timestamps(newer_members):
    state = alliance_state()
    state.update_from_packet("ain", {"A": {"AID": 301, "M": [{"OID": 8, "RNP": 60}]}})
    before = state.get_own_alliance()
    assert before is not None
    timestamps = [before.members[0].received_at]
    client = make_client({"acd": xt_packet("acd", {"ain": {"A": {"AID": 301, "D": "Description"}}})}, state=state)

    def received(packet):
        state.update_from_packet(packet.command_id, packet.payload, packet.error_code)
        if newer_members:
            state.update_from_packet("ain", {"A": {"AID": 301, "M": [{"OID": 9, "RNP": 30}]}})
            current = state.get_own_alliance()
            assert current is not None
            timestamps.append(current.members[0].received_at)

    conn(client).on_packet = received
    client.alliance.set_description("Description")
    current = state.get_own_alliance()
    assert current is not None and current.members[0].received_at == timestamps[-1]
    assert current.members[0].player_id == (9 if newer_members else 8)


def test_rename_keeps_preflight_membership_when_helper_starts_after_a_switch(monkeypatch):
    state = alliance_state()
    client = make_client({"ain": xt_packet("ain", {"A": {"AID": 301, "FR": 1}})}, state=state)
    change = client.alliance._change_settings

    def switched(*args, **kwargs):
        state.update_from_packet("gal", {"AID": 401})
        state.update_from_packet("ain", {"A": {"AID": 401, "FR": 0}})
        return change(*args, **kwargs)

    monkeypatch.setattr(client.alliance, "_change_settings", switched)
    with pytest.raises(ReplyMismatchError):
        client.alliance.rename("New Name")
    assert conn(client).requested == ["ain"]


def test_emblem_keeps_original_membership_at_final_send_check(monkeypatch):
    from contextlib import contextmanager

    client = emblem_client()
    state = client.state
    own_alliance = client.alliance._own_alliance

    @contextmanager
    def switched(**kwargs):
        with own_alliance(**kwargs):
            state.update_from_packet("gal", {"AID": 401})
            state.update_from_packet("ain", {"A": {"AID": 401}})
            yield

    monkeypatch.setattr(client.alliance, "_own_alliance", switched)
    with pytest.raises(ReplyMismatchError):
        client.alliance.set_emblem(900001, [900003, 900004])
    assert conn(client).requested == []


@pytest.mark.parametrize("changed_section", ["M", "AMI"])
def test_partial_member_updates_keep_activity_links(changed_section):
    state = alliance_state()
    state.update_from_packet("ain", {"A": {"AID": 301, "M": [{"OID": 8, "RNP": 60}], "AMI": [[8, 0, 0, 0, 4]]}})
    before = state.get_own_alliance()
    assert before is not None
    fields: dict[str, object] = {"M": [{"OID": 8, "RNP": 60}]} if changed_section == "M" else {"AMI": [[8, 0, 0, 0, 0]]}
    client = make_client({"acd": xt_packet("acd", {"ain": {"A": {"AID": 301, **fields}}})}, state=state)
    client.alliance.set_description("Description")
    current = state.get_own_alliance()
    assert current is not None
    if changed_section == "AMI":
        assert current.members[0].received_at == before.members[0].received_at
        assert current.members[0].activity_tier == 0 and current.online_count == 1
    else:
        received_at = current.members[0].received_at
        state.update_from_packet("acm", {"CM": {"PID": 8, "PN": "Member", "T": "hello"}})
        current = state.get_own_alliance()
        assert current is not None and current.members[0].received_at == received_at
        assert current.members[0].activity_tier == 0 and current.online_count == 1
