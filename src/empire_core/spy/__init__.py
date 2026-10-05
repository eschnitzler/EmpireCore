"""Espionage: spy missions, their risk and their reports."""

from empire_core.enums import LogResult, SpyLogType, SpyType

from .models import (
    AutoSpyRequest,
    AutoSpyResponse,
    MaxSpiesResponse,
    PlagueMonkInfoResponse,
    SendSpyRequest,
    SendSpyResponse,
    SpyScreenInfoRequest,
    SpyScreenInfoResponse,
    SpyTargetArea,
)
from .pool import total_spies
from .risk import SabotagePlan, SpyPlan, plan_mission, plan_sabotage, sabotage_risk, spy_risk
from .service import SpyHandle, SpyResult, SpyService

__all__ = [
    "AutoSpyRequest",
    "AutoSpyResponse",
    "MaxSpiesResponse",
    "PlagueMonkInfoResponse",
    "SendSpyRequest",
    "SendSpyResponse",
    "LogResult",
    "SpyLogType",
    "SpyScreenInfoRequest",
    "SpyScreenInfoResponse",
    "SpyTargetArea",
    "SpyType",
    "total_spies",
    "SabotagePlan",
    "SpyPlan",
    "plan_mission",
    "plan_sabotage",
    "sabotage_risk",
    "spy_risk",
    "SpyHandle",
    "SpyResult",
    "SpyService",
]
