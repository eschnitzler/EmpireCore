"""
Player service: other players' details and player search.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from empire_core.exceptions import CommandError, EmpireTimeoutError, PacketError
from empire_core.player.models.info import (
    GetPlayerInfoRequest,
    GetPlayerInfoResponse,
    SearchPlayerRequest,
    SearchPlayerResponse,
)
from empire_core.services.base import BaseService, register_service


@dataclass
class PlayerDetailsBulkResult:
    """What :meth:`PlayerService.get_player_details_bulk` got for each player."""

    found: dict[int, GetPlayerInfoResponse] = field(default_factory=dict)
    """The replies, by player id."""
    failed: dict[int, CommandError | PacketError] = field(default_factory=dict)
    """Players whose request the server refused, or whose reply could not be read."""
    timed_out: list[int] = field(default_factory=list)
    """Players whose reply did not come in time."""

    @property
    def complete(self) -> bool:
        """Whether every player was found."""
        return not self.failed and not self.timed_out


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
        timeout: float = 5.0,
        send_delay: float = 0.05,
    ) -> PlayerDetailsBulkResult:
        """
        Get detailed info for several players, one gdi request after another.

        Each request waits for its own reply before the next goes out: a gdi
        error reply names no player, so only one request in flight at a time
        tells which player it belongs to. Each runs as :meth:`get_player_info`
        does, under the gdi command lock and taking only a reply whose
        ``O.OID`` is the player asked for.

        Args:
            player_ids: Player ids to fetch, found as for :meth:`get_player_info`; repeats are fetched once
            timeout: Seconds to wait for each reply
            send_delay: Seconds to wait between two requests. The server drops
                connections that sustain high request rates (the same reason
                MapScanner paces its chunks). Set to 0 to send without pacing.

        Returns:
            Which players were found, which failed and why, and which timed out

        Raises:
            ConnectionClosedError / NetworkError: the connection failed; the players fetched so far are lost
            ReceiveThreadError: called on the receive thread
        """
        result = PlayerDetailsBulkResult()
        for index, pid in enumerate(dict.fromkeys(player_ids)):
            if index and send_delay > 0:
                time.sleep(send_delay)
            try:
                response = self.get_player_info(pid, timeout=timeout)
            except EmpireTimeoutError:
                result.timed_out.append(pid)
                continue
            except (CommandError, PacketError) as e:
                result.failed[pid] = e
                continue
            result.found[pid] = response
        return result

    def search_player_by_name(
        self,
        player_name: str,
        timeout: float = 5.0,
    ) -> SearchPlayerResponse:
        return self.request(SearchPlayerRequest(PN=player_name), SearchPlayerResponse, timeout=timeout)


__all__ = ["PlayerDetailsBulkResult", "PlayerService"]
