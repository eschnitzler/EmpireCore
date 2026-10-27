"""Espionage: spy missions, their risk and their reports."""

from typing import TYPE_CHECKING

from empire_core.enums import Kingdom, LogResult, SpyLogType, SpyOutcome, SpyStep, SpyType
from empire_core.utils.lazy import lazy_exports

from .models import (
    AutoSpyRequest,
    AutoSpyResponse,
    MaxSpiesResponse,
    PlagueDoctorInfoResponse,
    SendPlagueDoctorsRequest,
    SendPlagueDoctorsResponse,
    SendSpyRequest,
    SendSpyResponse,
    SpyScreenInfoRequest,
    SpyScreenInfoResponse,
    SpyTargetArea,
)
from .pool import total_spies
from .risk import SabotagePlan, SpyPlan, plan_mission, plan_sabotage, sabotage_risk, spy_risk
from .service import SpyHandle, SpyResult, SpyService

if TYPE_CHECKING:
    from empire_core.gamedata import Horse, LegendSkill, Research

__all__ = [
    "AutoSpyRequest",
    "AutoSpyResponse",
    "MaxSpiesResponse",
    "PlagueDoctorInfoResponse",
    "SendPlagueDoctorsRequest",
    "SendPlagueDoctorsResponse",
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
    "Kingdom",
    "SpyOutcome",
    "SpyStep",
    "Horse",
    "LegendSkill",
    "Research",
]


if not TYPE_CHECKING:
    __getattr__ = lazy_exports(__name__, "empire_core.gamedata.ids", ("Horse", "LegendSkill", "Research"))
