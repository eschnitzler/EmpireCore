"""
Castle service for EmpireCore.

Provides high-level APIs for:
- Castle management (list, join, rename)
- Resources and production
- Buildings and the construction queue
- Sending resources, support and units

Action methods return True when the server accepted the action and False
when it rejected it with an error code; transport failures (timeout,
disconnect) raise. Query methods raise on any failure.

Building methods act on the castle joined last (:meth:`CastleService.join`)
and name buildings by object id, a ``BuildingRow.object_id`` from
``join(...).buildings``. Their typed replies (``BuildResponse`` and the
others) can be read with ``client.request``.
"""

from __future__ import annotations

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
from empire_core.castle.models.transfers import KingdomUnitTransferRequest
from empire_core.enums import ExpansionType, Kingdom, ResourceCartType
from empire_core.services.base import BaseService


class CastleService(BaseService):
    """
    Service for castle operations.

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
        request = GetCastlesRequest(PID=player_id if isinstance(player_id, int) and player_id > 0 else None)
        return self.request(request, GetCastlesResponse, timeout=timeout).castles

    def get_details(self, castle_id: int, timeout: float = 5.0) -> DetailedCastleInfo | None:
        """
        Get resources and stationed units for one castle.

        The server answers with every castle; the one asked for is picked
        out here, and None means it was not in the list.

        Args:
            castle_id: One of your castles, from ``client.castle.get_all()``
                (``CastleInfo.castle_id``) or ``client.state.get_castles()`` (``Castle.id``)
            timeout: Timeout in seconds

        Example:
            details = client.castle.get_details(12345)
            if details:
                print(f"Wood: {details.wood}, units: {details.units}")
        """
        response = self.request(GetDetailedCastleRequest(), GetDetailedCastleResponse, timeout=timeout)
        return response.castle(castle_id)

    # =========================================================================
    # Castle Selection
    # =========================================================================

    def select(self, castle_id: int, kingdom_id: Kingdom = Kingdom.GREEN, timeout: float = 5.0) -> bool:
        """
        Select/jump to a castle (makes it the active castle).

        Use :meth:`join` for the castle's state the server sends back.

        Args:
            castle_id: One of your castles, from ``client.castle.get_all()``
                (``CastleInfo.castle_id``) or ``client.state.get_castles()`` (``Castle.id``)
            kingdom_id: The castle's kingdom, its ``CastleInfo.kingdom_id``
            timeout: Timeout in seconds

        Example:
            if client.castle.select(12345, kingdom_id=Kingdom.ICE):
                print("Castle selected!")
        """
        return self.execute(SelectCastleRequest(CID=castle_id, KID=kingdom_id), timeout=timeout)

    def join(self, castle_id: int, kingdom_id: Kingdom = Kingdom.GREEN, timeout: float = 5.0) -> SelectCastleResponse:
        """
        Join a castle, making it the active castle, and return its state.

        Args:
            castle_id: One of your castles, from ``client.castle.get_all()``
                (``CastleInfo.castle_id``) or ``client.state.get_castles()`` (``Castle.id``)
            kingdom_id: The castle's kingdom, its ``CastleInfo.kingdom_id``
            timeout: Timeout in seconds

        Raises:
            CommandError: The server refused the join.

        Example:
            castle = client.castle.join(12345)
            if castle.buildings:
                print([b.wod_id for b in castle.buildings.buildings])
        """
        return self.request(SelectCastleRequest(CID=castle_id, KID=kingdom_id), SelectCastleResponse, timeout=timeout)

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
        return self.request(JoinAreaRequest(PX=x, PY=y, KID=kingdom_id), SelectCastleResponse, timeout=timeout)

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
            ValueError: ``castle_id`` is not one of your castles.

        Example:
            if client.castle.rename(12345, "My Fortress"):
                print("Castle renamed!")
        """
        castle = next((c for c in self.get_all(timeout=timeout) if c.castle_id == castle_id), None)
        if castle is None:
            raise ValueError(f"castle {castle_id} is not one of your castles")
        return self.execute(
            RenameCastleRequest(
                CID=castle_id,
                N=new_name,
                AT=castle.castle_type,
                KID=castle.kingdom_id,
                P=0 if is_initial_name else 1,
            ),
            timeout=timeout,
        )

    # =========================================================================
    # Resource Operations
    # =========================================================================

    def get_resources(
        self, castle_id: int, kingdom_id: Kingdom = Kingdom.GREEN, timeout: float = 5.0
    ) -> CastleResources:
        """
        Get one of your castles' resources.

        Args:
            castle_id: One of your castles, from ``client.castle.get_all()``
                (``CastleInfo.castle_id``) or ``client.state.get_castles()`` (``Castle.id``)
            kingdom_id: The castle's kingdom, its ``CastleInfo.kingdom_id``
            timeout: Timeout in seconds

        Example:
            resources = client.castle.get_resources(12345)
            print(f"Wood: {resources.wood}")
        """
        return self.request(GetResourcesRequest(AID=castle_id, KID=kingdom_id), GetResourcesResponse, timeout=timeout)

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
            WID=wod_id,
            X=x,
            Y=y,
            R=rotation,
            PWR=pay_with_rubies,
            PO=private_offer_id,
            DOID=district_object_id,
        )
        return self.execute(request, timeout=timeout)

    def upgrade_building(
        self, object_id: int, *, pay_with_rubies: bool = False, private_offer_id: int = -1, timeout: float = 5.0
    ) -> bool:
        """Upgrade a building in the joined castle."""
        request = UpgradeBuildingRequest(OID=object_id, PWR=pay_with_rubies, PO=private_offer_id)
        return self.execute(request, timeout=timeout)

    def move_building(self, object_id: int, x: int, y: int, rotation: int = 0, timeout: float = 5.0) -> bool:
        """Move a building in the joined castle."""
        return self.execute(MoveBuildingRequest(OID=object_id, X=x, Y=y, R=rotation), timeout=timeout)

    def sell_decoration(self, object_id: int, timeout: float = 5.0) -> bool:
        """Sell a decoration placed in the joined castle."""
        return self.execute(SellBuildingRequest(OID=object_id), timeout=timeout)

    def destroy_building(self, object_id: int, timeout: float = 5.0) -> bool:
        """Start taking a building in the joined castle down."""
        return self.execute(DestroyBuildingRequest(OID=object_id), timeout=timeout)

    def finish_construction(self, object_id: int, *, free_skip: bool = False, timeout: float = 5.0) -> bool:
        """Finish a building's running construction at once, for rubies or with an event's free skip."""
        return self.execute(FastCompleteRequest(OID=object_id, FS=free_skip), timeout=timeout)

    def skip_construction_time(self, object_id: int, minute_skip: str, timeout: float = 5.0) -> bool:
        """
        Shorten a building's running construction with a minute skip.

        Args:
            object_id: The building's object id
            minute_skip: JSON key of the minute-skip currency to use, MS1 to MS7
                (``SCEItem.SKIP_1_MIN`` and the others)
            timeout: Timeout in seconds
        """
        return self.execute(TimeSkipBuildingRequest(OID=object_id, MST=minute_skip), timeout=timeout)

    def upgrade_defense(
        self, object_id: int, *, pay_with_rubies: bool = False, private_offer_id: int = -1, timeout: float = 5.0
    ) -> bool:
        """Upgrade the joined castle's wall, gate or one of its towers, by its object id."""
        request = UpgradeWallRequest(OID=object_id, PO=private_offer_id, PWR=pay_with_rubies)
        return self.execute(request, timeout=timeout)

    def repair_building(
        self, object_id: int, *, pay_with_rubies: bool = False, private_offer_id: int = -1, timeout: float = 5.0
    ) -> bool:
        """Repair a damaged building in the joined castle."""
        request = RepairBuildingRequest(OID=object_id, PO=private_offer_id, PWR=pay_with_rubies)
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
        return self.execute(BuyExtensionRequest(X=x, Y=y, R=rotation, CT=expansion_type), timeout=timeout)

    def open_treasure_chest(self, object_id: int, timeout: float = 5.0) -> bool:
        """Open a treasure chest found on an expansion of the joined castle."""
        return self.execute(CollectExtensionGiftRequest(OID=object_id), timeout=timeout)

    def collect_mine(self, object_id: int, timeout: float = 5.0) -> bool:
        """Collect what a mine in the joined castle has produced."""
        return self.execute(CollectMineResourcesRequest(OID=object_id), timeout=timeout)

    def collect_resource_cart(self, cart_type: ResourceCartType, timeout: float = 5.0) -> bool:
        """Collect the joined castle's resource cart of one resource."""
        return self.execute(CollectResourceCartRequest(RT=cart_type), timeout=timeout)

    # =========================================================================
    # Market
    # =========================================================================

    def send_resources(
        self,
        source_castle_id: int,
        target_x: int,
        target_y: int,
        goods: dict[str, int],
        *,
        kingdom_id: Kingdom = Kingdom.GREEN,
        horses_type: int = -1,
        feathers: bool = False,
        slowdown: int = 0,
        timeout: float = 5.0,
    ) -> bool:
        """
        Send resources from one of your castles to a castle on the map, by carriage.

        Args:
            source_castle_id: The castle the carriages leave from, one of yours
            target_x: Map x of the target castle
            target_y: Map y of the target castle
            goods: Amount per resource key, such as ``{"W": 1000, "S": 500}``
            kingdom_id: The source castle's kingdom
            horses_type: The horse's wod id, -1 for none; sent as -1 whenever
                feathers are used, as the client does
            feathers: Pay for the horse with feathers
            slowdown: Seconds to delay the arrival by
            timeout: Timeout in seconds
        """
        request = CreateMarketMovementRequest(
            KID=kingdom_id,
            SID=source_castle_id,
            TX=target_x,
            TY=target_y,
            HBW=-1 if feathers else horses_type,
            PTT=1 if feathers else 0,
            SD=slowdown,
            G=[[key, amount] for key, amount in goods.items()],
        )
        return self.execute(request, timeout=timeout)

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
        units: list[list[int]],
        commander_id: int,
        wait_time: int = 12,
        use_premium_commander: bool = False,
        horses_type: int = -1,
        feathers: bool = False,
        slowdown: int = 0,
        timeout: float = 5.0,
    ) -> bool:
        """
        Send support troops from a castle to a target location.

        The server refuses a support to your own area with NO_SELF_DESTRUCTION
        (92); move troops between your own areas with :meth:`send_troops`.

        Args:
            source_castle_id: The castle the troops leave from, one of yours: ``CastleInfo.castle_id``
                from ``client.castle.get_all()`` or ``Castle.id`` from ``client.state.get_castles()``
            target_x: Target X coordinate
            target_y: Target Y coordinate
            units: List of [unit_id, count] pairs
            commander_id: Commander to lead the support, a ``Commander.commander_id``
                from ``client.commanders.get_commanders()``.
                There is no default: ``0`` is a real commander (the free starting
                one), and the client never sends a support without a commander
                (with none picked it leads with the premium one, ``-14``)
            wait_time: Station duration in hours (0-12, default: 12)
            use_premium_commander: Lead with the premium commander (``commander_id``
                -14). It uses one of your premium commanders, or costs rubies when
                none are left; the client asks first, this does not
            horses_type: Type of horses for speed bonus (-1 = none, default: -1);
                sent as -1 whenever feathers are used, as the client does
            feathers: Pay for the movement with feathers
            slowdown: Movement slowdown modifier (0 = none, default: 0)
            timeout: Timeout in seconds
        """
        request = SendSupportRequest(
            SID=source_castle_id,
            TX=target_x,
            TY=target_y,
            A=units,
            WT=wait_time,
            BPC=1 if use_premium_commander else 0,
            HBW=-1 if feathers else horses_type,
            PTT=1 if feathers else 0,
            SD=slowdown,
            LID=commander_id,
        )
        return self.execute(request, timeout=timeout)

    def send_troops(
        self,
        source_x: int,
        source_y: int,
        target_x: int,
        target_y: int,
        units: list[list[int]],
        commander_id: int,
        *,
        kingdom_id: Kingdom = Kingdom.GREEN,
        use_premium_commander: bool = False,
        horses_type: int = -1,
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
            units: The units, then any tools, as [wod_id, amount] pairs
            commander_id: Commander to lead them, a ``Commander.commander_id``
                from ``client.commanders.get_commanders()``; ``0`` is the free
                starting one
            kingdom_id: The kingdom both areas sit in
            use_premium_commander: Lead with the premium commander (``commander_id``
                -14). It uses one of your premium commanders, or costs rubies when
                none are left; the client asks first, this does not
            horses_type: The horse's wod id, -1 for none; sent as -1 whenever
                feathers are used, as the client does
            feathers: Pay for the horse with feathers
            slowdown: Seconds to delay the arrival by
            timeout: Timeout in seconds
        """
        request = SendTroopsRequest(
            SX=source_x,
            SY=source_y,
            TX=target_x,
            TY=target_y,
            KID=kingdom_id,
            LID=commander_id,
            HBW=-1 if feathers else horses_type,
            BPC=1 if use_premium_commander else 0,
            PTT=1 if feathers else 0,
            SD=slowdown,
            A=units,
        )
        return self.execute(request, timeout=timeout)

    def transfer_units_to_kingdom(
        self,
        source_castle_id: int,
        target_kingdom_id: Kingdom,
        units: list[list[int]],
        *,
        source_kingdom_id: Kingdom = Kingdom.GREEN,
        target_castle_id: int = -1,
        timeout: float = 5.0,
    ) -> bool:
        """
        Send units from one of your castles to another kingdom.

        Args:
            source_castle_id: The castle the units leave from, one of yours
            target_kingdom_id: The kingdom to send them to
            units: The units, as [wod id, amount] pairs
            source_kingdom_id: The source castle's kingdom
            target_castle_id: Object id of a picked target castle, -1 for none
            timeout: Timeout in seconds
        """
        request = KingdomUnitTransferRequest(
            SCID=source_castle_id,
            SKID=source_kingdom_id,
            TKID=target_kingdom_id,
            CID=target_castle_id,
            A=units,
        )
        return self.execute(request, timeout=timeout)


__all__ = ["CastleService"]
