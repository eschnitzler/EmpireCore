"""Typed exceptions for EmpireCore.

Failure modes are kept distinct so callers can react to them individually:

- ``EmpireTimeoutError``: the server did not answer in time.
- ``ConnectionClosedError``: the connection dropped while waiting.
- ``CommandError``: the server answered with a non-zero error code.
- ``GameDataNotLoadedError``: an API needed the items payload; load it first.
"""

from typing import Any

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
            unrecognized codes to ``GENERAL_ERROR``, which would mislabel new
            server codes as a generic failure.
        payload: the error reply's payload when the server sent one. Some
            commands explain the error in it, e.g. ``cra`` for
            ``ATTACK_IN_PROGRESS``; see ``CreateAttackResponse``.
    """

    def __init__(self, command: str, code: int, payload: Any = None):
        self.command = command
        self.code = code
        self.payload = payload
        try:
            self.error: GGEError | None = GGEError(code)
        except ValueError:
            self.error = None
        name = self.error.name if self.error is not None else "UNKNOWN_ERROR"
        super().__init__(f"Server error {name} ({code}) for command '{command}'")


class AttackInProgressError(CommandError):
    """The server refused an attack with ``ATTACK_IN_PROGRESS`` (234): one of yours is already on its way there.

    The client shows how long until that attack arrives and how big it is,
    and offers to send anyway, which resends the same attack with ``FC`` 1;
    ``send_attack(send_anyway=True)`` does the same.

    Attributes:
        arrival_seconds: seconds until the attack already on its way arrives (``TS``), or None
        army_size: the size of that attack (``AS``), or None

    Client: ``CRACommand.executeCommand``, ``CastlePostPostAttackFactionDialog.onClick``.
    """

    def __init__(self, command: str, code: int, payload: Any = None):
        super().__init__(command, code, payload)
        details = payload if isinstance(payload, dict) else {}
        self.arrival_seconds: float | None = details.get("TS")
        self.army_size: float | None = details.get("AS")
