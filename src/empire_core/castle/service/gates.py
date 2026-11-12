"""Open Gate: open a castle's gate so attackers loot it without a battle, and close it again."""

from __future__ import annotations

from empire_core.castle.models.gates import (
    CLOSE_GATE,
    OpenGateQuote,
    OpenGateRequest,
    OpenGateResponse,
    open_gate_rubies,
)
from empire_core.enums import MapItemType, OpenGateDuration, OpenGateRefusal
from empire_core.services.base import ServiceMixin

_MIN_LEVEL = 5


class OpenGateMixin(ServiceMixin):
    def open_gate_quote(self, castle_id: int) -> OpenGateQuote:
        """
        What opening one of your castles' gate would cost now, and whether the client offers it; nothing is sent.

        The open time and opening count come from the castle list and the ``mos`` replies since, the
        prices before ruby discounts from that count, as the client's start dialog shows them.

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list
            StateNotLoadedError: No login has brought the player

        Client: ``CastleStartOpenGateDialog.updateCosts`` (bundle line 35144) and ``getCastleList``
        (bundle line 35133); ``CastleOpenGatePremiumShopVO.canBeBought`` (bundle line 76693)
        """
        castle = self._require_own_castle(castle_id)
        player = self.client.state.get_local_player()
        use = castle.open_gate_counter + 1
        if castle.castle_type == MapItemType.CAPITAL:
            refusal = OpenGateRefusal.CAPITAL
        elif castle.castle_type == MapItemType.TRADING_METROPOLIS:
            refusal = OpenGateRefusal.TRADING_METROPOLIS
        elif player.level < _MIN_LEVEL:
            refusal = OpenGateRefusal.LEVEL
        else:
            refusal = None
        return OpenGateQuote(
            castle_id=castle.id,
            kingdom=castle.kingdom_id,
            open_seconds=castle.open_gate_seconds(),
            uses=castle.open_gate_counter,
            prices={duration: open_gate_rubies(duration, use) for duration in OpenGateDuration},
            rubies=player.rubies,
            refusal=refusal,
        )

    def open_gate(
        self, castle_id: int, duration: OpenGateDuration, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> OpenGateResponse:
        """
        Buy an Open Gate for one of your castles: attackers loot it without a battle, so its buildings
        take no damage and it loses no units, for ``duration``. On an open gate it extends it, as the
        client's extend button does. Each opening this week raises the castle's next price.

        The reply updates the castle's Open Gate and your rubies in state. A timeout is not retried:
        the purchase may still have gone through, so read :meth:`open_gate_quote` before trying again.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            duration: How long
            spend_rubies: Allow the rubies it costs; :meth:`open_gate_quote` has the price before discounts
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False, or the client offers no Open Gate for the castle
                (see :class:`OpenGateRefusal`)
            UnknownCastleError: ``castle_id`` is not in your castle list
            StateNotLoadedError: No login has brought the player
            CommandError: The server refused it; ``INVALID_PARAMETER_VALUE`` while the castle's peace mode is on
            EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleStartOpenGateDialog.onClick`` (bundle line 35154); ``MOSCommand.executeCommand``
        (bundle line 125119) shows ``error_openGate_eilandProtection`` for ``INVALID_PARAMETER_VALUE``
        """
        quote = self.open_gate_quote(castle_id)
        if quote.refusal is not None:
            raise ValueError(f"the client offers no Open Gate for castle {castle_id}: {quote.refusal.value}")
        self._require_spend_rubies(
            spend_rubies,
            f"an Open Gate for {duration.name} costs {quote.prices[duration]} rubies before discounts",
        )
        request = OpenGateRequest(castle_id=quote.castle_id, kingdom=quote.kingdom, duration=duration)
        return self.request(request, OpenGateResponse, timeout=timeout, spend_rubies=spend_rubies)

    def close_gate(self, castle_id: int, *, timeout: float = 5.0) -> OpenGateResponse:
        """
        Close one of your castles' open gate; nothing is refunded.

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleManagementDialog.cancelOpenGateMode`` (bundle line 24683) sends ``C2SOpenGateStartVO`` with -1
        """
        castle = self._require_own_castle(castle_id)
        request = OpenGateRequest(castle_id=castle.id, kingdom=castle.kingdom_id, duration=CLOSE_GATE)
        return self.request(request, OpenGateResponse, timeout=timeout)
