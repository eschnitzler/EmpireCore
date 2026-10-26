"""
The base every service builds on: typed requests and action results.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from empire_core.enums import Kingdom
from empire_core.exceptions import UnknownCastleError
from empire_core.gamedata import Currency, GameData, PrebuiltCastleDef
from empire_core.gamedata.collectables import MINUTE_SKIP_FIRST_ID, MINUTE_SKIP_KEY
from empire_core.gamedata.lenient import known
from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.utils.callbacks import BoundEvent, Registry

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient
    from empire_core.gamedata import Horse, PrebuiltCastle
    from empire_core.state.models import Castle

logger = logging.getLogger(__name__)

R = TypeVar("R", bound=BaseResponse)

# TravelConst.SLOWDOWN_C2_COSTS (dll line 19872)
_SLOWDOWN_RUBIES = 200


class BaseService:
    """
    Base class for all services.

    Services provide high-level APIs for game domains and use
    protocol models for type-safe request/response handling. The client
    builds one of each in ``EmpireClient.__init__``.

    Every service method reports failure by one rule:

    - transport errors and server errors raise (``EmpireTimeoutError``,
      ``ConnectionClosedError``, ``CommandError``), an action the server refuses too;
    - ``None`` only for a not-found (or nothing-to-do) outcome mapped from a named
      ``GGEError``, matched on ``CommandError.error`` and documented on the method;
    - an empty collection only when the collection really is empty;
    - invalid arguments, and a call the client would not make, raise ``ValueError``
      or a typed error from ``empire_core.exceptions``;
    - a malformed reply raises ``PacketError``.

    Four kinds of method follow rules of their own, each documented on the method:

    - a read that sends nothing is a property, or a noun method when it takes an argument,
      never a ``get_*`` (a ``get_*`` always sends a request); it reads ``client.state`` and
      returns ``None`` while the push or reply it comes from has not arrived yet
      (``client.castle.horses`` before a ``gpc``); data every login brings is never
      ``None``: before a login its read raises ``StateNotLoadedError``;
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
        """One of the player's castles as the state knows it, or None when the state has no such castle."""
        return next((c for c in self._own_castles() if c.id == castle_id), None)

    def _require_own_castle(self, castle_id: int) -> Castle:
        """
        One of the player's castles from the castle list the server sent (``gcl``).

        Raises:
            UnknownCastleError: The list has no such castle
        """
        castle = self._own_castle(castle_id)
        if castle is None:
            raise UnknownCastleError(castle_id)
        return castle

    def _own_area_kingdom(self, x: int, y: int, kingdom: Kingdom | None = None) -> Kingdom:
        """
        The kingdom of your area at (x, y): ``kingdom`` when given, else read from the castle list.

        Each kingdom has a map of its own, so the position alone can name areas in several.

        Raises:
            UnknownCastleError: No area of yours in the list is at (x, y)
            ValueError: Areas of yours sit at (x, y) in several kingdoms
        """
        if kingdom is not None:
            return kingdom
        kingdoms = sorted({c.kingdom_id for c in self._own_castles() if (c.x, c.y) == (x, y)})
        if not kingdoms:
            raise UnknownCastleError(None, position=(x, y))
        if len(kingdoms) > 1:
            names = ", ".join(k.name for k in kingdoms)
            raise ValueError(f"Areas of yours sit at {x}:{y} in {names}; pass the kingdom")
        return kingdoms[0]

    def _require_minute_skip(self, minute_skip: Currency | str) -> None:
        """
        Check that ``minute_skip`` is a minute skip, and one you hold once the special currencies are known.

        The client offers only the minute skips (``CurrencyData.getMinuteSkips``, the currency id range
        1000-1999, bundle lines 141226-141231) that you hold one of at least (``CastleMinuteSkipDialog.showLoaded``,
        bundle line 7671). A key newer than the generated enum counts when it is ``MS<n>``, the minute skip
        ``1000 + n`` (``CollectableHelper.getTypeByServerKey``, bundle lines 1604-1605). Before any ``sce``
        arrived the holdings are unknown and not checked.

        Raises:
            ValueError: It is no minute skip, or you hold none of it
        """
        skip = known(Currency, minute_skip, warn=False)
        if isinstance(skip, Currency):
            if not MINUTE_SKIP_FIRST_ID <= skip.currency_id < MINUTE_SKIP_FIRST_ID + 1000:
                raise ValueError(f"{skip.name} is no minute skip")
        elif not (minute_skip.startswith(MINUTE_SKIP_KEY) and minute_skip[len(MINUTE_SKIP_KEY) :].isdigit()):
            raise ValueError(f"{minute_skip!r} is no minute skip")
        state = self.client.state
        if state.get_last_packet_time("sce") is not None and state.get_special_currencies().get(skip, 0) < 1:
            raise ValueError(f"you hold no {getattr(skip, 'name', skip)}")

    @staticmethod
    def _require_spend_rubies(spend_rubies: bool, cost: str | None) -> None:
        """
        Refuse a call that spends rubies unless ``spend_rubies`` allows it; ``cost`` says what
        spends them ("a slowdown costs 200 rubies"), None when nothing does.

        Raises:
            ValueError: ``cost`` is not None and ``spend_rubies`` is False
        """
        if cost is not None and not spend_rubies:
            raise ValueError(f"{cost}; pass spend_rubies=True to spend them")

    def _require_game_data(self) -> GameData:
        """
        The client's game data, loaded through :meth:`GameData.require` on first use.

        Raises:
            GameDataNotLoadedError: The game data cannot be loaded
        """
        game_data = self.client.game_data
        return game_data if game_data is not None else GameData.require()

    def _prebuilt_castle(self, castle: PrebuiltCastle | int, *, level_gated: bool = True) -> PrebuiltCastleDef:
        """
        A prebuilt castle's row; a ``level_gated`` one is refused above your level.

        Raises:
            ValueError: The game data lacks the castle, or your level is below its ``min_level``
            GameDataNotLoadedError: The game data cannot be loaded
            StateNotLoadedError: ``level_gated`` and no login has brought your level

        Client: ``CastleKingdomCastleDetails.findNextSelectableCastleIndex`` (bundle line 97897) and
        ``PrebuiltCastleSelector.validateSelection`` (bundle line 54604) offer only a castle whose ``minLevel``
        your level reaches
        """
        row = self._require_game_data().prebuilt_castles.get(castle)
        if row is None:
            raise ValueError(f"prebuilt castle {int(castle)} is not in the game data")
        if not level_gated:
            return row
        level = self.client.state.get_local_player().level
        if 0 < level < row.min_level:
            raise ValueError(f"prebuilt castle {int(castle)} needs level {row.min_level}; you are level {level}")
        return row

    @staticmethod
    def _castle_rubies(row: PrebuiltCastleDef, ruby_price: bool) -> int:
        """
        The rubies a prebuilt castle is bought for: its ruby price when that is its only price or
        ``ruby_price`` picks it, else 0.

        Raises:
            ValueError: ``ruby_price`` for a castle with no ruby price

        Client: ``UnlockPrebuiltCastleForRubies.onClick`` (bundle line 55514), the ruby button that
        ``UnlockPrebuiltCastleForResourcesOrRubies`` (bundle line 97981) also shows beside the resource one
        """
        if ruby_price and row.cost_rubies <= 0:
            raise ValueError(f"prebuilt castle {int(row.prebuilt_castle_id)} has no ruby price")
        return row.cost_rubies if row.is_premium or ruby_price else 0

    def _travel_ruby_cost(self, horse_booster_id: Horse | int | None, feathers: bool, slowdown: int) -> str | None:
        """
        What of a movement's horse and slowdown costs rubies, None when neither does.

        A slowdown costs ``TravelConst.SLOWDOWN_C2_COSTS`` rubies. A horse costs rubies when its
        ``HorseStats.cost_factor_c2`` is above 0, unless paid with feathers; one the game data
        lacks counts as costing them.

        Raises:
            GameDataNotLoadedError: A horse is picked without feathers and the game data cannot be loaded

        Client: ``ACastlePostActionDialog.getTotalCostsC2`` (bundle line 27330), the horse's
        ``getBoostCostC2`` per dialog (bundle lines 33395, 38397, 38477), 0 when
        ``isPayedWithPegasusTickets``; ``SLOWDOWN_C2_COSTS`` is 200 (dll line 19872)
        """
        if slowdown > 0:
            return f"a slowdown costs {_SLOWDOWN_RUBIES} rubies"
        if feathers or horse_booster_id is None:
            return None
        horse = self._require_game_data().get_horse(horse_booster_id)
        if horse is None:
            return f"horse {horse_booster_id} is not in the game data and may cost rubies"
        if horse.cost_factor_c2 > 0:
            return f"horse {horse_booster_id} costs rubies unless paid with feathers"
        return None

    def send(self, request: BaseRequest, wait: bool = False, *, timeout: float = 5.0) -> BaseResponse | None:
        """
        Send a request to the server.

        With ``wait=True``, raises the same typed exceptions as
        ``EmpireClient.send`` (CommandError, EmpireTimeoutError, ...).
        """
        return self.client.send(request, wait=wait, timeout=timeout)

    def request(self, request: BaseRequest, response_type: type[R], *, timeout: float = 5.0) -> R:
        """
        Send a request and return its typed response.

        Raises:
            CommandError: The server answered with a non-zero error code
            EmpireTimeoutError / ConnectionClosedError / NetworkError: transport failures
            PacketError: The response could not be parsed as ``response_type``
        """
        return self.client.request(request, response_type, timeout=timeout)

    def execute(self, request: BaseRequest, *, timeout: float = 5.0) -> None:
        """
        Send an action request and wait until the server accepts it.

        Raises:
            CommandError: The server refused the action, with the game's message
            EmpireTimeoutError / ConnectionClosedError / NetworkError: transport failures
        """
        self.client.send(request, wait=True, timeout=timeout)

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
