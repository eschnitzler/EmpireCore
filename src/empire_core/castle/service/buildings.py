"""Buildings, the construction queue and the building lookups."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

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
from empire_core.castle.models.collect import CollectMineResourcesRequest, CollectResourceCartRequest
from empire_core.castle.models.districts import (
    MoveToDistrictRequest,
    MoveToDistrictResponse,
    RemoveFromDistrictRequest,
    RemoveFromDistrictResponse,
)
from empire_core.castle.models.lookups import (
    FeastCostReductionResponse,
    GetFeastCostReductionRequest,
    GetTransportationBuildingsRequest,
    ShowUpgradableBuildingsRequest,
    ShowUpgradableBuildingsResponse,
    TransportationBuilding,
    TransportationBuildingsResponse,
)
from empire_core.castle.models.objects import (
    BuildingRow,
    ConstructionList,
    ShowConstructionListRequest,
    ShowConstructionListResponse,
)
from empire_core.castle.models.upkeep import CollectResourceCitizenRequest, ResourcePoolResponse
from empire_core.castle.service.castles import CastlesMixin
from empire_core.enums import BuildingState, ExpansionType, ResourceCartType
from empire_core.gamedata import BuildingDef, Currency

if TYPE_CHECKING:
    from empire_core.gamedata import Building

# ConstructionConst.FREE_SKIP_TIME (dll line 18962)
_FREE_SKIP_SECONDS = 240
_BUILDING = (BuildingState.BUILD_STOPPED, BuildingState.BUILD_IN_PROGRESS)
_UPGRADING = (BuildingState.UPGRADE_STOPPED, BuildingState.UPGRADE_IN_PROGRESS)


class BuildingsMixin(CastlesMixin):
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

    def move_to_district(self, object_id: int, district_object_id: int, *, timeout: float = 5.0) -> BuildingRow | None:
        """
        Move a building of the joined castle into a district, such as a decoration district.

        Returns:
            The building's row as it now stands; None when the reply has none

        Client: ``C2SMoveToDistrictVO`` (bundle line 41105), ``MDECommand.executeCommand`` (bundle line 123166)
        """
        request = MoveToDistrictRequest(object_id=object_id, district_object_id=district_object_id)
        return self.request(request, MoveToDistrictResponse, timeout=timeout).building

    def remove_from_district(
        self, object_id: int, x: int, y: int, rotation: int = 0, *, timeout: float = 5.0
    ) -> BuildingRow | None:
        """
        Move a building out of its district onto the joined castle's grounds.

        :meth:`move_building` moves a building that is in no district.

        Returns:
            The building's row as it now stands; None when the reply has none

        Client: ``IsoServerCommands.moveObject`` (bundle line 63799) sends ``C2SRemoveFromDistrictVO`` for a
        building in a district; ``RDECommand.executeCommand`` (bundle line 123249)
        """
        request = RemoveFromDistrictRequest(object_id=object_id, x=x, y=y, rotation=rotation)
        return self.request(request, RemoveFromDistrictResponse, timeout=timeout).building

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

    def collect_resource_citizen(self, *, timeout: float = 5.0) -> ResourcePoolResponse:
        """
        Collect what the citizen walking in the joined castle carries.

        Returns:
            The ``irc`` reply, which also reaches :attr:`resource_pool`

        Client: ``IsoServerCommands.collectResourcePool`` (bundle line 63801) sends ``C2SIsoResourceCitizenVO``;
        ``IRCCommand.executeCommand`` (bundle line 123132)
        """
        return self.request(CollectResourceCitizenRequest(), ResourcePoolResponse, timeout=timeout)

    # =========================================================================
    # Lookups
    # =========================================================================

    def get_upgradable_buildings(
        self, wod_id: Building, *, prime_sale_upgrade: bool = True, timeout: float = 5.0
    ) -> ShowUpgradableBuildingsResponse:
        """
        Find your castles holding a building of one type that a prime sale can upgrade.

        Args:
            wod_id: The building type the sale is for
            prime_sale_upgrade: The sale discounts the upgrade of every level, as the client sends by default

        Client: ``CastlePrimeSaleDialog.onOkButton`` (bundle line 37771) sends ``C2SShowMeUpgradeBuildingsVO``;
        ``SUBCommand.executeCommand`` (bundle line 129862)
        """
        request = ShowUpgradableBuildingsRequest(wod_id=wod_id, prime_sale_upgrade=prime_sale_upgrade)
        return self.request(request, ShowUpgradableBuildingsResponse, timeout=timeout)

    def get_transportation_buildings(self, *, timeout: float = 5.0) -> list[TransportationBuilding]:
        """
        The main castle's buildings a castle transport to the Outer Realms takes along.

        Client: ``CastleSpecialServerPreBuildCastleSelectionDialog.showLoaded`` (bundle line 27960) sends
        ``C2SGetCastleTransportationBuildingsVO``; ``GCTBCommand.executeCommand`` (bundle line 128860)
        """
        request = GetTransportationBuildingsRequest()
        return self.request(request, TransportationBuildingsResponse, timeout=timeout).buildings

    def get_feast_cost_reduction(self, *, timeout: float = 5.0) -> int | float:
        """
        The discount on feasts, in percent.

        Client: ``CastleFestivalDialog.showLoaded`` (bundle line 65030) sends ``C2SGetFeastCostReductionVO``;
        ``CastleFestivalDialog.onFCEArrived`` (bundle line 65044) reads ``FRM``
        """
        return self.request(
            GetFeastCostReductionRequest(), FeastCostReductionResponse, timeout=timeout
        ).reduction_percent
