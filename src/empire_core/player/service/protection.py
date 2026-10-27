"""Peace mode and faction protection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.enums import Kingdom, PeaceModeDuration
from empire_core.player.models.protection import (
    CANCEL_PEACE_MODE,
    FACTION_PROTECTION_RUBIES,
    GetProtectionRequest,
    ProtectionResponse,
    StartFactionProtectionRequest,
    StartFactionProtectionResponse,
    StartPeaceModeRequest,
)
from empire_core.player.service.base import PlayerBaseMixin

if TYPE_CHECKING:
    from empire_core.map.models.areas import KingdomProtection


class ProtectionMixin(PlayerBaseMixin):
    # =========================================================================
    # Protection
    # =========================================================================

    def protection(self, kingdom: Kingdom = Kingdom.GREEN) -> KingdomProtection | None:
        """
        Your protection in ``kingdom`` as last sent (login data, ``uap`` pushes and replies); nothing is sent.

        Its seconds count from when it arrived, ``client.state.get_last_packet_time("uap")`` for a push.
        None when none came for that kingdom.

        Raises:
            StateNotLoadedError: No login has brought the player
        """
        return self.local_player.protection.get(kingdom)

    def get_protection(self, kingdom: Kingdom = Kingdom.GREEN, *, timeout: float = 5.0) -> ProtectionResponse:
        """
        Ask for your protection in ``kingdom``; the reply also updates :meth:`protection`, and in Berimond the event.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SUserAttackProtectionVO`` (bundle line 65923) and, for Berimond,
        ``C2SUpdateFactionProtectionVO`` (bundle line 87993); ``UAPCommand`` (bundle line 129888)
        """
        return self.request(GetProtectionRequest(kingdom=kingdom), ProtectionResponse, timeout=timeout)

    def start_peace_mode(
        self, duration: PeaceModeDuration, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> None:
        """
        Buy peace mode: nobody can attack you, and you attack nobody, for ``duration``.

        It starts after a lead time; the stages arrive as ``uap`` pushes (see :meth:`protection`).

        Args:
            duration: How long; ``duration.rubies`` is its price before ruby discounts
            spend_rubies: Allow the rubies it costs
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleStartPeaceModeDialog.onClick`` (bundle line 35192) and ``setPrice``
        (bundle line 35188); ``C2SPeaceModeStartVO`` (bundle line 47478), ``MPSCommand`` (bundle line 125133)
        """
        self._require_spend_rubies(spend_rubies, f"peace mode for {duration.name} costs {duration.rubies} rubies")
        self.execute(StartPeaceModeRequest(duration=duration), timeout=timeout)

    def cancel_peace_mode(self, *, timeout: float = 5.0) -> None:
        """
        End your peace mode; the new stage arrives as a ``uap`` push.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleManagementDialog.cancelPeaceMode`` (bundle line 24682) sends ``C2SPeaceModeStartVO(-1)``
        """
        self.execute(StartPeaceModeRequest(duration=CANCEL_PEACE_MODE), timeout=timeout)

    def start_faction_protection(
        self, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> StartFactionProtectionResponse:
        """
        Buy Berimond faction protection; the reply also updates the running Berimond event.

        Args:
            spend_rubies: Allow the rubies it costs, ``FACTION_PROTECTION_RUBIES`` before discounts
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleFactionProtectionModeDialog.onClick`` (bundle line 64918), priced by
        ``FactionConst.getPeaceC2Cost`` (dll line 19316); ``FFPCommand`` (bundle line 127785)
        """
        self._require_spend_rubies(spend_rubies, f"faction protection costs {FACTION_PROTECTION_RUBIES} rubies")
        return self.request(StartFactionProtectionRequest(), StartFactionProtectionResponse, timeout=timeout)
