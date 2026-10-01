"""Tests for the spy service."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from empire_core.client.client import EmpireClient
from empire_core.enums import Kingdom, SpyOutcome, SpyStep, SpyType
from empire_core.exceptions import CommandError, EmpireTimeoutError
from empire_core.protocol.packet import Packet
from empire_core.spy import service as spy_module
from tests.service_helpers import conn, make_client, xt_packet
from tests.spy.payloads import BSD_NPC_CAMP_REPORT, CSM_REPLY

NPC_REPORT_HEADER = "1+0+2#0+-211+"
"""A spy log header naming CSM_REPLY's target: a robber baron camp (area type 2) of owner -211 in kingdom 0."""


def csm_reply(x: int = 700, y: int = 710) -> dict[str, Any]:
    """The live csm reply, aimed at (x, y)."""
    reply = copy.deepcopy(CSM_REPLY)
    reply["A"]["M"]["TA"][1:3] = [x, y]
    return reply


def sne_packet(header: str = NPC_REPORT_HEADER, message_id: int = 9001, message_type: int = 4) -> Packet:
    return xt_packet("sne", {"MSG": [[message_id, message_type, header, "", -1, 0, 0, 0, 0]]})


def bsd_reply(message_id: int = 9001, x: int = 700, y: int = 710) -> Packet:
    return xt_packet(
        "bsd",
        {
            "MID": message_id,
            "S": [[[487, 100]], [], [], [], [], []],
            "B": {"ID": 2, "WID": 1, "VIS": 4, "N": "", "W": 3, "D": 1, "SPR": 0, "E": [[12, [5.0], "EQ"]]},
            "AI": {"N": "Enemy Keep", "AT": 2, "X": x, "Y": y, "K": 0},
        },
    )


def caught_bsd(message_id: int = 9001, x: int = 700, y: int = 710) -> Packet:
    """A caught mission's report: no army, but the spied area's position."""
    return xt_packet("bsd", {"MID": message_id, "AI": {"N": "", "AT": 2, "X": x, "Y": y, "K": 0}})


def spy_client(
    ssi: Any = None,
    csm: Any = None,
    sne: Any = None,
    bsd: Any = None,
) -> EmpireClient:
    """A client whose server answers the spy round trip; ``sne`` is what it pushes after csm."""
    script = {
        "ssi": ssi if ssi is not None else xt_packet("ssi", {"AS": 46, "GC": 0}),
        "csm": csm if csm is not None else xt_packet("csm", csm_reply()),
        "bsd": bsd if bsd is not None else bsd_reply(),
    }
    pushed = sne_packet() if sne is None else sne
    return make_client(script, pushes={"csm": pushed if isinstance(pushed, list) else [pushed]})


class TestSpySuccessPath:
    def test_successful_mission_returns_the_report(self, no_sleep):
        client = spy_client()

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True
        assert (result.outcome, result.step, result.error) == (SpyOutcome.SUCCESS, None, None)
        assert result.message_id == 9001
        report = result.report
        assert report is not None
        assert report.spy_data == [[[487, 100]], [], [], [], [], []]
        assert report.defending_castellan is not None
        assert (report.defending_castellan.commander_id, report.defending_castellan.wins) == (2, 3)
        assert report.area is not None
        assert report.area.name == "Enemy Keep"
        assert result.army is not None
        assert result.army.left[0].count == 100
        assert result.mission is not None
        assert result.mission.movement_id == 5001

    def test_only_the_spies_the_risk_budget_needs_are_sent(self, no_sleep):
        # Sending the whole pool bought nothing: 6 spies already reach the 5%
        # floor against an unguarded castle, and draining the pool made the next
        # mission wait for spies to walk home.
        client = spy_client(ssi=xt_packet("ssi", {"AS": 46, "GC": 0}))

        client.spy.execute_instant_spy(12345, 700, 710, target_kingdom=Kingdom.ICE)

        payloads = dict(conn(client).request_payloads)
        assert payloads["ssi"] == {"TX": 700, "TY": 710, "KID": 2}
        assert payloads["csm"]["SC"] == 6
        assert payloads["csm"]["SE"] == 100
        assert payloads["csm"]["PTT"] == 0
        assert payloads["csm"]["HBW"] == -1
        assert payloads["csm"]["SID"] == 12345
        assert payloads["bsd"] == {"MID": 9001}

    def test_a_loose_ceiling_does_not_buy_a_riskier_mission(self, no_sleep):
        client = spy_client(ssi=xt_packet("ssi", {"AS": 46, "GC": 0}))

        client.spy.execute_instant_spy(12345, 700, 710, risk_tolerance=90)

        assert dict(conn(client).request_payloads)["csm"]["SC"] == 6

    def test_a_guarded_target_costs_more_spies(self, no_sleep):
        client = spy_client(ssi=xt_packet("ssi", {"AS": 200, "GC": 60}))

        client.spy.execute_instant_spy(12345, 700, 710)

        assert dict(conn(client).request_payloads)["csm"]["SC"] > 6

    def test_a_target_over_the_risk_ceiling_is_not_spied(self, no_sleep):
        # One spy against a fully guarded castle stays over a 10% ceiling at
        # every accuracy the game allows, so there is no mission to send.
        client = spy_client(ssi=xt_packet("ssi", {"AS": 1, "GC": 180}))

        result = client.spy.execute_instant_spy(12345, 700, 710, risk_tolerance=10)

        assert result.success is False
        assert result.outcome is SpyOutcome.RISK_OVER_BUDGET
        assert "csm" not in dict(conn(client).request_payloads), "sent a mission over the ceiling"

    def test_a_thin_pool_still_spies_when_no_ceiling_is_set(self, no_sleep):
        client = spy_client(ssi=xt_packet("ssi", {"AS": 2, "GC": 0}))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True
        assert dict(conn(client).request_payloads)["csm"]["SC"] == 2

    def test_sne_is_subscribed_before_the_spy_is_sent(self, no_sleep):
        # sne arrives after csm; subscribing afterwards races the notification.
        client = spy_client()

        client.spy.execute_instant_spy(12345, 700, 710)

        events = conn(client).events
        assert events.index("subscribe:sne") < events.index("request:csm")

    def test_no_sne_waiter_is_taken_from_anyone_else(self, no_sleep):
        client = spy_client()

        client.spy.execute_instant_spy(12345, 700, 710)

        assert conn(client).waiters_created == []

    def test_the_subscription_is_dropped_on_success(self, no_sleep):
        client = spy_client()
        client.spy.execute_instant_spy(12345, 700, 710)
        assert conn(client).subscribers["sne"] == []


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
    """sne carries the mission outcome in the spy log's header.

    Format, from MessageSpyPlayerVO / MessageSpyNpcVO.parseMessageHeader and
    MessageConst in the client:
        subtypeSpy+subtypeResult+areaType#kingdomID+ownerID+areaName
    with ATTACKER_SUCCESS=0, DEFENDER_SUCCESS=1, ATTACKER_FAILED=2.
    """

    def test_a_caught_mission_is_reported_as_caught(self, no_sleep):
        client = spy_client(sne=sne_packet("1+2+2#0+-211+"), bsd=caught_bsd())

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.outcome is SpyOutcome.SPY_CAUGHT
        # A caught report's header is shared by sibling camps; its position decides
        assert conn(client).request_payloads[-1] == ("bsd", {"MID": 9001})

    def test_a_sibling_camps_caught_report_is_not_this_mission(self, no_sleep):
        # Another mission to a robber baron of the same owner was caught first
        client = spy_client(
            sne=[sne_packet("1+2+2#0+-211+", message_id=8000), sne_packet(message_id=9001)],
            bsd=[caught_bsd(8000, x=111, y=222), bsd_reply(9001)],
        )

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True
        assert result.message_id == 9001

    def test_only_a_sibling_camps_caught_report_is_a_mismatch(self, no_sleep):
        client = spy_client(sne=sne_packet("1+2+2#0+-211+", message_id=8000), bsd=caught_bsd(8000, x=111, y=222))

        result = client.spy.execute_instant_spy(12345, 700, 710, max_wait=0.05)

        assert result.outcome is SpyOutcome.REPORT_TARGET_MISMATCH

    def test_a_successful_defense_for_the_target_is_also_a_loss(self, no_sleep):
        client = spy_client(sne=sne_packet("1+1+2#0+-211+"), bsd=caught_bsd())

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.outcome is SpyOutcome.SPY_CAUGHT

    def test_a_successful_mission_still_reads_as_success(self, no_sleep):
        client = spy_client(sne=sne_packet("1+0+2#0+-211+"))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True

    def test_a_header_without_the_area_part_is_not_a_report(self, no_sleep):
        client = spy_client(sne=sne_packet("garbage"))

        result = client.spy.execute_instant_spy(12345, 700, 710, max_wait=0.01)

        assert result.success is False
        assert result.outcome is SpyOutcome.TIMEOUT
        assert "bsd" not in conn(client).requested


class TestOnlyThisMissionsReportCounts:
    """sne has no mission id; a report counts only when it names this mission's target."""

    def test_an_unrelated_sne_is_skipped_for_the_right_report(self, no_sleep):
        other_target = sne_packet("1+0+1#0+777+Someone Else", message_id=8000, message_type=3)
        client = spy_client(sne=[other_target, sne_packet()])

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True
        assert result.message_id == 9001
        assert conn(client).request_payloads[-1] == ("bsd", {"MID": 9001})

    def test_other_message_types_are_skipped(self, no_sleep):
        # 1 is not a spy log; 68 is a cancelled spy mission, which the client reads another way
        client = spy_client(sne=[sne_packet(message_type=1), sne_packet(message_type=68), sne_packet(message_id=9002)])

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.message_id == 9002

    def test_another_kingdom_is_not_this_target(self, no_sleep):
        client = spy_client(sne=sne_packet("1+0+2#2+-211+"))

        result = client.spy.execute_instant_spy(12345, 700, 710, max_wait=0.01)

        assert result.outcome is SpyOutcome.TIMEOUT

    def test_another_area_type_is_not_this_target(self, no_sleep):
        client = spy_client(sne=sne_packet("1+0+4#0+-211+"))

        result = client.spy.execute_instant_spy(12345, 700, 710, max_wait=0.01)

        assert result.outcome is SpyOutcome.TIMEOUT

    def test_a_castle_target_is_matched_by_owner_and_name(self, no_sleep):
        reply = csm_reply()
        reply["A"]["M"]["TA"] = [1, 700, 710, 2001, 1001, 2, 2, 2, 1, 0, "Spy Castle", 0, 0, -1, -1, -1, 0, 0, [], 0]
        reply["A"]["M"]["TID"] = 1001
        wrong_name = sne_packet("1+0+1#0+1001+Other Castle", message_id=8000, message_type=3)
        right = sne_packet("1+0+1#0+1001+Spy Castle", message_type=3)
        client = spy_client(csm=xt_packet("csm", reply), sne=[wrong_name, right])

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.message_id == 9001

    def test_a_report_for_another_position_keeps_the_wait_going(self, no_sleep):
        # Robber barons share an owner id, so only the report's position tells them apart
        client = spy_client(
            sne=[sne_packet(message_id=8000), sne_packet(message_id=9001)],
            bsd=[bsd_reply(8000, x=111, y=222), bsd_reply(9001)],
        )

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True
        assert result.message_id == 9001

    def test_an_empty_header_name_is_unknown_not_a_mismatch(self, no_sleep):
        reply = csm_reply()
        reply["A"]["M"]["TA"] = [1, 700, 710, 2001, 1001, 2, 2, 2, 1, 0, "Spy Castle", 0, 0, -1, -1, -1, 0, 0, [], 0]
        reply["A"]["M"]["TID"] = 1001
        client = spy_client(csm=xt_packet("csm", reply), sne=sne_packet("1+0+1#0+1001+", message_type=3))

        assert client.spy.execute_instant_spy(12345, 700, 710).success is True

    def test_the_payment_options_are_keyword_only(self, no_sleep):
        client = spy_client()
        call: Any = client.spy.execute_instant_spy

        with pytest.raises(TypeError):
            call(12345, 700, 710, Kingdom.GREEN, None, 100, 1010)

    def test_the_deadline_ends_the_wait(self, no_sleep):
        client = spy_client(sne=[])

        result = client.spy.execute_instant_spy(12345, 700, 710, max_wait=0.05)

        assert result.success is False
        assert result.outcome is SpyOutcome.TIMEOUT

    def test_a_disconnect_ends_the_wait(self, no_sleep, monkeypatch):
        monkeypatch.setattr(spy_module, "_POLL_SECONDS", 0.01)
        client = spy_client(sne=[])
        conn(client).connected = False

        result = client.spy.execute_instant_spy(12345, 700, 710, max_wait=5)

        assert result.outcome is SpyOutcome.DISCONNECTED


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
                    "N": "Requiem",
                    "X": 700,
                    "Y": 710,
                    "K": 1,
                    "AT": 12,
                    "KL": 5,
                    "WL": 4,
                    "GL": 3,
                    "TL": 2,
                    "ML": 1,
                },
            },
        )
        client = spy_client(bsd=bsd)

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.report is not None
        area = result.report.area
        assert area is not None
        assert (area.keep_level, area.wall_level, area.gate_level, area.tower_level, area.moat_level) == (5, 4, 3, 2, 1)
        assert area.area_type == 12

    def test_a_report_without_fortifications_still_parses(self, no_sleep):
        client = spy_client()

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True
        assert result.report is not None
        assert result.report.area is not None
        # int(undefined) in parseAreaInfoBattleLog
        assert result.report.area.keep_level == 0


class TestSpyReportIsCheckedAgainstTheTarget:
    """sne has no mission id, and robber barons share an owner, so a header naming
    the target's owner can still be another area's report: its position decides."""

    def test_a_report_for_another_castle_is_rejected(self, no_sleep):
        bsd = xt_packet(
            "bsd",
            {"MID": 9001, "S": [[[487, 100]]], "AI": {"N": "Elsewhere", "AT": 2, "X": 111, "Y": 222, "K": 0}},
        )
        client = spy_client(bsd=bsd)

        result = client.spy.execute_instant_spy(12345, 700, 710, max_wait=0.05)

        assert result.success is False
        assert result.outcome is SpyOutcome.REPORT_TARGET_MISMATCH

    def test_the_requested_castle_is_accepted(self, no_sleep):
        bsd = xt_packet(
            "bsd",
            {"MID": 9001, "S": [[[487, 100]]], "AI": {"N": "Keep", "AT": 2, "X": 700, "Y": 710, "K": 0}},
        )
        client = spy_client(bsd=bsd)

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True
        assert result.report is not None
        assert result.report.area is not None
        assert (result.report.area.x, result.report.area.y) == (700, 710)

    def test_a_report_with_no_army_block_is_not_an_empty_castle(self, no_sleep):
        # The caught mission's report had no S and no B at all. Reporting that
        # as zero troops publishes a castle nobody actually read.
        bsd = xt_packet("bsd", {"MID": 9001, "AI": {"N": "Keep", "AT": 2, "X": 700, "Y": 710, "K": 0}})
        client = spy_client(bsd=bsd)

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.outcome is SpyOutcome.NO_SPY_DATA


class TestSpyFailurePaths:
    def test_no_spies_available_asks_once_by_default(self, no_sleep):
        client = spy_client(ssi=xt_packet("ssi", {"AS": 0}))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is False
        assert result.outcome is SpyOutcome.NO_SPIES_AVAILABLE
        assert conn(client).requested.count("ssi") == 1
        assert "csm" not in conn(client).requested

    @pytest.mark.parametrize(("wait", "asks"), [(0.5, 2), (2, 2), (2.5, 3), (0, 1)])
    def test_any_wait_for_spies_asks_again(self, no_sleep, wait, asks):
        client = spy_client(ssi=xt_packet("ssi", {"AS": 0}))

        client.spy.execute_instant_spy(12345, 700, 710, wait_for_spies=wait)

        assert conn(client).requested.count("ssi") == asks

    def test_waiting_for_spies_asks_again_until_the_limit(self, monkeypatch):
        slept: list[float] = []
        monkeypatch.setattr(spy_module.time, "sleep", slept.append)
        client = spy_client(ssi=xt_packet("ssi", {"AS": 0}))

        result = client.spy.execute_instant_spy(12345, 700, 710, wait_for_spies=8)

        assert result.outcome is SpyOutcome.NO_SPIES_AVAILABLE
        assert conn(client).requested.count("ssi") == 5
        assert slept == [2.0] * 4

    def test_spies_returning_are_picked_up_on_a_later_poll(self, no_sleep):
        client = spy_client(ssi=[xt_packet("ssi", {"AS": 0}), xt_packet("ssi", {"AS": 8})])

        result = client.spy.execute_instant_spy(12345, 700, 710, wait_for_spies=10)

        assert result.success is True
        assert conn(client).requested.count("ssi") == 2

    def test_ssi_error_code_is_tagged_with_the_code(self, no_sleep):
        client = spy_client(ssi=xt_packet("ssi", error_code=21))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert (result.outcome, result.step) == (SpyOutcome.COMMAND_FAILED, SpyStep.SSI)
        assert isinstance(result.error, CommandError)
        assert result.error.code == 21

    def test_ssi_timeout_is_tagged_by_type(self, no_sleep):
        client = spy_client(ssi=EmpireTimeoutError("no ssi"))
        result = client.spy.execute_instant_spy(12345, 700, 710)
        assert (result.outcome, result.step) == (SpyOutcome.COMMAND_FAILED, SpyStep.SSI)
        assert isinstance(result.error, EmpireTimeoutError)

    def test_csm_rejection_is_tagged(self, no_sleep):
        client = spy_client(csm=xt_packet("csm", error_code=21))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert (result.outcome, result.step) == (SpyOutcome.COMMAND_FAILED, SpyStep.CSM)
        assert isinstance(result.error, CommandError)
        assert result.error.code == 21

    @pytest.mark.parametrize(
        "sne_payload",
        [
            {},  # no MSG at all
            {"MSG": []},  # empty batch
            {"MSG": [[]]},  # empty first message
            {"MSG": "junk"},  # ValidationError inside parse_response
            {"MSG": [123]},  # entries of the wrong type
            [1, 2, 3],  # not an object
        ],
    )
    def test_unusable_sne_payloads_are_skipped(self, no_sleep, sne_payload):
        client = spy_client(sne=[xt_packet("sne", sne_payload), sne_packet()])

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert result.success is True

    def test_an_sne_error_is_skipped(self, no_sleep):
        client = spy_client(sne=[xt_packet("sne", error_code=21), sne_packet()])

        assert client.spy.execute_instant_spy(12345, 700, 710).success is True

    def test_bsd_failure_is_tagged(self, no_sleep):
        client = spy_client(bsd=xt_packet("bsd", error_code=21))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert (result.outcome, result.step) == (SpyOutcome.COMMAND_FAILED, SpyStep.BSD)
        assert isinstance(result.error, CommandError)
        assert result.error.code == 21
        assert result.mission is not None

    def test_a_failure_carries_no_report(self, no_sleep):
        client = spy_client(csm=xt_packet("csm", error_code=21))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert (result.report, result.army, result.message_id, result.mission) == (None, None, None, None)

    @pytest.mark.parametrize("code", [130, 66])
    def test_a_bsd_without_a_report_is_no_spy_data(self, no_sleep, code):
        # BSDCommand shows "no spy data" for NO_SPY_DATA and NO_SUCH_MESSAGE
        client = spy_client(bsd=xt_packet("bsd", error_code=code))

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert (result.outcome, result.step, result.message_id) == (SpyOutcome.NO_SPY_DATA, SpyStep.BSD, 9001)
        assert isinstance(result.error, CommandError)
        assert result.error.code == code
        assert result.report is None

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"csm": xt_packet("csm", error_code=21)},
            {"sne": []},
            {"bsd": xt_packet("bsd", error_code=21)},
        ],
    )
    def test_the_subscription_is_always_dropped(self, no_sleep, kwargs):
        client = spy_client(**kwargs)

        client.spy.execute_instant_spy(12345, 700, 710, max_wait=0.01)

        assert conn(client).subscribers["sne"] == []
        assert "unsubscribe:sne" in conn(client).events


class TestPaying:
    """Nothing is paid for unless asked (CastlePostSpyDialog.spyCastle, C2SCreateSpyMovementVO)."""

    def test_by_default_no_horse_is_used_and_nothing_is_paid(self, no_sleep):
        client = spy_client()

        client.spy.execute_instant_spy(12345, 700, 710)

        sent = dict(conn(client).request_payloads)["csm"]
        assert (sent["HBW"], sent["PTT"], sent["SD"]) == (-1, 0, 0)

    def test_feathers_send_no_horse_with_ptt(self, no_sleep):
        client = spy_client()

        client.spy.execute_instant_spy(12345, 700, 710, feathers=True)

        sent = dict(conn(client).request_payloads)["csm"]
        assert (sent["HBW"], sent["PTT"]) == (-1, 1)

    def test_a_horse_is_sent_by_its_wod_id(self, no_sleep):
        client = spy_client()

        client.spy.execute_instant_spy(12345, 700, 710, horse_booster_id=1010)

        sent = dict(conn(client).request_payloads)["csm"]
        assert (sent["HBW"], sent["PTT"]) == (1010, 0)

    def test_feathers_win_over_a_horse(self, no_sleep):
        client = spy_client()

        client.spy.execute_instant_spy(12345, 700, 710, feathers=True, horse_booster_id=1010)

        sent = dict(conn(client).request_payloads)["csm"]
        assert (sent["HBW"], sent["PTT"]) == (-1, 1)

    def test_the_slowdown_is_sent(self, no_sleep):
        client = spy_client()

        client.spy.execute_instant_spy(12345, 700, 710, slowdown=30)

        assert dict(conn(client).request_payloads)["csm"]["SD"] == 30

    def test_the_keys_keep_the_client_order(self, no_sleep):
        client = spy_client()

        client.spy.execute_instant_spy(12345, 700, 710, horse_booster_id=1010)

        sent = dict(conn(client).request_payloads)["csm"]
        assert list(sent) == ["SID", "TX", "TY", "SC", "ST", "SE", "HBW", "KID", "PTT", "SD"]


class TestReportWait:
    """The report can only come once the spies arrive, TT - PT seconds after the csm reply."""

    @staticmethod
    def _record_deadline(monkeypatch: pytest.MonkeyPatch) -> list[float]:
        deadlines: list[float] = []
        original = spy_module.SpyService._await_report

        def record(self: Any, notifications: Any, deadline: float, *args: Any, **kwargs: Any) -> Any:
            deadlines.append(deadline - spy_module.time.monotonic())
            return original(self, notifications, deadline, *args, **kwargs)

        monkeypatch.setattr(spy_module.SpyService, "_await_report", record)
        return deadlines

    def test_the_wait_covers_the_trip(self, no_sleep, monkeypatch):
        deadlines = self._record_deadline(monkeypatch)
        client = spy_client()

        assert client.spy.execute_instant_spy(12345, 700, 710).success is True

        assert deadlines[0] == pytest.approx(38 + 10.0, abs=0.5)

    def test_max_wait_caps_the_wait(self, no_sleep, monkeypatch):
        deadlines = self._record_deadline(monkeypatch)
        client = spy_client()

        client.spy.execute_instant_spy(12345, 700, 710, max_wait=5)

        assert deadlines[0] == pytest.approx(5, abs=0.5)

    def test_a_reply_without_a_movement_waits_the_margin_and_warns(self, no_sleep, monkeypatch, caplog):
        deadlines = self._record_deadline(monkeypatch)
        client = spy_client(csm=xt_packet("csm", {}))

        with caplog.at_level("WARNING", logger="empire_core.spy.service"):
            result = client.spy.execute_instant_spy(12345, 700, 710)

        assert deadlines[0] == pytest.approx(10.0, abs=0.5)
        assert "no readable movement" in caplog.text
        # Only the kingdom can be matched, so the report's position decides
        assert result.success is True


class TestAccuracyIsTradedForRisk:
    """A guarded castle is spied at lower detail rather than not at all."""

    def test_the_planned_accuracy_is_what_gets_sent(self, no_sleep):
        client = spy_client(ssi=xt_packet("ssi", {"AS": 46, "GC": 60}))

        client.spy.execute_instant_spy(12345, 700, 710, risk_tolerance=5)

        sent = dict(conn(client).request_payloads)["csm"]
        assert sent["SE"] < 100, "sent full accuracy the risk ceiling could not afford"
        assert sent["SC"] > 0


class TestTheRiskFloorFollowsTheTarget:
    """CastleStartSpyVO.setSpyValues: no floor for a dungeon NPC, 5% for players and NPC-PvP owners."""

    @staticmethod
    def screen(row: list[Any], available: int = 46, owners: list[Any] | None = None) -> Packet:
        return xt_packet(
            "ssi",
            {"AS": available, "GC": 0, "TX": 700, "TY": 710, "gaa": {"KID": 0, "OI": owners or [], "AI": [row]}},
        )

    def test_a_robber_baron_camp_is_costed_without_the_player_floor(self, no_sleep):
        # 7 spies reach 0% against an unguarded camp; the player floor stopped at 6 for 5%
        client = spy_client(ssi=self.screen([2, 700, 710, -1, 0, -1, 0]))

        client.spy.execute_instant_spy(12345, 700, 710)

        assert dict(conn(client).request_payloads)["csm"]["SC"] == 7

    def test_a_ceiling_under_the_player_floor_still_spies_a_camp(self, no_sleep):
        client = spy_client(ssi=self.screen([2, 700, 710, -1, 0, -1, 0]))

        result = client.spy.execute_instant_spy(12345, 700, 710, risk_tolerance=2)

        assert result.success is True

    def test_an_alien_camp_keeps_the_player_floor(self, no_sleep):
        client = spy_client(ssi=self.screen([21, 700, 710, -1, 0, -1, 0]))

        result = client.spy.execute_instant_spy(12345, 700, 710, risk_tolerance=2)

        assert result.outcome is SpyOutcome.RISK_OVER_BUDGET

    def test_a_player_castle_keeps_the_player_floor(self, no_sleep):
        client = spy_client(ssi=self.screen([1, 700, 710, 2001, 1001, 2, 2, 2, 1, 0, "Keep"]))

        client.spy.execute_instant_spy(12345, 700, 710)

        assert dict(conn(client).request_payloads)["csm"]["SC"] == 6

    def test_an_unclaimed_outpost_has_no_floor(self, no_sleep):
        client = spy_client(ssi=self.screen([4, 700, 710, -300, -300, 1, 1, 1, 0, 0, ""]))

        client.spy.execute_instant_spy(12345, 700, 710)

        assert dict(conn(client).request_payloads)["csm"]["SC"] == 7

    def test_a_target_whose_owner_is_not_known_keeps_the_player_floor(self, no_sleep):
        # A treasure camp's owner is not traced, so the player floor is kept
        client = spy_client(ssi=self.screen([8, 700, 710, 0, 0]))

        client.spy.execute_instant_spy(12345, 700, 710)

        assert dict(conn(client).request_payloads)["csm"]["SC"] == 6


class TestEconomyMissions:
    def test_an_economy_mission_is_sent_as_st_1(self, no_sleep):
        client = spy_client(sne=sne_packet("2+0+2#0+-211+"))

        result = client.spy.execute_instant_spy(12345, 700, 710, spy_type=SpyType.ECO)

        assert dict(conn(client).request_payloads)["csm"]["ST"] == 1
        assert result.success is True

    def test_an_economy_report_needs_no_army(self, no_sleep):
        bsd = xt_packet("bsd", {"MID": 9001, "R": [["W", 500]], "AI": {"AT": 2, "X": 700, "Y": 710, "K": 0}})
        client = spy_client(sne=sne_packet("2+0+2#0+-211+"), bsd=bsd)

        result = client.spy.execute_instant_spy(12345, 700, 710, spy_type=SpyType.ECO)

        assert result.success is True
        assert result.report is not None
        assert result.report.resources == [["W", 500]]

    @pytest.mark.parametrize("spy_type", [SpyType.SABOTAGE, SpyType.PLAGUE])
    def test_other_mission_types_are_refused(self, no_sleep, spy_type):
        client = spy_client()

        with pytest.raises(ValueError):
            client.spy.execute_instant_spy(12345, 700, 710, spy_type=spy_type)
        assert "ssi" not in conn(client).requested


class TestForwardingAlreadyShared:
    def test_a_recipient_who_has_the_report_counts_as_done(self):
        # MFSCommand treats ALREADY_HAS_SPY_REPORT like ALL_OK
        client = make_client({"mfs": xt_packet("mfs", error_code=167)})

        assert client.spy.forward_report(9001, [111]) is True


class TestReadingAnyReport:
    def test_a_report_is_read_by_its_message_id(self):
        client = make_client({"bsd": bsd_reply(4242)})

        report = client.spy.get_report(4242)

        assert report is not None
        assert report.message_id == 4242
        assert dict(conn(client).request_payloads)["bsd"] == {"MID": 4242}

    @pytest.mark.parametrize("code", [130, 66])
    def test_no_report_is_none(self, code):
        client = make_client({"bsd": xt_packet("bsd", error_code=code)})

        assert client.spy.get_report(4242) is None

    def test_another_refusal_raises(self):
        client = make_client({"bsd": xt_packet("bsd", error_code=21)})

        with pytest.raises(CommandError):
            client.spy.get_report(4242)


class TestAutoSpy:
    def test_ssu_sends_the_position_and_reads_a_report(self):
        client = make_client({"ssu": xt_packet("ssu", BSD_NPC_CAMP_REPORT)})

        report = client.spy.auto_spy(501, 297)

        assert dict(conn(client).request_payloads)["ssu"] == {"TX": 501, "TY": 297}
        assert report.area is not None
        assert (report.area.x, report.area.y) == (501, 297)
        assert report.has_army


class TestSendingAMissionAsGiven:
    def test_the_values_are_sent_unplanned(self):
        client = make_client({"csm": xt_packet("csm", csm_reply())})

        mission = client.spy.send_spy_mission(
            12345, 700, 710, Kingdom.SANDS, spy_type=SpyType.SABOTAGE, spies=4, accuracy_or_damage=30
        )

        assert mission.movement_id == 5001
        assert dict(conn(client).request_payloads)["csm"] == {
            "SID": 12345,
            "TX": 700,
            "TY": 710,
            "SC": 4,
            "ST": 2,
            "SE": 30,
            "HBW": -1,
            "KID": 1,
            "PTT": 0,
            "SD": 0,
        }
        assert "ssi" not in conn(client).requested

    def test_plague_monks_are_not_sent_with_csm(self):
        client = make_client()

        with pytest.raises(ValueError):
            client.spy.send_spy_mission(12345, 700, 710, spy_type=SpyType.PLAGUE, spies=1, accuracy_or_damage=10)


class TestSabotage:
    @staticmethod
    def screen(available: int = 12, guards: int = 30, level: int = 30) -> Packet:
        owner = {"OID": 1001, "N": "Enemy", "L": level}
        row = [1, 700, 710, 2001, 1001, 2, 2, 2, 1, 0, "Keep"]
        return xt_packet(
            "ssi", {"AS": available, "GC": guards, "TX": 700, "TY": 710, "gaa": {"OI": [owner], "AI": [row]}}
        )

    def test_the_fewest_spies_for_the_lowest_risk_are_sent(self):
        # getSabotageRisk(s, 30, 30) falls to 10 at 12 spies
        client = make_client({"ssi": self.screen(), "csm": xt_packet("csm", csm_reply())})

        result = client.spy.send_sabotage(12345, 700, 710, damage=30)

        assert result.outcome is SpyOutcome.SENT
        assert result.mission is not None
        sent = dict(conn(client).request_payloads)["csm"]
        assert (sent["ST"], sent["SE"], sent["SC"]) == (2, 30, 12)

    def test_a_ceiling_the_pool_cannot_reach_sends_nothing(self):
        client = make_client({"ssi": self.screen(available=3)})

        result = client.spy.send_sabotage(12345, 700, 710, damage=30, risk_tolerance=20)

        assert result.outcome is SpyOutcome.RISK_OVER_BUDGET
        assert "csm" not in conn(client).requested

    def test_more_damage_than_the_owner_level_allows_is_refused(self):
        # A level 15 owner can lose two buildings: 20 damage at most
        client = make_client({"ssi": self.screen(level=15)})

        with pytest.raises(ValueError):
            client.spy.send_sabotage(12345, 700, 710, damage=30)
        assert "csm" not in conn(client).requested

    def test_no_free_spies_sends_nothing(self):
        client = make_client({"ssi": self.screen(available=0)})

        assert client.spy.send_sabotage(12345, 700, 710, damage=10).outcome is SpyOutcome.NO_SPIES_AVAILABLE


class TestTheLogMustBeForThisKindOfMission:
    """A military mission's log is DEFENCE (1), an economy mission's is ECO (2)."""

    def test_a_military_mission_skips_an_economy_log(self, no_sleep):
        client = spy_client(sne=[sne_packet("2+0+2#0+-211+", message_id=8000), sne_packet(message_id=9001)])

        result = client.spy.execute_instant_spy(12345, 700, 710)

        assert (result.success, result.message_id) == (True, 9001)
        assert ("bsd", {"MID": 8000}) not in conn(client).request_payloads

    def test_an_economy_mission_skips_a_military_log(self, no_sleep):
        client = spy_client(sne=sne_packet("1+0+2#0+-211+"))

        result = client.spy.execute_instant_spy(12345, 700, 710, spy_type=SpyType.ECO, max_wait=0.05)

        assert result.outcome is SpyOutcome.TIMEOUT
        assert "bsd" not in conn(client).requested

    @pytest.mark.parametrize("header", ["0+0+2#0+-211+", "3+2+2#0+-211+"])
    def test_sabotage_and_plague_logs_are_skipped(self, no_sleep, header):
        client = spy_client(sne=sne_packet(header))

        result = client.spy.execute_instant_spy(12345, 700, 710, max_wait=0.05)

        assert result.outcome is SpyOutcome.TIMEOUT


class TestNpcDungeonsHaveNoPlayerFloor:
    """setSpyValues: these owners are fixed NPC ids below 0, so isDungeon and floor 0."""

    @pytest.mark.parametrize(
        "row",
        [
            [11, 700, 710, -1, 5, 0, -1, 1],  # boss dungeon: -230 minus the kingdom
            [25, 700, 710, 4, -1, 1, 0, 0, 0],  # isle dungeon: NPC_ID_EILAND_DUNGEON
            [42, 700, 710, -1, 5, 0, 0, 0, 0],  # wolf king: -1201
        ],
    )
    def test_a_ceiling_under_the_player_floor_still_spies(self, no_sleep, row):
        ssi = xt_packet("ssi", {"AS": 46, "GC": 0, "TX": 700, "TY": 710, "gaa": {"AI": [row]}})
        client = spy_client(ssi=ssi)

        result = client.spy.execute_instant_spy(12345, 700, 710, risk_tolerance=2)

        assert result.success is True
        assert dict(conn(client).request_payloads)["csm"]["SC"] == 7


class TestSabotageDamageRange:
    @pytest.mark.parametrize("damage", [9, 51])
    def test_damage_outside_the_slider_is_refused_before_anything_is_sent(self, damage):
        client = make_client()

        with pytest.raises(ValueError):
            client.spy.send_sabotage(12345, 700, 710, damage=damage)
        assert conn(client).requested == []
