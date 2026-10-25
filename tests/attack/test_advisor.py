"""The attack advisor: aa and aao."""

from __future__ import annotations

import pytest

from empire_core.attack import ActivateAttackAdvisorResponse, AttackAdvisorOverviewResponse
from empire_core.enums import AttackAdvisorType, CollectableKind
from empire_core.exceptions import CommandError
from empire_core.protocol.base import parse_response
from tests.service_helpers import conn, make_client, xt_packet

OVERVIEW = {
    "AAT": 3,
    "G": [["C1", 1200], ["C2", 5]],
    "L": [["C1", 300]],
    "LU": 120,
    "LT": 30,
    "W": 8,
    "D": 2,
    "P": 1,
    "C": 4,
    "GP": 77,
}


class TestActivate:
    def test_sends_the_advisor(self):
        client = make_client({"aa": xt_packet("aa", {"AAT": 2})})

        reply = client.attack.activate_attack_advisor(AttackAdvisorType.SAMURAI)

        assert reply.advisor is AttackAdvisorType.SAMURAI
        assert conn(client).request_payloads == [("aa", {"AAT": 2})]

    @pytest.mark.parametrize("body", [{}, {"AAT": 0}])
    def test_a_missing_advisor_is_the_nomad_one(self, body):
        reply = parse_response("aa", body)
        assert isinstance(reply, ActivateAttackAdvisorResponse) and reply.advisor is AttackAdvisorType.NOMAD

    def test_a_refusal_raises(self):
        client = make_client({"aa": xt_packet("aa", error_code=1)})
        with pytest.raises(CommandError):
            client.attack.activate_attack_advisor(AttackAdvisorType.NOMAD)


class TestOverview:
    def test_reads_the_summary(self):
        client = make_client({"aao": xt_packet("aao", OVERVIEW)})

        overview = client.attack.get_attack_advisor_overview(AttackAdvisorType.BERIMOND)

        assert isinstance(overview, AttackAdvisorOverviewResponse)
        assert conn(client).request_payloads == [("aao", {"AAT": 3})]
        assert overview.advisor is AttackAdvisorType.BERIMOND
        assert [(c.kind, c.amount) for c in overview.gained] == [
            (CollectableKind.COINS, 1200),
            (CollectableKind.RUBIES, 5),
        ]
        assert [(c.kind, c.amount) for c in overview.lost] == [(CollectableKind.COINS, 300)]
        assert (overview.lost_units, overview.lost_tools, overview.wins, overview.defeats, overview.stopped) == (
            120,
            30,
            8,
            2,
            1,
        )
        assert (overview.commanders, overview.gallantry_points) == (4, 77)

    def test_gallantry_points_default_to_zero(self):
        overview = parse_response("aao", {"AAT": 1})
        assert isinstance(overview, AttackAdvisorOverviewResponse) and overview.gallantry_points == 0

    def test_a_refusal_raises(self):
        client = make_client({"aao": xt_packet("aao", error_code=1)})
        with pytest.raises(CommandError):
            client.attack.get_attack_advisor_overview(AttackAdvisorType.NOMAD)
