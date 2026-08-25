"""
Commanders service for EmpireCore.

Provides APIs for reading the player's commanders and castellans.
"""

from __future__ import annotations

import logging

from empire_core.protocol.models import (
    Castellan,
    Commander,
    GetCommandersRequest,
    GetCommandersResponse,
)

from .base import BaseService, register_service

logger = logging.getLogger(__name__)


@register_service("commanders")
class CommandersService(BaseService):
    """
    Service for commander operations.

    Accessible via client.commanders after auto-registration.
    """

    def get_all(self, timeout: float = 5.0) -> GetCommandersResponse:
        """
        Get commanders and castellans in one request.

        Args:
            timeout: Timeout in seconds

        Returns:
            The full gli response

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError on failure
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
            CommandError / EmpireTimeoutError / ConnectionClosedError on failure
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
            CommandError / EmpireTimeoutError / ConnectionClosedError on failure
        """
        return self.get_all(timeout=timeout).castellans
