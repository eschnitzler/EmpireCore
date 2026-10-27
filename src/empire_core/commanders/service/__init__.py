"""Commanders and castellans, their generals, and their equipment.

- CommandersService reads and renames the player's commanders and castellans, says
  whether the premium commander leads for free, and changes generals: assigning one
  to a commander, choosing its abilities, unlocking and resetting its skills,
  feeding it xp items, unlocking it and raising its stars with shards, and spinning
  the generals hub for them. A general's skills widen the flanks whatever the target is.
- EquipmentService reads the equipment inventory, moves items on and off
  commanders and castellans, sells items and gems, sets gems in worn items and takes
  them out, crafts and enchants items, relics and gems, and reads and sets the
  auto-sell rules.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from empire_core.commanders.models.roster import (
    PREMIUM_COMMANDER_ID,
    Castellan,
    Commander,
    CommanderRoster,
    GetCommandersRequest,
    GetCommandersResponse,
    RenameCommanderRequest,
    RenameCommanderResponse,
)
from empire_core.commanders.service.equipment import EquipmentService
from empire_core.commanders.service.generals import GeneralsMixin
from empire_core.exceptions import PremiumCommanderCostError
from empire_core.services.base import BaseService

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

_Sent = TypeVar("_Sent")


class CommandersService(GeneralsMixin, BaseService):
    """
    Your commanders and castellans, renaming them, and their generals.

    Reached as client.commanders.
    """

    @property
    def roster(self) -> CommanderRoster:
        """Your commanders and castellans as the last ``gli`` listed them.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_commanders()

    def get_all(self, *, timeout: float = 5.0) -> GetCommandersResponse:
        """
        Get commanders and castellans in one request.

        Args:
            timeout: Timeout in seconds

        Returns:
            The full gli response

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.request(GetCommandersRequest(), GetCommandersResponse, timeout=timeout)

    def get_commanders(self, *, timeout: float = 5.0) -> list[Commander]:
        """
        Get every commander, whether or not it leads an army now.

        Args:
            timeout: Timeout in seconds

        Returns:
            List of Commander objects

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.get_all(timeout=timeout).commanders

    def get_castellans(self, *, timeout: float = 5.0) -> list[Castellan]:
        """
        Get all available castellans.

        Args:
            timeout: Timeout in seconds

        Returns:
            List of Castellan objects

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.get_all(timeout=timeout).castellans

    @property
    def travelling_commanders(self) -> list[Commander]:
        """
        The commanders leading one of your movements in state, returning ones included; nothing is sent.

        An attack that lands leaves state at its arrival, as in the client, but its army's way home
        is a new movement the server can send a little later. Until it is stored, or for
        ``LANDED_COMMANDER_HOLD`` seconds after the arrival, the commander is still listed here:
        in that window the server refuses a send it leads with ``GGEError.LORD_IS_USED``. Only as
        fresh as the movements in state.

        Raises:
            StateNotLoadedError: No login has brought the roster

        Client: ``LordVO.isAvailableForMovement`` (bundle line 26656), false while any map movement
        that ``isMyMovement`` (``BasicMapmovementVO``, bundle line 19436) has the lord as its ``lordVO``,
        whichever way it travels. The hold goes beyond the client, which frees the lord as soon as
        ``CastleArmyData.updateMapmovements`` (bundle line 133719) drops the arrived movement.
        """
        away = {c.commander_id for c in self.client.state.get_away_commanders()}
        return [c for c in self.roster.commanders if c.commander_id in away]

    @property
    def idle_commanders(self) -> list[Commander]:
        """
        The commanders free to lead an army: those not in :attr:`travelling_commanders`; nothing is sent.

        A commander whose attack just landed is not listed until its army's way home is in state or
        the hold described there runs out, though the client already offers it: the server answers
        ``GGEError.LORD_IS_USED`` to a send it leads in that window.

        Raises:
            StateNotLoadedError: No login has brought the roster
        """
        away = {c.commander_id for c in self.travelling_commanders}
        return [c for c in self.roster.commanders if c.commander_id not in away]

    def rename(self, commander_id: int, name: str, *, timeout: float = 5.0) -> CommanderRoster:
        """
        Rename a commander or castellan.

        Args:
            commander_id: The leader's ``commander_id``, a ``Commander`` or ``Castellan``
                from ``client.commanders.get_all()``
            name: The new name; the game's dialog allows 3 to 15 characters
            timeout: Timeout in seconds

        Returns:
            Your commanders and castellans after the rename, from the ``arl`` reply

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        request = RenameCommanderRequest(commander_id=commander_id, name=name)
        return self.request(request, RenameCommanderResponse, timeout=timeout).commander_roster

    def __init__(self, client: EmpireClient) -> None:
        super().__init__(client)
        self._premium_send_lock = threading.Lock()
        # Premium sends this client made since the vip stamped at that time: (vip stamp, count)
        self._own_premium_sends: tuple[float | None, int] = (None, 0)

    def free_premium_commanders(self, now: float | None = None) -> int | None:
        """
        How many more times today the premium commander (``PREMIUM_COMMANDER_ID``) can lead for free.

        Your VIP level's ``free_premium_commanders_per_day`` less those used today, and 0
        while no VIP time runs. It comes from state, kept current by the login data's
        ``vip`` and every ``vip`` the server pushes. A premium send this client made
        (:meth:`premium_send`) counts as used until the next ``vip`` arrives.
        A premium account makes the premium commander free on top of this:
        :meth:`premium_commander_is_free` counts both.

        Example:
            if client.commanders.premium_commander_is_free():
                client.movements.send_support(..., commander_id=PREMIUM_COMMANDER_ID, use_premium_commander=True)

        Args:
            now: Wall-clock time to measure the VIP time left at, ``time.time()`` when not given

        Returns:
            The count, 0 at least, or None before the login data brought your VIP

        Raises:
            GameDataNotLoadedError: VIP time runs and the game data cannot be loaded

        Client: ``CastleVIPData.remainingPremiumCommanders`` (bundle line 47554), the
        ``freePremiumCommandersPerDay`` of ``currentActiveVIPLevel`` (bundle line 47546), which
        is a level with none unless ``vipModeActive`` (bundle line 47550); ``parse_VIP``
        (bundle line 47527) reads ``UPG``, from ``GBDCommand`` (bundle line 129381),
        ``VIPCommand`` (bundle line 129941) and ``SBPCommand`` (bundle line 128320)
        """
        state = self.client.state
        player = state.get_local_player()
        received_at = state.get_last_packet_time("vip")
        if received_at is None:
            return None
        elapsed = (time.time() if now is None else now) - received_at
        if player.vip_time_left - elapsed <= 0:
            return 0
        game_data = self._require_game_data()
        level = game_data.vip_level(player.vip_points)
        per_day = level.free_premium_commanders_per_day if level is not None else 0
        counted_at, own_sends = self._own_premium_sends
        used = player.used_premium_commanders + (own_sends if counted_at == received_at else 0)
        return max(0, per_day - used)

    def premium_commander_is_free(self) -> bool:
        """
        Whether leading with the premium commander now costs no rubies: a premium account
        runs, or :meth:`free_premium_commanders` is 1 or more.

        False when neither is known yet.

        Raises:
            GameDataNotLoadedError: No premium account runs, VIP time does, and the game data cannot be loaded

        Client: ``CastlePostAttackDialog.startAttack`` (bundle line 38360), which sends with a
        free premium commander left and otherwise asks for
        ``getFinalCostsC2(TravelConst.TRAVEL_PREMIUM_COMMANDER_COSTS_C2)`` rubies, 0 while
        ``premiumAccountVO.isActive``; ``TRAVEL_PREMIUM_COMMANDER_COSTS_C2`` is 125 (dll line 19872)
        """
        return self._premium_account_runs() or (self.free_premium_commanders() or 0) >= 1

    def premium_send(
        self, commander_id: int, use_premium_commander: bool, send: Callable[[], _Sent], *, spend_rubies: bool = False
    ) -> _Sent:
        """
        Run ``send`` and return what it returns, refusing it first when the premium commander leads and may cost
        rubies, unless ``spend_rubies``.

        The army sends go through this: ``client.movements.send_support``,
        ``client.movements.send_troops``, ``client.attack.send_attack`` and
        ``client.attack.send_treasure_hunt_attack``. The premium commander
        leads when ``use_premium_commander`` is set or ``commander_id`` is ``PREMIUM_COMMANDER_ID``;
        the client always sends the two together.

        Library policy, not client behaviour: the server sends no ``vip`` with the send's
        reply (``CRACommand``, bundle line 125954; ``CDSCommand``, bundle line 125939; ``CATCommand``,
        bundle line 125924), so a
        premium send that the server accepts while no premium account runs counts as one
        used in :meth:`free_premium_commanders` until the next ``vip`` arrives. The check and the
        send hold one lock, so two premium sends at once cannot both take the last free one.

        Args:
            commander_id: The leader's ``commander_id``
            use_premium_commander: The send's ``BPC`` flag
            send: Sends the request and raises when the server refuses it
            spend_rubies: Send even when the premium commander may cost rubies

        Raises:
            PremiumCommanderCostError: The premium commander leads, :meth:`premium_commander_is_free`
                is False and ``spend_rubies`` is False
            GameDataNotLoadedError: See :meth:`premium_commander_is_free`

        Client: ``CastlePostAttackDialog.startAttack`` (bundle line 38360) sends ``BPC`` 1
        exactly when the selected commander is ``TravelConst.COMMANDER_PREMIUM``
        """
        if not (use_premium_commander or commander_id == PREMIUM_COMMANDER_ID):
            return send()
        with self._premium_send_lock:
            premium_account = self._premium_account_runs()
            if not (spend_rubies or premium_account or (self.free_premium_commanders() or 0) >= 1):
                raise PremiumCommanderCostError(self.free_premium_commanders())
            vip_at = self.client.state.get_last_packet_time("vip")
            sent = send()
            if not premium_account:
                counted_at, own_sends = self._own_premium_sends
                self._own_premium_sends = (vip_at, own_sends + 1 if counted_at == vip_at else 1)
            return sent

    def _premium_account_runs(self) -> bool:
        return self.client.state.get_boosts().is_premium_active()


__all__ = ["CommandersService", "EquipmentService"]
