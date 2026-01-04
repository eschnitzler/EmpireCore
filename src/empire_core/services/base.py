"""
Base service class and registration decorator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Type, TypeVar

from empire_core.protocol.models import BaseRequest, BaseResponse, parse_response

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

# Registry of service classes
_service_registry: dict[str, Type["BaseService"]] = {}

T = TypeVar("T", bound="BaseService")


def register_service(name: str) -> Callable[[Type[T]], Type[T]]:
    """
    Decorator to register a service class.

    Usage:
        @register_service("alliance")
        class AllianceService(BaseService):
            ...

    The service will be accessible as client.alliance
    """

    def decorator(cls: Type[T]) -> Type[T]:
        _service_registry[name] = cls
        cls._service_name = name
        return cls

    return decorator


def get_registered_services() -> dict[str, Type["BaseService"]]:
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

        Args:
            request: The request model to send
            wait: Whether to wait for a response
            timeout: Timeout in seconds when waiting

        Returns:
            The parsed response if wait=True, otherwise None
        """
        packet = request.to_packet(zone=self.zone)
        self.client.connection.send(packet)

        if wait:
            command = request.get_command()
            try:
                response_packet = self.client.connection.wait_for(command, timeout=timeout)
                if response_packet and isinstance(response_packet.payload, dict):
                    return parse_response(command, response_packet.payload)
            except Exception:
                return None

        return None

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
