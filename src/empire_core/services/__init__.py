"""
Service layer for EmpireCore.

Services provide high-level APIs for different game domains (alliance, castle, etc.)
and are auto-registered with the EmpireClient. Each lives in its area package
(``empire_core.alliance.service``, ...); this package holds only the base class
and the registry.

Usage:
    @register_service("alliance")
    class AllianceService(BaseService):
        def send_chat(self, message: str):
            request = AllianceChatMessageRequest.create(message)
            self.send(request)

    # Client auto-discovers services:
    client = EmpireClient(...)
    client.alliance.send_chat("Hello!")
"""

from .base import BaseService, get_registered_services, register_service

__all__ = [
    "BaseService",
    "register_service",
    "get_registered_services",
]
