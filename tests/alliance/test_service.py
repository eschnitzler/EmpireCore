"""Tests for the alliance service."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from empire_core.exceptions import CommandError
from empire_core.protocol.models import AllianceChatMessageResponse, AllianceMember, HelpType
from tests.service_helpers import StubPlayer, StubState, conn, make_client, request_payload, xt_packet

# =============================================================================
# Golden payloads (shapes captured from the live server)
# =============================================================================

GOLDEN_AIN: dict[str, Any] = {
    "A": {
        "AID": 190426,
        "N": "Test Alliance",
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
                "AR": 0,
                "MP": 1200000,
                "CF": 3,
                "HF": 9,
                "AID": 190426,
                "AN": "Test Alliance",
                "RPT": 0,
                "AP": [[0, 12345, 640, 655, 1], [2, 22222, 300, 400, 4]],
                "E": {"BGT": 1, "BGC1": 2, "SPT": 3, "S1": 4, "IS": 1},
            },
            {
                "OID": 7002,
                "N": "OfficerGal",
                "L": 70,
                "AR": 4,
                "AID": 190426,
                "MP": 900000,
                "RPT": 7200,
                "AP": [[0, 12346, 641, 656, 1]],
            },
            {"OID": 7003, "N": "AfkDude", "L": 55, "AR": 8, "AID": 190426, "MP": 100, "AP": []},
        ],
        # Positional activity array: [player_id, ?, ?, ?, activity_tier]
        "AMI": [[7001, 0, 0, 0, 0], [7002, 0, 0, 0, 2], [7003, 0, 0, 0, 4]],
    }
}


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

        castles = by_name["LeaderGuy"].castle_positions
        assert [(c.kingdom_id, c.x, c.y, c.area_type) for c in castles] == [
            (0, 640, 655, 1),
            (2, 300, 400, 4),
        ]
        assert by_name["AfkDude"].castle_positions == []

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
    GOLDEN_HGH: dict[str, Any] = {"L": [[1, 4213377, [190426, "Test Alliance", 47, 1520300]]]}

    def test_search_parses_positional_results(self):
        client = make_client({"hgh": xt_packet("hgh", self.GOLDEN_HGH)})

        results = client.alliance.search_alliances("HOPE")

        assert len(results) == 1
        assert results[0].alliance_id == 190426
        assert results[0].name == "Test Alliance"
        assert results[0].member_count == 47
        assert (results[0].rank, results[0].score, results[0].fame_points) == (1, 4213377, 1520300)

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

    def test_a_row_without_an_alliance_keeps_its_defaults(self):
        client = make_client({"hgh": xt_packet("hgh", {"L": [[1, 2], [1, 2, "not-a-list"]]})})
        results = client.alliance.search_alliances("HOPE")
        assert [(r.rank, r.score, r.name) for r in results] == [(1, 2, ""), (1, 2, "")]

    def test_a_list_that_is_not_a_list_is_an_empty_result(self):
        client = make_client({"hgh": xt_packet("hgh", {"L": "junk"})})
        assert client.alliance.search_alliances("HOPE") == []

    def test_a_row_that_is_not_a_list_is_skipped_not_fatal(self, caplog):
        payload = {"L": [[1, 2, ["x", "y"]], self.GOLDEN_HGH["L"][0], 5]}
        client = make_client({"hgh": xt_packet("hgh", payload)})

        with caplog.at_level(logging.WARNING, logger="empire_core.alliance.models.info"):
            results = client.alliance.search_alliances("HOPE")

        assert [(r.alliance_id, r.name) for r in results] == [(0, "y"), (190426, "Test Alliance")]
        assert "Skipped 1/3" in caplog.text


class TestAllianceChat:
    def test_send_chat_encodes_special_characters(self):
        client = make_client()

        client.alliance.send_chat('100% sure, said "go"')

        payload = request_payload(conn(client).sent[0])
        assert payload["M"] == "100&percnt; sure, said &quot;go&quot;"
        assert conn(client).requested == []

    def test_get_chat_log_parses_entries(self):
        payload = {
            "CM": [
                {"PID": 7001, "PN": "LeaderGuy", "MT": "100&percnt; ready", "MA": 90},
                {"PID": 7002, "PN": "OfficerGal", "MT": "on my way", "MA": 30},
            ]
        }
        client = make_client({"acl": xt_packet("acl", payload)})

        log = client.alliance.get_chat_log()

        assert [e.player_name for e in log] == ["LeaderGuy", "OfficerGal"]
        assert log[0].decoded_text == "100% ready"
        assert [e.age_seconds for e in log] == [90, 30]

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

        with caplog.at_level(logging.ERROR, logger="empire_core.alliance.service"):
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


HEAL_ENTRY: dict[str, Any] = {
    "AC": 0,
    "LID": 31,
    "PN": "OfficerGal",
    "P": 2,
    "PID": 7002,
    "TID": 2,
    "OP": {"RID": 5, "T": 1, "AID": 12346, "SID": 7},
    "RT": 3600,
}
REPAIR_ENTRY: dict[str, Any] = {
    "AC": 1,
    "LID": 32,
    "PN": "AfkDude",
    "P": 0,
    "PID": 7003,
    "TID": 3,
    "OP": {"KID": 0, "AID": 12347, "OID": 88},
    "RT": -1,
}


class TestAllianceHelp:
    """Payloads as C2SAllianceHelpConfirmedVO, C2SAllianceHelpAllRequestVO and C2SAllianceHelpRequestVO build them."""

    def test_help_member_sends_the_list_id_and_kingdom_1(self):
        client = make_client()
        client._on_packet(xt_packet("ahl", {"AHL": [HEAL_ENTRY], "TSL": -1}))

        client.alliance.help_member(client.alliance.help_requests[0])
        client.alliance.help_member(32)

        sent = [request_payload(p) for p in conn(client).sent]
        assert sent == [{"LID": 31, "KID": 1}, {"LID": 32, "KID": 1}]
        assert [list(p) for p in sent] == [["LID", "KID"], ["LID", "KID"]]

    def test_help_all_sends_kingdom_15_without_waiting(self):
        client = make_client()

        client.alliance.help_all()

        assert request_payload(conn(client).sent[0]) == {"KID": 15}
        assert conn(client).requested == []

    @pytest.mark.parametrize(
        ("call", "payload"),
        [
            (lambda a: a.request_build_help(88), {"ID": 88, "T": 4}),
            (lambda a: a.request_repair_help(88), {"ID": 88, "T": 3}),
            (lambda a: a.request_recruit_help(9, HelpType.LOOP_RECRUIT), {"ID": 9, "T": 5}),
            (lambda a: a.request_heal_help(5, 2), {"ID": 5, "T": 2}),
        ],
    )
    def test_asking_for_help(self, call, payload):
        client = make_client()

        assert call(client.alliance) is True

        (sent,) = conn(client).request_payloads
        assert sent == ("ahr", payload)
        assert list(sent[1]) == ["ID", "T"]

    def test_a_refused_request_is_false(self):
        client = make_client({"ahr": xt_packet("ahr", error_code=21)})
        assert client.alliance.request_repair_help(88) is False

    def test_recruit_help_needs_a_recruit_type(self):
        client = make_client()
        with pytest.raises(ValueError):
            client.alliance.request_recruit_help(9, HelpType.REPAIR)

    def test_the_help_list_follows_the_pushes(self):
        client = make_client()
        seen: list[Any] = []
        client.alliance.on_help_update(seen.append)

        client._on_packet(xt_packet("ahl", {"AHL": [HEAL_ENTRY], "TSL": 60}))
        client._on_packet(xt_packet("ahh", {**HEAL_ENTRY, "P": 3, "TSL": 60}))
        client._on_packet(xt_packet("ahh", REPAIR_ENTRY))
        assert [(r.list_id, r.progress) for r in client.alliance.help_requests] == [(31, 3), (32, 0)]

        client._on_packet(xt_packet("ahd", {"LID": 31}))
        assert [r.list_id for r in client.alliance.help_requests] == [32]

        client._on_packet(xt_packet("ahf", {"PN": "LeaderGuy", "LID": 32, "WID": 101}))
        assert [type(u).__name__ for u in seen] == [
            "AllianceHelpListResponse",
            "AllianceHelpRequestChanged",
            "AllianceHelpRequestChanged",
            "AllianceHelpRequestRemoved",
            "AllianceHelpReceived",
        ]
        assert seen[-1].building_wod_id == 101

    def test_a_removed_callback_hears_nothing(self):
        client = make_client()
        seen: list[Any] = []
        client.alliance.on_help_update(seen.append)
        client.alliance.remove_help_update_callback(seen.append)
        client.alliance.remove_help_update_callback(seen.append)

        client._on_packet(xt_packet("ahd", {"LID": 1}))

        assert seen == []

    def test_get_help_requests_sends_an_empty_ahl(self):
        client = make_client({"ahl": xt_packet("ahl", {"AHL": [REPAIR_ENTRY], "TSL": 600})})

        reply = client.alliance.get_help_requests()

        assert conn(client).request_payloads == [("ahl", {})]
        assert [r.list_id for r in reply.requests] == [32]
        assert reply.repair_help_cooldown_seconds == 10200


class TestAllianceBookmarks:
    def test_bookmarks_expose_their_positions(self):
        payload = {"ABL": [{"N": "Enemy cluster", "OI": {"OID": 4242, "AP": [[0, 1, 640, 655, 1]]}}, {"N": "Plot"}]}
        client = make_client({"gbl": xt_packet("gbl", payload)})

        bookmarks = client.alliance.get_bookmarks()

        assert [b.name for b in bookmarks] == ["Enemy cluster", "Plot"]
        assert bookmarks[0].owner is not None
        assert bookmarks[0].owner.owner_id == 4242
        assert [(p.area_id, p.x, p.y, p.area_type) for p in bookmarks[0].owner.castle_positions] == [(1, 640, 655, 1)]
        assert bookmarks[1].owner is None
