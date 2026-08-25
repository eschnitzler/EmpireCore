"""Typed exceptions for EmpireCore.

Failure modes are kept distinct so callers can react to them individually:

- ``EmpireTimeoutError``: the server did not answer in time.
- ``ConnectionClosedError``: the connection dropped while waiting.
- ``CommandError``: the server answered with a non-zero error code.
- ``GameDataNotLoadedError``: an API needed the items payload; load it first.
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


class GameDataNotLoadedError(EmpireError):
    """
    Raised when an API needs the static game data and it has not been loaded.

    Call :meth:`EmpireClient.load_game_data` first: it is explicit because the
    items payload is a large download.
    """


class CommandError(EmpireError):
    """Raised when the server responds to a command with a non-zero error code.

    Attributes:
        command: the command that failed (e.g. ``"gaa"``).
        code: the raw numeric status code sent by the server.
        error: the matching :class:`~empire_core.protocol.errors.GGEError`
            member, or ``None`` when the server sent a code this library does
            not know yet. Branch on it instead of on magic numbers::

                except CommandError as e:
                    if e.error is GGEError.NOT_ENOUGH_RESOURCES:
                        ...

            ``GGEError.from_code()`` deliberately is not used here: it collapses
            unrecognised codes to ``GENERAL_ERROR``, which would mislabel new
            server codes as a generic failure.
    """

    def __init__(self, command: str, code: int):
        self.command = command
        self.code = code
        try:
            self.error: GGEError | None = GGEError(code)
        except ValueError:
            self.error = None
        name = self.error.name if self.error is not None else "UNKNOWN_ERROR"
        super().__init__(f"Server error {name} ({code}) for command '{command}'")
