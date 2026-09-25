"""
Skills service: a general's unlocked skills, and the player's own.

Both feed wave sizing. A general's skills widen the flanks whatever the target
is; the player's legend skills widen them further and add waves, but only when
both sides are at the level cap.

The service also changes generals: assigning one to a commander, choosing its
abilities, unlocking and resetting its skills, and feeding it xp items.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from empire_core.protocol.models import (
    AddGeneralXpRequest,
    AssignGeneralRequest,
    AssignGeneralResponse,
    BaseResponse,
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

from .base import BaseService, register_service

logger = logging.getLogger(__name__)


@register_service("skills")
class SkillsService(BaseService):
    """
    Service for generals and player skills.

    Accessible via client.skills after auto-registration.
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
            CommandError / EmpireTimeoutError / ConnectionClosedError on failure
        """
        return self.request(GetGeneralsRequest(), GetGeneralsResponse, timeout=timeout)

    def assign_general(self, commander_id: int, general_id: int, timeout: float = 5.0) -> AssignGeneralResponse:
        """
        Assign a general to a commander; ``general_id=-1`` takes its general away.

        Returns:
            The ``gla`` response, with the commander list after the change

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError on failure
        """
        return self.request(
            AssignGeneralRequest(LID=commander_id, GID=general_id),
            AssignGeneralResponse,
            timeout=timeout,
        )

    def set_abilities(self, general_id: int, abilities: Iterable[tuple[int, int]], timeout: float = 5.0) -> bool:
        """
        Choose a general's abilities.

        Args:
            general_id: The general
            abilities: ``(slot_id, ability_id)`` pairs, ``-1`` to clear a slot.
                The client sends every slot it shows.
            timeout: Timeout in seconds

        Returns:
            True if the server accepted the change
        """
        pairs = [[slot_id, ability_id] for slot_id, ability_id in abilities]
        return self.execute(SetGeneralAbilitiesRequest(GID=general_id, SAIDS=pairs), timeout=timeout)

    def unlock_skill(self, skill_id: int, timeout: float = 5.0) -> bool:
        """
        Unlock a general skill; the skill id names the general.

        The general's new skills arrive with the next ``gie``.

        Returns:
            True if the server accepted the unlock
        """
        return self.execute(UnlockGeneralSkillRequest(ID=skill_id), timeout=timeout)

    def reset_skills(self, general_id: int, timeout: float = 5.0) -> bool:
        """
        Reset a general's skill tree.

        Returns:
            True if the server accepted the reset
        """
        return self.execute(ResetGeneralSkillsRequest(GID=general_id), timeout=timeout)

    def add_xp(self, general_id: int, currency_id: int, amount: int, timeout: float = 5.0) -> bool:
        """
        Feed a general xp items.

        Args:
            general_id: The general
            currency_id: The xp item, a currency
            amount: How many of the item to use
            timeout: Timeout in seconds

        Returns:
            True if the server accepted the items
        """
        return self.execute(AddGeneralXpRequest(GID=general_id, CID=currency_id, AMT=amount), timeout=timeout)

    def get_skills(self, timeout: float = 5.0) -> GetSkillsResponse:
        """
        The player's legend and sceat skills.

        Args:
            timeout: Timeout in seconds

        Returns:
            The ``skl`` response

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError on failure
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
