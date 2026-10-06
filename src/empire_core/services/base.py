"""
The base every service builds on: typed requests and action results.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection
from typing import TYPE_CHECKING, Any, TypeVar

from empire_core.enums import Kingdom
from empire_core.exceptions import AmbiguousCastleError, CommandError, UnknownCastleError
from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.protocol.errors import GGEError
from empire_core.utils.callbacks import BoundEvent, Registry

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient
    from empire_core.state.models import Castle

logger = logging.getLogger(__name__)

R = TypeVar("R", bound=BaseResponse)


class BaseService:
    """
    Base class for all services.

    Services provide high-level APIs for game domains and use
    protocol models for type-safe request/response handling. The client
    builds one of each in ``EmpireClient.__init__``.

    Every service method reports failure by one rule:

    - transport errors and unexpected server errors raise (``EmpireTimeoutError``,
      ``ConnectionClosedError``, ``CommandError``);
    - ``None`` only for a not-found (or nothing-to-do) outcome mapped from a named
      ``GGEError``, matched on ``CommandError.error`` and documented on the method;
    - an empty collection only when the collection really is empty;
    - invalid arguments, and a call the client would not make, raise ``ValueError``
      or a typed error from ``empire_core.exceptions``;
    - a malformed reply raises ``PacketError``;
    - an action the server refuses returns False (see :meth:`execute`).

    Four kinds of method follow rules of their own, each documented on the method:

    - state read without a request returns ``None`` while the login data or push it
      comes from has not arrived yet (``client.castle.get_horses`` before a ``gpc``);
    - a call made of several requests returns a result object that names each outcome,
      such as ``SpyOutcome.COMMAND_FAILED`` on a ``SpyResult`` or the ``failed`` and
      ``timed_out`` players of ``get_player_details_bulk``;
    - a best-effort fill goes on without a read the server refuses and names it,
      as ``fill_attack`` does in ``FilledAttack.unread``;
    - a request the server never answers, waiting for a push instead, returns ``None``
      when no push came in time (``open_activity_chest``).
    """

    def __init__(self, client: "EmpireClient") -> None:
        self.client = client
        self._registry = Registry(missing_ok=True)

    def _fire(self, callbacks: BoundEvent[Any], *args: Any) -> None:
        """Call every callback of an event here, on the receive thread; one that raises is logged."""
        for callback in callbacks.calls():
            try:
                callback(*args)
            except Exception:
                logging.getLogger(type(self).__module__).exception(f"{callbacks.name} callback error")

    @property
    def zone(self) -> str:
        """Get the game zone from client config."""
        return self.client.config.default_zone

    def _own_castles(self) -> list[Castle]:
        """The player's castles as the state knows them."""
        return list(getattr(self.client.state, "get_castles", list)() or [])

    def _own_castle(self, castle_id: int) -> Castle | None:
        """
        One of the player's castles as the state knows it, or None when the state has no such castle.

        Raises:
            AmbiguousCastleError: The id is listed in several of your kingdoms
        """
        matches = [c for c in self._own_castles() if c.id == castle_id]
        if len(matches) > 1:
            raise AmbiguousCastleError(castle_id, sorted(c.kingdom_id for c in matches))
        return matches[0] if matches else None

    def _require_own_castle(self, castle_id: int) -> Castle:
        """
        One of the player's castles from the castle list the server sent (``gcl``).

        The client keeps its list per kingdom (``CastleListVO.parseCastleList``,
        bundle line 13698), so an id could repeat across kingdoms; the id alone
        then names no single castle.

        Raises:
            UnknownCastleError: The list has no such castle
            AmbiguousCastleError: The id is listed in several of your kingdoms
        """
        castle = self._own_castle(castle_id)
        if castle is None:
            raise UnknownCastleError(castle_id)
        return castle

    def _own_area_kingdom(self, x: int, y: int, kingdom: Kingdom | None = None) -> Kingdom:
        """
        The kingdom of your area at (x, y): ``kingdom`` when given, else read from the castle list.

        Raises:
            UnknownCastleError: No area of yours in the list is at (x, y)
            AmbiguousCastleError: Areas of yours sit at (x, y) in several kingdoms
        """
        if kingdom is not None:
            return kingdom
        kingdoms = sorted({c.kingdom_id for c in self._own_castles() if (c.x, c.y) == (x, y)})
        if not kingdoms:
            raise UnknownCastleError(None, position=(x, y))
        if len(kingdoms) > 1:
            raise AmbiguousCastleError(None, list(kingdoms), position=(x, y))
        return kingdoms[0]

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

    def execute(self, request: BaseRequest, timeout: float = 5.0, *, raise_on: Collection[GGEError] = ()) -> bool:
        """
        Send an action request and report whether the server accepted it.

        Returns False when the server rejects the action with an error code
        (logged at warning level). Transport failures (timeout, disconnect)
        still raise, so infrastructure problems are never mistaken for a
        game-rule rejection.

        Args:
            raise_on: Errors that raise their ``CommandError`` instead, for a caller that maps them
        """
        try:
            self.client.send(request, wait=True, timeout=timeout)
            return True
        except CommandError as e:
            if e.error in raise_on:
                raise
            logger.warning(f"Action '{request.get_command()}' rejected: {e}")
            return False

    def on_response(self, command: str, handler: Callable[[BaseResponse], None]) -> None:
        """
        Register a handler for a specific response type.

        Handlers are registered with the client for efficient routing.
        Only commands with registered handlers will be parsed.

        Handlers run on the receive thread, which routes every reply: they must
        not block, and a call that waits for a reply raises ``ReceiveThreadError``.

        Args:
            command: The command code to handle (e.g., "acm")
            handler: Callback function that receives the parsed response
        """
        self.client._register_handler(command, handler)


__all__ = ["BaseService"]
