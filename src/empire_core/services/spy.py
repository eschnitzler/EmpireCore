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
    SpyCastleInfo,
    SystemNotificationEvent,
)
from .base import BaseService, register_service


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
        battle_data: the raw ``B`` mapping (present for battle reports).
        target: the spied castle, or ``None`` if the server sent no ``AI`` block.
    """

    success: bool
    reason: str | None = None
    message_id: int | None = None
    spy_data: list[Any] = field(default_factory=list)
    battle_data: dict[str, Any] = field(default_factory=dict)
    target: SpyCastleInfo | None = None


@register_service("spy")
class SpyService(BaseService):
    """Service for managing spy operations."""

    def execute_instant_spy(
        self,
        source_castle_id: int,
        target_x: int,
        target_y: int,
        target_kingdom: int = 0,
        risk_tolerance: int = 50,
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
            risk_tolerance: Maximum acceptable risk percentage (0-100)

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

        spies_to_send = 0
        for attempt in range(_SSI_POLL_ATTEMPTS):
            try:
                ssi_resp = self.request(ssi_req, SpyScreenInfoResponse)
            except EmpireError as e:
                return SpyResult(success=False, reason=f"ssi_failed_{_error_tag(e)}")

            spies_to_send = ssi_resp.available_spies
            if spies_to_send > 0:
                break

            # Spies not yet returned — wait and retry (unless this was the last attempt)
            if attempt < _SSI_POLL_ATTEMPTS - 1:
                time.sleep(_SSI_POLL_DELAY)

        if spies_to_send <= 0:
            return SpyResult(success=False, reason="no_spies_available")

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
            SE=100,
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

            message_id = sne_event.messages[0][0]

            # Check if spy was caught: the "1+2+1" pattern from the legacy bot
            first_msg = sne_event.messages[0]
            if len(first_msg) >= 4 and first_msg[1] == 1 and first_msg[2] == 2 and first_msg[3] == 1:
                return SpyResult(success=False, reason="spy_caught")

            # 5. Request the actual spy report data
            try:
                bsd_resp = self.request(BattleSpyDataRequest(MID=message_id), BattleSpyDataResponse)
            except EmpireError as e:
                return SpyResult(success=False, reason=f"bsd_failed_{_error_tag(e)}")

            return SpyResult(
                success=True,
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
