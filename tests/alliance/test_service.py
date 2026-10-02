"""Tests for the alliance service."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from empire_core.alliance.models.diplomacy import AllianceDonation
from empire_core.alliance.models.search import GetBookmarksResponse
from empire_core.enums import AllianceRank, BookmarkType, DiplomacyStatus, Kingdom
from empire_core.exceptions import AmbiguousCastleError, CommandError, UnknownCastleError
from empire_core.protocol.models import AllianceChatMessageResponse, AllianceMember, HelpType
from tests.service_helpers import StubPlayer, StubState, conn, make_client, request_payload, xt_packet

# =============================================================================
# Golden payloads (shapes captured from the live server)
# =============================================================================

GOLDEN_AIN: dict[str, Any] = {
    "A": {
        "AID": 301,
        "N": "Test Alliance",
        "A": "PACT",
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
                "AID": 301,
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
                "AID": 301,
                "MP": 900000,
                "RPT": 7200,
                "AP": [[0, 12346, 641, 656, 1]],
            },
            {"OID": 7003, "N": "AfkDude", "L": 55, "AR": 8, "AID": 301, "MP": 100, "AP": []},
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

        members = client.alliance.get_members(301)

        assert [m.name for m in members] == ["LeaderGuy", "OfficerGal", "AfkDude"]
        assert conn(client).request_payloads == [("ain", {"AID": 301})]

    def test_activity_tiers_come_from_the_ami_array(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})

        by_name = {m.name: m for m in client.alliance.get_members(301)}

        assert by_name["LeaderGuy"].activity_tier == 0
        assert by_name["LeaderGuy"].is_online is True
        assert by_name["OfficerGal"].activity_tier == 2
        assert by_name["OfficerGal"].is_online is False
        assert by_name["AfkDude"].activity_tier == 4

    def test_online_members_are_filtered(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})
        online = client.alliance.get_online_members(301)
        assert [m.name for m in online] == ["LeaderGuy"]

    def test_member_profile_fields_survive_the_round_trip(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})
        by_name = {m.name: m for m in client.alliance.get_members(301)}

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
        by_name = {m.name: m for m in client.alliance.get_members(301)}

        castles = by_name["LeaderGuy"].castle_positions
        assert [(c.kingdom_id, c.x, c.y, c.area_type) for c in castles] == [
            (0, 640, 655, 1),
            (2, 300, 400, 4),
        ]
        assert by_name["AfkDude"].castle_positions == []

    def test_typed_emblem_is_parsed(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})
        leader = client.alliance.get_members(301)[0]
        assert leader.emblem is not None
        assert leader.emblem.background_type == 1
        assert leader.emblem.symbol1 == 4

    def test_members_are_cached_and_handed_out_as_a_copy(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})
        client.alliance.get_members(301)

        cached = client.alliance.cached_members
        assert set(cached) == {7001, 7002, 7003}
        cached.clear()
        assert set(client.alliance.cached_members) == {7001, 7002, 7003}

    def test_get_member_reads_the_cache_without_a_request(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})
        client.alliance.get_members(301)
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
        client.alliance.get_members(301)
        conn(client).request_payloads.clear()

        client.alliance.get_member(7001, no_cache=True)

        assert conn(client).request_payloads == [("ain", {"AID": 301})]

    def test_get_member_no_cache_falls_back_to_the_local_alliance(self):
        state = StubState(local_player=StubPlayer(alliance_id=301))
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)}, state=state)

        member = client.alliance.get_member(7001, no_cache=True)

        assert conn(client).request_payloads == [("ain", {"AID": 301})]
        assert member is not None

    def test_unknown_member_is_none(self):
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)})
        client.alliance.get_members(301)
        assert client.alliance.get_member(424242) is None


class TestAllianceLocalHelpers:
    def test_local_alliance_id_comes_from_state(self):
        client = make_client(state=StubState(local_player=StubPlayer(alliance_id=301)))
        assert client.alliance.local_alliance_id == 301

    def test_local_alliance_id_is_none_without_a_local_player(self):
        client = make_client(state=StubState(local_player=None))
        assert client.alliance.local_alliance_id is None

    def test_local_members_without_an_alliance_sends_nothing(self):
        client = make_client(state=StubState(local_player=StubPlayer(alliance_id=None)))  # type: ignore[arg-type]
        assert client.alliance.get_local_members() == []
        assert conn(client).requested == []

    def test_local_members_uses_the_local_alliance_id(self):
        state = StubState(local_player=StubPlayer(alliance_id=301))
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)}, state=state)

        members = client.alliance.get_local_members()

        assert len(members) == 3
        assert conn(client).request_payloads == [("ain", {"AID": 301})]

    def test_local_online_members_filters(self):
        state = StubState(local_player=StubPlayer(alliance_id=301))
        client = make_client({"ain": xt_packet("ain", GOLDEN_AIN)}, state=state)
        assert [m.name for m in client.alliance.get_local_online_members()] == ["LeaderGuy"]

    def test_local_online_members_without_an_alliance_is_empty(self):
        client = make_client(state=StubState(local_player=None))
        assert client.alliance.get_local_online_members() == []
        assert conn(client).requested == []

    def test_chronicle(self):
        reply = {"AID": 301, "AL": [{"PID": 1, "PN": "First", "MA": 90, "A": 0, "AV": []}, {"PID": 2, "PN": "Last"}]}
        client = make_client({"all": xt_packet("all", reply)})

        actions = client.alliance.get_chronicle()

        assert conn(client).request_payloads == [("all", {})]
        assert [a.player_name for a in actions] == ["Last", "First"]

    def test_chronicle_without_an_alliance_raises(self):
        client = make_client({"all": xt_packet("all", error_code=114)})
        with pytest.raises(CommandError) as exc_info:
            client.alliance.get_chronicle()
        assert exc_info.value.code == 114

    def test_subscriber_count(self):
        client = make_client({"asc": xt_packet("asc", {"ASC": 12})})

        assert client.alliance.get_subscriber_count() == 12
        assert conn(client).request_payloads == [("asc", {})]


class TestAllianceSearch:
    GOLDEN_HGH: dict[str, Any] = {"L": [[1, 4213377, [301, "Test Alliance", 47, 1520300]]]}

    def test_search_parses_positional_results(self):
        client = make_client({"hgh": xt_packet("hgh", self.GOLDEN_HGH)})

        results = client.alliance.search_alliances("PACT")

        assert len(results) == 1
        assert results[0].alliance_id == 301
        assert results[0].name == "Test Alliance"
        assert results[0].member_count == 47
        assert (results[0].rank, results[0].score, results[0].fame_points) == (1, 4213377, 1520300)

    def test_search_sends_the_search_term(self):
        client = make_client({"hgh": xt_packet("hgh", self.GOLDEN_HGH)})
        client.alliance.search_alliances("PACT")
        command, payload = conn(client).request_payloads[0]
        assert command == "hgh"
        assert payload["SV"] == "PACT"

    def test_nothing_found_is_an_empty_result_not_an_error(self):
        # 114 is the server's "no match", which is a legitimate empty answer.
        client = make_client({"hgh": xt_packet("hgh", error_code=114)})
        assert client.alliance.search_alliances("nope") == []

    def test_other_error_codes_raise(self):
        client = make_client({"hgh": xt_packet("hgh", error_code=21)})
        with pytest.raises(CommandError) as exc_info:
            client.alliance.search_alliances("PACT")
        assert exc_info.value.code == 21

    def test_array_payload_is_an_empty_result(self):
        client = make_client({"hgh": xt_packet("hgh", [1, 2, 3])})
        assert client.alliance.search_alliances("PACT") == []

    def test_a_row_without_an_alliance_keeps_its_defaults(self):
        client = make_client({"hgh": xt_packet("hgh", {"L": [[1, 2], [1, 2, "not-a-list"]]})})
        results = client.alliance.search_alliances("PACT")
        assert [(r.rank, r.score, r.name) for r in results] == [(1, 2, ""), (1, 2, "")]

    def test_a_list_that_is_not_a_list_is_an_empty_result(self):
        client = make_client({"hgh": xt_packet("hgh", {"L": "junk"})})
        assert client.alliance.search_alliances("PACT") == []

    def test_a_row_that_is_not_a_list_is_skipped_not_fatal(self, caplog):
        payload = {"L": [[1, 2, ["x", "y"]], self.GOLDEN_HGH["L"][0], 5]}
        client = make_client({"hgh": xt_packet("hgh", payload)})

        with caplog.at_level(logging.WARNING, logger="empire_core.alliance.models.info"):
            results = client.alliance.search_alliances("PACT")

        assert [(r.alliance_id, r.name) for r in results] == [(0, "y"), (301, "Test Alliance")]
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

    def test_the_login_data_fills_the_help_list(self):
        client = make_client()
        seen: list[Any] = []
        client.alliance.on_help_update(seen.append)
        gbd = {"gcu": {"C1": 10, "C2": 0}, "ahl": {"AHL": [REPAIR_ENTRY, HEAL_ENTRY], "TSL": 600}, "ain": {}}

        client._on_packet(xt_packet("gbd", gbd))

        assert [r.list_id for r in client.alliance.help_requests] == [32, 31]
        assert [type(u).__name__ for u in seen] == ["AllianceHelpListResponse"]
        assert seen[0].repair_help_cooldown_seconds == 10200
        assert conn(client).sent == []

    def test_a_relogin_replaces_the_help_list(self):
        client = make_client()
        client._on_packet(xt_packet("gbd", {"ahl": {"AHL": [HEAL_ENTRY], "TSL": -1}}))

        client._on_packet(xt_packet("gbd", {"ahl": {"AHL": [REPAIR_ENTRY], "TSL": -1}}))

        assert [r.list_id for r in client.alliance.help_requests] == [32]

    @pytest.mark.parametrize("gbd", [{"gcu": {"C1": 1}}, {"ahl": None}])
    def test_login_data_without_a_help_list_keeps_it(self, gbd):
        client = make_client()
        client._on_packet(xt_packet("ahl", {"AHL": [HEAL_ENTRY], "TSL": -1}))

        client._on_packet(xt_packet("gbd", gbd))

        assert [r.list_id for r in client.alliance.help_requests] == [31]


class TestAllianceBookmarks:
    """As CastleBookmarkData.parse_GBL (bundle line 33453) and CastleWorldmapBookmarkVO.parseParamObject read them."""

    GBL: dict[str, Any] = {
        "BL": [
            {
                "KID": 0,
                "X": 640,
                "Y": 655,
                "AI": [1, 640, 655, 12345, 4242, 3],
                "OI": {"OID": 4242, "N": "TargetPlayer", "AID": -1},
                "N": "Farm",
                "TY": 0,
                "BID": 11,
            }
        ],
        "ABL": [
            {"K": 2, "X": 300, "Y": 400, "N": "Hit this", "TY": 4, "BID": 12, "C": 7001, "M": [7001, 7002], "TI": 900},
            {"KID": 1, "X": 5, "Y": 6, "N": "Hold", "TY": "3", "BID": 13, "C": 0, "M": [7001]},
        ],
    }

    def test_both_lists_are_read(self):
        client = make_client({"gbl": xt_packet("gbl", self.GBL)})

        reply = client.alliance.get_bookmarks()

        assert conn(client).request_payloads == [("gbl", {})]
        (own,) = reply.own_bookmarks
        assert (own.kingdom, own.x, own.y, own.name, own.bookmark_id) == (0, 640, 655, "Farm", 11)
        assert own.bookmark_type_enum is BookmarkType.PLAYER_ENEMY
        assert own.area is not None and (own.area.item_type, own.area.owner_id) == (1, 4242)
        assert own.owner is not None and own.owner.player_id == 4242
        assert (own.creator_id, own.attack_order) == (0, None)

    def test_an_attack_order_carries_its_attackers(self):
        order, defend = GetBookmarksResponse.model_validate(self.GBL).alliance_bookmarks
        assert (order.kingdom, order.creator_id, order.bookmark_type_enum) == (
            2,
            7001,
            BookmarkType.ALLIANCE_ATTACK_ORDER,
        )
        assert order.attack_order is not None
        assert (order.attack_order.assigned_attacker_ids, order.attack_order.attack_in_seconds) == ([7001, 7002], 900)
        # No creator: the client reads neither C nor the attack order
        assert (defend.kingdom, defend.bookmark_type, defend.creator_id, defend.attack_order) == (1, 3, 0, None)
        assert (order.area, order.owner) == (None, None)

    def test_a_bookmark_that_is_not_an_object_is_skipped(self):
        reply = GetBookmarksResponse.model_validate({"ABL": [None, 5, {"N": "ok"}]})
        assert [b.name for b in reply.alliance_bookmarks] == ["ok"]

    def test_an_owner_record_without_an_oid_is_no_owner(self):
        reply = GetBookmarksResponse.model_validate({"BL": [{"OI": {"N": "x"}}, {"OI": {"OID": 0}}]})
        assert [b.owner for b in reply.own_bookmarks] == [None, None]


class TestAllianceMemberManagement:
    """Payloads as the C2SAlliance*VO constructors build them (bundle lines 70354-70364, 42819, 70138, 70244, 69639)."""

    def test_kick_member(self):
        client = make_client({"akm": xt_packet("akm", {"ain": GOLDEN_AIN})})

        alliance = client.alliance.kick_member(7003)

        assert conn(client).request_payloads == [("akm", {"PID": 7003})]
        assert alliance is not None and alliance.alliance_id == 301

    def test_set_rank(self):
        client = make_client({"arm": xt_packet("arm", {"ain": GOLDEN_AIN})})

        alliance = client.alliance.set_rank(7002, AllianceRank.GENERAL)

        (sent,) = conn(client).request_payloads
        assert sent == ("arm", {"PID": 7002, "R": 6})
        assert list(sent[1]) == ["PID", "R"]
        assert alliance is not None

    def test_an_unchanged_rank_is_not_an_error(self):
        client = make_client({"arm": xt_packet("arm", error_code=15)})
        assert client.alliance.set_rank(7002, AllianceRank.GENERAL) is None

    def test_other_rank_errors_raise(self):
        client = make_client({"arm": xt_packet("arm", error_code=110)})
        with pytest.raises(CommandError):
            client.alliance.set_rank(7002, AllianceRank.GENERAL)

    def test_invite_sends_the_player_id_as_a_string(self):
        client = make_client()

        assert client.alliance.invite(4242) is True

        assert conn(client).request_payloads == [("aip", {"SV": "4242"})]

    def test_an_invitation_to_no_such_player_is_false(self):
        client = make_client({"aip": xt_packet("aip", error_code=65)})
        assert client.alliance.invite(4242) is False

    def test_applications(self):
        reply = {
            "OI": [{"OID": 4242, "N": "Applicant", "L": 30}, {"OID": 4243, "N": "Other"}],
            "AL": [
                {"PID": 4243, "D": 90, "AT": "let me in", "AA": 60},
                {"PID": 4242, "D": 12, "AT": "100&percnt; active", "AA": 3600},
            ],
        }
        client = make_client({"aal": xt_packet("aal", reply)})

        applications = client.alliance.get_applications()

        assert conn(client).request_payloads == [("aal", {})]
        nearest = applications.applications[0]
        assert (nearest.player_id, nearest.distance, nearest.text, nearest.seconds_since_applied) == (
            4242,
            12,
            "100% active",
            3600,
        )
        owner = applications.owner_of(nearest)
        assert owner is not None and owner.name == "Applicant"

    @pytest.mark.parametrize(("accept", "answer"), [(True, 1), (False, 0)])
    def test_answer_application(self, accept, answer):
        client = make_client()

        assert client.alliance.answer_application(4242, accept) is True

        (sent,) = conn(client).request_payloads
        assert sent == ("aaa", {"PID": 4242, "A": answer})
        assert list(sent[1]) == ["PID", "A"]

    def test_leave(self):
        client = make_client()

        assert client.alliance.leave() is True

        assert conn(client).request_payloads == [("aqi", {})]


class TestAllianceDiplomacy:
    """Payloads as C2SAllianceChangeDiplomacyVO, C2SAllianceRefuseDiplomacyVO, C2SSetAutoWar,
    C2SAllianceNewsletterVO and C2SAllianceDonateVO build them."""

    def test_change_diplomacy_always_sends_a_tribute(self):
        reply = {"ODR": 0, "NDR": 1, "S": 2, "AS": GOLDEN_AIN["A"], "AO": {"AID": 55, "N": "Other"}}
        client = make_client({"adp": xt_packet("adp", reply)})

        response = client.alliance.change_diplomacy(55, DiplomacyStatus.NEUTRAL)

        (sent,) = conn(client).request_payloads
        assert sent == ("adp", {"AID": 55, "NDR": 1, "T": 0})
        assert list(sent[1]) == ["AID", "NDR", "T"]
        assert (response.old_status, response.new_status, response.request_status) == (0, 1, 2)
        assert response.own_alliance is not None and response.own_alliance.alliance_id == 301
        assert response.other_alliance is not None and response.other_alliance.name == "Other"

    def test_accepting_a_demanded_peace_offer_sends_its_negative_tribute(self):
        client = make_client()
        client.alliance.change_diplomacy(55, DiplomacyStatus.NEUTRAL, tribute=-25)
        assert conn(client).request_payloads == [("adp", {"AID": 55, "NDR": 1, "T": -25})]

    def test_refuse_diplomacy(self):
        client = make_client({"ard": xt_packet("ard", {"A": {"AID": 55, "N": "Other"}})})

        alliance = client.alliance.refuse_diplomacy(55)

        assert conn(client).request_payloads == [("ard", {"AID": 55})]
        assert alliance is not None and alliance.alliance_id == 55

    @pytest.mark.parametrize(("enabled", "aw"), [(True, 1), (False, 0)])
    def test_set_auto_war(self, enabled, aw):
        client = make_client({"saw": xt_packet("saw", {"AW": aw})})

        assert client.alliance.set_auto_war(enabled) is enabled

        assert conn(client).request_payloads == [("saw", {"AW": aw})]

    def test_newsletter_encodes_both_parts(self):
        client = make_client()

        assert client.alliance.send_newsletter("Plan 100%", 'Say "go"\nnow') is True

        (sent,) = conn(client).request_payloads
        assert sent == ("anl", {"SJ": "Plan 100&percnt;", "TXT": "Say &quot;go&quot;<br />now"})
        assert list(sent[1]) == ["SJ", "TXT"]

    def test_an_empty_newsletter_is_not_sent(self):
        client = make_client()
        with pytest.raises(ValueError):
            client.alliance.send_newsletter("Subject", "")
        assert conn(client).request_payloads == []

    def test_donate_sends_the_castle_and_only_amounts_above_zero(self):
        reply = {"gcu": {"C1": 900, "C2": 10}, "grc": {"W": 1}, "ain": GOLDEN_AIN}
        client = make_client({"ado": xt_packet("ado", reply)}, castles=[(12345, Kingdom.ICE)])

        response = client.alliance.donate(12345, AllianceDonation(wood=500, coins=100, rift_coins=2))

        (sent,) = conn(client).request_payloads
        assert sent == ("ado", {"AID": 12345, "KID": 2, "RV": {"W": 500, "C1": 100, "RC": 2}})
        assert list(sent[1]) == ["AID", "KID", "RV"]
        assert response.currency is not None and response.currency.coins == 900
        assert response.alliance is not None and response.alliance.alliance_id == 301

    def test_an_empty_donation_is_not_sent(self):
        client = make_client(castles=[(12345, Kingdom.GREEN)])
        with pytest.raises(ValueError):
            client.alliance.donate(12345, AllianceDonation())
        assert conn(client).request_payloads == []

    def test_a_donation_from_an_id_repeated_across_your_kingdoms_raises(self):
        client = make_client(castles=[(1, Kingdom.STORM), (1, Kingdom.BERIMOND)])

        with pytest.raises(AmbiguousCastleError):
            client.alliance.donate(1, AllianceDonation(wood=1))

        assert conn(client).request_payloads == []

    def test_a_donation_from_a_castle_not_in_the_castle_list_raises(self):
        client = make_client(castles=[(777, Kingdom.GREEN)])
        with pytest.raises(UnknownCastleError):
            client.alliance.donate(12345, AllianceDonation(wood=1))
        assert conn(client).request_payloads == []


class TestAllianceReviewFollowUps:
    def test_a_bookmark_name_that_is_not_text_keeps_the_bookmark(self):
        (bookmark,) = GetBookmarksResponse.model_validate({"BL": [{"N": 5, "X": 1}]}).own_bookmarks
        assert (bookmark.name, bookmark.x) == (None, 1)

    def test_leaving_empties_the_help_list(self):
        client = make_client()
        client._on_packet(xt_packet("ahl", {"AHL": [HEAL_ENTRY]}))

        assert client.alliance.leave() is True

        assert client.alliance.help_requests == []

    def test_a_refused_leave_keeps_the_help_list(self):
        client = make_client({"aqi": xt_packet("aqi", error_code=21)})
        client._on_packet(xt_packet("ahl", {"AHL": [HEAL_ENTRY]}))

        assert client.alliance.leave() is False

        assert [r.list_id for r in client.alliance.help_requests] == [31]
