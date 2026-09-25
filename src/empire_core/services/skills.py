"""
Skills service: a general's unlocked skills, and the player's own.

Both feed wave sizing. A general's skills widen the flanks whatever the target
is; the player's legend skills widen them further and add waves, but only when
both sides are at the level cap.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from empire_core.protocol.models import (
    BaseResponse,
    GetGeneralsRequest,
    GetGeneralsResponse,
    GetSkillsRequest,
    GetSkillsResponse,
    ObjectUpdateEvent,
    SkillList,
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
