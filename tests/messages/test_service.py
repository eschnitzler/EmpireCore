"""Tests for the messages service: payloads as the client's mail VOs build them."""

from __future__ import annotations

import pytest

from empire_core.exceptions import CommandError, MessageUnavailableError
from empire_core.messages.models import DeleteMessagesResponse
from tests.messages.battle_log_payloads import BLD, BLM, BLS, LOG_ID, MAILBOX_ROW, MESSAGE_ID
from tests.service_helpers import conn, make_client, request_payload, xt_packet

ROW = [501, 1, "Hello", "Sender", 4242, 30, 0, 0, 0]


class TestMailbox:
    def test_rows_merge_by_message_id(self):
        client = make_client()
        seen: list = []
        client.messages.on_new_messages(seen.append)

        client._on_packet(xt_packet("sne", {"MSG": [ROW, [502, 6, "0+1", "", -1, 5, 0, 0, 0]]}))
        client._on_packet(xt_packet("sne", {"MSG": [[501, 1, "Hello", "Sender", 4242, 40, 1, 0, 0]]}))

        assert [(m.message_id, m.is_read) for m in client.messages.mailbox] == [(501, True), (502, False)]
        assert len(seen) == 2

    def test_deleted_and_archived_answers_update_it(self):
        client = make_client()
        client._on_packet(xt_packet("sne", {"MSG": [ROW, [502, 1, "x", "", 1, 5, 0, 0, 0]]}))

        client._on_packet(xt_packet("ams", {"MID": 502}))
        client._on_packet(xt_packet("dms", {"MID": [501]}))

        assert [(m.message_id, m.is_archived) for m in client.messages.mailbox] == [(502, True)]

    def test_the_login_data_fills_it(self):
        client = make_client()
        seen: list = []
        client.messages.on_new_messages(seen.append)
        gbd = {"gcu": {"C1": 10, "C2": 0}, "sne": {"MSG": [ROW, [502, 6, "0+1", "", -1, 5, 0, 0, 0]]}, "mcd": {}}

        client._on_packet(xt_packet("gbd", gbd))

        assert [m.message_id for m in client.messages.mailbox] == [501, 502]
        assert len(seen) == 1

    def test_pushes_after_the_login_data_merge_into_it(self):
        client = make_client()
        client._on_packet(xt_packet("gbd", {"sne": {"MSG": [ROW]}}))
        client._on_packet(xt_packet("sne", {"MSG": [[501, 1, "Hello", "Sender", 4242, 40, 1, 0, 0]]}))

        assert [(m.message_id, m.is_read) for m in client.messages.mailbox] == [(501, True)]

    def test_a_relogin_refills_it_after_the_reset(self):
        client = make_client()
        client._on_packet(xt_packet("gbd", {"sne": {"MSG": [ROW]}}))
        client.messages._reset()
        assert client.messages.mailbox == []

        client._on_packet(xt_packet("gbd", {"sne": {"MSG": [ROW]}}))

        assert [m.message_id for m in client.messages.mailbox] == [501]

    @pytest.mark.parametrize(("gbd", "error_code"), [({"sne": {"MSG": [ROW]}}, 1), ({"gcu": {"C1": 1}}, 0)])
    def test_a_failed_or_sne_less_login_data_leaves_it(self, gbd, error_code):
        client = make_client()
        client._on_packet(xt_packet("gbd", gbd, error_code=error_code))
        assert client.messages.mailbox == []

    def test_a_removed_callback_hears_nothing(self):
        client = make_client()
        seen: list = []
        client.messages.on_new_messages(seen.append)
        client.messages.on_new_messages.remove(seen.append)
        client.messages.on_new_messages.remove(seen.append)

        client._on_packet(xt_packet("sne", {"MSG": [ROW]}))

        assert seen == []


class TestMail:
    def test_read(self):
        client = make_client(
            {
                "rms": xt_packet(
                    "rms", {"MTXT": "Hi &quot;you&quot;<br />bye", "ABI": {"KID": 1, "X": 5, "Y": 6, "BID": 9}}
                )
            }
        )

        reply = client.messages.read(501)

        assert conn(client).request_payloads == [("rms", {"MID": 501})]
        assert reply.decoded_body == 'Hi "you"\nbye'
        assert reply.bookmark is not None and (reply.bookmark.x, reply.bookmark.bookmark_id) == (5, 9)

    @pytest.mark.parametrize("code", [66, 225])
    def test_a_missing_or_old_message_is_unavailable(self, code):
        client = make_client({"rms": xt_packet("rms", error_code=code)})
        with pytest.raises(MessageUnavailableError) as raised:
            client.messages.read(501)
        assert raised.value.code == code

    def test_other_read_errors_stay_command_errors(self):
        client = make_client({"rms": xt_packet("rms", error_code=21)})
        with pytest.raises(CommandError) as raised:
            client.messages.read(501)
        assert not isinstance(raised.value, MessageUnavailableError)

    def test_mark_read_does_not_wait_and_marks_the_copy(self):
        client = make_client()
        client._on_packet(xt_packet("sne", {"MSG": [ROW]}))

        client.messages.mark_read(501)

        assert [request_payload(p) for p in conn(client).sent] == [{"MID": 501}]
        assert conn(client).requested == []
        assert client.messages.mailbox[0].is_read is True

    def test_archive(self):
        client = make_client({"ams": xt_packet("ams", {"MID": 501})})
        assert client.messages.archive(501).message_id == 501
        assert conn(client).request_payloads == [("ams", {"MID": 501})]

    def test_delete_one(self):
        client = make_client({"dms": xt_packet("dms", {"MID": 501})})
        assert client.messages.delete(501) == [501]
        assert conn(client).request_payloads == [("dms", {"MID": 501})]

    def test_delete_many(self):
        client = make_client({"dms": xt_packet("dms", {"MID": [501, 502]})})
        assert client.messages.delete_many([501, 502]) == [501, 502]
        assert conn(client).request_payloads == [("dms", {"MIDS": [501, 502]})]

    @pytest.mark.parametrize(("mid", "ids"), [(7, [7]), ([7, 8], [7, 8]), (None, [])])
    def test_a_delete_answer_reads_one_id_or_many(self, mid, ids):
        assert DeleteMessagesResponse.model_validate({"MID": mid}).message_ids == ids

    def test_send_encodes_subject_and_text_but_not_the_receiver(self):
        client = make_client()

        client.messages.send_message("Receiver", "Hi 100%", 'Say "go"\nnow')

        (sent,) = conn(client).request_payloads
        assert sent == ("sms", {"RN": "Receiver", "MH": "Hi 100&percnt;", "TXT": "Say &quot;go&quot;<br />now"})
        assert list(sent[1]) == ["RN", "MH", "TXT"]

    @pytest.mark.parametrize(
        ("receiver", "subject", "text"),
        [
            ("", "s", "hello"),
            ("r", "x" * 21, "hello"),
            ("r", "s", "x" * 1301),
            ("r", "s", " a b  "),
            ("r", "s", "   "),
        ],
    )
    def test_the_client_limits_are_checked_first(self, receiver, subject, text):
        client = make_client()
        with pytest.raises(ValueError):
            client.messages.send_message(receiver, subject, text)
        assert conn(client).request_payloads == []

    def test_a_refused_message_raises(self):
        client = make_client({"sms": xt_packet("sms", error_code=68)})
        with pytest.raises(CommandError):
            client.messages.send_message("Nobody", "s", "hello")


class TestReviewFollowUps:
    def test_a_dropped_session_empties_the_mailbox(self):
        client = make_client()
        client._on_packet(xt_packet("sne", {"MSG": [ROW]}))

        client._session.dropped(conn(client).generation)

        assert client.messages.mailbox == []

    def test_a_late_drop_report_keeps_the_mailbox(self):
        client = make_client()
        client._on_packet(xt_packet("sne", {"MSG": [ROW]}))

        client._session.dropped(conn(client).generation - 1)

        assert len(client.messages.mailbox) == 1

    def test_one_bad_delete_id_costs_only_itself(self):
        reply = DeleteMessagesResponse.model_validate({"MID": [7, "8", "x", 9.5, None, True]})
        assert reply.message_ids == [7, 8]

    def test_a_row_with_an_unreadable_age_is_kept(self):
        client = make_client()
        client._on_packet(xt_packet("sne", {"MSG": [[501, 1, "Hi", "S", 1, "soon", 0, 0, 0]]}))
        (message,) = client.messages.mailbox
        assert message.seconds_since_sent is None


class TestBattleReports:
    def test_short_only(self):
        client = make_client({"bls": xt_packet("bls", BLS)})

        report = client.messages.get_battle_report(MESSAGE_ID)

        assert conn(client).request_payloads == [("bls", {"MID": MESSAGE_ID, "IM": 0})]
        assert report.short.log_id == LOG_ID
        assert (report.middle, report.detail) == (None, None)

    def test_middle_is_asked_for_by_the_log_id(self):
        client = make_client({"bls": xt_packet("bls", BLS), "blm": xt_packet("blm", BLM)})

        report = client.messages.get_battle_report(MESSAGE_ID, detail="middle")

        assert conn(client).request_payloads == [("bls", {"MID": MESSAGE_ID, "IM": 0}), ("blm", {"LID": LOG_ID})]
        assert report.middle is not None and len(report.middle.waves) == 1
        assert report.detail is None

    def test_full_asks_for_each_log_with_im_0(self):
        # The client only ever sends IM 0 (CastleMessageData.getBattleLogShort), then blm and bld by LID
        script = {"bls": xt_packet("bls", BLS), "blm": xt_packet("blm", BLM), "bld": xt_packet("bld", BLD)}
        client = make_client(script)

        report = client.messages.get_battle_report(MESSAGE_ID, detail="full")

        assert conn(client).request_payloads == [
            ("bls", {"MID": MESSAGE_ID, "IM": 0}),
            ("blm", {"LID": LOG_ID}),
            ("bld", {"LID": LOG_ID}),
        ]
        assert report.middle is not None and report.middle.log_id == LOG_ID
        assert report.detail is not None and len(report.detail.waves) == 1

    @pytest.mark.parametrize("code", [66, 225])
    def test_a_missing_or_old_log_is_unavailable(self, code):
        client = make_client({"bls": xt_packet("bls", error_code=code)})
        with pytest.raises(MessageUnavailableError) as raised:
            client.messages.get_battle_report(MESSAGE_ID, detail="full")
        assert raised.value.code == code

    def test_a_middle_log_error_stays_a_command_error(self):
        client = make_client({"bls": xt_packet("bls", BLS), "blm": xt_packet("blm", error_code=66)})
        with pytest.raises(CommandError) as raised:
            client.messages.get_battle_report(MESSAGE_ID, detail="middle")
        assert not isinstance(raised.value, MessageUnavailableError)

    def test_an_unknown_detail_is_refused(self):
        client = make_client()
        with pytest.raises(ValueError):
            client.messages.get_battle_report(MESSAGE_ID, detail="everything")  # type: ignore[arg-type]
        assert conn(client).request_payloads == []

    def test_battle_logs_are_found_in_the_mailbox(self):
        client = make_client()
        client._on_packet(xt_packet("sne", {"MSG": [ROW, MAILBOX_ROW]}))
        assert [m.message_id for m in client.messages.mailbox if m.is_battle_log] == [MESSAGE_ID]

    def test_forward(self):
        client = make_client({"mfb": xt_packet("mfb")})

        client.messages.forward_battle_report(MESSAGE_ID, [7, 8])

        assert conn(client).request_payloads == [("mfb", {"MID": MESSAGE_ID, "PID": [7, 8]})]

    def test_a_refused_forward_raises(self):
        client = make_client({"mfb": xt_packet("mfb", error_code=21)})
        with pytest.raises(CommandError):
            client.messages.forward_battle_report(MESSAGE_ID, [7])

    def test_a_forward_needs_a_recipient(self):
        client = make_client()
        with pytest.raises(ValueError):
            client.messages.forward_battle_report(MESSAGE_ID, [])
        assert conn(client).sent == []
