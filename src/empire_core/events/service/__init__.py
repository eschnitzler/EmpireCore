"""
The running events, as the state keeps them, and their scoreboards.
"""

from __future__ import annotations

from empire_core.events.models import ShuttingDownEvents, SpecialEvent, SpecialEventInfoRequest
from empire_core.events.service.base import EventsBaseMixin
from empire_core.events.service.minigames import MinigamesMixin
from empire_core.events.service.scores import ScoresMixin
from empire_core.events.service.seasons import SeasonsMixin
from empire_core.events.service.special_servers import SpecialServersMixin
from empire_core.events.service.tournament import GrandTournamentMixin
from empire_core.gamedata.ids.events import Event
from empire_core.services.base import BaseService


class EventsService(
    SpecialServersMixin, SeasonsMixin, GrandTournamentMixin, MinigamesMixin, ScoresMixin, EventsBaseMixin, BaseService
):
    """
    The server's active events, your event leagues and the events' scoreboards.

    Reached as client.events.
    """

    @property
    def shutting_down(self) -> ShuttingDownEvents | None:
        """The events shutting down, whose buildings stay in your castles, from the last ``sde``; None until one
        arrived."""
        return self.client.state.get_shutting_down_events()

    @property
    def running(self) -> dict[int, SpecialEvent]:
        """The running events by id, in the order they started; a copy."""
        return self.client.state.get_events()

    def is_running(self, event: Event | int) -> bool:
        """Whether an event runs and has not ended."""
        return self.client.state.is_event_active(event)

    def refresh(self, *, timeout: float = 5.0) -> dict[int, SpecialEvent]:
        """
        Ask the server for the running events and return them once its ``sei`` is applied.

        The server's answer updates the events as any ``sei`` does; events it does not
        name keep running until a ``see`` or their time ends them. It asks for the ``sei``
        events only: the trigger events (the kingdoms league, the global effects) come with
        the login data's ``tei`` and the ``tei`` pushes.

        Raises:
            CommandError: The server refused the request
            EmpireTimeoutError: No ``sei`` within ``timeout``

        Client: ``C2SSpecialEventInfoVO`` (bundle line 37406)
        """
        self.send(SpecialEventInfoRequest(), wait=True, timeout=timeout)
        return self.client.state.get_events()
