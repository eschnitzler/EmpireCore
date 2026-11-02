"""The event pushes: sei and tei entries, see and tee ends."""

import pytest

from empire_core.events.models import (
    EventEndedResponse,
    SpecialEventsResponse,
    TriggerEventEndedResponse,
    TriggerEventsResponse,
)
from empire_core.gamedata import Event
from empire_core.protocol.models import parse_response


class TestEventEntries:
    def test_sei_entries_keep_the_entry_whole_and_read_the_id_through_int(self):
        # parse_SEI: int(a.EID); the entry goes whole to the event's parseData
        events = parse_response(
            "sei", {"E": [{"EID": "83", "RS": 60}, {"EID": 60.0, "RS": 5, "KL": 1}, {"RS": 60}, None]}
        )
        assert isinstance(events, SpecialEventsResponse)
        assert [(e.event_id, e.entry) for e in events.entries] == [
            (Event(83), {"EID": "83", "RS": 60}),
            (60, {"EID": 60.0, "RS": 5, "KL": 1}),
            (0, {"RS": 60}),
        ]

    @pytest.mark.parametrize("body", [{}, {"E": None}, {"E": "x"}])
    def test_no_entries(self, body):
        assert SpecialEventsResponse.model_validate(body).entries == ()

    def test_tei_entries_are_keyed_by_trid(self):
        events = TriggerEventsResponse.model_validate({"TE": [{"TRID": 612, "RS": 10}]})
        assert [(e.event_id, e.entry) for e in events.entries] == [(612, {"TRID": 612, "RS": 10})]


class TestEventEnds:
    @pytest.mark.parametrize(("value", "expected"), [(83, 83), (83.0, 83), ("83", None), (83.5, None), (True, None)])
    def test_a_see_names_its_event_as_sent(self, value, expected):
        # parse_SEE: _activeEvents.get(e.EID), no int(), so only a number finds the event
        assert EventEndedResponse.model_validate({"EID": value}).event_id == expected

    @pytest.mark.parametrize(("value", "expected"), [("612", 612), (0, None), (None, None), (-3, None), (7.9, 7)])
    def test_a_tee_reads_a_truthy_trid_through_int(self, value, expected):
        # parseTEE: int(e && e.TRID ? e.TRID : -1), removed when 0 or above
        assert TriggerEventEndedResponse.model_validate({"TRID": value}).event_id == expected
        assert TriggerEventEndedResponse.model_validate({}).event_id is None
