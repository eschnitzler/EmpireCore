"""
Spy service for high-level espionage operations.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from empire_core.exceptions import CommandError, EmpireError

from ..protocol.models.attack import SendSpyRequest, SpyScreenInfoRequest, SpyScreenInfoResponse
from ..protocol.models.base import parse_response
from ..protocol.models.messages import (
    BattleSpyDataRequest,
    BattleSpyDataResponse,
    ForwardSpyLogRequest,
    SpyCastleInfo,
    SystemNotificationEvent,
)
from .base import BaseService, register_service
from .spy_army import SpyArmy
from .spy_risk import MAX_ACCURACY, MAX_RISK_SPY, plan_mission

# Outcome codes from MessageConst in the game client. A spy log is a loss when
# the attacker failed or the defender succeeded (AMessageSpyVO.isFailedSpyLog).
_SUBTYPE_ATTACKER_SUCCESS = 0
_SUBTYPE_DEFENDER_SUCCESS = 1
_SUBTYPE_ATTACKER_FAILED = 2
_LOST_SPY_RESULTS = frozenset({_SUBTYPE_DEFENDER_SUCCESS, _SUBTYPE_ATTACKER_FAILED})


def _parse_spy_notification(message: list[Any]) -> int | None:
    """The mission's result code from an ``sne`` message, or None if unreadable.

    The params field is ``subtypeSpy+subtypeResult+areaType#kingdomID+ownerID+
    areaName``; only the result matters here. Returning None rather than
    assuming success keeps an unrecognised shape from publishing a report the
    mission may never have earned.
    """
    if len(message) < 3 or not isinstance(message[2], str):
        return None
    fields = message[2].split("+")
    if len(fields) < 2:
        return None
    try:
        return int(fields[1])
    except ValueError:
        return None


@dataclass
class SpyResult:
    """Outcome of an instant spy mission.

    The payload fields mirror :class:`~empire_core.protocol.models.messages.BattleSpyDataResponse`
    and default to empty containers on failure, so callers can read them without
    a ``None`` check.

    Attributes:
        success: whether a spy report was retrieved.
        reason: machine-readable failure tag when ``success`` is False.
        message_id: id of the report message the server created.
        spy_data: the raw ``S`` array of the report -- one entry per defending
            position, each a nested array of ``[unit_id, count]`` pairs. Still
            untyped by the protocol layer, so it is exposed as-is.
        army: the same block split by position (left/middle/right flanks, keep,
            stronghold, support, reserve). None when the report carried nothing
            usable.
        battle_data: the raw ``B`` mapping (present for battle reports).
        target: the spied castle, or ``None`` if the server sent no ``AI`` block.
    """

    success: bool
    reason: str | None = None
    message_id: int | None = None
    spy_data: list[Any] = field(default_factory=list)
    battle_data: dict[str, Any] = field(default_factory=dict)
    target: SpyCastleInfo | None = None
    army: SpyArmy | None = None


@register_service("spy")
class SpyService(BaseService):
    """Service for managing spy operations."""

    def forward_report(self, message_id: int, player_ids: list[int]) -> bool:
        """Share a spy report with other players in game.

        Returns False when the server rejects it — a report can age out of the
        mailbox, and the recipients may no longer be reachable.
        """
        if not player_ids:
            return False
        return self.execute(ForwardSpyLogRequest(PID=list(player_ids), MID=message_id))

    def execute_instant_spy(
        self,
        source_castle_id: int,
        target_x: int,
        target_y: int,
        target_kingdom: int = 0,
        risk_tolerance: int | None = None,
        accuracy: int = MAX_ACCURACY,
    ) -> SpyResult:
        """
        Execute an instant spy mission using feathers.

        Blocks the calling thread for up to ~10s while polling for spy
        availability — do not call this from a state callback.

        Args:
            source_castle_id: Source castle ID
            target_x: Target X coordinate
            target_y: Target Y coordinate
            target_kingdom: Target kingdom ID (default 0 for Green)
            risk_tolerance: Ceiling on the chance of being caught, as a
                percentage. Missions always run at the lowest risk the spy pool
                allows; this only decides whether to send at all, so a target
                that stays above it is skipped rather than spied badly.
            accuracy: Spy accuracy (50-100). Lower values need fewer spies for
                the same risk but return a less complete report.

        Returns:
            SpyResult with the spy report data or a failure reason.
        """
        # 1. Get spy screen info, polling until spies are available (they may be returning)
        _SSI_POLL_ATTEMPTS = 5
        _SSI_POLL_DELAY = 2  # seconds between retries

        ssi_req = SpyScreenInfoRequest(
            TX=target_x,
            TY=target_y,
            KID=target_kingdom,
        )

        max_risk = risk_tolerance if risk_tolerance is not None else MAX_RISK_SPY

        available = 0
        plan = None
        for attempt in range(_SSI_POLL_ATTEMPTS):
            try:
                ssi_resp = self.request(ssi_req, SpyScreenInfoResponse)
            except EmpireError as e:
                return SpyResult(success=False, reason=f"ssi_failed_{_error_tag(e)}")

            available = ssi_resp.available_spies
            if available > 0:
                plan = plan_mission(
                    guards=ssi_resp.guard_count,
                    available=available,
                    accuracy=accuracy,
                    max_risk=max_risk,
                )
                if plan is not None:
                    break

            # Spies still walking home. A fuller pool lowers the achievable
            # risk, so waiting can bring an over-budget target into range.
            if attempt < _SSI_POLL_ATTEMPTS - 1:
                time.sleep(_SSI_POLL_DELAY)

        if available <= 0:
            return SpyResult(success=False, reason="no_spies_available")

        if plan is None:
            # Even the whole pool leaves this target above the risk ceiling.
            return SpyResult(success=False, reason="risk_over_budget")

        spies_to_send = plan.spies
        # The plan may have traded detail for risk; send what it settled on.
        accuracy = plan.accuracy

        # 2. Calculate risk (simplified for now - just use max spies)
        # In a real implementation, we'd calculate exact spies needed for risk_tolerance

        # 3. Send the spy mission (instant with feathers)
        csm_req = SendSpyRequest(
            SID=source_castle_id,
            TX=target_x,
            TY=target_y,
            KID=target_kingdom,
            SC=spies_to_send,
            ST=0,
            SE=accuracy,
            HBW=-1,
            PTT=1,  # Use feathers
            SD=0,
        )

        # Register the sne waiter before sending csm so the notification
        # can't slip past between the two calls. Note: sne is a generic
        # system-notification channel; an unrelated notification arriving
        # in this window would be misattributed (no correlation id exists).
        sne_waiter = self.client.connection.create_waiter("sne")

        try:
            try:
                self.send(csm_req, wait=True)
            except EmpireError as e:
                return SpyResult(success=False, reason=f"csm_failed_{_error_tag(e)}")

            # 4. Wait for the SNE event to get the message ID
            try:
                sne_packet = self.client.connection.wait_for_result("sne", sne_waiter, timeout=10.0)
            except EmpireError as e:
                return SpyResult(success=False, reason=f"sne_timeout_or_error_{_error_tag(e)}")

            if not isinstance(sne_packet.payload, dict):
                return SpyResult(success=False, reason="invalid_sne_format")

            try:
                sne_event = parse_response("sne", sne_packet.payload)
            except ValidationError:
                # A drifted sne payload is a failed mission, not a crash out
                # of the service layer.
                return SpyResult(success=False, reason="invalid_sne_format")

            if not isinstance(sne_event, SystemNotificationEvent):
                return SpyResult(success=False, reason="invalid_sne_format")

            # Extract MID from the first message
            if not sne_event.messages or not sne_event.messages[0]:
                return SpyResult(success=False, reason="invalid_sne_format")

            first_msg = sne_event.messages[0]
            message_id = first_msg[0]

            outcome = _parse_spy_notification(first_msg)
            if outcome is None:
                return SpyResult(success=False, reason="invalid_sne_format")
            if outcome in _LOST_SPY_RESULTS:
                return SpyResult(success=False, reason="spy_caught")

            # 5. Request the actual spy report data
            try:
                bsd_resp = self.request(BattleSpyDataRequest(MID=message_id), BattleSpyDataResponse)
            except EmpireError as e:
                return SpyResult(success=False, reason=f"bsd_failed_{_error_tag(e)}")

            if not bsd_resp.spy_data:
                # A report with no army block was never read: the castle is not
                # empty, the mission just brought nothing back.
                return SpyResult(success=False, reason="no_spy_data")

            report_target = bsd_resp.target
            if report_target is not None and report_target.x >= 0 and report_target.y >= 0:
                if (report_target.x, report_target.y) != (target_x, target_y):
                    return SpyResult(success=False, reason="report_target_mismatch")

            return SpyResult(
                success=True,
                army=SpyArmy.from_spy_data(bsd_resp.spy_data),
                message_id=message_id,
                spy_data=bsd_resp.spy_data,
                battle_data=bsd_resp.battle_data,
                target=bsd_resp.target,
            )
        finally:
            self.client.connection.cancel_waiter("sne", sne_waiter)


def _error_tag(e: Exception) -> str:
    """Short machine-readable tag for a failure reason."""
    if isinstance(e, CommandError):
        return str(e.code)
    return type(e).__name__
