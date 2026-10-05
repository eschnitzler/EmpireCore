"""Commanders and castellans, their equipment, and generals and skills.

- CommandersService reads and renames the player's commanders and castellans, and
  says whether the premium commander leads for free.
- EquipmentService reads the equipment inventory and moves items on and off
  commanders and castellans.
- SkillsService reads a general's unlocked skills and the player's own, and
  changes generals: assigning one to a commander, choosing its abilities,
  unlocking and resetting its skills, and feeding it xp items. A general's
  skills widen the flanks whatever the target is; the player's legend skills
  widen them further and add waves, but only when both sides are at the level cap.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable

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
    GetCommandersRequest,
    GetCommandersResponse,
    RenameCommanderRequest,
    RenameCommanderResponse,
)
from empire_core.commanders.models.skills import (
    AddGeneralXpRequest,
    AssignGeneralRequest,
    AssignGeneralResponse,
    GetGeneralsRequest,
    GetGeneralsResponse,
    GetSkillsRequest,
    GetSkillsResponse,
    ObjectUpdateEvent,
    ResetGeneralSkillsRequest,
    SetGeneralAbilitiesRequest,
    SkillList,
    UnlockGeneralSkillRequest,
)
from empire_core.exceptions import GameDataNotLoadedError, PremiumCommanderCostError
from empire_core.protocol.base import BaseResponse
from empire_core.services.base import BaseService

logger = logging.getLogger(__name__)


class CommandersService(BaseService):
    """
    Your commanders and castellans, and renaming them.

    Reached as client.commanders.
    """

    def get_all(self, timeout: float = 5.0) -> GetCommandersResponse:
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

    def get_commanders(self, timeout: float = 5.0) -> list[Commander]:
        """
        Get all available commanders.

        Args:
            timeout: Timeout in seconds

        Returns:
            List of Commander objects

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.get_all(timeout=timeout).commanders

    def get_castellans(self, timeout: float = 5.0) -> list[Castellan]:
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

    def rename(self, commander_id: int, name: str, timeout: float = 5.0) -> RenameCommanderResponse:
        """
        Rename a commander or castellan.

        Args:
            commander_id: The leader's ``commander_id``, a ``Commander`` or ``Castellan``
                from ``client.commanders.get_all()``
            name: The new name; the game's dialog allows 3 to 15 characters
            timeout: Timeout in seconds

        Returns:
            The arl response, which carries the updated commander list

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.request(
            RenameCommanderRequest(commander_id=commander_id, name=name), RenameCommanderResponse, timeout=timeout
        )

    def __init__(self, client) -> None:
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
                client.castle.send_support(..., commander_id=PREMIUM_COMMANDER_ID, use_premium_commander=True)

        Args:
            now: Wall-clock time to measure the VIP time left at, ``time.time()`` when not given

        Returns:
            The count, 0 at least, or None before the login data brought your VIP

        Raises:
            GameDataNotLoadedError: VIP time runs and ``client.load_game_data()`` has not been called

        Client: ``CastleVIPData.remainingPremiumCommanders`` (bundle line 47554), the
        ``freePremiumCommandersPerDay`` of ``currentActiveVIPLevel`` (bundle line 47546), which
        is a level with none unless ``vipModeActive`` (bundle line 47550); ``parse_VIP``
        (bundle line 47527) reads ``UPG``, from ``GBDCommand`` (bundle line 129381),
        ``VIPCommand`` (bundle line 129941) and ``SBPCommand`` (bundle line 128320)
        """
        state = self.client.state
        player = state.get_local_player()
        received_at = state.get_last_packet_time("vip")
        if player is None or received_at is None:
            return None
        elapsed = (time.time() if now is None else now) - received_at
        if player.vip_time_left - elapsed <= 0:
            return 0
        game_data = self.client.game_data
        if game_data is None:
            raise GameDataNotLoadedError("VIP levels need the items payload: call client.load_game_data() first")
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
            GameDataNotLoadedError: No premium account runs, VIP time does, and
                ``client.load_game_data()`` has not been called

        Client: ``CastlePostAttackDialog.startAttack`` (bundle line 38360), which sends with a
        free premium commander left and otherwise asks for
        ``getFinalCostsC2(TravelConst.TRAVEL_PREMIUM_COMMANDER_COSTS_C2)`` rubies, 0 while
        ``premiumAccountVO.isActive``; ``TRAVEL_PREMIUM_COMMANDER_COSTS_C2`` is 125 (dll line 19872)
        """
        return self._premium_account_runs() or (self.free_premium_commanders() or 0) >= 1

    def premium_send(
        self, commander_id: int, use_premium_commander: bool, send: Callable[[], bool], *, spend_rubies: bool
    ) -> bool:
        """
        Run ``send``, refusing it first when the premium commander leads and may cost rubies, unless ``spend_rubies``.

        The army sends go through this: ``client.castle.send_support``,
        ``client.castle.send_troops`` and ``client.attack.send_attack``. The premium commander
        leads when ``use_premium_commander`` is set or ``commander_id`` is ``PREMIUM_COMMANDER_ID``;
        the client always sends the two together.

        Library policy, not client behaviour: the server sends no ``vip`` with the send's
        reply (``CRACommand``, bundle line 125954; ``CDSCommand``, bundle line 125939; ``CATCommand``,
        bundle line 125924), so a
        premium send that ``send`` reports accepted while no premium account runs counts as one
        used in :meth:`free_premium_commanders` until the next ``vip`` arrives. The check and the
        send hold one lock, so two premium sends at once cannot both take the last free one.

        Args:
            commander_id: The leader's ``commander_id``
            use_premium_commander: The send's ``BPC`` flag
            send: Sends the request; True when the server accepted it
            spend_rubies: Send even when the premium commander may cost rubies

        Returns:
            What ``send`` returned

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
            accepted = send()
            if accepted and not premium_account:
                counted_at, own_sends = self._own_premium_sends
                self._own_premium_sends = (vip_at, own_sends + 1 if counted_at == vip_at else 1)
            return accepted

    def _premium_account_runs(self) -> bool:
        boosts = self.client.state.get_boosts()
        return boosts is not None and boosts.is_premium_active()


class EquipmentService(BaseService):
    """
    The equipment inventory, and putting items on and off commanders and castellans.

    Reached as client.equipment. What a leader
    wears comes with ``client.commanders`` (``gli`` ``EQ``).
    """

    def get_inventory(self, timeout: float = 5.0) -> list[Equipment]:
        """
        The items in the player's inventory, the ones no leader wears.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.request(GetEquipmentInventoryRequest(), GetEquipmentInventoryResponse, timeout=timeout).items

    def equip(self, equipment_id: int, commander_id: int, timeout: float = 5.0) -> bool:
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

        Returns:
            False when the server rejects the request
        """
        request = EquipEquipmentRequest(equipment_id=equipment_id, commander_id=commander_id, equip=1)
        return self.execute(request, timeout=timeout)

    def unequip(self, equipment_id: int, commander_id: int, timeout: float = 5.0) -> bool:
        """
        Take an item off a commander or castellan.

        Args:
            equipment_id: An item the leader wears, the ``Equipment.equipment_id`` of an
                entry in its ``equipment`` list from ``client.commanders.get_all()``
            commander_id: The leader's ``commander_id``, a ``Commander`` or ``Castellan``
                from ``client.commanders.get_all()``
            timeout: Timeout in seconds

        Returns:
            False when the server rejects the request
        """
        request = EquipEquipmentRequest(equipment_id=equipment_id, commander_id=commander_id, equip=0)
        return self.execute(request, timeout=timeout)


class SkillsService(BaseService):
    """
    Generals, their abilities and skills, and the player's legend and sceat skills.

    Reached as client.skills.
    """

    def __init__(self, client) -> None:
        super().__init__(client)
        self._callbacks_lock = threading.Lock()
        self._skill_list_callbacks: list[Callable[[SkillList], None]] = []
        self.on_response("skl", self._handle_skill_list)
        self.on_response("ego", self._handle_skill_list)

    def get_generals(self, timeout: float = 5.0) -> GetGeneralsResponse:
        """
        Every general the player owns, with the skills each has unlocked.

        Args:
            timeout: Timeout in seconds

        Returns:
            The ``gie`` response

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.request(GetGeneralsRequest(), GetGeneralsResponse, timeout=timeout)

    def assign_general(self, commander_id: int, general_id: int, timeout: float = 5.0) -> AssignGeneralResponse:
        """
        Assign a general to a commander; ``general_id=-1`` takes its general away.

        Args:
            commander_id: A ``Commander.commander_id`` from
                ``client.commanders.get_commanders()``
            general_id: An owned general's ``General.general_id`` from :meth:`get_generals`;
                ``client.game_data.general(name)`` finds its ``generalID`` by name
            timeout: Timeout in seconds

        Returns:
            The ``gla`` response, with the commander list after the change

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.request(
            AssignGeneralRequest(commander_id=commander_id, general_id=general_id),
            AssignGeneralResponse,
            timeout=timeout,
        )

    def set_abilities(self, general_id: int, abilities: Iterable[tuple[int, int]], timeout: float = 5.0) -> bool:
        """
        Choose a general's abilities.

        Args:
            general_id: An owned general's ``General.general_id`` from :meth:`get_generals`;
                ``client.game_data.general(name)`` finds its ``generalID`` by name
            abilities: ``(slot_id, ability_id)`` pairs, ``-1`` to clear a slot.
                The client sends every slot it shows. An ability id comes from
                ``client.game_data.general_ability(name, level)``
            timeout: Timeout in seconds

        Returns:
            True if the server accepted the change
        """
        pairs = [[slot_id, ability_id] for slot_id, ability_id in abilities]
        return self.execute(SetGeneralAbilitiesRequest(general_id=general_id, abilities=pairs), timeout=timeout)

    def unlock_skill(self, skill_id: int, timeout: float = 5.0) -> bool:
        """
        Unlock a general skill; the skill id names the general.

        The general's new skills arrive with the next ``gie``.

        Args:
            skill_id: The skill level's ``skillID``, from
                ``client.game_data.general_skill(general_id, name, level)``
                (``GeneralVO.unlockSkill``, bundle line 26773)
            timeout: Timeout in seconds

        Returns:
            True if the server accepted the unlock
        """
        return self.execute(UnlockGeneralSkillRequest(skill_id=skill_id), timeout=timeout)

    def reset_skills(self, general_id: int, timeout: float = 5.0) -> bool:
        """
        Reset a general's skill tree.

        Args:
            general_id: An owned general's ``General.general_id`` from :meth:`get_generals`;
                ``client.game_data.general(name)`` finds its ``generalID`` by name
            timeout: Timeout in seconds

        Returns:
            True if the server accepted the reset
        """
        return self.execute(ResetGeneralSkillsRequest(general_id=general_id), timeout=timeout)

    def add_xp(self, general_id: int, currency_id: int, amount: int, timeout: float = 5.0) -> bool:
        """
        Feed a general xp items.

        Args:
            general_id: An owned general's ``General.general_id`` from :meth:`get_generals`;
                ``client.game_data.general(name)`` finds its ``generalID`` by name
            currency_id: The xp item's ``currencyID``, e.g.
                ``client.game_data.currency("GXP1").currency_id``
                (``GeneralsLevelUpDialogListItem.sendXPSelected``, bundle line 74485)
            amount: How many of the item to use
            timeout: Timeout in seconds

        Returns:
            True if the server accepted the items
        """
        return self.execute(
            AddGeneralXpRequest(general_id=general_id, currency_id=currency_id, amount=amount), timeout=timeout
        )

    def get_skills(self, timeout: float = 5.0) -> GetSkillsResponse:
        """
        The player's legend and sceat skills.

        Args:
            timeout: Timeout in seconds

        Returns:
            The ``skl`` response

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: The request failed
        """
        return self.request(GetSkillsRequest(), GetSkillsResponse, timeout=timeout)

    def on_skill_list(self, callback: Callable[[SkillList], None]) -> None:
        """
        Register a callback for every skill list the server sends.

        That is each ``skl`` packet, including the reply to :meth:`get_skills`,
        and the ``skl`` block of an ``ego`` push.

        Client: ``SKLCommand.executeCommand`` (bundle line 129742) and
        ``EGOCommand.executeCommand`` (bundle line 122801) both call ``parse_SKL``.
        """
        with self._callbacks_lock:
            self._skill_list_callbacks.append(callback)

    def remove_skill_list_callback(self, callback: Callable[[SkillList], None]) -> None:
        """Remove a callback registered with :meth:`on_skill_list`; a no-op if it is not registered."""
        with self._callbacks_lock:
            if callback in self._skill_list_callbacks:
                self._skill_list_callbacks.remove(callback)

    def _handle_skill_list(self, response: BaseResponse) -> None:
        if isinstance(response, GetSkillsResponse):
            skills: SkillList | None = response
        elif isinstance(response, ObjectUpdateEvent):
            skills = response.skills
        else:
            return
        if skills is None:
            return
        with self._callbacks_lock:
            callbacks = list(self._skill_list_callbacks)
        for callback in callbacks:
            try:
                callback(skills)
            except Exception:
                logger.exception("Skill list callback error")
