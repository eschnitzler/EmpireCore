"""
Spy service for high-level espionage operations.
"""

from typing import Any

from ..protocol.models.attack import SendSpyRequest, SpyScreenInfoRequest, SpyScreenInfoResponse
from ..protocol.models.base import parse_response
from ..protocol.models.messages import BattleSpyDataRequest, BattleSpyDataResponse, SystemNotificationEvent
from .base import BaseService, register_service


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
    ) -> dict[str, Any]:
        """
        Execute an instant spy mission using feathers.

        Args:
            target_x: Target X coordinate
            target_y: Target Y coordinate
            target_kingdom: Target kingdom ID (default 0 for Green)
            risk_tolerance: Maximum acceptable risk percentage (0-100)

        Returns:
            Dictionary containing the spy report data, or error info.
        """
        # 1. Get spy screen info
        ssi_req = SpyScreenInfoRequest(
            TX=target_x,
            TY=target_y,
            KID=target_kingdom,
        )
        ssi_resp = self.send(ssi_req, wait=True)

        if not isinstance(ssi_resp, SpyScreenInfoResponse) or ssi_resp.error_code != 0:
            return {"status": "error", "reason": f"ssi_failed_{getattr(ssi_resp, 'error_code', 'unknown')}"}

        # 2. Calculate risk (simplified for now - just use max spies)
        # In a real implementation, we'd calculate exact spies needed for risk_tolerance
        spies_to_send = ssi_resp.available_spies
        if spies_to_send <= 0:
            return {"status": "error", "reason": "no_spies_available"}

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

        # We need to send the packet manually so we can wait for SNE instead of CSM response
        # Actually, we can just send it and then wait for SNE
        packet = csm_req.to_packet(zone=self.zone)
        self.client.connection.send(packet)

        # 4. Wait for the SNE event to get the message ID
        try:
            sne_packet = self.client.connection.wait_for("sne", timeout=10.0)
            if not sne_packet or not isinstance(sne_packet.payload, dict):
                return {"status": "error", "reason": "invalid_sne_format"}

            sne_event = parse_response("sne", sne_packet.payload)

            if not isinstance(sne_event, SystemNotificationEvent):
                return {"status": "error", "reason": "invalid_sne_format"}

            # Extract MID from the first message
            if not sne_event.messages or not sne_event.messages[0]:
                return {"status": "error", "reason": "invalid_sne_format"}

            message_id = sne_event.messages[0][0]

            # 5. Request the actual spy report data
            bsd_req = BattleSpyDataRequest(MID=message_id)
            bsd_resp = self.send(bsd_req, wait=True)

            if not isinstance(bsd_resp, BattleSpyDataResponse) or bsd_resp.error_code != 0:
                return {"status": "error", "reason": f"bsd_failed_{getattr(bsd_resp, 'error_code', 'unknown')}"}

            return {
                "status": "success",
                "message_id": message_id,
                "spy_data": bsd_resp.spy_data,
                "battle_data": bsd_resp.battle_data,
            }

        except Exception as e:
            return {"status": "error", "reason": f"sne_timeout_or_error_{str(e)}"}
