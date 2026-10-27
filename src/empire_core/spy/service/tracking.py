"""Matching the spy logs that come in to the missions awaiting them."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

from pydantic import ValidationError

from empire_core.enums import GGEError, SpyOutcome, SpyStep, SpyType
from empire_core.exceptions import CommandError, EmpireError
from empire_core.messages.models import GetSpyReportRequest, MessageInfo, SpyReportResponse, SystemNotificationEvent
from empire_core.protocol.base import parse_response
from empire_core.protocol.packet import Packet
from empire_core.services.base import ServiceMixin
from empire_core.spy.models import SendSpyResponse
from empire_core.spy.service.results import SpyHandle, SpyResult, _SpyLog

# BSDCommand.executeCommand (bundle line 125223) shows "no spy data" for these
_NO_REPORT_ERRORS = frozenset({GGEError.NO_SPY_DATA, GGEError.NO_SUCH_MESSAGE})
_REPORT_MARGIN = 10.0
# A handle never awaited or cancelled stops listening this long after its report was due.
_ABANDONED_SECONDS = 600.0

_POLL_SECONDS = 1.0


def _spy_messages(packet: Packet) -> list[MessageInfo]:
    """The messages of an ``sne`` push; none when it cannot be read."""
    if packet.error_code != 0 or not isinstance(packet.payload, dict):
        return []
    try:
        event = parse_response("sne", packet.payload)
    except ValidationError:
        return []
    return event.messages if isinstance(event, SystemNotificationEvent) else []


class ReportTrackingMixin(ServiceMixin):
    if TYPE_CHECKING:
        _logs_changed: threading.Condition
        _missions: list[SpyHandle]
        _spy_logs: list[_SpyLog]

    def _listen(self, handle: SpyHandle) -> None:
        """Keep spy logs for ``handle`` from now on; subscribed before csm is sent so the report can't slip past."""
        with self._logs_changed:
            self._prune()
            if not self._missions:
                self.client.connection.subscribe("sne", self._on_sne)
            self._missions.append(handle)
            handle._on_cancel = self._changed

    def _arm(self, handle: SpyHandle, mission: SendSpyResponse) -> None:
        """Give a listening handle its csm reply, from which its reports are matched."""
        with self._logs_changed:
            handle.mission = mission
            handle.arrival_eta = time.monotonic() + (mission.seconds_until_arrival or 0)
            self._prune()
            self._logs_changed.notify_all()

    def _release(self, handle: SpyHandle) -> None:
        """``handle`` no longer reads; it keeps listening only as a cancelled mission's place (see :meth:`_prune`)."""
        with self._logs_changed:
            handle._reading = None
            self._prune()
            self._logs_changed.notify_all()

    def _changed(self) -> None:
        """Wake the waits and settle the logs after a handle was cancelled."""
        with self._logs_changed:
            self._prune()
            self._logs_changed.notify_all()

    def _on_sne(self, packet: Packet) -> None:
        """Receive-thread subscriber: keep the spy logs of an ``sne`` push for the missions waiting."""
        logs = [(message, header) for message in _spy_messages(packet) if (header := message.spy_log_header())]
        with self._logs_changed:
            self._spy_logs.extend(logs)
            self._prune()
            self._logs_changed.notify_all()

    @staticmethod
    def _listening(handle: SpyHandle, now: float) -> bool:
        """
        Whether ``handle`` still takes spy logs.

        A handle waiting for its csm reply does, and an armed one until its
        result is known or, never awaited, until ``_ABANDONED_SECONDS`` after
        its report was due. A mission whose spies were sent and which left
        its wait without reading its report (cancelled, ``max_wait``) stays
        until 10s after they arrive, so the report routed to it is dropped
        instead of reaching a mission whose spies arrive later.
        """
        if handle.mission is None or handle.arrival_eta is None:
            return handle.result is None
        if handle._reading is not None:
            return True
        due = handle.arrival_eta + _REPORT_MARGIN
        if handle.result is None:
            return now < due + (0 if handle.cancel_event.is_set() else _ABANDONED_SECONDS)
        return handle.result.step is SpyStep.SNE and now < due

    def _prune(self) -> None:
        """
        Settle the missions and kept logs; called under ``_logs_changed``.

        Drops the handles no longer listening (one left alone gets a
        ``TIMEOUT`` result), each mission that stopped reading together with
        the log routed to it, and the logs no handle can take; unsubscribes
        once no handle is left.
        """
        now = time.monotonic()
        for handle in self._missions:
            if not self._listening(handle, now) and handle.result is None:
                handle.result = SpyResult(SpyOutcome.TIMEOUT, SpyStep.SNE, mission=handle.mission)
        self._missions = [h for h in self._missions if self._listening(h, now)]
        for log, handle in list(self._routes()):
            if handle.cancel_event.is_set() or handle.result is not None:
                self._spy_logs.remove(log)
                self._missions.remove(handle)
        self._spy_logs = [log for log in self._spy_logs if any(h._may_read(log) for h in self._missions)]
        if not self._missions:
            self.client.connection.unsubscribe("sne", self._on_sne)

    def _routes(self) -> Iterator[tuple[_SpyLog, SpyHandle]]:
        """
        The kept spy logs with the mission each goes to now; called under ``_logs_changed``.

        Logs go in the order they came, each to the free mission whose spies
        arrive first among those whose target its header names and which have
        not turned it down; a mission reading a log is not free, and each
        mission gets one log at a time. A log a mission still waiting for its
        csm reply could take is held, and so are the missions it could go to,
        since the waiting one may arrive first (a feathered mission arrives
        with the reply).
        """
        taken: set[int] = set()
        for log in self._spy_logs:
            armed = [h for h in self._missions if h.mission is not None and id(h) not in taken and h._may_read(log)]
            if any(h.mission is None and h._may_read(log) for h in self._missions):
                taken.update(id(h) for h in armed)
                continue
            free = [h for h in armed if h._reading is None]
            if free:
                first = min(free, key=lambda h: h.arrival_eta or 0.0)
                taken.add(id(first))
                yield log, first

    def _take_log(self, handle: SpyHandle, deadline: float) -> _SpyLog | SpyOutcome:
        """Wait for the next spy log ``handle`` should read, or the outcome that ends the wait."""
        with self._logs_changed:
            while (remaining := deadline - time.monotonic()) > 0:
                if handle.cancel_event.is_set():
                    return SpyOutcome.CANCELLED
                self._prune()
                log = next((log for log, h in self._routes() if h is handle), None)
                if log is not None:
                    self._spy_logs.remove(log)
                    handle._reading = log
                    return log
                if not self.client.connection.connected:
                    return SpyOutcome.DISCONNECTED
                self._logs_changed.wait(min(remaining, _POLL_SECONDS))
        return SpyOutcome.TIMEOUT

    def _decline(self, handle: SpyHandle, log: _SpyLog) -> None:
        """Hand back a report for another position, for the next mission whose target its header names."""
        with self._logs_changed:
            handle._declined.add(log[0].message_id)
            handle._reading = None
            self._spy_logs.append(log)
            self._prune()
            self._logs_changed.notify_all()

    def _read_report(self, handle: SpyHandle, mission: SendSpyResponse, deadline: float) -> SpyResult:
        """Read the spy logs given to ``handle`` until one is its report, or the deadline passes."""
        missed = SpyOutcome.TIMEOUT
        while True:
            log = self._take_log(handle, deadline)
            if isinstance(log, SpyOutcome):
                return SpyResult(missed if log is SpyOutcome.TIMEOUT else log, SpyStep.SNE, mission=mission)
            message, header = log
            try:
                report = self.request(GetSpyReportRequest(message_id=message.message_id), SpyReportResponse)
            except CommandError as e:
                if e.error in _NO_REPORT_ERRORS:
                    return SpyResult(
                        SpyOutcome.NO_SPY_DATA,
                        SpyStep.BSD,
                        error=e,
                        message_id=message.message_id,
                        mission=mission,
                    )
                return SpyResult(SpyOutcome.COMMAND_FAILED, SpyStep.BSD, error=e, mission=mission)
            except EmpireError as e:
                return SpyResult(SpyOutcome.COMMAND_FAILED, SpyStep.BSD, error=e, mission=mission)

            area = report.area
            target = (handle.target_x, handle.target_y)
            if area is not None and area.x >= 0 and area.y >= 0 and (area.x, area.y) != target:
                # Another area with the same owner, e.g. one of many robber barons.
                missed = SpyOutcome.REPORT_TARGET_MISMATCH
                self._decline(handle, log)
                continue

            result = SpyResult(SpyOutcome.SUCCESS, message_id=message.message_id, report=report, mission=mission)
            if header.spies_lost:
                result.outcome = SpyOutcome.SPY_CAUGHT
            elif handle.spy_type == SpyType.MILITARY and not report.has_army:
                result.outcome = SpyOutcome.NO_SPY_DATA
            return result
