"""Claiming the event announcement's reward: car, as CastleEventTeaserDialog sends it and CARCommand reads it."""

import pytest

from empire_core.enums import GGEError
from empire_core.events import (
    ClaimAnnouncementRewardRequest,
    ClaimAnnouncementRewardResponse,
    EventAnnouncementEvent,
)
from empire_core.exceptions import CommandError
from empire_core.gamedata.ids.events import Event
from empire_core.protocol.models import parse_response
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet


def test_the_request_has_no_fields():
    assert ClaimAnnouncementRewardRequest().to_payload() == {}


def test_the_reply_reads_nothing():
    assert isinstance(parse_response("car", {}), ClaimAnnouncementRewardResponse)


def test_claim_sends_and_waits():
    client = make_client()

    client.events.claim_announcement_reward()

    assert conn(client).request_payloads == [("car", {})]


def test_a_refusal_raises():
    client = make_client({"car": xt_packet("car", {}, error_code=GGEError.GENERAL_ERROR)})

    with pytest.raises(CommandError) as raised:
        client.events.claim_announcement_reward()

    assert raised.value.error is GGEError.GENERAL_ERROR


class TestState:
    # EventAnnouncementData.parseCAR marks the running announcement collected; isClaimed reads it
    def test_a_claim_marks_the_running_announcement_collected(self):
        state = logged_in_state(sei={"E": [{"EID": 73, "RS": 3600}]})
        announcement = state.get_event(Event.EVENT_ANNOUNCEMENT)
        assert announcement is not None and announcement.reward_collected is False

        state.update_from_packet("car", {})
        state.update_from_packet("sei", {"E": [{"EID": 73, "RS": 1800}]})

        announcement = state.get_event(Event.EVENT_ANNOUNCEMENT)
        assert isinstance(announcement, EventAnnouncementEvent) and announcement.reward_collected

    def test_a_refused_claim_or_no_announcement_changes_nothing(self):
        state = logged_in_state(sei={"E": [{"EID": 73, "RS": 3600}]})

        state.update_from_packet("car", {}, error_code=GGEError.GENERAL_ERROR)
        announcement = state.get_event(Event.EVENT_ANNOUNCEMENT)
        assert announcement is not None and announcement.reward_collected is False

        empty = logged_in_state()
        empty.update_from_packet("car", {})
        assert empty.get_event(Event.EVENT_ANNOUNCEMENT) is None
