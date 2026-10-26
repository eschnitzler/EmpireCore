"""
The army movements the state tracks, and the sends that start them: support, troops, market goods,
kingdom transfers and transfers to a season's treasure map.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from empire_core.enums import Kingdom, KingdomTransferType, Resource
from empire_core.events.models import SeasonEvent
from empire_core.events.season_models import MinuteSkipSeasonTransferRequest
from empire_core.exceptions import CommandError, UnsendableGoodsError
from empire_core.gamedata import Currency, TreasureMapId, WodAmount, WodAmountMapping
from empire_core.movements.models import (
    NO_HORSE,
    CancelMovementRequest,
    CancelMovementResponse,
    CreateMarketMovementRequest,
    GetMovementsRequest,
    GetTravelInfoRequest,
    GetTravelInfoResponse,
    KingdomGoodsTransferRequest,
    KingdomSkipTransferRequest,
    KingdomUnitTransferRequest,
    MarketCastle,
    MarketInfoRequest,
    MarketInfoResponse,
    MinuteSkipKingdomTransferRequest,
    MovementWrapper,
    SendSupportRequest,
    SendSupportResponse,
    SendTowerSupportRequest,
    SendTowerSupportResponse,
    SendTownshipSupportRequest,
    SendTownshipSupportResponse,
    SendTroopsRequest,
    TreasureMapGoodsTransferRequest,
    TreasureMapTransferSkipRequest,
    TreasureMapUnitTransferRequest,
)
from empire_core.movements.tracked import Movement
from empire_core.services.base import BaseService

if TYPE_CHECKING:
    from empire_core.gamedata import Horse

_CLASSIC_GOODS = (Resource.WOOD.value, Resource.STONE.value, Resource.FOOD.value)
_GOODS_TABS = (
    _CLASSIC_GOODS,
    (Resource.COAL.value, Resource.OIL.value, Resource.GLASS.value, Resource.IRON.value),
    (Resource.HONEY.value, Resource.MEAD.value, Resource.BEEF.value),
)


class MovementsService(BaseService):
    """
    Army movements: listing them, recalling your own, and sending support, troops, goods and
    kingdom transfers.

    Reached as client.movements.
    """

    @property
    def tracked(self) -> list[Movement]:
        """All tracked movements (stale ones pruned first)."""
        return self.client.state.get_all_movements()

    def movement(self, movement_id: int) -> Movement | None:
        """a tracked movement by its ``Movement.movement_id``, as ``client.movements.get_movements()`` lists it."""
        return self.client.state.get_movement_by_id(movement_id)

    @property
    def announced_attacks(self) -> list[Movement]:
        """The attacks :meth:`on_incoming_attack` announced that are still on their way, in the order announced."""
        return self.client.state.get_announced_attacks()

    @property
    def occupations(self) -> list[Movement]:
        """The occupations :meth:`on_occupation_started` announced that have not ended, in the order announced."""
        return self.client.state.get_occupations()

    def get_movements(self, wait: bool = True, *, timeout: float = 5.0) -> list[Movement]:
        """
        Request army movements from server.

        Args:
            wait: If True, wait for response before returning
            timeout: Timeout in seconds when waiting; with ``wait=False``, how long
                to wait for a gam request in flight before sending, and how long
                the reply is kept from other gam requests at most

        Returns:
            List of Movement objects, read from state after the response has
            been applied. With ``wait=False`` this is whatever state holds
            right now, which is not yet the answer to this request.

        Raises:
            CommandError: ``wait=True`` and the server rejected 'gam'
            EmpireTimeoutError: ``wait=True`` and no response within ``timeout``,
                or ``wait=False`` and a gam request in flight for all of ``timeout``
        """
        if wait:
            response = self.client.request_packet(GetMovementsRequest(), "gam", timeout=timeout)
            # Without this, a rejected request returns the previous (possibly
            # empty) movement list, indistinguishable from "no movements".
            if response.error_code != 0:
                raise CommandError("gam", response.error_code)
        else:
            self.client.connection.send_and_drop_reply(self.client.frame(GetMovementsRequest()), "gam", window=timeout)

        return self.client.state.get_all_movements()

    @property
    def incoming_attacks(self) -> list[Movement]:
        """The attacks heading for you, as the movement pushes left them; nothing is sent."""
        return self.client.state.get_incoming_attacks()

    @property
    def incoming_movements(self) -> list[Movement]:
        """Every movement heading for you, as the movement pushes left them; nothing is sent."""
        return self.client.state.get_incoming_movements()

    @property
    def outgoing_movements(self) -> list[Movement]:
        """Your movements on their way, as the movement pushes left them; nothing is sent."""
        return self.client.state.get_outgoing_movements()

    def recall(self, movement_id: int, *, timeout: float = 5.0) -> MovementWrapper:
        """
        Recall one of your movements (``mcm``), as the client's retreat and "send home" buttons do.

        Which movements the client lets you recall is listed on
        :class:`CancelMovementRequest`: in short, your own that are still
        heading to their target (attacks only within 600 seconds of leaving,
        with exceptions) and your supports in either direction. The reply
        also updates state and fires :meth:`GameState.on_movement_recalled`.

        Args:
            movement_id: The movement to recall (``Movement.movement_id``)
            timeout: Timeout in seconds

        Returns:
            The movement as the reply has it now, normally on its way home

        Raises:
            CommandError: The server refused the recall, such as
                INVALID_STARTAREA_FOR_CANCEL_MOVEMENT (189)

        Client: ``CastleAskRetreatDialog.onClick`` (bundle line 33234),
        ``MCMCommand.executeCommand`` (bundle line 126041)
        """
        return self.request(
            CancelMovementRequest(movement_id=movement_id), CancelMovementResponse, timeout=timeout
        ).movement

    # =========================================================================
    # Market
    # =========================================================================

    def send_resources(
        self,
        source_castle_id: int,
        target_x: int,
        target_y: int,
        goods: dict[Resource, int],
        *,
        horse_booster_id: Horse | None = None,
        feathers: bool = False,
        slowdown: int = 0,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Send resources from one of your castles to a castle on the map, by carriage.

        A horse that costs rubies, unless paid with feathers, and a slowdown spend rubies;
        see "Spending rubies" in the guides.

        Nothing is sent when the goods fail a check the client makes before
        sending: an amount that is not a positive int (the client drops zeros
        and refuses a send of nothing; this raises on a zero instead), goods
        from more than one of the dialog's tabs (classic, kingdom, mead), or,
        once the player is known and has no legend level, anything but wood,
        stone and food (the client then shows only that tab). The client sends
        one tab's goods per send, and the server refuses a send that mixes tabs
        with INVALID_PARAMETER_VALUE (seen live for wood with coal and coal
        with honey).

        Not checked, since they depend on the target or on data this call does
        not have: the target owner's level for kingdom resources and legend
        level for mead goods, at most 2 goods (wood and stone) to a monument
        or laboratory, the carriage capacity and the castle's stock.

        Args:
            source_castle_id: The castle the carriages leave from, one of yours
            target_x: Map x of the target castle
            target_y: Map y of the target castle
            goods: Amount per resource, all from one tab, such as
                ``{Resource.WOOD: 1000, Resource.STONE: 500}`` or ``{Resource.COAL: 500, Resource.OIL: 500}``
            horse_booster_id: The horse, None for none; sent as none whenever feathers are used, as the
                client does
            feathers: Pay for the horse with feathers
            slowdown: Seconds to delay the arrival by; costs rubies
            spend_rubies: Allow a horse or slowdown that costs rubies
            timeout: Timeout in seconds

        Raises:
            UnsendableGoodsError: The goods fail one of the checks above
            UnknownCastleError: ``source_castle_id`` is not in your castle list
            ValueError: The horse or slowdown costs rubies and ``spend_rubies`` is False
            GameDataNotLoadedError: A horse is picked without feathers and the game data cannot be loaded

        Client: ``CastlePostSendGoodsDialog.sendGoods`` (bundle line 33378), which
        sends ``castleList.getKingdomIdByCastleId`` of the source castle as ``KID``;
        ``CastleSendGoodsDialog.sendGoodsCastle`` (bundle line 27202), which refuses
        a zero sum; ``CollectableParser._createGoodsList`` (bundle line 40530),
        which drops zero amounts; ``CastleSendGoodsComponent.rewardList`` (bundle
        line 44340), which sends one tab's goods, and ``setTabVisibility`` (bundle
        line 44261), which shows the kingdom and mead tabs only to a legend. Not
        mirrored: ``applySpecialLevelRestrictions`` (bundle line 44289) and
        ``isBoosterArea`` (bundle line 44356).
        """
        amounts = self._sendable_goods(goods)
        self._require_spend_rubies(spend_rubies, self._travel_ruby_cost(horse_booster_id, feathers, slowdown))
        request = CreateMarketMovementRequest(
            kingdom_id=self._require_own_castle(source_castle_id).kingdom_id,
            source_castle_id=source_castle_id,
            target_x=target_x,
            target_y=target_y,
            horse_booster_id=NO_HORSE if feathers or horse_booster_id is None else horse_booster_id,
            feathers=1 if feathers else 0,
            slowdown=slowdown,
            goods=amounts,
        )
        self.execute(request, timeout=timeout)

    def _sendable_goods(self, goods: dict[Resource, int]) -> dict[Resource, int]:
        if not goods:
            raise UnsendableGoodsError("No goods to send", goods)
        amounts: dict[Resource, int] = {}
        for key, amount in goods.items():
            try:
                resource = Resource(key)
            except ValueError:
                raise UnsendableGoodsError(f"{key!r} is not a resource the market sends", goods) from None
            if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
                raise UnsendableGoodsError(f"{resource.name} amount must be a positive int, got {amount!r}", goods)
            amounts[resource] = amount
        tabs = {index for key in amounts for index, tab in enumerate(_GOODS_TABS) if key in tab}
        if len(tabs) > 1:
            raise UnsendableGoodsError(
                "One send carries goods from one tab only: wood, stone and food; coal, oil, glass and iron;"
                " or honey, mead and beef",
                goods,
            )
        player = self.client.state.get_local_player()
        if player.level > 0 and player.legendary_level <= 0:
            beyond = [key.value for key in amounts if key not in _CLASSIC_GOODS]
            if beyond:
                raise UnsendableGoodsError(
                    f"Only wood, stone and food can be sent below legend level, not {', '.join(map(str, beyond))}",
                    goods,
                )
        return amounts

    def get_market_info(self, *, timeout: float = 5.0) -> list[MarketCastle]:
        """
        List every castle's market carriages, those not on the road, and its resources.

        Example:
            for castle in client.movements.get_market_info():
                print(castle.castle_id, castle.available_carriages, "/", castle.total_carriages)
        """
        return self.request(MarketInfoRequest(), MarketInfoResponse, timeout=timeout).castles

    # =========================================================================
    # Support and Transfers
    # =========================================================================

    def send_support(
        self,
        source_castle_id: int,
        target_x: int,
        target_y: int,
        units: WodAmountMapping | Sequence[WodAmount],
        commander_id: int,
        wait_time: int = 12,
        use_premium_commander: bool = False,
        horse_booster_id: Horse | None = None,
        feathers: bool = False,
        slowdown: int = 0,
        *,
        alliance_tower: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> SendSupportResponse:
        """
        Send support troops from a castle to a target location and return the server's reply.

        The server refuses a support to your own area with NO_SELF_DESTRUCTION
        (92); move troops between your own areas with :meth:`send_troops`, and
        support a daimyo township with :meth:`send_township_support`.

        A support led by the premium commander is refused before sending when it
        may cost rubies, unless ``spend_rubies`` is True; see
        ``client.commanders.premium_send``. So is a horse that costs rubies, unless
        paid with feathers, and a slowdown; see "Spending rubies" in the guides.

        Args:
            source_castle_id: The castle the troops leave from, one of yours: ``CastleInfo.castle_id``
                from ``client.castle.get_all()`` or ``Castle.id`` from ``client.state.get_castles()``
            target_x: Target X coordinate
            target_y: Target Y coordinate
            units: The units: ``{Unit.X: 100}``, or pairs one per slot; the client sends no tools
            commander_id: Commander to lead the support, a ``Commander.commander_id``
                from ``client.commanders.get_commanders()``.
                There is no default: ``0`` is a real commander (the free starting
                one), and the client never sends a support without a commander
                (with none picked it leads with the premium one, ``-14``)
            wait_time: Station duration in hours (0-12, default: 12)
            use_premium_commander: Lead with the premium commander (``commander_id``
                -14). It uses one of your free premium commanders, or costs rubies
                when none is left and no premium account runs
            horse_booster_id: The horse, None for none; sent as none whenever feathers are used, as the
                client does
            feathers: Pay for the movement with feathers
            slowdown: Movement slowdown modifier (0 = none, default: 0); costs rubies
            alliance_tower: The target is a Beyond the Horizon tower: sent as ``tde``,
                as the client does for that target, and answered with a ``SendTowerSupportResponse``
            timeout: Timeout in seconds
            spend_rubies: Send even when the premium commander, the horse or the slowdown costs rubies

        Raises:
            PremiumCommanderCostError: The premium commander leads, may cost rubies,
                and ``spend_rubies`` is False
            ValueError: The horse or slowdown costs rubies and ``spend_rubies`` is False
            GameDataNotLoadedError: The premium commander leads, VIP time runs and
                the game data cannot be loaded; or a horse is picked without feathers
                before it was called
            CommandError: The server refused the support

        Client: ``CastleAttackData.sendSupport`` (bundle line 133904) sends ``tde`` when the
        target's area type is ``AREA_TYPE_ALLIANCE_BATTLE_GROUND_TOWER``, else ``cds``
        """
        self._require_spend_rubies(spend_rubies, self._travel_ruby_cost(horse_booster_id, feathers, slowdown))
        response_type = SendTowerSupportResponse if alliance_tower else SendSupportResponse
        request = (SendTowerSupportRequest if alliance_tower else SendSupportRequest)(
            source_castle_id=source_castle_id,
            target_x=target_x,
            target_y=target_y,
            units=WodAmount.slots(units),
            wait_time=wait_time,
            use_premium_commander=1 if use_premium_commander else 0,
            horse_booster_id=NO_HORSE if feathers or horse_booster_id is None else horse_booster_id,
            feathers=1 if feathers else 0,
            slowdown=slowdown,
            commander_id=commander_id,
        )
        return self.client.commanders.premium_send(
            commander_id,
            use_premium_commander,
            lambda: self.request(request, response_type, timeout=timeout),
            spend_rubies=spend_rubies,
        )

    def send_township_support(
        self,
        source_castle_id: int,
        target_x: int,
        target_y: int,
        units: WodAmountMapping | Sequence[WodAmount],
        *,
        timeout: float = 5.0,
    ) -> SendTownshipSupportResponse:
        """
        Send support troops from a castle to a daimyo township and return the server's reply.

        The client sends no commander, horse, wait time or slowdown with it.

        Args:
            source_castle_id: The castle the troops leave from, one of yours: ``CastleInfo.castle_id``
                from ``client.castle.get_all()`` or ``Castle.id`` from ``client.state.get_castles()``
            target_x: The township's map x
            target_y: The township's map y
            units: The units: ``{Unit.X: 100}``, or pairs one per slot
            timeout: Timeout in seconds

        Raises:
            ValueError: No units are given, which the client refuses
            CommandError: The server refused the support

        Client: ``CastleSupportDefenceDialog.closeScreen`` (bundle line 122483) refuses an empty
        army and picks ``ACTION_TYPE_SUPPORTDEFENSE_TOWNSHIP`` for an ``AREA_TYPE_DAIMYO_TOWNSHIP``,
        which ``OpenPostAttackDialogCommand.execute`` (bundle line 99685) sends as ``cdd``
        """
        slots = WodAmount.slots(units)
        if not any(slot.amount > 0 for slot in slots if slot.item is not None):
            raise ValueError("a township support needs units")
        request = SendTownshipSupportRequest(
            source_castle_id=source_castle_id, target_x=target_x, target_y=target_y, units=slots
        )
        return self.request(request, SendTownshipSupportResponse, timeout=timeout)

    def send_troops(
        self,
        source_x: int,
        source_y: int,
        target_x: int,
        target_y: int,
        units: WodAmountMapping | Sequence[WodAmount],
        commander_id: int,
        *,
        kingdom_id: Kingdom = Kingdom.GREEN,
        use_premium_commander: bool = False,
        spend_rubies: bool = False,
        horse_booster_id: Horse | None = None,
        feathers: bool = False,
        slowdown: int = 0,
        timeout: float = 5.0,
    ) -> None:
        """
        Send troops from one of your areas to another of your own, where they stay.

        This is how the client moves troops between your own areas; a support
        (:meth:`send_support`) to your own area is refused with
        NO_SELF_DESTRUCTION (92). While the troops are heading out they can be
        recalled with ``client.movements.recall``.

        Targets the client offers: your castle (main or kingdom castle), your
        outposts not under conquer control, your villages and resource isles,
        your king's towers, monuments and laboratories, and your faction camps.
        Sources: your castles and outposts (not occupied ones), villages,
        resource isles, king's towers, monuments and laboratories. Both must
        sit in the same kingdom; to move troops between kingdoms use
        :meth:`transfer_units_to_kingdom`.

        Rubies as for :meth:`send_support`: the premium commander, a horse that costs
        rubies unless paid with feathers, and a slowdown need ``spend_rubies``.

        Client: ``CastleTroopSupportData.sendTroops`` (bundle line 38420); the
        targets from the ``canBeTroupsSended`` overrides (``CastleMapobjectVO``
        bundle line 18917, ``OutpostMapobjectVO`` 18819, ``KingstowerMapobjectVO``
        19075, ``FactionCampMapobjectVO`` 21530, ``VillageMapobjectVO`` 22673,
        ``UpgradableLandmarkMapobjectVO`` 42648), the sources from
        ``CastleStartAttackDialog.fillCastleList`` (bundle line 14725)

        Args:
            source_x: Map x of the area the troops leave from
            source_y: Map y of the area the troops leave from
            target_x: Map x of the area they go to
            target_y: Map y of the area they go to
            units: The units, then any tools: ``{Unit.X: 100}``, or pairs one per slot
            commander_id: Commander to lead them, a ``Commander.commander_id``
                from ``client.commanders.get_commanders()``; ``0`` is the free
                starting one
            kingdom_id: The kingdom both areas sit in
            use_premium_commander: Lead with the premium commander (``commander_id``
                -14). It uses one of your free premium commanders, or costs rubies
                when none is left and no premium account runs
            spend_rubies: Send even when the premium commander, the horse or the slowdown costs rubies
            horse_booster_id: The horse, None for none; sent as none whenever feathers are used, as the
                client does
            feathers: Pay for the horse with feathers
            slowdown: Seconds to delay the arrival by; costs rubies
            timeout: Timeout in seconds

        Raises:
            PremiumCommanderCostError: The premium commander leads, may cost rubies,
                and ``spend_rubies`` is False; see ``client.commanders.premium_send``
            ValueError: The horse or slowdown costs rubies and ``spend_rubies`` is False
            GameDataNotLoadedError: The premium commander leads, VIP time runs and
                the game data cannot be loaded; or a horse is picked without feathers
                before it was called
        """
        self._require_spend_rubies(spend_rubies, self._travel_ruby_cost(horse_booster_id, feathers, slowdown))
        request = SendTroopsRequest(
            source_x=source_x,
            source_y=source_y,
            target_x=target_x,
            target_y=target_y,
            kingdom_id=kingdom_id,
            commander_id=commander_id,
            horse_booster_id=NO_HORSE if feathers or horse_booster_id is None else horse_booster_id,
            use_premium_commander=1 if use_premium_commander else 0,
            feathers=1 if feathers else 0,
            slowdown=slowdown,
            units=WodAmount.slots(units),
        )
        self.client.commanders.premium_send(
            commander_id,
            use_premium_commander,
            lambda: self.execute(request, timeout=timeout),
            spend_rubies=spend_rubies,
        )

    def get_travel_info(
        self,
        source_x: int,
        source_y: int,
        target_x: int,
        target_y: int,
        *,
        kingdom_id: Kingdom = Kingdom.GREEN,
        timeout: float = 5.0,
    ) -> GetTravelInfoResponse:
        """
        Get the pre-calculation of troops sent from one of your areas to another, before :meth:`send_troops`.

        This is what the client asks for when it opens the dialog to send
        troops: the target's map row and owner, and your units and tools at the
        source. The commanders it carries update ``client.state``. The travel
        time and cost are not in the reply; the client works them out from the
        units picked.

        Args:
            source_x: Map x of the area the troops would leave from
            source_y: Map y of the area the troops would leave from
            target_x: Map x of the area they would go to
            target_y: Map y of the area they would go to
            kingdom_id: The kingdom both areas sit in
            timeout: Timeout in seconds

        Raises:
            CommandError: The server refused it, ``NOT_IN_OWNED_CASTLE`` when the
                source is not one of your areas

        Client: ``C2STroopSupportInfoVO`` (bundle line 72087), sent by
        ``CastleStartAttackDialog`` (bundle line 14831); ``STICommand`` (bundle line 129095)
        """
        request = GetTravelInfoRequest(
            source_x=source_x, source_y=source_y, target_x=target_x, target_y=target_y, kingdom_id=kingdom_id
        )
        return self.request(request, GetTravelInfoResponse, timeout=timeout)

    def transfer_units_to_kingdom(
        self,
        source_castle_id: int,
        target_kingdom_id: Kingdom,
        units: WodAmountMapping | Sequence[WodAmount],
        *,
        target_castle_id: int = -1,
        timeout: float = 5.0,
    ) -> None:
        """
        Send units from one of your castles to another kingdom.

        Args:
            source_castle_id: The castle the units leave from, one of yours
            target_kingdom_id: The kingdom to send them to
            units: The units, ``{Unit.X: 100}``
            target_castle_id: Object id of a picked target castle, -1 for none
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``source_castle_id`` is not in your castle list

        Client: ``CastleTransferTroopsToKingdomProperties.getUnitTransferCommand``
        (bundle line 37448) sends the source castle's ``kingdomID`` as ``SKID``
        """
        request = KingdomUnitTransferRequest(
            source_castle_id=source_castle_id,
            source_kingdom_id=self._require_own_castle(source_castle_id).kingdom_id,
            target_kingdom_id=target_kingdom_id,
            target_castle_id=target_castle_id,
            units=WodAmount.slots(units),
        )
        self.execute(request, timeout=timeout)

    def transfer_goods_to_kingdom(
        self,
        source_castle_id: int,
        target_kingdom_id: Kingdom,
        goods: dict[Resource, int],
        *,
        timeout: float = 5.0,
    ) -> None:
        """
        Send goods from one of your castles to your castle in another kingdom.

        The goods pass the checks of :meth:`send_resources`, since the client
        sends them from the same send component: positive amounts, one tab per
        send, classic goods only below legend level. The source castle may not
        sit in the target kingdom or in Berimond, which the client leaves out
        of its castle picker, and the target kingdom must hold a castle of
        yours, which the client sends the goods to. The travel tax and the
        target's storage are left to the server.

        Args:
            source_castle_id: The castle the goods leave from, one of yours
            target_kingdom_id: The kingdom to send them to
            goods: Amount per resource, all from one tab, such as ``{Resource.WOOD: 1000}``
            timeout: Timeout in seconds

        Raises:
            UnsendableGoodsError: The goods fail one of the checks of :meth:`send_resources`
            ValueError: The source castle sits in the target kingdom or in Berimond,
                or no castle of yours sits in the target kingdom
            UnknownCastleError: ``source_castle_id`` is not in your castle list

        Client: ``CastleTransferResourcesDialog.sendResources`` (bundle line 38082) sends the
        picked castle's ``kingdomID`` as ``SKID``; its castle picker leaves out
        ``CastleTransferResToKingdomProperties.exceptingKingdomIDs`` (bundle line 55533), and
        ``targetInitialized`` (bundle line 55553) needs ``getMainCastleByKingdomID`` of the
        target kingdom; ``CastleSendGoodsComponent.setTabVisibility`` (bundle line 44261)
        """
        amounts = self._sendable_goods(goods)
        source_kingdom = self._require_own_castle(source_castle_id).kingdom_id
        if source_kingdom in (target_kingdom_id, Kingdom.BERIMOND):
            raise ValueError(f"Goods cannot be sent to another kingdom from a castle in {source_kingdom.name}")
        if not any(castle.kingdom_id == target_kingdom_id for castle in self._own_castles()):
            raise ValueError(f"No castle of yours sits in {Kingdom(target_kingdom_id).name} to receive the goods")
        request = KingdomGoodsTransferRequest(
            source_castle_id=source_castle_id,
            source_kingdom_id=source_kingdom,
            target_kingdom_id=target_kingdom_id,
            goods=amounts,
        )
        self.execute(request, timeout=timeout)

    def skip_kingdom_transfer_time(
        self,
        kingdom_id: Kingdom,
        transfer_type: KingdomTransferType,
        minute_skip: Currency | str,
        *,
        timeout: float = 5.0,
    ) -> None:
        """
        Shorten the units or goods on their way to a kingdom with a minute skip item.

        Each kingdom has at most one units transfer and one goods transfer on
        the way; ``client.state.get_kingdoms()`` lists them. :meth:`skip_kingdom_transfer`
        finishes one at once for rubies.

        Args:
            kingdom_id: The kingdom the transfer goes to
            transfer_type: ``KingdomTransferType.UNITS`` or ``GOODS``
            minute_skip: The minute skip to use, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``;
                its key (``"MS1"``) also works, for a skip newer than the generated enum
            timeout: Timeout in seconds

        Raises:
            ValueError: ``minute_skip`` is no minute skip, or the special currencies hold none of it

        Client: ``KingdomUnitsTravelMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 37497),
        ``KingdomGoodsTravelMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 55567);
        ``CastleMinuteSkipDialog.showLoaded`` (bundle line 7671); ``MSKCommand`` (bundle line 125795)
        """
        self._require_minute_skip(minute_skip)
        request = MinuteSkipKingdomTransferRequest(
            minute_skip=minute_skip, kingdom_id=kingdom_id, transfer_type=transfer_type
        )
        self.execute(request, timeout=timeout)

    def transfer_goods_to_treasure_map(
        self,
        map_id: TreasureMapId | int,
        source_castle_id: int,
        goods: dict[Resource, int],
        *,
        timeout: float = 5.0,
    ) -> None:
        """
        Send wood, stone and food from one of your castles to a season's treasure map camp.

        The goods pass the checks of :meth:`send_resources`, and only the classic goods go: the
        client hides the other tabs, and the camp stores only those. The source castle may not
        sit in Berimond, which the client leaves out of its castle picker. The camp's free storage,
        the travel tax and the season's time left are left to the server. ``client.map.treasure_maps``
        shows the goods on their way.

        Args:
            map_id: The season's treasure map
            source_castle_id: The castle the goods leave from, one of yours
            goods: Amount per resource, such as ``{Resource.WOOD: 1000}``
            timeout: Timeout in seconds

        Raises:
            UnsendableGoodsError: The goods fail one of the checks of :meth:`send_resources`, or
                hold more than wood, stone and food
            ValueError: The source castle sits in Berimond
            UnknownCastleError: ``source_castle_id`` is not in your castle list
            CommandError: The server refused the transfer, ``NOT_ENOUGH_RESOURCES`` among others

        Client: ``CastleTransferResToSeasonProperties`` (bundle lines 99566-99588): ``exceptingKingdomIDs``,
        ``hideTabs``, ``getSendResourcesCommand``; ``TreasureMapVO.parseStorage`` (bundle line 140575);
        ``TGTCommand`` (bundle line 129068)
        """
        amounts = self._sendable_goods(goods)
        if extra := [resource.name for resource in amounts if resource.value not in _CLASSIC_GOODS]:
            raise UnsendableGoodsError(f"Only wood, stone and food go to a treasure map, not {extra}", goods)
        source_kingdom = self._require_own_castle(source_castle_id).kingdom_id
        if source_kingdom == Kingdom.BERIMOND:
            raise ValueError("Goods cannot be sent to a treasure map from a castle in Berimond")
        request = TreasureMapGoodsTransferRequest(
            map_id=map_id, source_castle_id=source_castle_id, source_kingdom_id=source_kingdom, goods=amounts
        )
        self.execute(request, timeout=timeout)

    def transfer_units_to_treasure_map(
        self,
        map_id: TreasureMapId | int,
        source_castle_id: int,
        units: WodAmountMapping | Sequence[WodAmount],
        *,
        timeout: float = 5.0,
    ) -> None:
        """
        Send units from one of your castles to a season's treasure map camp.

        The source castle may not sit in Berimond, which the client leaves out of its castle picker.
        The camp's free unit slots (``TreasureMapStorage.free_unit_slots``) and the season's time
        left are left to the server. ``client.map.treasure_maps`` shows the units on their way.

        Args:
            map_id: The season's treasure map
            source_castle_id: The castle the units leave from, one of yours
            units: The units, ``{Unit.X: 100}``
            timeout: Timeout in seconds

        Raises:
            ValueError: The source castle sits in Berimond
            UnknownCastleError: ``source_castle_id`` is not in your castle list
            CommandError: The server refused the transfer

        Client: ``CastleTransferTroopsToSeasonProperties`` (bundle lines 55367-55392):
        ``exceptingKingdomID``, ``getUnitTransferCommand``; ``TUTCommand`` (bundle line 129118)
        """
        source_kingdom = self._require_own_castle(source_castle_id).kingdom_id
        if source_kingdom == Kingdom.BERIMOND:
            raise ValueError("Units cannot be sent to a treasure map from a castle in Berimond")
        request = TreasureMapUnitTransferRequest(
            map_id=map_id,
            source_castle_id=source_castle_id,
            source_kingdom_id=source_kingdom,
            units=WodAmount.slots(units),
        )
        self.execute(request, timeout=timeout)

    def skip_treasure_map_transfer(
        self,
        map_id: TreasureMapId | int,
        transfer_type: KingdomTransferType,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Let the units or goods on their way to a season's treasure map arrive at once, for rubies.

        The request names the season event the map belongs to, taken from the running events.

        Args:
            map_id: The season's treasure map
            transfer_type: ``KingdomTransferType.UNITS`` or ``GOODS``
            spend_rubies: Allow the rubies the skip costs
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False, or no running season event has this map
            CommandError: The server refused the skip

        Client: ``CastleStartSeasonEventDialogSupport.onMouseUp`` (bundle lines 99541, 99543) sends the
        season's ``eventId``; the skip costs the map's ``skipCostC2`` rubies (bundle line 99514);
        ``TKTCommand`` (bundle line 129088)
        """
        self._require_spend_rubies(spend_rubies, "skipping a treasure map transfer costs rubies")
        season = self._running_season(map_id)
        request = TreasureMapTransferSkipRequest(event_id=season.event_id, map_id=map_id, transfer_type=transfer_type)
        self.execute(request, timeout=timeout)

    def skip_treasure_map_transfer_time(
        self,
        map_id: TreasureMapId | int,
        transfer_type: KingdomTransferType,
        minute_skip: Currency | str,
        *,
        timeout: float = 5.0,
    ) -> None:
        """
        Shorten the units or goods on their way to a season's treasure map with a minute skip item.

        Args:
            map_id: The season's treasure map
            transfer_type: ``KingdomTransferType.UNITS`` or ``GOODS``
            minute_skip: The minute skip used, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``
            timeout: Timeout in seconds

        Raises:
            ValueError: No running season event has this map, or ``minute_skip`` is no minute skip you hold
            CommandError: The server refused the skip

        Client: ``SeasonTravelGoodsMinuteSkipProperties.getMinuteSkipCommand`` and
        ``SeasonTravelUnitsMinuteSkipProperties.getMinuteSkipCommand`` (bundle lines 99612, 99644);
        ``MSMCommand`` (bundle line 125852)
        """
        self._running_season(map_id)
        self._require_minute_skip(minute_skip)
        request = MinuteSkipSeasonTransferRequest(map_id=map_id, transfer_type=transfer_type, minute_skip=minute_skip)
        self.execute(request, timeout=timeout)

    def _running_season(self, map_id: TreasureMapId | int) -> SeasonEvent:
        for event in self.client.state.get_events().values():
            if isinstance(event, SeasonEvent) and event.map_id == map_id:
                return event
        raise ValueError(f"No running season event has treasure map {map_id}")

    def skip_kingdom_transfer(
        self,
        kingdom_id: Kingdom,
        transfer_type: KingdomTransferType,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Finish the units or goods on their way to a kingdom at once, for rubies.

        The price is the kingdom's ``skipUnitTravelC2Cost`` or ``skipResourceTravelC2Cost`` in the
        items ``kingdoms`` table, less any ruby discount. Once a ``kpi`` is known, the transfer must
        be on its way there with a second left at least, as the client offers it only then.

        Args:
            kingdom_id: The kingdom the transfer goes to
            transfer_type: ``KingdomTransferType.UNITS`` or ``GOODS``
            spend_rubies: Allow spending the rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False, or no such transfer is on its way
            CommandError: The server refused

        Client: ``CastleHandleKingdomDialogSupport.onClick`` (bundle lines 98420, 98422) sends
        ``C2SKingdomSkipTransferVO`` while ``remainingTimeInSeconds >= 1``, its button priced with
        ``skipUnitTravelC2Cost`` / ``skipResourceTravelC2Cost`` (bundle line 98398); ``KSTCommand``
        (bundle line 124755)
        """
        self._require_spend_rubies(spend_rubies, "a full transfer skip costs rubies")
        kingdoms = self.client.state.get_kingdoms()
        if kingdoms is not None:
            transfers = (
                kingdoms.unit_transfers if transfer_type == KingdomTransferType.UNITS else kingdoms.goods_transfers
            )
            if not any(t.kingdom_id == kingdom_id and t.remaining_seconds() >= 1 for t in transfers):
                what = KingdomTransferType(transfer_type).name.lower()
                raise ValueError(f"no {what} transfer is on its way to {Kingdom(kingdom_id).name}")
        request = KingdomSkipTransferRequest(kingdom_id=kingdom_id, transfer_type=transfer_type)
        self.execute(request, timeout=timeout)
