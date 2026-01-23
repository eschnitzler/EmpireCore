"""
Service layer for EmpireCore.

Services provide high-level APIs for different game domains (alliance, castle, etc.)
and are auto-registered with the EmpireClient.

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

# Import services to trigger registration
from .alliance import AllianceService
from .army import ArmyService
from .base import BaseService, get_registered_services, register_service
from .castle import CastleService
from .lords import LordsService

__all__ = [
    "BaseService",
    "register_service",
    "get_registered_services",
    # Services
    "AllianceService",
    "ArmyService",
    "CastleService",
    "LordsService",
]
