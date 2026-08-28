"""
Skills service: a general's unlocked skills, and the player's own.

Both feed wave sizing. A general's skills widen the flanks whatever the target
is; the player's legend skills widen them further and add waves, but only when
both sides are at the level cap.
"""

from __future__ import annotations

import logging

from empire_core.protocol.models import (
    GetGeneralsRequest,
    GetGeneralsResponse,
    GetSkillsRequest,
    GetSkillsResponse,
)

from .base import BaseService, register_service

logger = logging.getLogger(__name__)


@register_service("skills")
class SkillsService(BaseService):
    """
    Service for generals and player skills.

    Accessible via client.skills after auto-registration.
    """

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
