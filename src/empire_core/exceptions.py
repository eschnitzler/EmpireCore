"""Typed exceptions for EmpireCore.

Failure modes are kept distinct so callers can react to them individually:

- ``EmpireTimeoutError``: the server did not answer in time.
- ``ConnectionClosedError``: the connection dropped while waiting.
- ``CommandError``: the server answered with a non-zero error code.
- ``GameDataNotLoadedError``: an API needed the items payload; load it first.
- ``AmbiguousLookupError``: a game-data lookup matched more than one row.
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


class AccountBannedError(LoginError):
    """
    Raised when the server refuses the login because the account is banned (``IS_BANNED``, 27).

    Attributes:
        remaining_seconds: seconds until the ban ends (``RS``), or None
        deleted: the account was deleted (``GDPR``)

    Client: ``LLICommand.executeCommand`` (bundle line 120651)
    """

    def __init__(self, remaining_seconds: float | None, deleted: bool = False):
        self.remaining_seconds = remaining_seconds
        self.deleted = deleted
        detail = "account deleted" if deleted else f"{remaining_seconds}s remaining"
        super().__init__(f"Account is banned ({detail})")


class WrongServerError(LoginError):
    """
    Raised when the account belongs to another server (``EXISTING_MAPPING_WRONG_SERVER``, 368).

    Attributes:
        instance_id: the instance id of the account's server (``IID``), or None;
            ``NetworkInstance.instance_id`` in ``network.xml``

    Client: ``LLICommand.executeCommand`` (bundle line 120651)
    """

    def __init__(self, instance_id: float | None):
        self.instance_id = instance_id
        super().__init__(f"Account is on another server (instance {instance_id})")


class ClientVersionError(LoginError):
    """
    Raised when the version check (``vck``) says the client's version is too low (1) or too high (2).

    Set ``EmpireConfig.client_version`` to the current game client's version.

    Attributes:
        status: 1 (too low) or 2 (too high)
        server_build: the server's build number, or None when the reply had none

    Client: ``CastleVCKCommand.executeCommand`` (bundle line 120444)
    """

    def __init__(self, status: int, server_build: str | None):
        self.status = status
        self.server_build = server_build
        which = "too low" if status == 1 else "too high"
        super().__init__(f"Client version {which} for the server (server build {server_build})")


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


class AmbiguousLookupError(EmpireError, LookupError):
    """
    Raised when a game-data lookup matches more than one row.

    Attributes:
        ids: the ids of every matching row, to pick one from the table directly.
    """

    def __init__(self, message: str, ids: list[int]):
        self.ids = ids
        super().__init__(f"{message}: matches ids {ids}")


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


class ReceiveThreadError(EmpireError):
    """Raised when a call that waits for a reply is made on the receive thread.

    Packet handlers, ``Connection.subscribe`` callbacks and service ``on_response``
    handlers run on the thread that routes every reply, so a call there that waits
    could only time out. Hand the work to another thread, or use a GameState
    callback, which runs on its own callback thread.
    """
