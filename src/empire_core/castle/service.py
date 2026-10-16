"""
Your castles: resources, buildings, the construction queue, research and the mercenary camp.

It covers:

- Castle management (list, join, rename)
- Resources and production
- Buildings and the construction queue
- Tax collection
- Research and the mercenary camp's missions

Sending goods, support and troops from a castle is on ``client.movements``.

Actions raise ``CommandError`` when the server refuses them.

Methods that take one of your castles send its kingdom from the castle
list the server sent at login (``client.state.get_castles()``), as the
client does, and raise ``UnknownCastleError`` for an id not in it.

Building methods act on the castle joined last (:meth:`CastleService.join`)
and name buildings by object id, a ``BuildingRow.object_id`` from
``join(...).buildings``; ``upgrade_building``, ``upgrade_defense`` and
``finish_construction`` take the castle and join it themselves. Their typed replies (``BuildResponse`` and the
others) can be read with ``client.request``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

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
from empire_core.castle.models.mercenaries import MercenaryMission, MercenaryMissionsResponse, MercenaryPackageRequest
from empire_core.castle.models.objects import (
    BuildingRow,
    ConstructionList,
    ShowConstructionListRequest,
    ShowConstructionListResponse,
)
from empire_core.castle.models.research import SkipResearchRequest, StartResearchRequest
from empire_core.castle.models.resources import (
    CastleResources,
    GetProductionRequest,
    GetProductionResponse,
    GetResourcesRequest,
    GetResourcesResponse,
)
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
from empire_core.enums import (
    BuildingState,
    CollectableKind,
    ExpansionType,
    Kingdom,
    MercenaryMissionState,
    ResourceCartType,
)
from empire_core.exceptions import UnknownCastleError
from empire_core.gamedata import BuildingDef, Currency, HorseStats, Research
from empire_core.protocol.js import js_truthy
from empire_core.services.base import BaseService

if TYPE_CHECKING:
    from empire_core.castle.models.collect import MineStatus, ResourceCart
    from empire_core.castle.models.kingdoms import KingdomInfoResponse
    from empire_core.castle.models.permanent import PermanentCastle
    from empire_core.castle.models.research import ResearchInfoResponse
    from empire_core.castle.models.upkeep import ConstructionItemExpiryResponse, ResourcePoolResponse
    from empire_core.castle.models.wishing_well import WishingWellResponse
    from empire_core.state.models import Castle, JoinedArea

# PlayerConst.CHANGE_CASTLE_NAME_C2 (dll line 19599)
_RENAME_RUBIES = 2500
# ConstructionConst.FREE_SKIP_TIME (dll line 18962)
_FREE_SKIP_SECONDS = 240
_BUILDING = (BuildingState.BUILD_STOPPED, BuildingState.BUILD_IN_PROGRESS)
_UPGRADING = (BuildingState.UPGRADE_STOPPED, BuildingState.UPGRADE_IN_PROGRESS)


# a started mission's RD is rounded, and a collect sent while time remains is a ruby skip
_COLLECT_MARGIN_SECONDS = 2


class CastleService(BaseService):
    """
    Your castles, their buildings and resources, research and the mercenary camp.

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

    @property
    def castles(self) -> list[Castle]:
        """A snapshot of the player's castles."""
        return self.client.state.get_castles()

    def unlocks(self, castle_id: int) -> PermanentCastle | None:
        """One of your castles' unlocked units and horses, from the last gpc that named it."""
        return self.client.state.get_permanent_castle(castle_id)

    @property
    def joined_area(self) -> JoinedArea | None:
        """The area joined, with its slum level and builder discount; ``None`` before any join."""
        return self.client.state.get_joined_area()

    @property
    def mines(self) -> dict[int, MineStatus]:
        """The joined castle's mines by object id, as the last ``gsm`` sent them."""
        return self.client.state.get_mines()

    @property
    def resource_carts(self) -> list[ResourceCart]:
        """The joined castle's resource carts, wood, stone and food, as the last ``rci`` sent them."""
        return self.client.state.get_resource_carts()

    def resource_cart(self, cart_type: ResourceCartType) -> ResourceCart | None:
        """The cart of one resource in the last ``rci``; ``None`` before any."""
        return self.client.state.get_resource_cart(cart_type)

    @property
    def tax(self) -> TaxInfo | None:
        """The tax collection, from the last ``txi``; None until one arrived."""
        return self.client.state.get_tax()

    @property
    def kingdoms(self) -> KingdomInfoResponse | None:
        """Your kingdoms and the transfers to them; None until a ``kpi`` arrived."""
        return self.client.state.get_kingdoms()

    @property
    def construction_item_expiry(self) -> ConstructionItemExpiryResponse | None:
        """When the next construction item expires, from the last ``nec``; None until one arrived."""
        return self.client.state.get_construction_item_expiry()

    @property
    def resource_pool(self) -> ResourcePoolResponse | None:
        """What the citizen in your castle carries, from the last ``irc`` push; None until one arrived."""
        return self.client.state.get_resource_pool()

    @property
    def wishing_well(self) -> WishingWellResponse | None:
        """The ruby wishing well, from the last ``rww``; None until one arrived."""
        return self.client.state.get_wishing_well()

    @property
    def research(self) -> ResearchInfoResponse:
        """Your finished and running research, from the last ``rei``.

        Raises:
            StateNotLoadedError: No login has brought it
        """
        return self.client.state.get_research()

    @property
    def mercenary_missions(self) -> MercenaryMissionsResponse | None:
        """The mercenary camp's missions, from the last ``mpe``; None until one arrived."""
        return self.client.state.get_mercenary_missions()

    def get_all(self, *, timeout: float = 5.0) -> list[CastleInfo]:
        """
        Get list of all player's castles.

        Sends the logged-in player's id, as the client does, once the state knows it.

        Example:
            castles = client.castle.get_all()
            for c in castles:
                print(f"{c.castle_name} (ID: {c.castle_id}) at ({c.x}, {c.y})")
        """
        player_id = self.client.state.get_local_player().id
        request = GetCastlesRequest(player_id=player_id if isinstance(player_id, int) and player_id > 0 else None)
        return self.request(request, GetCastlesResponse, timeout=timeout).castles

    def get_details(self, castle_id: int, *, timeout: float = 5.0) -> DetailedCastleInfo:
        """
        Get resources and stationed units for one castle.

        The server answers with every castle of yours; the one asked for is picked out here.

        Args:
            castle_id: One of your castles, from ``client.castle.get_all()``
                (``CastleInfo.castle_id``) or ``client.state.get_castles()`` (``Castle.id``)
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: The reply lists no castle with that id

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

    def select(self, castle_id: int, *, timeout: float = 5.0) -> None:
        """
        Select/jump to a castle (makes it the active castle).

        Use :meth:`join` for the castle's state the server sends back.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list

        Client: ``C2SJoinCastleVO`` sent with the castle's ``objectId`` and
        ``kingdomID`` (``JoinAreaAndSavePositionCommand.execute``, bundle line 100892)

        Example:
            client.castle.select(12345)
        """
        kingdom_id = self._require_own_castle(castle_id).kingdom_id
        self.execute(SelectCastleRequest(castle_id=castle_id, kingdom_id=kingdom_id), timeout=timeout)

    def join(self, castle_id: int, *, timeout: float = 5.0) -> SelectCastleResponse:
        """
        Join a castle, making it the active castle, and return its state.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list
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
        self, x: int, y: int, kingdom_id: Kingdom = Kingdom.GREEN, *, timeout: float = 5.0
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

    def rename(
        self,
        castle_id: int,
        new_name: str,
        *,
        is_initial_name: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Rename one of your castles.

        Looks the castle up in the castle list for the type and kingdom the
        server needs, so this costs one extra round trip. Pass
        ``is_initial_name=True`` to name a newly acquired castle, such as a
        monument or laboratory, instead of renaming one. A rename costs
        ``PlayerConst.CHANGE_CASTLE_NAME_C2`` (2500) rubies unless a premium account runs;
        see "Spending rubies" in the guides.

        Args:
            castle_id: One of your castles, from ``client.castle.get_all()``
                (``CastleInfo.castle_id``)
            new_name: The new name
            is_initial_name: Name a newly acquired castle instead of renaming one, which is free
            spend_rubies: Allow a rename while no premium account is known to run
            timeout: Timeout in seconds

        Raises:
            ValueError: A rename, no premium account is known to run, and ``spend_rubies`` is False
            UnknownCastleError: ``castle_id`` is not one of your castles.

        Client: ``CastleRenameCastleDialog.showLoaded`` and ``sendCommand`` (bundle lines 57219, 57231)
        price a rename, sent with 1; ``CastleNameCastleDialog.sendCommand`` (bundle line 32589) sends
        the first name with 0 and shows no price; ``CHANGE_CASTLE_NAME_C2`` (dll line 19599)

        Example:
            client.castle.rename(12345, "My Fortress", spend_rubies=True)
        """
        if not is_initial_name:
            if not self.client.state.get_boosts().is_premium_active():
                self._require_spend_rubies(spend_rubies, f"renaming a castle costs {_RENAME_RUBIES} rubies")
        castle = next((c for c in self.get_all(timeout=timeout) if c.castle_id == castle_id), None)
        if castle is None:
            raise UnknownCastleError(castle_id)
        self.execute(
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

    def get_resources(self, castle_id: int, *, timeout: float = 5.0) -> CastleResources:
        """
        Get one of your castles' resources.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list

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

    def get_production(self, *, timeout: float = 5.0) -> CastleProductionArea:
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

    def get_build_queue(self, *, timeout: float = 5.0) -> ConstructionList:
        """
        Get the joined castle's construction slots.

        Example:
            queue = client.castle.get_build_queue()
            print(queue.building_object_ids, queue.free_slots)
        """
        return self.request(ShowConstructionListRequest(), ShowConstructionListResponse, timeout=timeout)

    def _castle_object(self, castle_id: int, object_id: int, timeout: float) -> BuildingRow | None:
        """Join the castle and read the object from the join's reply; None when the reply has no such object."""
        buildings = self.join(castle_id, timeout=timeout).buildings
        return None if buildings is None else buildings.find(object_id)

    def _player_level(self) -> int | None:
        level = self.client.state.get_local_player().level
        return level if level > 0 else None

    def _next_level(self, row: BuildingRow) -> BuildingDef | None:
        """
        The level a building upgrades to: the row's upgrade target while it upgrades, else its ``upgradeWodID``.

        Client: ``ABasicBuildingVO.upgradeTargetWodId`` and ``getUpgradeVO`` (bundle lines 17918-17922)
        """
        buildings = self._require_game_data().buildings
        if row.state in _UPGRADING and row.upgrade_target_wod_id > 0:
            return buildings.get(row.upgrade_target_wod_id)
        current = buildings.get(row.wod_id)
        return None if current is None else buildings.get(current.upgrade_building_id)

    def _building_ruby_cost(self, wod_id: int) -> str | None:
        building = self._require_game_data().buildings.get(wod_id)
        if building is None:
            return f"building {wod_id} is not in the game data and may cost rubies"
        rubies = building.rubies_to_build(self._player_level())
        return f"building {wod_id} costs {rubies} rubies" if rubies > 0 else None

    def _upgrade_ruby_cost(self, row: BuildingRow | None, object_id: int) -> str | None:
        if row is None:
            return f"object {object_id} is not in the castle, so its upgrade may cost rubies"
        upgrade = self._next_level(row)
        if upgrade is None:
            return f"building {row.wod_id} has no next level in the game data, so its upgrade may cost rubies"
        rubies = upgrade.rubies_to_build(self._player_level())
        return f"upgrading to building {upgrade.building_id} costs {rubies} rubies" if rubies > 0 else None

    def _construction_seconds_left(self, row: BuildingRow | None) -> int | None:
        """
        The seconds left of a running build or upgrade when its row was sent; None when any input is unknown.

        The duration is the build time (``BuildingDef.seconds_to_build`` at your level), the upgrade
        target's for an upgrade, divided by the boost at its start, less the seconds done.

        Client: ``ABasicBuildingVO.getTimeLeftForBuilding`` and ``setStateEndTime`` (bundle lines
        17967-17976, 17990-17996), ``getBuildDuration`` (bundle line 17956), ``getUpgradeDuration``
        (bundle lines 17963-17964)
        """
        level = self._player_level()
        if row is None or level is None or row.construction_completed_seconds is None:
            return None
        boost = row.construction_boost_at_start
        if boost is None or boost <= 0:
            return None
        if row.state in _BUILDING:
            building = self._require_game_data().buildings.get(row.wod_id)
        elif row.state in _UPGRADING:
            building = self._next_level(row)
        else:
            return None
        if building is None:
            return None
        return int(building.seconds_to_build(level) / boost) - row.construction_completed_seconds

    def _join_and_price_upgrade(self, castle_id: int, object_id: int, spend_rubies: bool, timeout: float) -> None:
        if not spend_rubies:
            self._require_game_data()
        row = self._castle_object(castle_id, object_id, timeout)
        if not spend_rubies:
            self._require_spend_rubies(spend_rubies, self._upgrade_ruby_cost(row, object_id))

    def build(
        self,
        wod_id: int,
        x: int,
        y: int,
        rotation: int = 0,
        *,
        spend_rubies: bool = False,
        private_offer_id: int = -1,
        district_object_id: int = -1,
        timeout: float = 5.0,
    ) -> None:
        """
        Place a new building in the joined castle.

        Spends rubies when the building has a ruby price (``BuildingDef.rubies_to_build`` at your
        level), and with ``spend_rubies`` on missing resources; see "Spending rubies" in the guides.

        Args:
            wod_id: The building type's wod id
            x: Castle grid x, -1 when placing into a district
            y: Castle grid y, -1 when placing into a district
            rotation: Rotation
            spend_rubies: Allow a ruby price, and pay the missing resources with rubies
            private_offer_id: The private offer the purchase uses, -1 for none
            district_object_id: Object id of the district to place into, -1 for none
            timeout: Timeout in seconds

        Raises:
            ValueError: The building has a ruby price, or is not in the game data, and ``spend_rubies`` is False
            GameDataNotLoadedError: ``spend_rubies`` is False and the game data cannot be loaded

        Client: ``IsoServerCommands.buyObjectFromShop`` (bundle line 63766); ``ABasicBuildingVO.costC2``
        (bundle lines 17950-17953)
        """
        if not spend_rubies:
            self._require_spend_rubies(spend_rubies, self._building_ruby_cost(wod_id))
        request = BuildRequest(
            wod_id=wod_id,
            x=x,
            y=y,
            rotation=rotation,
            pay_with_rubies=spend_rubies,
            private_offer_id=private_offer_id,
            district_object_id=district_object_id,
        )
        self.execute(request, timeout=timeout)

    def upgrade_building(
        self,
        castle_id: int,
        object_id: int,
        *,
        spend_rubies: bool = False,
        private_offer_id: int = -1,
        timeout: float = 5.0,
    ) -> None:
        """
        Upgrade a building in one of your castles.

        Joins the castle first, as the client is inside it, and prices the building from the
        join's reply: the level it upgrades to, by ``BuildingDef.rubies_to_build`` at your level,
        needs ``spend_rubies`` when it has a ruby price; see "Spending rubies" in the guides.
        ``spend_rubies`` also pays missing resources with rubies.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            object_id: The building's object id
            spend_rubies: Allow a ruby price, and pay the missing resources with rubies
            private_offer_id: The prime sale offer the upgrade uses, -1 for none
            timeout: Timeout in seconds

        Raises:
            ValueError: The next level has a ruby price, or the building or its next level is not
                known, and ``spend_rubies`` is False
            GameDataNotLoadedError: ``spend_rubies`` is False and the game data cannot be loaded
            UnknownCastleError / CommandError: see :meth:`join`

        Client: ``RingMenuButtonUpgradeBuilding.onClick`` (bundle line 50092),
        ``IsoServerCommands.upgradeBuilding`` (bundle line 63774); the price is the next level's
        ``costC2``, ``BuildingCostHelper.getUpgradeCostList`` (bundle lines 41106-41116) through
        ``AShopVO.getCost`` (bundle line 31766) and ``ABasicBuildingVO.costC2`` (bundle lines 17950-17953)
        """
        self._join_and_price_upgrade(castle_id, object_id, spend_rubies, timeout)
        request = UpgradeBuildingRequest(
            object_id=object_id, pay_with_rubies=spend_rubies, private_offer_id=private_offer_id
        )
        self.execute(request, timeout=timeout)

    def move_building(self, object_id: int, x: int, y: int, rotation: int = 0, *, timeout: float = 5.0) -> None:
        """Move a building in the joined castle."""
        self.execute(MoveBuildingRequest(object_id=object_id, x=x, y=y, rotation=rotation), timeout=timeout)

    def sell_decoration(self, object_id: int, *, timeout: float = 5.0) -> None:
        """Sell a decoration placed in the joined castle."""
        self.execute(SellBuildingRequest(object_id=object_id), timeout=timeout)

    def destroy_building(self, object_id: int, *, timeout: float = 5.0) -> None:
        """Start taking a building in the joined castle down."""
        self.execute(DestroyBuildingRequest(object_id=object_id), timeout=timeout)

    def finish_construction(
        self, castle_id: int, object_id: int, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> None:
        """
        Finish a building's running build or upgrade at once.

        Joins the castle first, as the client is inside it, and works out the time left from the
        join's reply as the client does. With at most ``FREE_SKIP_TIME`` (240) seconds left it
        finishes for free, sent as a free skip; with more left, or the time left not known (a
        repair or tear-down, an unknown building or player level), it costs rubies; see "Spending
        rubies" in the guides. A subscription that lengthens the free time is not checked.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            object_id: The building's object id
            spend_rubies: Allow finishing a construction that costs rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: More than 240 seconds are left, or the time left is not known, and
                ``spend_rubies`` is False
            GameDataNotLoadedError: the game data cannot be loaded
            UnknownCastleError / CommandError: see :meth:`join`

        Client: ``IsoServerCommands.fastCompleteBuilding`` (bundle line 63773) sends ``FS`` 1 when
        ``CastleSpecialEventData.hasSkipForFree`` (bundle line 139853), which ``calculateSkipCosts``
        (bundle line 139849) decides from ``getTimeLeftForBuilding`` (bundle line 17967);
        ``FREE_SKIP_TIME`` (dll line 18962)
        """
        self._require_game_data()
        row = self._castle_object(castle_id, object_id, timeout)
        received = time.monotonic()
        seconds_left = self._construction_seconds_left(row)
        free = seconds_left is not None and seconds_left - (time.monotonic() - received) <= _FREE_SKIP_SECONDS
        cost = None if free else f"finishing with over {_FREE_SKIP_SECONDS} seconds left, or unknown, costs rubies"
        self._require_spend_rubies(spend_rubies, cost)
        self.execute(FastCompleteRequest(object_id=object_id, free_skip=free), timeout=timeout)

    def skip_construction_time(self, object_id: int, minute_skip: Currency | str, *, timeout: float = 5.0) -> None:
        """
        Shorten a building's running construction with a minute skip.

        Args:
            object_id: The building's object id
            minute_skip: The minute skip to use, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``;
                its key (``"MS1"``) also works, for a skip newer than the generated enum
            timeout: Timeout in seconds

        Raises:
            ValueError: ``minute_skip`` is no minute skip, or the special currencies hold none of it

        Client: ``BuildingMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 50021),
        ``CastleMinuteSkipDialog.showLoaded`` (bundle line 7671)
        """
        self._require_minute_skip(minute_skip)
        self.execute(TimeSkipBuildingRequest(object_id=object_id, minute_skip=minute_skip), timeout=timeout)

    def upgrade_defense(
        self,
        castle_id: int,
        object_id: int,
        *,
        spend_rubies: bool = False,
        private_offer_id: int = -1,
        timeout: float = 5.0,
    ) -> None:
        """
        Upgrade a wall, gate or tower of one of your castles, by its object id.

        Joins the castle first, as the client is inside it, and prices the building from the
        join's reply: the level it upgrades to, by ``BuildingDef.rubies_to_build`` at your level,
        needs ``spend_rubies`` when it has a ruby price; see "Spending rubies" in the guides.
        ``spend_rubies`` also pays missing resources with rubies.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            object_id: The wall's, gate's or tower's object id
            spend_rubies: Allow a ruby price, and pay the missing resources with rubies
            private_offer_id: The private offer the upgrade uses, -1 for none
            timeout: Timeout in seconds

        Raises:
            ValueError: The next level has a ruby price, or the object or its next level is not
                known, and ``spend_rubies`` is False
            GameDataNotLoadedError: ``spend_rubies`` is False and the game data cannot be loaded
            UnknownCastleError / CommandError: see :meth:`join`

        Client: ``C2SIsoUpgradeDefenceVO``, sent with ``PWR`` 1 by
        ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (bundle line 35220); the price
        as for :meth:`upgrade_building`
        """
        self._join_and_price_upgrade(castle_id, object_id, spend_rubies, timeout)
        request = UpgradeWallRequest(
            object_id=object_id, private_offer_id=private_offer_id, pay_with_rubies=spend_rubies
        )
        self.execute(request, timeout=timeout)

    def repair_building(
        self, object_id: int, *, spend_rubies: bool = False, private_offer_id: int = -1, timeout: float = 5.0
    ) -> None:
        """
        Repair a damaged building in the joined castle.

        Args:
            object_id: The building's object id
            spend_rubies: Pay the missing resources with rubies; see "Spending rubies" in the guides
            private_offer_id: The private offer the repair uses, -1 for none
            timeout: Timeout in seconds

        Client: ``IsoServerCommands.repairBuilding`` (bundle line 63770); with rubies,
        ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (bundle line 35221)
        """
        request = RepairBuildingRequest(
            object_id=object_id, private_offer_id=private_offer_id, pay_with_rubies=spend_rubies
        )
        self.execute(request, timeout=timeout)

    def repair_all(self, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Repair every damaged building in the joined castle at once, for rubies; see "Spending
        rubies" in the guides.

        The price follows the damage's total repair time and is not worked out here, so this
        always needs ``spend_rubies``.

        Args:
            spend_rubies: Allow the rubies it costs; without it nothing is sent
            timeout: Timeout in seconds

        Raises:
            ValueError: ``spend_rubies`` is False

        Client: ``CastleRepairTipDialog`` (bundle lines 97414, 97430) prices it with
        ``AreaData.getTotalRepairCostC2`` (bundle line 131460), ``ConstructionConst.getRepairAllCostsC2``
        (dll lines 18966-18969)
        """
        self._require_spend_rubies(spend_rubies, "repairing every building at once costs rubies")
        self.execute(RepairAllRequest(), timeout=timeout)

    def buy_expansion(
        self,
        x: int,
        y: int,
        rotation: int = 0,
        expansion_type: ExpansionType = ExpansionType.NORMAL,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Buy an expansion of the joined castle's grounds, with resources (NORMAL) or rubies (PREMIUM).

        Args:
            x: Castle grid x of the expansion
            y: Castle grid y of the expansion
            rotation: Rotation
            expansion_type: NORMAL or PREMIUM; PREMIUM costs rubies, see "Spending rubies" in the guides
            spend_rubies: Allow a PREMIUM expansion
            timeout: Timeout in seconds

        Raises:
            ValueError: ``expansion_type`` is PREMIUM and ``spend_rubies`` is False

        Client: ``CastleExpansionVE`` (bundle line 86849) needs ``userHasC2ForBuy`` for a premium
        expansion before ``sendBuyRequestToServer`` (bundle line 86854)
        """
        premium = expansion_type == ExpansionType.PREMIUM
        self._require_spend_rubies(spend_rubies, "a premium expansion costs rubies" if premium else None)
        self.execute(BuyExtensionRequest(x=x, y=y, rotation=rotation, expansion_type=expansion_type), timeout=timeout)

    def open_treasure_chest(self, object_id: int, *, timeout: float = 5.0) -> None:
        """Open a treasure chest found on an expansion of the joined castle."""
        self.execute(CollectExtensionGiftRequest(object_id=object_id), timeout=timeout)

    def collect_mine(self, object_id: int, *, timeout: float = 5.0) -> None:
        """Collect what a mine in the joined castle has produced."""
        self.execute(CollectMineResourcesRequest(object_id=object_id), timeout=timeout)

    def collect_resource_cart(self, cart_type: ResourceCartType, *, timeout: float = 5.0) -> None:
        """Collect the joined castle's resource cart of one resource."""
        self.execute(CollectResourceCartRequest(cart_type=cart_type), timeout=timeout)

    # =========================================================================
    # Tax
    # =========================================================================

    def get_tax_info(self, *, timeout: float = 5.0) -> TaxInfo:
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

    def collect_tax(self, *, timeout: float = 5.0) -> CollectTaxResponse:
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
    # Horses
    # =========================================================================

    def horses(self, castle_id: int) -> list[HorseStats] | None:
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
            GameDataNotLoadedError: the game data cannot be loaded
            UnknownCastleError: ``castle_id`` is not in your castle list

        Client: ``CastleHorsesVO.parseParamObject`` (bundle line 139177),
        ``CastlePermanentCastleData.getCastleByWorldAreaId`` (bundle line 139145)
        """
        game_data = self._require_game_data()
        self._require_own_castle(castle_id)
        permanent = self.client.state.get_permanent_castle(castle_id)
        if permanent is None:
            return None
        horses = [horse for wod_id in permanent.horse_ids if (horse := game_data.get_horse(wod_id)) is not None]
        return sorted(horses, key=lambda horse: horse.wod_id)

    # =========================================================================
    # Research
    # =========================================================================

    def start_research(self, research: Research | int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Start a research, paying what it costs.

        Missing resources are never paid with rubies: the request sends ``PWR`` 0, as the research
        dialog does. Some researches cost rubies themselves (``ResearchDef.cost_rubies``), and the
        client sends the same request for them; this method refuses those unless ``spend_rubies`` is
        True. Other costs, legendary tokens included, are a normal game currency and are paid. The
        reply's research reaches ``client.state.get_research()``.

        Args:
            research: The research to start
            spend_rubies: Allow a research that costs rubies, on either kind of server
            timeout: Timeout in seconds

        Raises:
            GameDataNotLoadedError: the game data cannot be loaded
            ValueError: The game data has no such research, or it costs rubies and ``spend_rubies`` is False

        Client: ``ResearchInfo.buyResearch`` (bundle line 79704) sends ``C2SResearchStartVO`` whatever the
        costs; ``updateBuyArea`` shows the ruby overlay when ``getFinalCosts`` holds rubies (bundle lines
        79679-79680), and ``AResearchVO.getBaseCosts`` takes the temporary server's costs there (bundle
        line 61530); ``RESCommand`` (bundle line 126872)
        """
        game_data = self._require_game_data()
        row = game_data.researches.get(research)
        if row is None:
            raise ValueError(f"the game data has no research {research!r}")
        costs = (*row.costs, *row.temp_server_costs)
        rubies = max((cost.amount for cost in costs if cost.kind is CollectableKind.RUBIES), default=0)
        if rubies > 0 and not spend_rubies:
            raise ValueError(f"research {research!r} costs {rubies} rubies; pass spend_rubies=True")
        self.execute(StartResearchRequest(research_id=research), timeout=timeout)

    def skip_research(self, minute_skip: Currency | str, *, timeout: float = 5.0) -> None:
        """
        Shorten the running research with a minute skip from your inventory.

        The reply's research reaches ``client.state.get_research()``.

        Args:
            minute_skip: The minute skip to use, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``;
                its key (``"MS1"``) also works, for a skip newer than the generated enum
            timeout: Timeout in seconds

        Raises:
            ValueError: ``minute_skip`` is no minute skip, or the special currencies hold none of it

        Client: ``ResearchMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 79784),
        ``CastleMinuteSkipDialog.showLoaded`` (bundle line 7671), ``MSRCommand`` (bundle line 125825)
        """
        self._require_minute_skip(minute_skip)
        self.execute(SkipResearchRequest(minute_skip=minute_skip), timeout=timeout)

    # =========================================================================
    # Mercenary camp
    # =========================================================================

    def list_missions(self, *, timeout: float = 5.0) -> MercenaryMissionsResponse:
        """
        The mercenary camp's missions, and when new ones come.

        Sends ``mpe`` with ``MID`` -1, as the client does when it opens the camp and when new missions
        are due; the reply also reaches ``client.state.get_mercenary_missions()``.

        Client: ``CastleMercenaryOverviewDialog.showLoaded`` and ``CastleMercenaryData.onNewMissions``
        (bundle lines 51996, 28851)
        """
        return self.request(MercenaryPackageRequest(), MercenaryMissionsResponse, timeout=timeout)

    def start_mission(self, mission_id: int, *, timeout: float = 5.0) -> None:
        """
        Start an open mercenary mission, paying its price in coins.

        Lists the missions first and decides from that reply, as the client decides from its mission
        state: only an open mission starts, and only while no mission runs or waits to be collected.
        While one runs the client would first finish it for rubies; that is left out.

        Args:
            mission_id: A ``MercenaryMission.mission_id`` from :meth:`list_missions`
            timeout: Timeout in seconds, for each request

        Raises:
            ValueError: The missions list no such mission, it is not open, or another mission runs
                or waits to be collected

        Client: ``CastleMercenaryMissionItem.startMission``, ``showStartAndRefreshButton`` and
        ``startMissionCallback`` (bundle lines 87377, 87361, 87379)
        """
        missions = self.list_missions(timeout=timeout)
        mission = self._mission(missions, mission_id)
        if mission.current_state() != MercenaryMissionState.OPEN:
            raise ValueError(f"mercenary mission {mission_id} is not open")
        if missions.current_mission_state() != MercenaryMissionState.OPEN:
            raise ValueError("another mercenary mission runs or waits to be collected")
        self.execute(MercenaryPackageRequest(mission_id=mission_id), timeout=timeout)

    def collect_mission(self, mission_id: int, *, timeout: float = 5.0) -> None:
        """
        Collect a finished mercenary mission's rewards.

        The collect is the same ``mpe`` as the ruby skip of a running mission, which costs
        ``ceil(remaining seconds / 60 * 5)`` rubies. So this lists the missions first and sends the
        collect only for one the server lists as collectable, as started with no ``RD`` (finished for
        the client, and a skip of it would cost 0 rubies), or as started with its time run out at
        least two seconds ago, since ``RD`` is rounded. A started mission whose ``RD`` still counts
        down is refused. Another session can still change the mission between the list and the
        send; that window is not closed.

        Args:
            mission_id: A ``MercenaryMission.mission_id`` from :meth:`list_missions`
            timeout: Timeout in seconds, for each request

        Raises:
            ValueError: The missions list no such mission, or it is not collectable by that rule

        Client: ``CastleMercenaryMissionItem.showCollectButton`` and ``collectMissionRewards``
        (bundle lines 87365, 87382); ``CastleMercenaryMissionItemVO.fillFromParamObject`` sets no end
        time without ``RD`` (bundle line 81134); ``CastleMercenarySkipMissionDialog.confirmSkip`` (bundle
        line 87459) sends the same id, ``MercenaryConst.getSkipC2Cost`` (dll line 19508)
        """
        mission = self._mission(self.list_missions(timeout=timeout), mission_id)
        finished = mission.state == MercenaryMissionState.STARTED and (
            not js_truthy(mission.seconds) or mission.seconds_past_end() >= _COLLECT_MARGIN_SECONDS
        )
        if mission.state != MercenaryMissionState.COLLECTABLE and not finished:
            raise ValueError(f"mercenary mission {mission_id} is not collectable")
        self.execute(MercenaryPackageRequest(mission_id=mission_id), timeout=timeout)

    @staticmethod
    def _mission(missions: MercenaryMissionsResponse, mission_id: int) -> MercenaryMission:
        mission = missions.get_mission(mission_id)
        if mission is None:
            raise ValueError(f"no mercenary mission {mission_id}")
        return mission


__all__ = ["CastleService"]
