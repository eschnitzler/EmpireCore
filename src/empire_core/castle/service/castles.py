"""Your castles: the castle list, joining a castle, resources and horses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from empire_core.castle.models.actions import JoinAreaRequest, SelectCastleRequest, SelectCastleResponse
from empire_core.castle.models.castles import CastleInfo, GetCastlesRequest, GetCastlesResponse
from empire_core.castle.models.details import (
    CastleProductionArea,
    DetailedCastleInfo,
    GetDetailedCastleRequest,
    GetDetailedCastleResponse,
)
from empire_core.castle.models.hunter import HunterInfo, SetHunterRequest
from empire_core.castle.models.judgement import JudgeCitizenRequest, JudgeCitizenResponse
from empire_core.castle.models.kingdoms import KingdomInfoRequest, KingdomInfoResponse, SelectKingdomCastleRequest
from empire_core.castle.models.landmarks import (
    GetLaboratoryProgressRequest,
    GetMonumentProgressRequest,
    KingsTowerListResponse,
    LaboratoryListResponse,
    LaboratoryProgressResponse,
    LaboratoryResetResponse,
    LandmarkProgress,
    MonumentListResponse,
    MonumentProgressResponse,
    MonumentResetResponse,
)
from empire_core.castle.models.mercenaries import MercenaryMissionsResponse
from empire_core.castle.models.research import ResearchInfoResponse
from empire_core.castle.models.resources import (
    CastleResources,
    GetProductionRequest,
    GetProductionResponse,
    GetResourcesRequest,
    GetResourcesResponse,
)
from empire_core.castle.models.tax import TaxInfo
from empire_core.castle.models.upkeep import ConstructionItemExpiryResponse, ResourcePoolResponse
from empire_core.castle.models.villages import GetVillageListRequest, VillageListResponse
from empire_core.enums import JudgementOption, Kingdom, KingdomDirection, MapItemType, ResourceCartType
from empire_core.exceptions import UnknownCastleError
from empire_core.gamedata import HorseStats
from empire_core.map.models.items import MapAreaItem
from empire_core.services.base import ServiceMixin

if TYPE_CHECKING:
    from empire_core.castle.models.collect import MineStatus, ResourceCart
    from empire_core.castle.models.permanent import PermanentCastle
    from empire_core.castle.models.wishing_well import WishingWellResponse
    from empire_core.gamedata import Judgement, PrebuiltCastle
    from empire_core.state.models import Castle, JoinedArea

_LANDMARK_PROGRESS: dict[
    MapItemType, tuple[type[GetLaboratoryProgressRequest | GetMonumentProgressRequest], type[LandmarkProgress]]
] = {
    MapItemType.LABORATORY: (GetLaboratoryProgressRequest, LaboratoryProgressResponse),
    MapItemType.MONUMENT: (GetMonumentProgressRequest, MonumentProgressResponse),
}


class CastlesMixin(ServiceMixin):
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
    def hunter(self) -> HunterInfo | None:
        """The hunter's food boost, from the last ``hin`` or castle join that carried it; None until one did."""
        return self.client.state.get_hunter()

    def set_hunter(self, food_boost: int, *, timeout: float = 5.0) -> HunterInfo:
        """
        Set the joined castle's hunter to turn wood and stone production into ``food_boost`` more food.

        Raises:
            CommandError: The server refused, e.g. a boost above the hunter's maximum

        Client: ``CastleHunterDialog.onClick`` (bundle line 51530) sends ``C2SHunterInfoVO`` with a value from 0 to
        the hunter building's ``hunterMax``; ``HINCommand.executeCommand`` (bundle line 124591)
        """
        return self.request(SetHunterRequest(food_boost=food_boost), HunterInfo, timeout=timeout)

    @property
    def judgement_id(self) -> Judgement | int | None:
        """The open citizen judgement, from the last ``sjc``; None while none is open."""
        return self.client.state.get_judgement_id()

    def judge_citizen(self, option: JudgementOption, *, timeout: float = 5.0) -> None:
        """
        Give your verdict on the open citizen judgement, which ends it.

        Raises:
            CommandError: The server refused, e.g. no judgement is open or the verdict's requirements are unmet

        Client: ``CastleJudgementChooseOptionDialog.onClick`` (bundle lines 95550-95552),
        ``JJCCommand.executeCommand`` (bundle line 124666)
        """
        self.request(JudgeCitizenRequest(option=option), JudgeCitizenResponse, timeout=timeout)

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
    def laboratories(self) -> LaboratoryListResponse | None:
        """Your laboratories, from the last ``gll``; None until one arrived."""
        return self.client.state.get_laboratories()

    @property
    def laboratory_reset(self) -> LaboratoryResetResponse | None:
        """When the laboratories reset next, from the last ``lrr`` that counted down; None until one arrived."""
        return self.client.state.get_laboratory_reset()

    @property
    def kings_towers(self) -> KingsTowerListResponse | None:
        """Your kings towers, from the last ``gkl``; None until one arrived."""
        return self.client.state.get_kings_towers()

    @property
    def monuments(self) -> MonumentListResponse | None:
        """Your monuments, from the last ``gml``; None until one arrived."""
        return self.client.state.get_monuments()

    @property
    def monument_reset(self) -> MonumentResetResponse | None:
        """When the monuments reset next, from the last ``mre`` that counted down; None until one arrived."""
        return self.client.state.get_monument_reset()

    @property
    def villages(self) -> VillageListResponse | None:
        """Your villages and private resource villages, from the last ``kgv``; None until one arrived."""
        return self.client.state.get_villages()

    @property
    def tax(self) -> TaxInfo | None:
        """The tax collection, from the last ``txi``; None until one arrived."""
        return self.client.state.get_tax()

    @property
    def kingdoms(self) -> KingdomInfoResponse | None:
        """Your kingdoms and the transfers to them; None until a ``kpi`` arrived."""
        return self.client.state.get_kingdoms()

    def get_kingdoms(self, *, timeout: float = 5.0) -> KingdomInfoResponse:
        """
        Ask for your kingdoms and the transfers to them; the reply also updates :attr:`kingdoms`.

        It lists the kingdoms the server sends, which :attr:`kingdoms` merges over those known.

        Client: ``CastleHandleKingdomDialog.showLoaded`` (bundle line 55406) sends ``C2SKingdomPayInfoVO``
        """
        return self.request(KingdomInfoRequest(), KingdomInfoResponse, timeout=timeout)

    def get_villages(self, *, timeout: float = 5.0) -> VillageListResponse:
        """
        Ask for your villages and private resource villages; the reply also updates :attr:`villages`.

        Client: ``CastleListVillagesOverviewDialog.getData`` (bundle line 108009) sends
        ``C2SKingdomGetVillageListVO``
        """
        return self.request(GetVillageListRequest(), VillageListResponse, timeout=timeout)

    def unlock_kingdom(
        self,
        castle: PrebuiltCastle,
        direction: KingdomDirection | None = None,
        *,
        ruby_price: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Unlock a kingdom with one of its prebuilt castles, e.g. ``PrebuiltCastle.ICE_KNIGHTLY_CASTLE``.

        The castle names its kingdom and price. One whose only price is rubies is bought with them; one
        priced in resources is bought with those, or with ``ruby_price`` at its ruby price, as the client's
        two buttons offer. Rubies spent need ``spend_rubies``; buying with resources, ``spend_rubies`` pays
        any missing ones with rubies. A Storm Islands castle is priced by the islands' castle selection
        alone and asks for no level.

        Args:
            castle: The prebuilt castle
            direction: The side of the map to place the castle on; None for the Storm Islands, which take none
            ruby_price: Buy the castle at its ruby price
            spend_rubies: Allow spending rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: The castle starts no kingdom (Battle for Berimond's camps join with
                ``client.events.join_berimond``, season camps unlock with ``client.events.unlock_season_camp``,
                special-server castles with ``client.events.select_special_server_castle``), needs a higher
                level, has no direction outside the Storm Islands or one on them, has no ruby price for
                ``ruby_price``, or costs rubies without ``spend_rubies``
            GameDataNotLoadedError: The game data cannot be loaded
            StateNotLoadedError: Outside the Storm Islands, no login has brought your level
            CommandError: The server refused

        Client: ``AUnlockPrebuiltCastle.buyPrebuiltCastle`` (bundle line 55479) sends the castle's first space
        and asks the direction (``CastleKingdomChooseLocalizationDialog``), offering only a castle your level
        reaches (``PrebuiltCastleSelector.validateSelection``, bundle line 54604); ``UnlockPrebuiltCastleForRubies``
        (bundle line 55514) sets ``OC2`` for the castle ``CastleKingdomCastleDetails.getSublayerForCastle``
        (bundle line 97911) shows as premium; the Storm Islands castle selection, which checks no level, always
        sends a direction of 0 and ``OC2`` when its costs hold rubies
        (``CastleSpecialServerPreBuildCastleSelectionDialog.onConfirmed``, bundle line 27956);
        ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (bundle line 35239) sends ``PWR``
        """
        selection = self._require_game_data().storm_islands_prebuilt_castles.get(castle)
        row = self._prebuilt_castle(castle, level_gated=selection is None)
        kingdom = row.kingdom
        if kingdom is None or kingdom in (Kingdom.GREEN, Kingdom.BERIMOND):
            raise ValueError(
                f"prebuilt castle {int(castle)} starts no kingdom; join Battle for Berimond with "
                "client.events.join_berimond, a season map with client.events.unlock_season_camp, a special "
                "server with client.events.select_special_server_castle"
            )
        if kingdom is Kingdom.STORM:
            if direction is not None:
                raise ValueError("the Storm Islands take no direction")
            if selection is None:
                raise ValueError(f"prebuilt castle {int(castle)} is not in the Storm Islands' castle selection")
            ruby_castle, rubies = selection.is_ruby_castle(row), selection.cost_rubies(row)
            if ruby_price and rubies <= 0:
                raise ValueError(f"prebuilt castle {int(castle)} has no ruby price")
        else:
            if direction is None:
                raise ValueError(f"unlocking {kingdom.name} needs a direction")
            rubies = self._castle_rubies(row, ruby_price)
            ruby_castle = rubies > 0
        self._require_spend_rubies(spend_rubies, f"the castle costs {rubies} rubies" if rubies else None)
        request = SelectKingdomCastleRequest(
            prebuilt_castle_id=row.prebuilt_castle_id,
            direction=direction or 0,
            pay_with_rubies=spend_rubies and not ruby_castle,
            ruby_castle=ruby_castle,
            kingdom_id=kingdom,
        )
        self.execute(request, timeout=timeout)

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

    def get_landmark_progress(self, landmark: MapAreaItem, *, timeout: float = 5.0) -> LandmarkProgress:
        """
        A monument's or laboratory's upgrade points, asked for by its map row's object id.

        A laboratory is asked with ``glp``, a monument with ``gmp``, as their upgrade dialogs ask.

        Args:
            landmark: The landmark's map row, e.g. from ``client.map.scan_map_area``

        Raises:
            ValueError: The row is neither a monument nor a laboratory
            CommandError / EmpireTimeoutError / ConnectionClosedError: see :meth:`EmpireClient.send`

        Client: ``CastleUpgradeLaboratoryDialogProperties.progressCommandVO`` and
        ``CastleUpgradeLandmarkDialogProperties.progressCommandVO`` (bundle lines 51665, 51709)
        """
        if landmark.location_id is None or landmark.item_type not in _LANDMARK_PROGRESS:
            raise ValueError(f"{landmark.item_type.name} is neither a monument nor a laboratory")
        request_type, response_type = _LANDMARK_PROGRESS[landmark.item_type]
        return self.request(request_type(object_id=landmark.location_id), response_type, timeout=timeout)

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
