"""What the events sections share: the check that an event runs."""

from __future__ import annotations

from empire_core.events.models import SpecialEvent
from empire_core.exceptions import EventNotRunningError
from empire_core.gamedata.ids.events import Event
from empire_core.services.base import ServiceMixin


class EventsBaseMixin(ServiceMixin):
    def _require_running(self, event: Event | int) -> SpecialEvent:
        found = self.client.state.get_event(event)
        if found is None:
            raise EventNotRunningError(int(event))
        return found
