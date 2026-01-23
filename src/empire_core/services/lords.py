"""
Lords service for EmpireCore.

Provides APIs for managing commanders/lords.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from empire_core.protocol.models import GetLordsRequest, GetLordsResponse, Lord

from .base import BaseService, register_service

if TYPE_CHECKING:
    pass

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
        """
        try:
            request = GetLordsRequest()
            response = self.send(request, wait=True, timeout=timeout)

            if isinstance(response, GetLordsResponse):
                return response.lords

            # If response is None, it means timeout or error
            if response is None:
                logger.debug("GetLordsRequest returned None (timeout or error)")
                return []

            logger.warning(f"Unexpected response type for get_lords: {type(response)}")
            return []
        except Exception as e:
            logger.error(f"Error fetching lords: {e}")
            return []
