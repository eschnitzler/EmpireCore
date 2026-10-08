"""
Your castles: resources, buildings, the construction queue, and sending goods and troops.

It covers:

- Castle management (list, join, rename)
- Resources and production
- Buildings and the construction queue
- Sending resources, support and units
- Tax collection

Action methods return True when the server accepted the action and False
when it rejected it with an error code; transport failures (timeout,
disconnect) raise. Query methods raise on any failure, and so do
``start_tax`` and ``collect_tax``, which return their replies.

Methods that take one of your castles send its kingdom from the castle
list the server sent at login (``client.state.get_castles()``), as the
client does, and raise ``UnknownCastleError`` for an id not in it, or
``AmbiguousCastleError`` for an id listed in several of your kingdoms.

Building methods act on the castle joined last (:meth:`CastleService.join`)
and name buildings by object id, a ``BuildingRow.object_id`` from
``join(...).buildings``. Their typed replies (``BuildResponse`` and the
others) can be read with ``client.request``.
"""

from __future__ import annotations

from collections.abc import Sequence

from empire_core.castle.models.actions import (
    JoinAreaRequest,
    RenameCastleRequest,
    SelectCastleRequest,
    SelectCastleResponse,
)
from empire_core.castle.models.buildings import (
    BuildRequest,
    BuyExtensionRequest,
    CollectExtensionGiftRequest,
    DestroyBuildingRequest,
    FastCompleteRequest,
    MoveBuildingRequest,
    RepairAllRequest,
    RepairBuildingRequest,
    SellBuildingRequest,
    TimeSkipBuildingRequest,
    UpgradeBuildingRequest,
    UpgradeWallRequest,
)
from empire_core.castle.models.castles import CastleInfo, GetCastlesRequest, GetCastlesResponse
from empire_core.castle.models.collect import CollectMineResourcesRequest, CollectResourceCartRequest
from empire_core.castle.models.details import (
    CastleProductionArea,
    DetailedCastleInfo,
    GetDetailedCastleRequest,
    GetDetailedCastleResponse,
)
from empire_core.castle.models.market import (
    CreateMarketMovementRequest,
    MarketCastle,
    MarketInfoRequest,
    MarketInfoResponse,
)
from empire_core.castle.models.objects import (
    ConstructionList,
    ShowConstructionListRequest,
    ShowConstructionListResponse,
)
from empire_core.castle.models.resources import (
    CastleResources,
    GetProductionRequest,
    GetProductionResponse,
    GetResourcesRequest,
    GetResourcesResponse,
)
from empire_core.castle.models.support import SendSupportRequest, SendTroopsRequest
from empire_core.castle.models.tax import (
    TAX_DURATIONS,
    TAX_RUBY_COSTS,
    CollectTaxRequest,
    CollectTaxResponse,
    GetTaxInfoRequest,
    StartTaxRequest,
    StartTaxResponse,
    TaxInfo,
    TaxInfoResponse,
)
from empire_core.castle.models.transfers import KingdomUnitTransferRequest
from empire_core.enums import ExpansionType, Kingdom, Resource, ResourceCartType
from empire_core.exceptions import (
    AmbiguousCastleError,
    GameDataNotLoadedError,
    UnknownCastleError,
    UnsendableGoodsError,
)
from empire_core.gamedata import Currency, HorseStats, WodAmount, WodAmountMapping
from empire_core.services.base import BaseService

_CLASSIC_GOODS = (Resource.WOOD.value, Resource.STONE.value, Resource.FOOD.value)
_GOODS_TABS = (
    _CLASSIC_GOODS,
    (Resource.COAL.value, Resource.OIL.value, Resource.GLASS.value, Resource.IRON.value),
    (Resource.HONEY.value, Resource.MEAD.value, Resource.BEEF.value),
)


class CastleService(BaseService):
    """
    Your castles, their buildings and resources, and sending goods and troops.

    Reached as client.castle.

    Usage:
        client = EmpireClient(...)
        client.login()

        # Get all castles
        castles = client.castle.get_all()
        for c in castles:
            print(f"{c.castle_name} at ({c.x}, {c.y})")

        # Join a castle and read its buildings
        castle = client.castle.join(castle_id=12345)

        # Get resources
        resources = client.castle.get_resources(castle_id=12345)
    """

    # =========================================================================
    # Castle List Operations
    # =========================================================================

    def get_all(self, timeout: float = 5.0) -> list[CastleInfo]:
        """
        Get list of all player's castles.

        Sends the logged-in player's id, as the client does, once the state knows it.

        Example:
            castles = client.castle.get_all()
            for c in castles:
                print(f"{c.castle_name} (ID: {c.castle_id}) at ({c.x}, {c.y})")
        """
        player = self.client.state.get_local_player()
        player_id = getattr(player, "id", None)
        request = GetCastlesRequest(player_id=player_id if isinstance(player_id, int) and player_id > 0 else None)
        return self.request(request, GetCastlesResponse, timeout=timeout).castles

    def get_details(self, castle_id: int, timeout: float = 5.0) -> DetailedCastleInfo:
        """
        Get resources and stationed units for one castle.

        The server answers with every castle of yours; the one asked for is picked out here.

        Args:
            castle_id: One of your castles, from ``client.castle.get_all()``
                (``CastleInfo.castle_id``) or ``client.state.get_castles()`` (``Castle.id``)
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: The reply lists no castle with that id
            AmbiguousCastleError: The reply lists the id in several kingdoms

        Example:
            details = client.castle.get_details(12345)
            print(f"Wood: {details.wood}, units: {details.units}")
        """
        response = self.request(GetDetailedCastleRequest(), GetDetailedCastleResponse, timeout=timeout)
        castle = response.castle(castle_id)
        if castle is None:
            raise UnknownCastleError(castle_id)
        return castle

    # =========================================================================
    # Castle Selection
    # =========================================================================

    def select(self, castle_id: int, timeout: float = 5.0) -> bool:
        """
        Select/jump to a castle (makes it the active castle).

        Use :meth:`join` for the castle's state the server sends back.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list
            AmbiguousCastleError: ``castle_id`` repeats across your kingdoms

        Client: ``C2SJoinCastleVO`` sent with the castle's ``objectId`` and
        ``kingdomID`` (``JoinAreaAndSavePositionCommand.execute``, bundle line 100892)

        Example:
            if client.castle.select(12345):
                print("Castle selected!")
        """
        kingdom_id = self._require_own_castle(castle_id).kingdom_id
        return self.execute(SelectCastleRequest(castle_id=castle_id, kingdom_id=kingdom_id), timeout=timeout)

    def join(self, castle_id: int, timeout: float = 5.0) -> SelectCastleResponse:
        """
        Join a castle, making it the active castle, and return its state.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list
            AmbiguousCastleError: ``castle_id`` repeats across your kingdoms
            CommandError: The server refused the join.

        Client: ``C2SJoinCastleVO`` sent with the castle's ``objectId`` and
        ``kingdomID`` (``JoinAreaAndSavePositionCommand.execute``, bundle line 100892)

        Example:
            castle = client.castle.join(12345)
            if castle.buildings:
                print([b.wod_id for b in castle.buildings.buildings])
        """
        kingdom_id = self._require_own_castle(castle_id).kingdom_id
        return self.request(
            SelectCastleRequest(castle_id=castle_id, kingdom_id=kingdom_id), SelectCastleResponse, timeout=timeout
        )

    def join_area(
        self, x: int, y: int, kingdom_id: Kingdom = Kingdom.GREEN, timeout: float = 5.0
    ) -> SelectCastleResponse:
        """
        Join an area by its position (``jaa``), making it the active area, and return its state.

        The client joins this way the objects it may visit that are not
        castles: outposts, capitals, metropolises and faction camps that are
        not destroyed, and a kingdom castle just after its first naming. It
        joins main and kingdom castles otherwise by id, as :meth:`join` does.
        It never joins anything else (see :class:`JoinAreaRequest`).

        Args:
            x: Map x of the area
            y: Map y of the area
            kingdom_id: The kingdom it lies in
            timeout: Timeout in seconds

        Raises:
            CommandError: The server refused the join; a live server answered
                INVALID_POSITION (6) for objects the client never joins, such as NPC camps
                and kings towers

        Client: ``JoinAreaAndSavePositionCommand.execute`` (bundle line 100892),
        ``JAACommand.executeCommand`` (bundle line 130190)
        """
        return self.request(JoinAreaRequest(x=x, y=y, kingdom_id=kingdom_id), SelectCastleResponse, timeout=timeout)

    # =========================================================================
    # Castle Modification
    # =========================================================================

    def rename(self, castle_id: int, new_name: str, *, is_initial_name: bool = False, timeout: float = 5.0) -> bool:
        """
        Rename one of your castles.

        Looks the castle up in the castle list for the type and kingdom the
        server needs, so this costs one extra round trip. Pass
        ``is_initial_name=True`` to name a newly acquired castle, such as a
        monument or laboratory, instead of renaming one.

        Args:
            castle_id: One of your castles, from ``client.castle.get_all()``
                (``CastleInfo.castle_id``)
            new_name: The new name
            is_initial_name: Name a newly acquired castle instead of renaming one
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not one of your castles.
            AmbiguousCastleError: ``castle_id`` repeats across your kingdoms

        Example:
            if client.castle.rename(12345, "My Fortress"):
                print("Castle renamed!")
        """
        matches = [c for c in self.get_all(timeout=timeout) if c.castle_id == castle_id]
        if len(matches) > 1:
            raise AmbiguousCastleError(castle_id, [c.kingdom_id for c in matches])
        if not matches:
            raise UnknownCastleError(castle_id)
        castle = matches[0]
        return self.execute(
            RenameCastleRequest(
                castle_id=castle_id,
                castle_name=new_name,
                castle_type=castle.castle_type,
                kingdom_id=castle.kingdom_id,
                is_rename=0 if is_initial_name else 1,
            ),
            timeout=timeout,
        )

    # =========================================================================
    # Resource Operations
    # =========================================================================

    def get_resources(self, castle_id: int, timeout: float = 5.0) -> CastleResources:
        """
        Get one of your castles' resources.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list
            AmbiguousCastleError: ``castle_id`` repeats across your kingdoms

        Client: ``C2SGetCastleResourcesVO`` sent with the castle's ``objectId`` and
        ``kingdomID`` (``CastleTransferResourcesDialog.onSelectCastle``, bundle line 38076)

        Example:
            resources = client.castle.get_resources(12345)
            print(f"Wood: {resources.wood}")
        """
        kingdom_id = self._require_own_castle(castle_id).kingdom_id
        return self.request(
            GetResourcesRequest(castle_id=castle_id, kingdom_id=kingdom_id), GetResourcesResponse, timeout=timeout
        )

    def get_production(self, timeout: float = 5.0) -> CastleProductionArea:
        """
        Get the joined castle's production area: production, storage, population and the rest.

        Join the castle first with :meth:`join`; the server answers for the joined castle.

        Example:
            client.castle.join(12345)
            area = client.castle.get_production()
            print(f"Wood/hr: {area.production.wood}")
        """
        return self.request(GetProductionRequest(), GetProductionResponse, timeout=timeout)

    # =========================================================================
    # Buildings
    # =========================================================================

    def get_build_queue(self, timeout: float = 5.0) -> ConstructionList:
        """
        Get the joined castle's construction slots.

        Example:
            queue = client.castle.get_build_queue()
            print(queue.building_object_ids, queue.free_slots)
        """
        return self.request(ShowConstructionListRequest(), ShowConstructionListResponse, timeout=timeout)

    def build(
        self,
        wod_id: int,
        x: int,
        y: int,
        rotation: int = 0,
        *,
        pay_with_rubies: bool = False,
        private_offer_id: int = -1,
        district_object_id: int = -1,
        timeout: float = 5.0,
    ) -> bool:
        """
        Place a new building in the joined castle.

        Args:
            wod_id: The building type's wod id
            x: Castle grid x, -1 when placing into a district
            y: Castle grid y, -1 when placing into a district
            rotation: Rotation
            pay_with_rubies: Pay the missing resources with rubies
            private_offer_id: The private offer the purchase uses, -1 for none
            district_object_id: Object id of the district to place into, -1 for none
            timeout: Timeout in seconds
        """
        request = BuildRequest(
            wod_id=wod_id,
            x=x,
            y=y,
            rotation=rotation,
            pay_with_rubies=pay_with_rubies,
            private_offer_id=private_offer_id,
            district_object_id=district_object_id,
        )
        return self.execute(request, timeout=timeout)

    def upgrade_building(
        self, object_id: int, *, pay_with_rubies: bool = False, private_offer_id: int = -1, timeout: float = 5.0
    ) -> bool:
        """Upgrade a building in the joined castle."""
        request = UpgradeBuildingRequest(
            object_id=object_id, pay_with_rubies=pay_with_rubies, private_offer_id=private_offer_id
        )
        return self.execute(request, timeout=timeout)

    def move_building(self, object_id: int, x: int, y: int, rotation: int = 0, timeout: float = 5.0) -> bool:
        """Move a building in the joined castle."""
        return self.execute(MoveBuildingRequest(object_id=object_id, x=x, y=y, rotation=rotation), timeout=timeout)

    def sell_decoration(self, object_id: int, timeout: float = 5.0) -> bool:
        """Sell a decoration placed in the joined castle."""
        return self.execute(SellBuildingRequest(object_id=object_id), timeout=timeout)

    def destroy_building(self, object_id: int, timeout: float = 5.0) -> bool:
        """Start taking a building in the joined castle down."""
        return self.execute(DestroyBuildingRequest(object_id=object_id), timeout=timeout)

    def finish_construction(self, object_id: int, *, free_skip: bool = False, timeout: float = 5.0) -> bool:
        """Finish a building's running construction at once, for rubies or with an event's free skip."""
        return self.execute(FastCompleteRequest(object_id=object_id, free_skip=free_skip), timeout=timeout)

    def skip_construction_time(self, object_id: int, minute_skip: Currency | str, timeout: float = 5.0) -> bool:
        """
        Shorten a building's running construction with a minute skip.

        Args:
            object_id: The building's object id
            minute_skip: The minute skip to use, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``;
                its key (``"MS1"``) also works, for a skip newer than the generated enum
            timeout: Timeout in seconds
        """
        return self.execute(TimeSkipBuildingRequest(object_id=object_id, minute_skip=minute_skip), timeout=timeout)

    def upgrade_defense(
        self, object_id: int, *, pay_with_rubies: bool = False, private_offer_id: int = -1, timeout: float = 5.0
    ) -> bool:
        """Upgrade the joined castle's wall, gate or one of its towers, by its object id."""
        request = UpgradeWallRequest(
            object_id=object_id, private_offer_id=private_offer_id, pay_with_rubies=pay_with_rubies
        )
        return self.execute(request, timeout=timeout)

    def repair_building(
        self, object_id: int, *, pay_with_rubies: bool = False, private_offer_id: int = -1, timeout: float = 5.0
    ) -> bool:
        """Repair a damaged building in the joined castle."""
        request = RepairBuildingRequest(
            object_id=object_id, private_offer_id=private_offer_id, pay_with_rubies=pay_with_rubies
        )
        return self.execute(request, timeout=timeout)

    def repair_all(self, timeout: float = 5.0) -> bool:
        """Repair every damaged building in the joined castle at once."""
        return self.execute(RepairAllRequest(), timeout=timeout)

    def buy_expansion(
        self,
        x: int,
        y: int,
        rotation: int = 0,
        expansion_type: ExpansionType = ExpansionType.NORMAL,
        timeout: float = 5.0,
    ) -> bool:
        """Buy an expansion of the joined castle's grounds, with resources (NORMAL) or rubies (PREMIUM)."""
        return self.execute(
            BuyExtensionRequest(x=x, y=y, rotation=rotation, expansion_type=expansion_type), timeout=timeout
        )

    def open_treasure_chest(self, object_id: int, timeout: float = 5.0) -> bool:
        """Open a treasure chest found on an expansion of the joined castle."""
        return self.execute(CollectExtensionGiftRequest(object_id=object_id), timeout=timeout)

    def collect_mine(self, object_id: int, timeout: float = 5.0) -> bool:
        """Collect what a mine in the joined castle has produced."""
        return self.execute(CollectMineResourcesRequest(object_id=object_id), timeout=timeout)

    def collect_resource_cart(self, cart_type: ResourceCartType, timeout: float = 5.0) -> bool:
        """Collect the joined castle's resource cart of one resource."""
        return self.execute(CollectResourceCartRequest(cart_type=cart_type), timeout=timeout)

    # =========================================================================
    # Tax
    # =========================================================================

    def get_tax_info(self, timeout: float = 5.0) -> TaxInfo:
        """
        Read the tax collection status.

        Example:
            tax = client.castle.get_tax_info()
            print(tax.status, tax.remaining_seconds, tax.expected_income)

        Client: ``C2SGetTaxInfoVO`` (bundle line 37186), ``TXICommand`` (bundle line 128792)
        """
        return self.request(GetTaxInfoRequest(), TaxInfoResponse, timeout=timeout).tax

    def start_tax(self, tax_type: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> StartTaxResponse:
        """
        Start a tax collection.

        Tax types 0 to 6 collect for ``TAX_DURATIONS[tax_type]`` seconds. Type 0
        is free and types 1 to 4 cost a tenth of their income in coins. Types 5
        and 6 cost ``TAX_RUBY_COSTS`` rubies unless a premium account, a VIP
        level or the tax research waives it; this method refuses them unless
        ``spend_rubies`` is True, and does not check for a waiver.

        Args:
            tax_type: The tax type, 0 to 6
            spend_rubies: Allow types 5 and 6, which may spend rubies
            timeout: Timeout in seconds

        Returns:
            The reply: coins and rubies after, and the tax status.

        Raises:
            ValueError: ``tax_type`` is not 0 to 6, or costs rubies and ``spend_rubies`` is False
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SStartCollectTaxVO`` (bundle line 91088), sent by
        ``CastleCollectTaxElement.onStartTaxCollection`` (bundle line 91069), which
        shows a ruby cost when ``CollectTaxElementVO.hasC2CostWithoutPremium``
        (bundle line 91050); ``TaxConst`` (dll lines 19771-19790)
        """
        if not 0 <= tax_type < len(TAX_DURATIONS):
            raise ValueError(f"tax_type must be 0 to {len(TAX_DURATIONS) - 1}, got {tax_type}")
        if TAX_RUBY_COSTS[tax_type] > 0 and not spend_rubies:
            raise ValueError(
                f"tax type {tax_type} costs {TAX_RUBY_COSTS[tax_type]} rubies unless waived; pass spend_rubies=True"
            )
        return self.request(StartTaxRequest(tax_type=tax_type), StartTaxResponse, timeout=timeout)

    def collect_tax(self, timeout: float = 5.0) -> CollectTaxResponse:
        """
        Collect the tax.

        Collecting while the collection runs brings the share of its income
        earned so far; the client asks first when that is nothing.

        Returns:
            The reply: the coins collected, coins and rubies after, and the tax status.

        Raises:
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``C2SCollectTaxVO`` (bundle line 41083), sent by
        ``CastleCollectTaxDialog.collectTax`` (bundle line 91027) after
        ``onCollectTaxClick`` (bundle line 91015); ``TaxConst.getCollectedMoney``
        (dll line 19784); ``TXCCommand`` (bundle line 128747)
        """
        return self.request(CollectTaxRequest(), CollectTaxResponse, timeout=timeout)

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
        horse_booster_id: int = -1,
        feathers: bool = False,
        slowdown: int = 0,
        timeout: float = 5.0,
    ) -> bool:
        """
        Send resources from one of your castles to a castle on the map, by carriage.

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
            horse_booster_id: The horse's wod id, -1 for none; sent as -1 whenever
                feathers are used, as the client does
            feathers: Pay for the horse with feathers
            slowdown: Seconds to delay the arrival by
            timeout: Timeout in seconds

        Raises:
            UnsendableGoodsError: The goods fail one of the checks above
            UnknownCastleError: ``source_castle_id`` is not in your castle list
            AmbiguousCastleError: ``source_castle_id`` repeats across your kingdoms

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
        request = CreateMarketMovementRequest(
            kingdom_id=self._require_own_castle(source_castle_id).kingdom_id,
            source_castle_id=source_castle_id,
            target_x=target_x,
            target_y=target_y,
            horse_booster_id=-1 if feathers else horse_booster_id,
            feathers=1 if feathers else 0,
            slowdown=slowdown,
            goods=amounts,
        )
        return self.execute(request, timeout=timeout)

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
        if player is not None and player.level > 0 and player.legendary_level <= 0:
            beyond = [key.value for key in amounts if key not in _CLASSIC_GOODS]
            if beyond:
                raise UnsendableGoodsError(
                    f"Only wood, stone and food can be sent below legend level, not {', '.join(map(str, beyond))}",
                    goods,
                )
        return amounts

    def get_market_info(self, timeout: float = 5.0) -> list[MarketCastle]:
        """
        List every castle's market carriages, those not on the road, and its resources.

        Example:
            for castle in client.castle.get_market_info():
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
        horse_booster_id: int = -1,
        feathers: bool = False,
        slowdown: int = 0,
        timeout: float = 5.0,
        *,
        spend_rubies: bool = False,
    ) -> bool:
        """
        Send support troops from a castle to a target location.

        The server refuses a support to your own area with NO_SELF_DESTRUCTION
        (92); move troops between your own areas with :meth:`send_troops`.

        A support led by the premium commander is refused before sending when it
        may cost rubies, unless ``spend_rubies`` is True; see
        ``client.commanders.premium_send``.

        Args:
            source_castle_id: The castle the troops leave from, one of yours: ``CastleInfo.castle_id``
                from ``client.castle.get_all()`` or ``Castle.id`` from ``client.state.get_castles()``
            target_x: Target X coordinate
            target_y: Target Y coordinate
            units: The units, then any tools: ``{Unit.X: 100}``, or pairs one per slot
            commander_id: Commander to lead the support, a ``Commander.commander_id``
                from ``client.commanders.get_commanders()``.
                There is no default: ``0`` is a real commander (the free starting
                one), and the client never sends a support without a commander
                (with none picked it leads with the premium one, ``-14``)
            wait_time: Station duration in hours (0-12, default: 12)
            use_premium_commander: Lead with the premium commander (``commander_id``
                -14). It uses one of your free premium commanders, or costs rubies
                when none is left and no premium account runs
            horse_booster_id: Type of horses for speed bonus (-1 = none, default: -1);
                sent as -1 whenever feathers are used, as the client does
            feathers: Pay for the movement with feathers
            slowdown: Movement slowdown modifier (0 = none, default: 0)
            timeout: Timeout in seconds
            spend_rubies: Send with the premium commander even when it may cost rubies

        Raises:
            PremiumCommanderCostError: The premium commander leads, may cost rubies,
                and ``spend_rubies`` is False
            GameDataNotLoadedError: The premium commander leads, VIP time runs and
                ``client.load_game_data()`` has not been called
        """
        request = SendSupportRequest(
            source_castle_id=source_castle_id,
            target_x=target_x,
            target_y=target_y,
            units=WodAmount.slots(units),
            wait_time=wait_time,
            use_premium_commander=1 if use_premium_commander else 0,
            horse_booster_id=-1 if feathers else horse_booster_id,
            feathers=1 if feathers else 0,
            slowdown=slowdown,
            commander_id=commander_id,
        )
        return self.client.commanders.premium_send(
            commander_id,
            use_premium_commander,
            lambda: self.execute(request, timeout=timeout),
            spend_rubies=spend_rubies,
        )

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
        horse_booster_id: int = -1,
        feathers: bool = False,
        slowdown: int = 0,
        timeout: float = 5.0,
    ) -> bool:
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
            spend_rubies: Send with the premium commander even when it may cost rubies
            horse_booster_id: The horse's wod id, -1 for none; sent as -1 whenever
                feathers are used, as the client does
            feathers: Pay for the horse with feathers
            slowdown: Seconds to delay the arrival by
            timeout: Timeout in seconds

        Raises:
            PremiumCommanderCostError: The premium commander leads, may cost rubies,
                and ``spend_rubies`` is False; see ``client.commanders.premium_send``
            GameDataNotLoadedError: The premium commander leads, VIP time runs and
                ``client.load_game_data()`` has not been called
        """
        request = SendTroopsRequest(
            source_x=source_x,
            source_y=source_y,
            target_x=target_x,
            target_y=target_y,
            kingdom_id=kingdom_id,
            commander_id=commander_id,
            horse_booster_id=-1 if feathers else horse_booster_id,
            use_premium_commander=1 if use_premium_commander else 0,
            feathers=1 if feathers else 0,
            slowdown=slowdown,
            units=WodAmount.slots(units),
        )
        return self.client.commanders.premium_send(
            commander_id,
            use_premium_commander,
            lambda: self.execute(request, timeout=timeout),
            spend_rubies=spend_rubies,
        )

    def transfer_units_to_kingdom(
        self,
        source_castle_id: int,
        target_kingdom_id: Kingdom,
        units: WodAmountMapping | Sequence[WodAmount],
        *,
        target_castle_id: int = -1,
        timeout: float = 5.0,
    ) -> bool:
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
            AmbiguousCastleError: ``source_castle_id`` repeats across your kingdoms

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
        return self.execute(request, timeout=timeout)

    def get_horses(self, castle_id: int) -> list[HorseStats] | None:
        """
        The horses one of your castles can send movements with, by wod id.

        Read from the login data's ``gpc`` section and its pushes; nothing is
        sent. A horse whose ``is_instant_spy_horse`` is set can be paid with
        rubies or, sent as ``feathers=True``, with feathers; the client shows it
        twice, once per payment. An id missing from the game data is left out,
        as the client leaves it out.

        Args:
            castle_id: One of your castles, ``Castle.id`` from ``client.state.get_castles()``;
                its kingdom is taken from the castle list

        Returns:
            The horses sorted by wod id, or None when no ``gpc`` named the castle yet

        Raises:
            GameDataNotLoadedError: ``client.load_game_data()`` has not been called
            UnknownCastleError: ``castle_id`` is not in your castle list
            AmbiguousCastleError: ``castle_id`` repeats across your kingdoms

        Client: ``CastleHorsesVO.parseParamObject`` (bundle line 139177),
        ``CastlePermanentCastleData.getCastleByWorldAreaId`` (bundle line 139145)
        """
        game_data = self.client.game_data
        if game_data is None:
            raise GameDataNotLoadedError("Horse stats need the items payload: call client.load_game_data() first")
        self._require_own_castle(castle_id)
        horse_ids = self.client.state.get_castle_horse_ids(castle_id)
        if horse_ids is None:
            return None
        horses = [horse for wod_id in horse_ids if (horse := game_data.get_horse(wod_id)) is not None]
        return sorted(horses, key=lambda horse: horse.wod_id)


__all__ = ["CastleService"]
