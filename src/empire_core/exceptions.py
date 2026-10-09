"""Every error the library raises; all derive from ``EmpireError``.

Failure modes are kept distinct so callers can react to them individually:

- ``EmpireTimeoutError``: the server did not answer in time.
- ``ConnectionClosedError``: the connection dropped while waiting.
- ``CommandError``: the server answered with a non-zero error code.
- ``GameDataNotLoadedError``: an API needed the items payload; load it first.
- ``AmbiguousLookupError``: a game-data lookup matched more than one row.
- ``UnknownCastleError``: a castle is not one of the logged-in player's castles.
- ``AmbiguousCastleError``: a castle id or position matches castles in several kingdoms.
- ``EventNotRunningError``: a call needs an event that is not running.
- ``EventHasNoPointsError``: a call needs an event that keeps your rank and points.
- ``NotInAllianceError``: a call needs your alliance and you are in none.
- ``ReplyMismatchError``: a reply answers another list than the one asked for.
- ``UnsendableGoodsError``: a market send carries goods the client would not send.
- ``PremiumCommanderCostError``: a send led by the premium commander may cost rubies.
- ``LoginBonusUnavailableError``: the login bonus is asked for below the XP the client asks from.
"""

from typing import Any

from empire_core.enums import GGEError, Kingdom, VersionCheckStatus
from empire_core.texts import cached_text


class EmpireError(Exception):
    """Base class for all EmpireCore exceptions."""


class NetworkError(EmpireError):
    """Raised when a network operation fails."""


class ConnectionClosedError(NetworkError):
    """Raised when the connection closes while an operation is in flight."""


class LoginError(EmpireError):
    """
    Raised when the login sequence fails.

    Attributes:
        code: the server's status code when the server refused the login, else None
        error: the matching :class:`~empire_core.enums.errors.GGEError` member,
            or None for no code or a code this library does not know yet
    """

    def __init__(self, message: str, code: int | None = None):
        self.code = code
        self.error: GGEError | None = None
        if code is not None:
            try:
                self.error = GGEError(code)
            except ValueError:
                self.error = None
            name = self.error.name if self.error is not None else "UNKNOWN_ERROR"
            message = f"{message}: {name} ({code})"
            game_message = self.game_message()
            if game_message:
                message = f"{message}: {' '.join(game_message.split())}"
        super().__init__(message)

    def game_message(self, lang: str = "en") -> str | None:
        """
        The game's message for :attr:`code` in ``lang``, if those texts are already loaded.

        Never fetches: load them first with :func:`empire_core.texts.get_texts`. None for no
        code, texts not loaded, or a code the game has no message for.

        Client: ``CastleHandleServerErrorCommand.performDefaultError`` (bundle line 120328)
        shows ``Localize.text("errorCode_"+code)`` when that text exists
        """
        code = self.code
        return None if code is None else cached_text(f"errorCode_{code}", lang=lang)


class LoginCooldownError(LoginError):
    """Raised when the server rejects login due to rate limiting."""

    def __init__(self, cooldown: int, message: str = "Login cooldown active"):
        self.cooldown = cooldown
        super().__init__(f"{message}: Retry in {cooldown}s", GGEError.LOGIN_COOLDOWN_ACTIVE.value)


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
        super().__init__(f"Account is banned ({detail})", GGEError.IS_BANNED.value)


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
        super().__init__(
            f"Account is on another server (instance {instance_id})", GGEError.EXISTING_MAPPING_WRONG_SERVER.value
        )


class ClientVersionError(LoginError):
    """
    Raised when the version check (``vck``) says the client's version is too low or too high.

    Set ``EmpireConfig.client_version`` to the current game client's version.

    Attributes:
        status: ``VersionCheckStatus.VERSION_TOO_LOW`` or ``VERSION_TOO_HIGH``
        server_build: the server's build number, or None when the reply had none

    Client: ``CastleVCKCommand.executeCommand`` (bundle line 120444)
    """

    def __init__(self, status: VersionCheckStatus, server_build: str | None):
        self.status = status
        self.server_build = server_build
        which = "too low" if status is VersionCheckStatus.VERSION_TOO_LOW else "too high"
        super().__init__(f"Client version {which} for the server (server build {server_build})")


class PacketError(EmpireError):
    """Raised when packet parsing fails."""


class ReplyMismatchError(PacketError):
    """
    Raised when a reply answers another list than the one asked for, e.g. a late ``hgh`` reply.

    Attributes:
        expected: the list asked for
        received: the list the reply names
    """

    def __init__(self, expected: int, received: int):
        self.expected = expected
        self.received = received
        super().__init__(f"asked for list {expected}, the reply is for list {received}")


class EmpireTimeoutError(EmpireError, TimeoutError):
    """Raised when an operation times out.

    Subclasses the builtin ``TimeoutError`` so ``except TimeoutError``
    catches it too.
    """


class GameDataNotLoadedError(EmpireError):
    """
    Raised when an API needs the static game data and it has not been loaded.

    Call :meth:`EmpireClient.load_game_data` (or :meth:`GameData.load`, which
    it calls) first: it is explicit because the items payload is a large download.
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


class EventNotRunningError(EmpireError, LookupError):
    """
    Raised when a call needs an event that is not running: no sei packet named it, or a see ended it.

    Attributes:
        event_id: the event looked for
    """

    def __init__(self, event_id: int):
        self.event_id = event_id
        super().__init__(f"event {event_id} is not running")


class EventHasNoPointsError(EmpireError, ValueError):
    """
    Raised when a call needs an event that keeps your rank and points, and the event keeps none.

    Attributes:
        event_id: the event asked about, an ``Event`` member when the event table has it
    """

    def __init__(self, event_id: int):
        self.event_id = event_id
        name = getattr(event_id, "name", None)
        named = f"event {int(event_id)}" + (f" ({name})" if name else "")
        super().__init__(f"{named} keeps no rank and points of yours; see empire_core.events.POINT_EVENTS")


class NotInAllianceError(EmpireError, LookupError):
    """
    Raised when a call needs your own alliance and the player data names none.

    The client reads your alliance from the player data (``AID``); the server
    answers a request about your alliance outside one with ``ALLI_NOT_FOUND``.
    """

    def __init__(self) -> None:
        super().__init__("you are in no alliance")


class UnknownCastleError(EmpireError, ValueError):
    """
    Raised when a castle is not in the logged-in player's castle list (``gcl``).

    Methods acting on one of your areas send its kingdom, read from the list;
    the client only offers areas from it.

    Attributes:
        castle_id: the castle id looked for, or None when looked for by position
        position: the (x, y) looked for, or None when looked for by id
    """

    def __init__(self, castle_id: int | None, *, position: tuple[int, int] | None = None):
        self.castle_id = castle_id
        self.position = position
        what = f"castle {castle_id}" if position is None else f"position {position[0]}:{position[1]}"
        super().__init__(f"{what} is not one of your castles")


class AmbiguousCastleError(EmpireError, LookupError):
    """
    Raised when a castle id or position matches your castles in several kingdoms.

    The client keeps its castle list per kingdom, so an id could repeat across
    them; the library then cannot tell which castle is meant.

    Attributes:
        castle_id: the castle id looked for, or None when looked for by position
        position: the (x, y) looked for, or None when looked for by id
        kingdoms: the kingdom id of every match
    """

    def __init__(self, castle_id: int | None, kingdoms: list[int], *, position: tuple[int, int] | None = None):
        self.castle_id = castle_id
        self.position = position
        self.kingdoms = kingdoms
        what = f"castle {castle_id}" if position is None else f"position {position[0]}:{position[1]}"
        names = ", ".join(Kingdom(k).name if k in Kingdom._value2member_map_ else str(k) for k in kingdoms)
        super().__init__(
            f"{what} repeats across your kingdoms ({names}); the library cannot tell which castle is meant"
        )


class CommandError(EmpireError):
    """Raised when the server responds to a command with a non-zero error code.

    Attributes:
        command: the command that failed (e.g. ``"gaa"``).
        code: the raw numeric status code sent by the server.
        error: the matching :class:`~empire_core.enums.errors.GGEError`
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

    The message ends with the game's English text for the code, on one line, when
    those texts are already loaded; :meth:`game_message` gives it as the game has
    it, in any loaded language.
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
        message = f"Server error {name} ({code}) for command '{command}'"
        game_message = self.game_message()
        super().__init__(f"{message}: {' '.join(game_message.split())}" if game_message else message)

    def game_message(self, lang: str = "en") -> str | None:
        """
        The game's message for :attr:`code` in ``lang``, if those texts are already loaded.

        Never fetches: load them first with :func:`empire_core.texts.get_texts`. None when
        they are not loaded or the game has no message for the code. Placeholders the
        client fills for a few codes (a time, a count) stay as ``{0}``.

        Client: ``CastleCommand.showErrorDialog`` (bundle line 202) hands the code to
        ``CastleHandleServerErrorCommand.performDefaultError`` (bundle line 120328), which
        shows ``Localize.text("errorCode_"+code)`` when that text exists
        """
        return cached_text(f"errorCode_{self.code}", lang=lang)


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


class AttackBelowMinimumError(EmpireError, ValueError):
    """An attack's waves carry fewer units than the client lets it send.

    The client refuses such an attack with ``errorCode_100`` and the minimum.
    The server refused one on a player's castle with MOVEMENT_HAS_NO_UNITS
    (100); whether it enforces the minimum on NPC camps is unverified. Send
    the error's ``attack`` anyway to find out.

    Attributes:
        minimum: the fewest units the waves must carry together
        soldiers: the units they carry
        attack: the filled attack, when ``fill_attack`` raised it, else None

    Client: ``AttackDialogStartAttackCheck.onAttack`` (bundle line 56306).
    """

    def __init__(self, minimum: int, soldiers: int, attack: Any = None):
        super().__init__(f"The waves carry {soldiers} units, fewer than the {minimum} an attack on this target needs")
        self.minimum = minimum
        self.soldiers = soldiers
        self.attack = attack


class UnsendableGoodsError(EmpireError, ValueError):
    """A market send or kingdom transfer carries goods the client's send dialog would not send.

    Attributes:
        goods: the goods as given

    Client: ``CastleSendGoodsDialog.sendGoodsCastle`` (bundle line 27202),
    ``CastleSendGoodsComponent.setTabVisibility`` (bundle line 44260).
    """

    def __init__(self, message: str, goods: Any):
        super().__init__(message)
        self.goods = goods


class PremiumCommanderCostError(EmpireError, ValueError):
    """A send led by the premium commander may cost rubies, and the caller did not allow it.

    The client asks before such a send; pass ``spend_rubies=True`` to send it regardless.

    Attributes:
        free_premium_commanders: the free premium commanders left, None when not known

    Client: ``CastlePostAttackDialog.startAttack`` (bundle line 38360) shows
    ``CastleBuyTempCommanderDialog`` when no free premium commander is left.
    """

    def __init__(self, free_premium_commanders: int | None):
        known = "is not known" if free_premium_commanders is None else f"is {free_premium_commanders}"
        super().__init__(
            f"Leading with the premium commander may cost rubies: the free premium commanders left {known}"
            " and no premium account is known to run; pass spend_rubies=True to send anyway"
        )
        self.free_premium_commanders = free_premium_commanders


class LoginBonusUnavailableError(EmpireError):
    """The login bonus was asked for while your XP is below the client's gate, or not known yet.

    The server sends no ``alb`` below it (seen live), so a request would only time out.

    Attributes:
        xp: your XP from the player data, None before it arrived
        required_xp: the XP the client asks for the login bonus from

    Client: ``CastleLoginBonusData.REQUIRED_XP`` (bundle line 39163), checked by ``GBDCommand``
    (bundle line 129389) and ``onUserXpChanged`` (bundle line 39132) before ``C2SGetLoginBonusVO``
    """

    def __init__(self, xp: int | None, required_xp: int):
        known = "is not known yet" if xp is None else f"is {xp}"
        super().__init__(f"the login bonus needs {required_xp} XP; yours {known}")
        self.xp = xp
        self.required_xp = required_xp


class ReceiveThreadError(EmpireError):
    """Raised when a call that waits for a reply is made on the receive thread.

    Packet handlers, ``Connection.subscribe`` callbacks and service ``on_response``
    handlers run on the thread that routes every reply, so a call there that waits
    could only time out. Hand the work to another thread, or use a GameState
    callback, which runs on its own callback thread.
    """


class MessageUnavailableError(CommandError):
    """Raised when a message cannot be read: ``NO_SUCH_MESSAGE`` or ``MESSAGEDATA_TOO_OLD`` (too old to read)."""


class EventStreamOverflowError(EmpireError):
    """Raised by an :class:`~empire_core.client.stream.EventStream` given a ``maxsize`` once that
    many events waited unread: the stream has stopped listening, after the events it holds.

    Read the state you need again and open a new stream.
    """


__all__ = [
    "EmpireError",
    "NetworkError",
    "ConnectionClosedError",
    "LoginError",
    "LoginCooldownError",
    "AccountBannedError",
    "WrongServerError",
    "ClientVersionError",
    "VersionCheckStatus",
    "PacketError",
    "ReplyMismatchError",
    "EmpireTimeoutError",
    "GameDataNotLoadedError",
    "AmbiguousLookupError",
    "EventNotRunningError",
    "EventHasNoPointsError",
    "UnknownCastleError",
    "AmbiguousCastleError",
    "CommandError",
    "AttackInProgressError",
    "AttackBelowMinimumError",
    "UnsendableGoodsError",
    "PremiumCommanderCostError",
    "LoginBonusUnavailableError",
    "ReceiveThreadError",
    "MessageUnavailableError",
    "NotInAllianceError",
    "EventStreamOverflowError",
]
