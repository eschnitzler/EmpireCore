"""The sne and bsd models, checked against payloads in the shape the client reads."""

import copy

import pytest

from empire_core.enums import Kingdom, LogResult, MapItemType, MessageType, SpyLogType
from empire_core.messages.models import SPY_VALIDITY, SpyLogHeader, repair_header
from empire_core.protocol.base import parse_response
from empire_core.protocol.models import (
    ForwardSpyLogRequest,
    GetSpyReportRequest,
    MessageInfo,
    SpyReportResponse,
    SystemNotificationEvent,
)
from tests.spy.payloads import BSD_NPC_CAMP_REPORT


class TestSystemNotificationEvent:
    def test_message_row_as_the_client_reads_it(self):
        event = SystemNotificationEvent.model_validate(
            {"MSG": [[9001, 3, "1+0+4#0+16324240+Enemy Keep", "", -1, 42, 1, 0, "1"]]}
        )
        [message] = event.messages
        assert (message.message_id, message.message_type, message.sender_id) == (9001, 3, -1)
        assert message.header == "1+0+4#0+16324240+Enemy Keep"
        assert message.seconds_since_sent == 42
        assert (message.is_read, message.is_archived, message.is_forwarded) == (True, False, True)

    def test_short_row_keeps_the_defaults(self):
        message = MessageInfo.model_validate([7, 12, "x"])
        assert (message.sender_name, message.sender_id, message.is_read) == ("", -1, False)


class TestMailboxRows:
    """Rows as AMessageVO.loadFromParamArray (bundle line 3808) and CastleMessageFactory.parseMessage read them."""

    ROWS = [
        [501, 1, "Hello &quot;there&quot;<br />again", "Sender", 4242, 30, 0, 0, 0],
        [502, 22, "Plan [war]", "Leader", 7001, 60, 1, 1, 0],
        [503, 6, "0+1+2#3", "", -1, 90, 1, 0, 1],
        [504, 40, "Underworld", "", -1, 5, 0, 0, 0],
        [505, 999, "future type", "", -1, 5, 0, 0, 0],
    ]

    def test_types_and_subjects(self):
        messages = SystemNotificationEvent.model_validate({"MSG": self.ROWS}).messages
        assert [m.message_type_enum for m in messages] == [
            MessageType.USER_IN,
            MessageType.ALLIANCE_NEWSLETTER,
            MessageType.BATTLE_LOG,
            MessageType.LOWLEVEL_UNDERWORLD,
            None,
        ]
        # A type the factory has no case for reads as player mail, whose subject is the whole header
        assert [m.subject for m in messages] == ['Hello "there" again', "Plan  war ", None, "Underworld", "future type"]
        assert messages[0].decoded_header == 'Hello "there"\nagain'
        assert messages[2].header == "0+1+2#3"

    # Expectations printed by node running AMessageVO.repairSpecialCharacters and TextValide.parseChatJSONMessage
    @pytest.mark.parametrize(
        ("header", "repaired"),
        [
            ("100&perc...", "100%..."),
            ("Say &qu...", 'Say "...'),
            ("It&14...", "It'..."),
            ("line<br ...", "line..."),
            ("path %5...", "path \\..."),
            ("a&percnt;5C b", "a\\ b"),
            ("[tag] hi<br />there", " tag  hi\nthere"),
            ("x &p y ... z &q w ...", "x %..."),
            ("", ""),
            (None, ""),
        ],
    )
    def test_a_header_is_repaired_as_the_client_repairs_it(self, header, repaired):
        assert repair_header(header) == repaired


class TestSpyReportResponse:
    def test_report_as_the_client_reads_it(self):
        response = SpyReportResponse.model_validate(
            {
                "MID": 9001,
                "S": [[[487, 100], [620, 3]], [], [[487, 5]], [], [], [], [[10, 1]]],
                "B": {"ID": 2, "WID": 1, "VIS": 4, "N": "", "W": 3, "D": 1, "SPR": 0, "AE": [[426, [10.0], "GE"]]},
                "AI": {"N": "Enemy Keep", "X": 700, "Y": 710, "K": 0, "AT": 1},
                "LS": [7, 9],
            }
        )
        assert response.spy_data[0] == [[487, 100], [620, 3]]
        assert response.spy_data[6] == [[10, 1]]
        castellan = response.defending_castellan
        assert castellan is not None
        assert (castellan.commander_id, castellan.wearer_id, castellan.picture_id) == (2, 1, 4)

    def test_non_array_pairs_are_skipped_like_the_client(self):
        response = SpyReportResponse.model_validate({"S": [[[487, 100], "junk"], "junk"]})
        assert response.spy_data == [[[487, 100]], []]

    def test_pairs_are_read_through_int_like_the_client(self):
        response = SpyReportResponse.model_validate({"S": [[[487, "100"], [488, "x"], [489]], [[490, 0]]]})
        assert response.spy_data == [[[487, 100]], []]

    def test_unreadable_castellan_keeps_the_report(self):
        response = SpyReportResponse.model_validate({"S": [[[487, 100]]], "B": {"N": "no id"}})
        assert response.defending_castellan is None
        assert response.spy_data == [[[487, 100]]]

    def test_the_full_report_as_the_server_sends_it(self):
        report = SpyReportResponse.model_validate(BSD_NPC_CAMP_REPORT)

        assert (report.message_id, report.area_object_id, report.spy_owner_id, report.owner_id) == (
            9001,
            -1,
            1001,
            -211,
        )
        assert (report.spy_count, report.guard_count, report.accuracy_or_damage, report.risk) == (2, 0, 100, 26)
        assert report.seconds_since_spy == 0
        assert report.dungeon_cooldown_seconds == -3023358
        assert report.legend_skill_ids == []
        assert report.resources == []
        castellan = report.defending_castellan
        assert castellan is not None
        assert (castellan.commander_id, castellan.general_id) == (-21, 115)
        assert report.owner is not None
        assert (report.owner.owner_id, report.owner.is_dummy) == (-211, True)
        assert report.spy_owner is not None
        assert (report.spy_owner.owner_id, report.spy_owner.owner_name) == (1001, "Spy Player")
        area = report.area
        assert area is not None
        assert (area.area_type, area.x, area.y, area.kingdom) == (MapItemType.DUNGEON, 501, 297, Kingdom.GREEN)
        assert (area.owner_id, area.level, area.map_id, area.skin_id) == (-211, 2, -1, 0)
        assert (area.area_subtype, area.special_camp_id, area.name) == (0, -1, "")
        army = report.army()
        assert army is not None
        assert [stack.count for stack in army.left] == [1]
        assert report.is_fresh
        assert report.remaining_validity_seconds == SPY_VALIDITY

    def test_bsd_parses_to_the_spy_report(self):
        assert isinstance(parse_response("bsd", BSD_NPC_CAMP_REPORT), SpyReportResponse)

    def test_a_report_without_an_army_has_no_age(self):
        # parseArmyInfo sets the age to -1 for an empty S, so remainingSpyInfoTime is 0
        payload = {**BSD_NPC_CAMP_REPORT, "S": [], "AS": 120}
        report = SpyReportResponse.model_validate(payload)

        assert (report.seconds_since_spy, report.remaining_validity_seconds, report.is_fresh) == (-1, 0, False)
        assert report.army() is None

    def test_an_old_report_is_no_longer_fresh(self):
        report = SpyReportResponse.model_validate({**BSD_NPC_CAMP_REPORT, "AS": SPY_VALIDITY + 5})

        assert (report.remaining_validity_seconds, report.is_fresh) == (0, False)

    def test_the_top_level_daimyo_rank_goes_into_the_area(self):
        # Client: e.DAR&&(e.AI.DAR=e.DAR)
        payload = copy.deepcopy(BSD_NPC_CAMP_REPORT)
        payload["DAR"] = 3
        payload["AI"]["DDCID"] = 12

        area = SpyReportResponse.model_validate(payload).area

        assert area is not None
        assert (area.daimyo_rank, area.daimyo_camp_id) == (3, 12)

    def test_an_unreadable_area_costs_only_itself(self):
        payload = {**BSD_NPC_CAMP_REPORT, "AI": {"AT": "junk"}}

        report = SpyReportResponse.model_validate(payload)

        assert report.area is None
        assert report.spy_count == 2

    def test_an_owner_record_that_is_no_object_is_none(self):
        report = SpyReportResponse.model_validate({**BSD_NPC_CAMP_REPORT, "OI": [], "SO": 0})

        assert (report.owner, report.spy_owner) == (None, None)


class TestSpyReportRequests:
    def test_bsd_sends_the_message_id(self):
        assert GetSpyReportRequest(message_id=9001).to_payload() == {"MID": 9001}

    def test_mfs_sends_the_message_id_before_the_recipients(self):
        # C2SForwardSpyLogVO sets MID before PID
        payload = ForwardSpyLogRequest(player_ids=[111, 222], message_id=9001).to_payload()

        assert list(payload) == ["MID", "PID"]
        assert payload == {"MID": 9001, "PID": [111, 222]}


class TestSpyLogHeader:
    """Header layouts from MessageSpyPlayerVO / MessageSpyNpcVO.parseMessageHeader."""

    def test_an_npc_camp_log(self):
        header = MessageInfo.model_validate([9001, 4, "1+0+2#0+-211+", "", -1, 0, 0, 0, 0]).spy_log_header()

        assert header == SpyLogHeader(
            SpyLogType.DEFENCE, LogResult.ATTACKER_SUCCESS, 2, kingdom_id=0, owner_id=-211, area_name=""
        )
        assert header.has_army_report
        assert not header.spies_lost

    def test_a_player_castle_log(self):
        header = MessageInfo.model_validate([9001, 3, "2+2+1#1+1001+Enemy Keep"]).spy_log_header()

        assert header == SpyLogHeader(
            SpyLogType.ECO, LogResult.ATTACKER_FAILED, 1, kingdom_id=1, owner_id=1001, area_name="Enemy Keep"
        )
        assert header.spies_lost
        assert not header.has_army_report

    def test_the_header_is_read_decoded(self):
        header = MessageInfo.model_validate([9001, 3, "2+2+1#1+1001+100&percnt; &quot;Keep&quot;"]).spy_log_header()

        assert header is not None
        assert header.area_name == '100% "Keep"'

    @pytest.mark.parametrize("subtype", [SpyLogType.SABOTAGE, SpyLogType.PLAGUE_MONK])
    @pytest.mark.parametrize("result", [LogResult.ATTACKER_SUCCESS, LogResult.DEFENDER_FAILED])
    def test_a_sabotage_or_plague_success_names_the_area_by_name_and_id(self, subtype, result):
        header = MessageInfo.model_validate(
            [9001, 3, f"{int(subtype)}+{int(result)}+1#Enemy Keep+2001"]
        ).spy_log_header()

        assert header == SpyLogHeader(subtype, result, 1, area_name="Enemy Keep", area_id=2001)
        assert header.kingdom_id is None

    def test_a_caught_sabotage_keeps_the_kingdom_layout(self):
        header = MessageInfo.model_validate([9001, 3, "0+2+1#0+1001+Enemy Keep"]).spy_log_header()

        assert header is not None
        assert (header.kingdom_id, header.owner_id, header.area_name, header.area_id) == (0, 1001, "Enemy Keep", None)

    def test_an_npc_sabotage_success_keeps_the_kingdom_layout(self):
        # Only MessageSpyPlayerVO has the name+id layout
        header = MessageInfo.model_validate([9001, 4, "0+0+2#0+-211+"]).spy_log_header()

        assert header is not None
        assert (header.kingdom_id, header.owner_id) == (0, -211)

    @pytest.mark.parametrize(
        "row",
        [
            [9001, 1, "1+0+2#0+-211+"],  # not a spy log
            [9001, 68, "1+0+2#0+-211+"],  # a cancelled mission
            [9001, 3, "1+0+2"],  # nothing after '#'
        ],
    )
    def test_no_header_without_a_spy_log(self, row):
        assert MessageInfo.model_validate(row).spy_log_header() is None

    def test_an_unknown_subtype_is_none(self):
        header = MessageInfo.model_validate([9001, 4, "9+x+2#0+-211+"]).spy_log_header()

        assert header is not None
        assert (header.log_type, header.result, header.area_type) == (None, None, 2)
