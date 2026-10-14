"""Commanders and castellans, their generals, and their equipment.

- CommandersService reads and renames the player's commanders and castellans, says
  whether the premium commander leads for free, and changes generals: assigning one
  to a commander, choosing its abilities, unlocking and resetting its skills, and
  feeding it xp items. A general's skills widen the flanks whatever the target is.
- EquipmentService reads the equipment inventory and moves items on and off
  commanders and castellans.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from empire_core.commanders.models.equipment import (
    EquipEquipmentRequest,
    Equipment,
    GetEquipmentInventoryRequest,
    GetEquipmentInventoryResponse,
)
from empire_core.commanders.models.roster import (
    PREMIUM_COMMANDER_ID,
    Castellan,
    Commander,
    CommanderRoster,
    GetCommandersRequest,
    GetCommandersResponse,
    RenameCommanderRequest,
    RenameCommanderResponse,
    SelectedAbility,
)
from empire_core.commanders.models.skills import (
    AddGeneralXpRequest,
    AssignGeneralRequest,
    AssignGeneralResponse,
    GetGeneralsRequest,
    GetGeneralsResponse,
    OwnedGeneral,
    ResetGeneralSkillsRequest,
    SetGeneralAbilitiesRequest,
    UnlockGeneralSkillRequest,
)
from empire_core.exceptions import PremiumCommanderCostError
from empire_core.services.base import BaseService

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient
    from empire_core.commanders.models.inventory import GemInventoryResponse, InventorySpace, NewRelicsResponse


class CommandersService(BaseService):
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

        Only as fresh as the movements in state.

        Raises:
            StateNotLoadedError: No login has brought the roster

        Client: ``LordVO.isAvailableForMovement`` (bundle line 26607), false while any map movement
        that ``isMyMovement`` (``BasicMapmovementVO``, bundle line 19436) has the lord as its ``lordVO``,
        whichever way it travels
        """
        movements = self.client.state.get_all_movements()
        leading = {m.commander.commander_id for m in movements if m.is_mine and m.commander is not None}
        return [c for c in self.roster.commanders if c.commander_id in leading]

    @property
    def idle_commanders(self) -> list[Commander]:
        """
        The commanders free to lead an army: those not in :attr:`travelling_commanders`; nothing is sent.

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

    def get_generals(self, *, timeout: float = 5.0) -> list[OwnedGeneral]:
        """
        Every general the player owns, with the skills each has unlocked.

        Args:
            timeout: Timeout in seconds

        Returns:
            Your generals, from the ``gie`` reply

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.request(GetGeneralsRequest(), GetGeneralsResponse, timeout=timeout).generals

    def assign_general(self, commander_id: int, general_id: int, *, timeout: float = 5.0) -> CommanderRoster:
        """
        Assign a general to a commander; ``general_id=-1`` takes its general away.

        Args:
            commander_id: A ``Commander.commander_id`` from
                ``client.commanders.get_commanders()``
            general_id: An ``OwnedGeneral.general_id`` from :meth:`get_generals`;
                ``GameData.require().general(name)`` finds its ``generalID`` by name
            timeout: Timeout in seconds

        Returns:
            Your commanders and castellans after the change, from the ``gla`` reply

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        request = AssignGeneralRequest(commander_id=commander_id, general_id=general_id)
        return self.request(request, AssignGeneralResponse, timeout=timeout).commander_roster

    def set_general_abilities(
        self, general_id: int, abilities: Iterable[tuple[int, int | None]], *, timeout: float = 5.0
    ) -> None:
        """
        Choose a general's abilities.

        Args:
            general_id: An ``OwnedGeneral.general_id`` from :meth:`get_generals`;
                ``GameData.require().general(name)`` finds its ``generalID`` by name
            abilities: ``(slot_id, ability_id)`` pairs, ``-1`` or ``None`` to clear a slot.
                The client sends every slot it shows. An ability id comes from
                ``GameData.require().general_ability(name, level)``
            timeout: Timeout in seconds
        """
        slots = [SelectedAbility(slot_id=slot_id, ability_id=ability_id) for slot_id, ability_id in abilities]
        self.execute(SetGeneralAbilitiesRequest(general_id=general_id, abilities=slots), timeout=timeout)

    def unlock_general_skill(self, skill_id: int, *, timeout: float = 5.0) -> None:
        """
        Unlock a general skill; the skill id names the general.

        The general's new skills arrive with the next ``gie``.

        Args:
            skill_id: The skill level's ``skillID``, from
                ``GameData.require().general_skill(general_id, name, level)``
                (``GeneralVO.unlockSkill``, bundle line 26773)
            timeout: Timeout in seconds
        """
        self.execute(UnlockGeneralSkillRequest(skill_id=skill_id), timeout=timeout)

    def reset_general_skills(self, general_id: int, *, timeout: float = 5.0) -> None:
        """
        Reset a general's skill tree.

        Args:
            general_id: An ``OwnedGeneral.general_id`` from :meth:`get_generals`;
                ``GameData.require().general(name)`` finds its ``generalID`` by name
            timeout: Timeout in seconds
        """
        self.execute(ResetGeneralSkillsRequest(general_id=general_id), timeout=timeout)

    def add_general_xp(self, general_id: int, currency_id: int, amount: int, *, timeout: float = 5.0) -> None:
        """
        Feed a general xp items.

        Args:
            general_id: An ``OwnedGeneral.general_id`` from :meth:`get_generals`;
                ``GameData.require().general(name)`` finds its ``generalID`` by name
            currency_id: The xp item's ``currencyID``, e.g.
                ``GameData.require().currency("GXP1").currency_id``
                (``GeneralsLevelUpDialogListItem.sendXPSelected``, bundle line 74485)
            amount: How many of the item to use
            timeout: Timeout in seconds
        """
        self.execute(
            AddGeneralXpRequest(general_id=general_id, currency_id=currency_id, amount=amount), timeout=timeout
        )

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
        self, commander_id: int, use_premium_commander: bool, send: Callable[[], None], *, spend_rubies: bool = False
    ) -> None:
        """
        Run ``send``, refusing it first when the premium commander leads and may cost rubies, unless ``spend_rubies``.

        The army sends go through this: ``client.movements.send_support``,
        ``client.movements.send_troops`` and ``client.attack.send_attack``. The premium commander
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
            send()
            return
        with self._premium_send_lock:
            premium_account = self._premium_account_runs()
            if not (spend_rubies or premium_account or (self.free_premium_commanders() or 0) >= 1):
                raise PremiumCommanderCostError(self.free_premium_commanders())
            vip_at = self.client.state.get_last_packet_time("vip")
            send()
            if not premium_account:
                counted_at, own_sends = self._own_premium_sends
                self._own_premium_sends = (vip_at, own_sends + 1 if counted_at == vip_at else 1)

    def _premium_account_runs(self) -> bool:
        return self.client.state.get_boosts().is_premium_active()


class EquipmentService(BaseService):
    """
    The equipment inventory, and putting items on and off commanders and castellans.

    Reached as client.equipment. What a leader
    wears comes with ``client.commanders`` (``gli`` ``EQ``).
    """

    @property
    def gems(self) -> GemInventoryResponse | None:
        """The gems and relic gems in your inventory; None until a ``ggm`` or ``gec`` arrived."""
        return self.client.state.get_gems()

    @property
    def inventory_space(self) -> InventorySpace | None:
        """The equipment and gem inventory space, from the last ``esl``; None until one arrived."""
        return self.client.state.get_inventory_space()

    @property
    def new_relics(self) -> NewRelicsResponse:
        """Whether new relics wait to be seen, from the last ``nrf``.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_new_relics()

    def get_inventory(self, *, timeout: float = 5.0) -> list[Equipment]:
        """
        The items in the player's inventory, the ones no leader wears.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.request(GetEquipmentInventoryRequest(), GetEquipmentInventoryResponse, timeout=timeout).items

    def equip(self, equipment_id: int, commander_id: int, *, timeout: float = 5.0) -> None:
        """
        Put an item on a commander or castellan.

        The client moves an item between leaders by taking it off the first
        and then putting it on the second. The reply carries no data; re-read
        ``client.commanders.get_all()`` to see the change.

        Args:
            equipment_id: An item in the inventory, its ``Equipment.equipment_id``
                from :meth:`get_inventory`
            commander_id: The leader's ``commander_id``, a ``Commander`` or ``Castellan``
                from ``client.commanders.get_all()``
            timeout: Timeout in seconds
        """
        request = EquipEquipmentRequest(equipment_id=equipment_id, commander_id=commander_id, equip=1)
        self.execute(request, timeout=timeout)

    def unequip(self, equipment_id: int, commander_id: int, *, timeout: float = 5.0) -> None:
        """
        Take an item off a commander or castellan.

        Args:
            equipment_id: An item the leader wears, the ``Equipment.equipment_id`` of an
                entry in its ``equipment`` list from ``client.commanders.get_all()``
            commander_id: The leader's ``commander_id``, a ``Commander`` or ``Castellan``
                from ``client.commanders.get_all()``
            timeout: Timeout in seconds
        """
        request = EquipEquipmentRequest(equipment_id=equipment_id, commander_id=commander_id, equip=0)
        self.execute(request, timeout=timeout)
