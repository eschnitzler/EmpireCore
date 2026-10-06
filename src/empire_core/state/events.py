"""The running events: sei and tei entries, see and tee ends, pep scores, cqs campaigns, and their callbacks."""

import logging
import time
from collections.abc import Callable
from typing import Any

from empire_core.events.models import CampaignEvent, KingdomsLeagueEvent, SpecialEvent, event_class
from empire_core.gamedata.ids.events import Event
from empire_core.protocol.js import js_int, js_truthy
from empire_core.state.base import StateBase
from empire_core.utils import callbacks

logger = logging.getLogger(__name__)
_clock = time.monotonic

EventCallback = Callable[[SpecialEvent], Any]
EventsCallback = Callable[[dict[int, SpecialEvent]], Any]


class EventState(StateBase):
    on_event_added = callbacks.Event[SpecialEvent]()
    """Register a callback for an event that starts: a ``sei`` or ``tei`` entry for an event not running.

    Called with the event as that entry left it. Runs on the callback thread, in packet
    order (see :class:`GameState`).

    Client: ``CastleSpecialEventEvent.ADD_SPECIALEVENT`` from ``parseServerEventData`` (bundle line 139814)
    """

    on_event_removed = callbacks.Event[SpecialEvent]()
    """Register a callback for an event that ends: a ``see`` or ``tee``, or its time running out.

    Called with the event as it last stood. A disconnect (see :meth:`reset`) fires none.

    Client: ``CastleSpecialEventEvent.REMOVE_SPECIALEVENT`` from ``removeEventById`` (bundle line 139840),
    reached from ``parse_SEE``, ``parseTEE`` and ``executeUpdateForEvents`` (bundle lines 139826, 139915, 139836)
    """

    on_events_updated = callbacks.Event[dict[int, SpecialEvent]]()
    """Register a callback for every ``sei``, non-empty ``tei``, ``pep`` and ``cqs`` applied.

    Called with every running event (a copy of :meth:`get_events`), after the
    :meth:`on_event_added` and :meth:`on_event_removed` callbacks of the same packet.

    Client: ``onEventDataParsed`` (bundle line 139818) sends ``REFRESH_SPECIALEVENT`` for every
    event and ``SERVER_DATA_PARSED``; ``AScoreEventVO.setRankAndPoints`` (bundle line 15044)
    sends ``UPDATE_POINTS`` for a ``pep``; ``CQSCommand.exec`` (bundle line 126495) sends
    ``CAMPAIGN_UPDATED`` for a ``cqs``
    """

    def _handle_sei(self, data: Any) -> None:
        """Handle 'Send Event Information': each entry updates its event, or adds it.

        An entry for a running event is read over it: the raw entries are merged (the parts an
        event rebuilds from every entry are replaced), and each field the event reads only when
        the entry has it keeps its value. Events the packet does not name run on until a see
        ends them or their time runs out. An entry whose ``EID`` reads as 0 or below is skipped;
        the client drops ids its events table lacks, the library keeps every other id. An entry
        the client fails to read (a global effect event's effects without ``SGE``) is skipped.

        Where the library differs: the client also refuses to add a prime sale it cannot offer
        (``canBeAddedToActiveEvents``, e.g. 75 and 90, bundle lines 115951, 118134), which the
        library adds; and an ``RS`` that is not a number gives the client an end it never
        reaches nor passes, where the library keeps the event's earlier end.

        Client: ``CastleSpecialEventData.parse_SEI`` (bundle line 139800), which reads ``int(a.EID)``,
        and ``parseServerEventData`` (bundle line 139811)
        """
        events = data.get("E") if isinstance(data, dict) else None
        self._apply_event_entries(events if isinstance(events, list) else [], "EID")

    def _apply_sei(self, data: dict[str, Any]) -> None:
        """Apply the ``sei`` a reply carries, stamped as a sei."""
        if "sei" in data:
            self._packet_times["sei"] = time.time()
            self._handle_sei(data["sei"])

    def _handle_tei(self, data: Any) -> None:
        """Handle 'trigger event info': each ``TE`` entry updates or adds its event, keyed by ``TRID``.

        The trigger events (the kingdoms league and the global effect events) join the
        other running events; their ends come from their own fields, as their models say.

        Client: ``TEICommand`` (bundle line 128410) and ``CastleSpecialEventData.parseTEI``
        (bundle line 139905), which reads ``int(a.TRID)`` and does nothing for an empty ``TE``;
        ``ATriggerEventVO.parseBasicsFromParamObject`` (bundle line 39815)
        """
        entries = data.get("TE") if isinstance(data, dict) else None
        if isinstance(entries, list) and entries:
            self._apply_event_entries(entries, "TRID")
        else:
            self._events_updated_at = time.time()

    def _apply_event_entries(self, entries: list[Any], key: str) -> None:
        now = _clock()
        events = dict(self.events)
        added: list[SpecialEvent] = []
        for entry in entries:
            if not isinstance(entry, dict) or (eid := js_int(entry.get(key))) <= 0:
                continue
            model = event_class(eid)
            if not model.accepts(entry):
                logger.debug(f"Skipping an entry for event {eid} that the client fails to read")
                continue
            previous = events.get(eid)
            events[eid] = model.from_entry(eid, entry, previous, now, events)
            if previous is None:
                added.append(events[eid])
        self.events = events
        self._events_updated_at = time.time()
        for event in added:
            self._fire(self.on_event_added, event)
        self._expire_events()
        self._fire(self.on_events_updated, dict(self.events))

    def _handle_see(self, data: Any) -> None:
        """Handle a 'special event end' push: the event it names has ended.

        Client: ``CastleSpecialEventData.parse_SEE`` (bundle line 139826), from ``SEECommand``
        (bundle line 128364), looks the ``EID`` up as sent; ``removeEventById`` (bundle line
        139838) destroys the event, so one added again starts over
        """
        if (event := self._sent_event(data.get("EID") if isinstance(data, dict) else None)) is not None:
            self._remove_event(event.event_id)
        self._events_updated_at = time.time()

    def _handle_tee(self, data: Any) -> None:
        """Handle 'trigger event end': the trigger event it names (``TRID``) has ended.

        Client: ``TEECommand`` (bundle line 128395) and ``CastleSpecialEventData.parseTEE``
        (bundle line 139915): ``int(e&&e.TRID?e.TRID:-1)``, removed when 0 or above
        """
        trid = data.get("TRID") if isinstance(data, dict) else None
        eid = js_int(trid if js_truthy(trid) else -1)
        if eid >= 0:
            self._remove_event(eid)
        self._events_updated_at = time.time()

    def _handle_pep(self, data: Any) -> None:
        """Handle 'point event points': your rank (``OR``), points (``OP``) and the event's most points (``PT``).

        Each event reads them as its client class does: a score event its first of each, an
        invasion one per part in order, Berimond and the lucky wheels the first rank and points,
        the raid boss and the alliance mobilisation the first for you and the second for your
        alliance, the alliance tournament the first for your alliance, and ``BLPP`` the raid boss's
        level points. The library reads every value through ``int()``, where the client keeps them
        as sent.

        Client: ``PEPCommand.exec`` (bundle lines 128213-128216), which looks the ``EID`` up as sent,
        and the ``setRankAndPoints`` of each class
        """
        self._events_updated_at = time.time()
        self._expire_events()
        event = self._sent_event(data.get("EID") if isinstance(data, dict) else None)
        if event is None:
            return
        updated = event.with_points(data.get("OR"), data.get("OP"), data.get("PT"))
        if data.get("BLPP") is not None and "boss_level_points" in type(updated).model_fields:
            updated = updated.model_copy(update={"boss_level_points": js_int(data["BLPP"])})
        self.events = {**self.events, event.event_id: updated}
        self._fire(self.on_events_updated, dict(self.events))

    def _handle_cqs(self, data: Any) -> None:
        """Handle a campaign quest status: the running time-limited campaign reads its campaign from it again.

        Client: ``CQSCommand.exec`` (bundle line 126495) does nothing without the campaign running;
        ``TimeLimitedCampaignEventEventVO.parseCQS`` (bundle line 118555)
        """
        self._expire_events()
        campaign = self.events.get(Event.TIME_LIMITED_CAMPAIGN_EVENT)
        if not (isinstance(campaign, CampaignEvent) and isinstance(data, dict)):
            return
        self.events = {**self.events, campaign.event_id: campaign.with_campaign(data, _clock())}
        self._events_updated_at = time.time()
        self._fire(self.on_events_updated, dict(self.events))

    def _sent_event(self, eid: Any) -> SpecialEvent | None:
        # The id as sent, compared as the client's Map compares keys: 3.0 is 3, "3" is not
        if not isinstance(eid, (int, float)) or isinstance(eid, bool):
            return None
        return next((event for key, event in self.events.items() if key == eid), None)

    def _remove_event(self, eid: int) -> None:
        event = self.events.get(eid)
        if event is None:
            return
        self.events = {key: value for key, value in self.events.items() if key != eid}
        self._fire(self.on_event_removed, event)
        self._expire_events()

    def _expire_events(self) -> None:
        """Drop the events whose time is up, the kingdoms league's end read anew first.

        Client: ``CastleSpecialEventData.executeUpdateForEvents`` (bundle line 139833):
        ``remainingEventTimeInSeconds<=0``; ``SeasonLeagueEventVO.endTimestamp`` (bundle line 118061)
        is read whenever it is asked for
        """
        now = _clock()
        while self.events:
            events = dict(self.events)
            for eid, event in events.items():
                if isinstance(event, KingdomsLeagueEvent) and (end := event.end_with(events, now)) != event.end_time:
                    events[eid] = event.model_copy(update={"end_time": end})
            ended = [event for event in events.values() if event.end_time <= now]
            if events != self.events:
                self.events = events
            if not ended:
                return
            self.events = {eid: event for eid, event in events.items() if event.end_time > now}
            for event in ended:
                self._fire(self.on_event_removed, event)

    def get_events(self) -> dict[int, SpecialEvent]:
        """The running events by id, in the order they started; a copy.

        Each is the model its type has (:data:`~empire_core.events.models.EVENT_CLASSES`), or a
        plain :class:`~empire_core.events.models.SpecialEvent`. The models never change: a
        later packet replaces them.
        """
        with self._lock:
            self._expire_events()
            return dict(self.events)

    def get_event(self, event: Event | int) -> SpecialEvent | None:
        """A running event, or None when it is not running."""
        with self._lock:
            self._expire_events()
            return self.events.get(int(event))

    def is_event_active(self, event: Event | int) -> bool:
        """Whether an event runs and has not ended.

        Client: ``CastleSpecialEventData.isEventActive`` (bundle line 139892); the client also
        waits for some events' graphics to load, which the library has none of.
        """
        found = self.get_event(event)
        return found is not None and found.is_active(_clock())

    def get_events_last_updated(self) -> float | None:
        """When a sei, tei, see, tee or pep was last applied, wall clock; None before any."""
        with self._lock:
            return self._events_updated_at
