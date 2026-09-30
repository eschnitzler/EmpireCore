"""
Movements service: the army movements the state tracks.
"""

from __future__ import annotations

from empire_core.exceptions import CommandError
from empire_core.movements.tracked import Movement
from empire_core.protocol.packet import Packet
from empire_core.services.base import BaseService


class MovementsService(BaseService):
    """
    Service for army movements.

    Reached as client.movements.
    """

    def get_movements(self, wait: bool = True, timeout: float = 5.0) -> list[Movement]:
        """
        Request army movements from server.

        Args:
            wait: If True, wait for response before returning
            timeout: Timeout in seconds when waiting

        Returns:
            List of Movement objects, read from state after the response has
            been applied. With ``wait=False`` this is whatever state holds
            right now, which is not yet the answer to this request.

        Raises:
            CommandError: ``wait=True`` and the server rejected 'gam'
            EmpireTimeoutError: ``wait=True`` and no response within ``timeout``
        """
        packet = Packet.build_xt(self.zone, "gam", {}, room_id=self.client.connection.room_id)

        if wait:
            response = self.client.connection.request(packet, "gam", timeout=timeout)
            # Without this, a rejected request returns the previous (possibly
            # empty) movement list, indistinguishable from "no movements".
            if response.error_code != 0:
                raise CommandError("gam", response.error_code)
        else:
            self.client.connection.send(packet)

        return self.client.state.get_all_movements()

    def get_incoming_attacks(self) -> list[Movement]:
        """Get all incoming attack movements."""
        return self.client.state.get_incoming_attacks()

    def get_incoming_movements(self) -> list[Movement]:
        """Get all incoming movements."""
        return self.client.state.get_incoming_movements()

    def get_outgoing_movements(self) -> list[Movement]:
        """Get all outgoing movements."""
        return self.client.state.get_outgoing_movements()
