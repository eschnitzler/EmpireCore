"""Your alliance's details after diplomacy and auto war replies.

ADPCommand.executeCommand (split.js 623011) reads AS and AO with parseAllianceInfo (split.js 61810),
which keeps only your own alliance; SAWCommand.executeCommand (split.js 625171) sets autoWarOn from AW.
"""

from typing import Any

import pytest

from empire_core.enums import DiplomacyStatus
from empire_core.exceptions import CommandError, ReplyMismatchError
from empire_core.protocol.packet import Packet
from empire_core.state.manager import GameState
from tests.alliance.test_pushes import alliance_state
from tests.service_helpers import conn, make_client, xt_packet

AT_WAR = [{"AID": 55, "AN": "Other", "AS": 0, "AC": 1}]
NEUTRAL = [{"AID": 55, "AN": "Other", "AS": 1, "AC": 1}]


def own_state(**fields: Any) -> GameState:
    state = alliance_state()
    state.update_from_packet("ain", {"A": {"AID": 301, "ADL": AT_WAR, **fields}})
    return state


def adp_reply(own: dict[str, Any]) -> dict[str, Any]:
    return {"ODR": 0, "NDR": 1, "S": 0, "AS": own, "AO": {"AID": 55, "N": "Other", "ADL": []}}


def wired(state: GameState, command: str, payload: Any, error_code: int = 0, then: Any = None):
    client = make_client({command: xt_packet(command, payload, error_code)}, state=state)

    def received(packet: Packet) -> None:
        state.update_from_packet(packet.command_id, packet.payload, packet.error_code)
        if then is not None:
            then()

    conn(client).on_packet = received
    return client


def statuses(state: GameState) -> list[tuple[int, int]]:
    held = state.get_own_alliance()
    assert held is not None
    return [(row.alliance_id, row.status) for row in held.alliance_diplomacy]


def rejoin(state: GameState) -> None:
    state.update_from_packet("gal", {"AID": -1})
    state.update_from_packet("gal", {"AID": 301})
    state.update_from_packet("ain", {"A": {"AID": 301, "N": "New membership", "ADL": AT_WAR, "AW": 0}})


class TestChangeDiplomacy:
    def test_the_replys_own_alliance_updates_yours(self):
        state = own_state()
        client = wired(state, "adp", adp_reply({"AID": 301, "ADL": NEUTRAL}))

        client.alliance.change_diplomacy(55, DiplomacyStatus.NEUTRAL)

        assert statuses(state) == [(55, 1)]

    def test_the_other_alliance_is_not_kept(self):
        state = own_state()
        client = wired(state, "adp", adp_reply({"AID": 401, "ADL": NEUTRAL}))

        response = client.alliance.change_diplomacy(55, DiplomacyStatus.NEUTRAL)

        assert response.other_alliance is not None and response.other_alliance.alliance_id == 55
        held = state.get_own_alliance()
        assert held is not None and held.alliance_id == 301
        assert statuses(state) == [(55, 0)]

    def test_a_refusal_changes_nothing(self):
        state = own_state()
        before = state.get_own_alliance()
        client = wired(state, "adp", adp_reply({"AID": 301, "ADL": NEUTRAL}), error_code=1)

        with pytest.raises(CommandError):
            client.alliance.change_diplomacy(55, DiplomacyStatus.NEUTRAL)

        assert state.get_own_alliance() == before

    def test_a_reply_from_an_earlier_membership_changes_nothing(self):
        state = own_state()
        client = wired(state, "adp", adp_reply({"AID": 301, "ADL": NEUTRAL}), then=lambda: rejoin(state))

        with pytest.raises(ReplyMismatchError):
            client.alliance.change_diplomacy(55, DiplomacyStatus.NEUTRAL)

        held = state.get_own_alliance()
        assert held is not None and held.name == "New membership"
        assert statuses(state) == [(55, 0)]

    def test_a_push_after_the_reply_is_kept(self):
        state = own_state()
        client = wired(
            state,
            "adp",
            adp_reply({"AID": 301, "ADL": NEUTRAL, "CF": 2, "HF": 3}),
            then=lambda: state.update_from_packet("afa", {"CF": 77, "HF": 88}),
        )

        client.alliance.change_diplomacy(55, DiplomacyStatus.NEUTRAL)

        held = state.get_own_alliance()
        assert held is not None and (held.glory_points, held.highest_glory_points) == (77, 88)
        assert statuses(state) == [(55, 1)]


class TestSetAutoWar:
    @pytest.mark.parametrize(("enabled", "aw"), [(True, 1), (False, 0)])
    def test_the_reply_sets_your_alliances_auto_war(self, enabled, aw):
        state = own_state(AW=1 - aw)
        client = wired(state, "saw", {"AW": aw})

        assert client.alliance.set_auto_war(enabled) is enabled

        held = state.get_own_alliance()
        assert held is not None and held.auto_war is enabled
        assert conn(client).request_payloads == [("saw", {"AW": aw})]

    def test_a_refusal_changes_nothing(self):
        state = own_state(AW=0)
        client = wired(state, "saw", {"AW": 1}, error_code=1)

        with pytest.raises(CommandError):
            client.alliance.set_auto_war(True)

        held = state.get_own_alliance()
        assert held is not None and held.auto_war is False

    def test_a_reply_from_an_earlier_membership_changes_nothing(self):
        state = own_state(AW=0)
        client = wired(state, "saw", {"AW": 1}, then=lambda: rejoin(state))

        with pytest.raises(ReplyMismatchError):
            client.alliance.set_auto_war(True)

        held = state.get_own_alliance()
        assert held is not None and held.name == "New membership" and held.auto_war is False

    def test_a_push_after_the_reply_is_kept(self):
        state = own_state(AW=0)
        client = wired(
            state, "saw", {"AW": 1}, then=lambda: state.update_from_packet("ain", {"A": {"AID": 301, "AW": 0}})
        )

        client.alliance.set_auto_war(True)

        held = state.get_own_alliance()
        assert held is not None and held.auto_war is False

    def test_no_alliance_details_are_made_up(self):
        state = alliance_state()
        state.own_alliance = None
        client = wired(state, "saw", {"AW": 1})

        assert client.alliance.set_auto_war(True) is True

        assert state.get_own_alliance() is None
