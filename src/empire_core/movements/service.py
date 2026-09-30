"""
The army movements the state tracks.
"""

from __future__ import annotations

from empire_core.exceptions import CommandError
from empire_core.movements.models import (
    CancelMovementRequest,
    CancelMovementResponse,
    GetMovementsRequest,
    MovementWrapper,
)
from empire_core.movements.tracked import Movement
from empire_core.services.base import BaseService


class MovementsService(BaseService):
    """
    Army movements: listing them and recalling your own.

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
        if wait:
            response = self.client.request_packet(GetMovementsRequest(), "gam", timeout=timeout)
            # Without this, a rejected request returns the previous (possibly
            # empty) movement list, indistinguishable from "no movements".
            if response.error_code != 0:
                raise CommandError("gam", response.error_code)
        else:
            self.client.connection.send(self.client.frame(GetMovementsRequest()))

        return self.client.state.get_all_movements()

    def recall(self, movement_id: int, timeout: float = 5.0) -> MovementWrapper:
        """
        Recall one of your movements (``mcm``), as the client's retreat and "send home" buttons do.

        Which movements the client lets you recall is listed on
        :class:`CancelMovementRequest`: in short, your own that are still
        heading to their target (attacks only within 600 seconds of leaving,
        with exceptions) and your supports in either direction. The reply
        also updates state and fires :meth:`GameState.on_movement_recalled`.

        Args:
            movement_id: The movement to recall (``Movement.movement_id``)
            timeout: Timeout in seconds

        Returns:
            The movement as the reply has it now, normally on its way home

        Raises:
            CommandError: The server refused the recall, such as
                INVALID_STARTAREA_FOR_CANCEL_MOVEMENT (189)

        Client: ``CastleAskRetreatDialog.onClick`` (bundle line 33234),
        ``MCMCommand.executeCommand`` (bundle line 126041)
        """
        return self.request(CancelMovementRequest(MID=movement_id), CancelMovementResponse, timeout=timeout).movement

    def get_incoming_attacks(self) -> list[Movement]:
        """Get all incoming attack movements."""
        return self.client.state.get_incoming_attacks()

    def get_incoming_movements(self) -> list[Movement]:
        """Get all incoming movements."""
        return self.client.state.get_incoming_movements()

    def get_outgoing_movements(self) -> list[Movement]:
        """Get all outgoing movements."""
        return self.client.state.get_outgoing_movements()
