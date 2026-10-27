"""
Espionage: spy missions, sabotage and spy reports.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from empire_core.enums import SpyOutcome, SpyStep
from empire_core.services.base import BaseService
from empire_core.spy.service.instant import InstantSpyMixin
from empire_core.spy.service.missions import MissionsMixin
from empire_core.spy.service.reports import ReportsMixin
from empire_core.spy.service.results import SpyHandle, SpyResult, _SpyLog
from empire_core.spy.service.spies import SpiesMixin
from empire_core.spy.service.tracking import ReportTrackingMixin

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient


class SpyService(InstantSpyMixin, MissionsMixin, SpiesMixin, ReportsMixin, ReportTrackingMixin, BaseService):
    """Spy missions planned for risk, sabotage, and reading spy reports."""

    def __init__(self, client: EmpireClient) -> None:
        super().__init__(client)
        self._logs_changed = threading.Condition()
        self._missions: list[SpyHandle] = []
        self._spy_logs: list[_SpyLog] = []


__all__ = ["SpyHandle", "SpyOutcome", "SpyResult", "SpyService", "SpyStep"]
