"""
Lords service for EmpireCore.

Provides APIs for managing commanders/lords.
"""

from __future__ import annotations

import logging

from empire_core.protocol.models import GetLordsRequest, GetLordsResponse, Lord

from .base import BaseService, register_service

logger = logging.getLogger(__name__)


@register_service("lords")
class LordsService(BaseService):
    """
    Service for lords/commanders operations.

    Accessible via client.lords after auto-registration.
    """

    def get_lords(self, timeout: float = 5.0) -> list[Lord]:
        """
        Get all available lords/commanders.

        Args:
            timeout: Timeout in seconds

        Returns:
            List of Lord objects

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError on failure
        """
        return self.request(GetLordsRequest(), GetLordsResponse, timeout=timeout).lords
