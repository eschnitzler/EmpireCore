"""Commanders and castellans, their equipment, and generals and skills.

- CommandersService reads and renames the player's commanders and castellans.
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
from collections.abc import Callable, Iterable

from empire_core.commanders.models.equipment import (
    EquipEquipmentRequest,
    Equipment,
    GetEquipmentInventoryRequest,
    GetEquipmentInventoryResponse,
)
from empire_core.commanders.models.roster import (
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
        self._skill_list_callbacks.append(callback)

    def remove_skill_list_callback(self, callback: Callable[[SkillList], None]) -> None:
        """Remove a callback registered with :meth:`on_skill_list`; a no-op if it is not registered."""
        try:
            self._skill_list_callbacks.remove(callback)
        except ValueError:
            pass

    def _handle_skill_list(self, response: BaseResponse) -> None:
        if isinstance(response, GetSkillsResponse):
            skills: SkillList | None = response
        elif isinstance(response, ObjectUpdateEvent):
            skills = response.skills
        else:
            return
        if skills is None:
            return
        for callback in list(self._skill_list_callbacks):
            try:
                callback(skills)
            except Exception:
                logger.exception("Skill list callback error")
