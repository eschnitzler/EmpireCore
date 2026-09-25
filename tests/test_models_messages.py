"""The sne and bsd models, checked against payloads in the shape the client reads."""

from empire_core.protocol.models import BattleSpyDataResponse, MessageInfo, SystemNotificationEvent


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


class TestBattleSpyDataResponse:
    def test_report_as_the_client_reads_it(self):
        response = BattleSpyDataResponse.model_validate(
            {
                "MID": 9001,
                "S": [[[487, 100], [620, 3]], [], [[487, 5]], [], [], [], [[10, 1]]],
                "B": {"ID": 2, "WID": 1, "VIS": 4, "N": "", "W": 3, "D": 1, "SPR": 0, "AE": [[426, [10.0], "GE"]]},
                "AI": {"N": "Enemy Keep", "X": 700, "Y": 710, "K": 0, "AT": 1},
            }
        )
        assert response.spy_data[0] == [[487, 100], [620, 3]]
        assert response.spy_data[6] == [[10, 1]]
        castellan = response.defending_castellan
        assert castellan is not None
        assert (castellan.commander_id, castellan.wearer_id, castellan.picture_id) == (2, 1, 4)

    def test_non_array_pairs_are_skipped_like_the_client(self):
        response = BattleSpyDataResponse.model_validate({"S": [[[487, 100], "junk"], "junk"]})
        assert response.spy_data == [[[487, 100]], []]

    def test_pairs_are_read_through_int_like_the_client(self):
        response = BattleSpyDataResponse.model_validate({"S": [[[487, "100"], [488, "x"], [489]], [[490, 0]]]})
        assert response.spy_data == [[[487, 100]], []]

    def test_unreadable_castellan_keeps_the_report(self):
        response = BattleSpyDataResponse.model_validate({"S": [[[487, 100]]], "B": {"N": "no id"}})
        assert response.defending_castellan is None
        assert response.spy_data == [[[487, 100]]]
