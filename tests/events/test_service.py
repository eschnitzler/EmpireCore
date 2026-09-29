"""Tests for the events service."""

from __future__ import annotations

from empire_core.events import service as events_module
from tests.service_helpers import StubState, make_client


class TestActiveEvents:
    def test_ids_are_a_copy_of_the_state_list(self):
        state = StubState()
        state.active_event_ids = [10, 11]  # type: ignore[attr-defined]
        client = make_client(state=state)

        ids = client.events.get_active_event_ids()
        ids.append(99)

        assert client.events.get_active_event_ids() == [10, 11]

    def test_events_resolve_the_state_ids(self, monkeypatch):
        calls = []

        def fake_get_active_events(event_ids, lang="en", force_refresh=False):
            calls.append((event_ids, lang, force_refresh))
            return []

        monkeypatch.setattr(events_module, "_get_active_events", fake_get_active_events)
        state = StubState()
        state.active_event_ids = [10]  # type: ignore[attr-defined]
        client = make_client(state=state)

        assert client.events.get_active_events(lang="de", force_refresh=True) == []
        assert calls == [([10], "de", True)]
