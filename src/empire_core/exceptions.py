"""Typed exceptions for EmpireCore.

Failure modes are kept distinct so callers can react to them individually:

- ``EmpireTimeoutError``: the server did not answer in time.
- ``ConnectionClosedError``: the connection dropped while waiting.
- ``CommandError``: the server answered with a non-zero error code.
"""

from empire_core.protocol.errors import GGEError


class EmpireError(Exception):
    """Base class for all EmpireCore exceptions."""


class NetworkError(EmpireError):
    """Raised when a network operation fails."""


class ConnectionClosedError(NetworkError):
    """Raised when the connection closes while an operation is in flight."""


class LoginError(EmpireError):
    """Raised when the login sequence fails."""


class LoginCooldownError(LoginError):
    """Raised when the server rejects login due to rate limiting."""

    def __init__(self, cooldown: int, message: str = "Login cooldown active"):
        self.cooldown = cooldown
        super().__init__(f"{message}: Retry in {cooldown}s")


class PacketError(EmpireError):
    """Raised when packet parsing fails."""


class EmpireTimeoutError(EmpireError, TimeoutError):
    """Raised when an operation times out.

    Subclasses the builtin ``TimeoutError`` so ``except TimeoutError``
    catches it too.
    """


class CommandError(EmpireError):
    """Raised when the server responds to a command with a non-zero error code."""

    def __init__(self, command: str, code: int):
        self.command = command
        self.code = code
        super().__init__(f"Server error {GGEError.from_code(code).name} ({code}) for command '{command}'")


class ActionError(EmpireError):
    """Raised when a game action fails."""
