"""
Events service: the server's currently active events.
"""

from __future__ import annotations

from empire_core.services.base import BaseService, register_service
from empire_core.utils.events import GameEvent
from empire_core.utils.events import get_active_events as _get_active_events


@register_service("events")
class EventsService(BaseService):
    """
    Service for active event info.

    Accessible via client.events after auto-registration.
    """

    def get_active_event_ids(self) -> list[int]:
        """
        Get list of currently active event IDs.

        Returns:
            List of event IDs (EID) from sei packet.
            Empty list if no events are active or not yet logged in.
        """
        return list(self.client.state.active_event_ids)  # Return copy, not reference

    def get_active_events(
        self,
        lang: str = "en",
        force_refresh: bool = False,
    ) -> list[GameEvent]:
        """
        Get currently active events with human-readable names resolved from the GGS CDN.

        Combines ``get_active_event_ids()`` with a CDN lookup to produce typed
        ``GameEvent`` objects. CDN data is cached after the first call.

        Args:
            lang: Language code for display names (default: "en").
            force_refresh: Force re-fetch of CDN data, bypassing the cache.

        Returns:
            List of GameEvent objects for currently active events. An empty
            list always means "no events are active" — CDN failures raise.

        Raises:
            NetworkError: The CDN fetch failed and no cached data exists, so
                the answer is unknown rather than empty.

        Example:
            events = client.events.get_active_events()
            event_names = {e.internal_name for e in events}

            if "Nomad" in event_names:
                # handle nomad event ...
                pass
        """
        event_ids = self.get_active_event_ids()
        return _get_active_events(event_ids, lang=lang, force_refresh=force_refresh)
