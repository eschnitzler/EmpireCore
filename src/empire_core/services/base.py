"""
Base service class and registration decorator.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from empire_core.exceptions import CommandError
from empire_core.protocol.models import BaseRequest, BaseResponse

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)

# Registry of service classes
_service_registry: dict[str, type["BaseService"]] = {}

T = TypeVar("T", bound="BaseService")
R = TypeVar("R", bound=BaseResponse)


def register_service(name: str) -> Callable[[type[T]], type[T]]:
    """
    Decorator to register a service class.

    Usage:
        @register_service("alliance")
        class AllianceService(BaseService):
            ...

    The service will be accessible as client.alliance
    """

    def decorator(cls: type[T]) -> type[T]:
        _service_registry[name] = cls
        cls._service_name = name
        return cls

    return decorator


def get_registered_services() -> dict[str, type["BaseService"]]:
    """Get all registered service classes."""
    return _service_registry.copy()


class BaseService:
    """
    Base class for all services.

    Services provide high-level APIs for game domains and use
    protocol models for type-safe request/response handling.
    """

    _service_name: str = ""

    def __init__(self, client: "EmpireClient") -> None:
        self.client = client

    @property
    def zone(self) -> str:
        """Get the game zone from client config."""
        return self.client.config.default_zone

    def send(self, request: BaseRequest, wait: bool = False, timeout: float = 5.0) -> BaseResponse | None:
        """
        Send a request to the server.

        With ``wait=True``, raises the same typed exceptions as
        ``EmpireClient.send`` (CommandError, EmpireTimeoutError, ...).
        """
        return self.client.send(request, wait=wait, timeout=timeout)

    def request(self, request: BaseRequest, response_type: type[R], timeout: float = 5.0) -> R:
        """
        Send a request and return its typed response.

        Raises:
            CommandError: The server answered with a non-zero error code
            EmpireTimeoutError / ConnectionClosedError / NetworkError: transport failures
            PacketError: The response could not be parsed as ``response_type``
        """
        return self.client.request(request, response_type, timeout=timeout)

    def execute(self, request: BaseRequest, timeout: float = 5.0) -> bool:
        """
        Send an action request and report whether the server accepted it.

        Returns False when the server rejects the action with an error code
        (logged at warning level). Transport failures (timeout, disconnect)
        still raise, so infrastructure problems are never mistaken for a
        game-rule rejection.
        """
        try:
            self.client.send(request, wait=True, timeout=timeout)
            return True
        except CommandError as e:
            logger.warning(f"Action '{request.get_command()}' rejected: {e}")
            return False

    def on_response(self, command: str, handler: Callable[[BaseResponse], None]) -> None:
        """
        Register a handler for a specific response type.

        Handlers are registered with the client for efficient routing.
        Only commands with registered handlers will be parsed.

        Args:
            command: The command code to handle (e.g., "acm")
            handler: Callback function that receives the parsed response
        """
        self.client._register_handler(command, handler)


__all__ = [
    "BaseService",
    "register_service",
    "get_registered_services",
]
