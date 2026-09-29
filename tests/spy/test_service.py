"""Tests for the spy service."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.enums import Kingdom
from empire_core.exceptions import EmpireTimeoutError
from tests.service_helpers import conn, make_client, xt_packet
from tests.spy.payloads import CSM_REPLY


def spy_script(
    ssi: Any = None,
    csm: Any = None,
    sne: Any = None,
    bsd: Any = None,
) -> dict[str, Any]:
    return {
        "ssi": ssi if ssi is not None else xt_packet("ssi", {"AS": 46, "GC": 0}),
        "csm": csm if csm is not None else xt_packet("csm", CSM_REPLY),
        "sne": sne
        if sne is not None
        else xt_packet("sne", {"MSG": [[9001, 3, "1+0+4#0+16324240+Enemy Keep", "", -1, 0, 0, 0, 0]]}),
        "bsd": bsd
        if bsd is not None
        else xt_packet(
            "bsd",
            {
                "MID": 9001,
                "S": [[[487, 100]], [], [], [], [], []],
                "B": {"ID": 2, "WID": 1, "VIS": 4, "N": "", "W": 3, "D": 1, "SPR": 0, "E": [[12, [5.0], "EQ"]]},
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
        assert result.spy_data == [[[487, 100]], [], [], [], [], []]
        assert result.defending_castellan is not None
        assert (result.defending_castellan.commander_id, result.defending_castellan.wins) == (2, 3)
        assert result.target is not None
        assert result.target.castle_name == "Enemy Keep"

    def test_only_the_spies_the_risk_budget_needs_are_sent(self, no_sleep):
        # Sending the whole pool bought nothing: 6 spies already reach the 5%
        # floor against an unguarded castle, and draining the pool made the next
        # mission wait for spies to walk home.
        client = make_client(spy_script(ssi=xt_packet("ssi", {"AS": 46, "GC": 0})))

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
        client = make_client(spy_script(ssi=xt_packet("ssi", {"AS": 46, "GC": 0})))

        client.spy.execute_instant_spy(12345, 700, 710, risk_tolerance=90)

        assert dict(conn(client).request_payloads)["csm"]["SC"] == 6

    def test_a_guarded_target_costs_more_spies(self, no_sleep):
        client = make_client(spy_script(ssi=xt_packet("ssi", {"AS": 200, "GC": 60})))

        client.spy.execute_instant_spy(12345, 700, 710)

        assert dict(conn(client).request_payloads)["csm"]["SC"] > 6

    def test_a_target_over_the_risk_ceiling_is_not_spied(self, no_sleep):
        # One spy against a fully guarded castle stays over a 10% ceiling at
        # every accuracy the game allows, so there is no mission to send.
        client = make_client(spy_script(ssi=xt_packet("ssi", {"AS": 1, "GC": 180})))

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

    def test_waiter_is_canceled_on_success(self, no_sleep):
        client = make_client(spy_script())
        client.spy.execute_instant_spy(12345, 700, 710)
        assert conn(client).waiters_canceled == ["sne"]


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

    def test_a_successful_defense_for_the_target_is_also_a_loss(self, no_sleep):
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
        assert result.defending_castellan is None
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
    def test_waiter_is_always_canceled(self, no_sleep, script):
        client = make_client(script)

        client.spy.execute_instant_spy(12345, 700, 710)

        assert conn(client).waiters_canceled == ["sne"]


class TestPaying:
    """Nothing is paid for unless asked (CastlePostSpyDialog.spyCastle, C2SCreateSpyMovementVO)."""

    def test_by_default_no_horse_is_used_and_nothing_is_paid(self, no_sleep):
        client = make_client(spy_script())

        client.spy.execute_instant_spy(12345, 700, 710)

        sent = dict(conn(client).request_payloads)["csm"]
        assert (sent["HBW"], sent["PTT"], sent["SD"]) == (-1, 0, 0)

    def test_feathers_send_no_horse_with_ptt(self, no_sleep):
        client = make_client(spy_script())

        client.spy.execute_instant_spy(12345, 700, 710, pay_with_feathers=True)

        sent = dict(conn(client).request_payloads)["csm"]
        assert (sent["HBW"], sent["PTT"]) == (-1, 1)

    def test_a_horse_is_sent_by_its_wod_id(self, no_sleep):
        client = make_client(spy_script())

        client.spy.execute_instant_spy(12345, 700, 710, horse_wod_id=1010)

        sent = dict(conn(client).request_payloads)["csm"]
        assert (sent["HBW"], sent["PTT"]) == (1010, 0)

    def test_feathers_win_over_a_horse(self, no_sleep):
        client = make_client(spy_script())

        client.spy.execute_instant_spy(12345, 700, 710, pay_with_feathers=True, horse_wod_id=1010)

        sent = dict(conn(client).request_payloads)["csm"]
        assert (sent["HBW"], sent["PTT"]) == (-1, 1)

    def test_the_slowdown_is_sent(self, no_sleep):
        client = make_client(spy_script())

        client.spy.execute_instant_spy(12345, 700, 710, slowdown=30)

        assert dict(conn(client).request_payloads)["csm"]["SD"] == 30

    def test_the_keys_keep_the_client_order(self, no_sleep):
        client = make_client(spy_script())

        client.spy.execute_instant_spy(12345, 700, 710, horse_wod_id=1010)

        sent = dict(conn(client).request_payloads)["csm"]
        assert list(sent) == ["SID", "TX", "TY", "SC", "ST", "SE", "HBW", "KID", "PTT", "SD"]


class TestReportWait:
    """The report can only come once the spies arrive, TT - PT seconds after the csm reply."""

    @staticmethod
    def _record_timeouts(client: Any, monkeypatch: pytest.MonkeyPatch) -> list[float]:
        fake = conn(client)
        timeouts: list[float] = []
        original = fake.wait_for_result

        def wait_for_result(cmd_id: str, waiter: Any, timeout: float = 5.0) -> Any:
            timeouts.append(timeout)
            return original(cmd_id, waiter, timeout)

        monkeypatch.setattr(fake, "wait_for_result", wait_for_result)
        return timeouts

    def test_the_wait_covers_the_trip(self, no_sleep, monkeypatch):
        client = make_client(spy_script())
        timeouts = self._record_timeouts(client, monkeypatch)

        assert client.spy.execute_instant_spy(12345, 700, 710).success is True

        assert timeouts == [38 + 10.0]

    def test_a_reply_without_a_movement_waits_the_margin_only(self, no_sleep, monkeypatch):
        client = make_client(spy_script(csm=xt_packet("csm", {})))
        timeouts = self._record_timeouts(client, monkeypatch)

        client.spy.execute_instant_spy(12345, 700, 710)

        assert timeouts == [10.0]


class TestAccuracyIsTradedForRisk:
    """A guarded castle is spied at lower detail rather than not at all."""

    def test_the_planned_accuracy_is_what_gets_sent(self, no_sleep):
        client = make_client(spy_script(ssi=xt_packet("ssi", {"AS": 46, "GC": 60})))

        client.spy.execute_instant_spy(12345, 700, 710, risk_tolerance=5)

        sent = dict(conn(client).request_payloads)["csm"]
        assert sent["SE"] < 100, "sent full accuracy the risk ceiling could not afford"
        assert sent["SC"] > 0
