"""
Player service: other players' details and player search.
"""

from __future__ import annotations

import queue
import time

from empire_core.player.models.info import (
    GetPlayerInfoRequest,
    GetPlayerInfoResponse,
    SearchPlayerRequest,
    SearchPlayerResponse,
)
from empire_core.protocol.base import BaseResponse
from empire_core.services.base import BaseService, register_service


@register_service("player")
class PlayerService(BaseService):
    """
    Service for player info and search.

    Accessible via client.player after auto-registration.
    """

    def get_player_info(self, player_id: int, timeout: float = 5.0) -> GetPlayerInfoResponse:
        """
        Get detailed player information (gdi), including castle list with
        capture info.

        Args:
            player_id: A player's id: ``search_player_by_name(name).get_player().owner_id``,
                an owner record's ``MapObject.owner_id`` from a map scan, or an
                ``AllianceMember.player_id`` from ``client.alliance.get_members()``
            timeout: Timeout in seconds

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`
        """
        return self.request(GetPlayerInfoRequest(PID=player_id), GetPlayerInfoResponse, timeout=timeout)

    def get_player_details(
        self,
        player_id: int,
        timeout: float = 5.0,
    ) -> GetPlayerInfoResponse:
        """Alias for :meth:`get_player_info` (both use the 'gdi' command)."""
        return self.get_player_info(player_id, timeout=timeout)

    def get_player_details_bulk(
        self,
        player_ids: list[int],
        timeout: float = 10.0,
        send_delay: float = 0.05,
    ) -> dict[int, GetPlayerInfoResponse]:
        """
        Get detailed info for multiple players in parallel.

        Registers a handler first, then sends all requests (paced by
        ``send_delay``), and collects responses via a thread-safe queue.

        Args:
            player_ids: Player ids to fetch, found as for :meth:`get_player_info`
            timeout: Max time to wait for all responses. The pacing sleeps are
                not charged against it - the clock starts once all requests
                are out.
            send_delay: Seconds to wait between consecutive 'gdi' sends. The
                server drops connections that sustain high request rates (the
                same reason MapScanner paces its chunks), and a large id list
                would otherwise go out as one burst on a connection other
                callers share. Set to 0 to send without pacing.

        Returns:
            Dict mapping player_id -> GetPlayerInfoResponse
        """
        if not player_ids:
            return {}

        unique_ids = set(player_ids)
        response_queue: queue.Queue[GetPlayerInfoResponse] = queue.Queue()

        def capture_gdi(response: BaseResponse) -> None:
            if isinstance(response, GetPlayerInfoResponse):
                response_queue.put(response)

        # Register BEFORE sending to avoid dropping early responses
        self.client._register_handler("gdi", capture_gdi)

        try:
            for index, pid in enumerate(unique_ids):
                if index and send_delay > 0:
                    time.sleep(send_delay)
                request = GetPlayerInfoRequest(PID=pid)
                self.client.send(request, wait=False)

            collected: dict[int, GetPlayerInfoResponse] = {}
            deadline = time.time() + timeout

            while len(collected) < len(unique_ids) and time.time() < deadline:
                try:
                    resp = response_queue.get(timeout=max(0.05, min(0.5, deadline - time.time())))
                    if resp.player_id in unique_ids:
                        collected[resp.player_id] = resp
                except queue.Empty:
                    continue

            return collected
        finally:
            self.client._unregister_handler("gdi", capture_gdi)

    def search_player_by_name(
        self,
        player_name: str,
        timeout: float = 5.0,
    ) -> SearchPlayerResponse:
        return self.request(SearchPlayerRequest(PN=player_name), SearchPlayerResponse, timeout=timeout)
