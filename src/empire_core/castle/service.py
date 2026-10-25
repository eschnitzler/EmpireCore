"""
Your castles: resources, buildings, the construction queue, research and the mercenary camp.

It covers:

- Castle management (list, join, rename, abandon)
- Resources and production
- Buildings and the construction queue
- Tax collection
- Research and the mercenary camp's missions
- The refinery and toolsmith crafting queues, construction item crafting and the decoration fusion forge
- A monument's or laboratory's upgrade progress

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

import logging
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, TypeVar

from pydantic import ValidationError

from empire_core.castle.models.actions import (
    AbandonCastleRequest,
    AbandonCastleResponse,
    CancelAbandonCastleRequest,
    JoinAreaRequest,
    LeaveAreaRequest,
    RelocateCastleRequest,
    RenameCastleRequest,
    SelectCastleRequest,
    SelectCastleResponse,
)
from empire_core.castle.models.brewery import (
    BreweryProductionResponse,
    BreweryStops,
    GetBreweryProductionRequest,
    MeadShare,
    SetBreweryProductionRequest,
    SetMeadPriorityRequest,
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
from empire_core.castle.models.construction_items import (
    BoostConstructionItemRequest,
    BoostConstructionItemResponse,
    ConstructionItemInventory,
    ConstructionItemSpace,
    ConstructionItemSpaceRequest,
    DisassembleConstructionItemRequest,
    DisassembleConstructionItemResponse,
    EquipConstructionItemRequest,
    EquipConstructionItemResponse,
    ExpiredConstructionItemsResponse,
    GetConstructionItemsRequest,
    GetExpiredConstructionItemsRequest,
    MarkExpiredConstructionItemsSeenRequest,
    MarkExpiredConstructionItemsSeenResponse,
    MoveConstructionSlotRequest,
    MoveConstructionSlotResponse,
    RemoveConstructionItemRequest,
    RemoveConstructionItemResponse,
)
from empire_core.castle.models.crafting import (
    FULL_SKIP,
    CancelCraftingRequest,
    CancelCraftingResponse,
    ConstructionCraftingResponse,
    CraftConstructionItemRequest,
    CraftConstructionItemResponse,
    CraftingInfoResponse,
    CraftingQueue,
    CraftingSlot,
    GetConstructionCraftingRequest,
    GetCraftingInfoRequest,
    MoveCraftingSlotRequest,
    MoveCraftingSlotResponse,
    SkipConstructionCraftingRequest,
    SkipConstructionCraftingResponse,
    SkipCraftingRequest,
    SkipCraftingResponse,
    StartCraftingRequest,
    StartCraftingResponse,
    UnlockCraftingSlotsRequest,
    UnlockCraftingSlotsResponse,
)
from empire_core.castle.models.details import (
    CastleProductionArea,
    DetailedCastleInfo,
    GetDetailedCastleRequest,
    GetDetailedCastleResponse,
)
from empire_core.castle.models.districts import (
    MoveToDistrictRequest,
    MoveToDistrictResponse,
    RemoveFromDistrictRequest,
    RemoveFromDistrictResponse,
)
from empire_core.castle.models.fusion_forge import (
    DECORATION_FORGE_ID,
    ConvertCatalystRequest,
    ConvertCatalystResponse,
    FuseDecorationRequest,
    FuseDecorationResponse,
    FusionDecoration,
    FusionForge,
    FusionForgesResponse,
    FusionTargetArea,
    FusionTargetsResponse,
    GetFusionForgesRequest,
    GetFusionTargetsRequest,
    LevelUpFusionForgeRequest,
    LevelUpFusionForgeResponse,
    RefillFusionForgeRequest,
    RefillFusionForgeResponse,
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
from empire_core.castle.models.lookups import (
    FeastCostReductionResponse,
    GetFeastCostReductionRequest,
    GetTransportationBuildingsRequest,
    ShowUpgradableBuildingsRequest,
    ShowUpgradableBuildingsResponse,
    TransportationBuilding,
    TransportationBuildingsResponse,
)
from empire_core.castle.models.mercenaries import (
    MercenaryMission,
    MercenaryMissionsResponse,
    MercenaryPackageRequest,
    RefreshMercenaryMissionRequest,
)
from empire_core.castle.models.objects import (
    BuildingConstructionItems,
    BuildingRow,
    ConstructionList,
    ShowConstructionListRequest,
    ShowConstructionListResponse,
)
from empire_core.castle.models.research import (
    ResearchInfoRequest,
    ResearchInfoResponse,
    SkipResearchRequest,
    StartResearchRequest,
)
from empire_core.castle.models.resources import (
    CastleResources,
    GetProductionRequest,
    GetProductionResponse,
    GetResourcesRequest,
    GetResourcesResponse,
)
from empire_core.castle.models.storage import (
    DecorationStorage,
    DecorationStorageResponse,
    MarkStorageSeenRequest,
    PlaceStoredDecorationRequest,
    PlaceStoredDecorationResponse,
    SellStoredDecorationRequest,
    SellStoredDecorationResponse,
    ShowInventoryRequest,
    StoreBuildingRequest,
    StoreBuildingResponse,
)
from empire_core.castle.models.tax import (
    TAX_DURATIONS,
    TAX_RUBY_COSTS,
    BribeTaxCollectorRequest,
    BribeTaxCollectorResponse,
    CollectTaxRequest,
    CollectTaxResponse,
    GetTaxInfoRequest,
    StartTaxRequest,
    StartTaxResponse,
    TaxInfo,
    TaxInfoResponse,
)
from empire_core.castle.models.updates import (
    BuildingFinished,
    BuildingXP,
    CastleBuildingsPushed,
    DamagedBuildings,
    JoinedAreaMoved,
)
from empire_core.castle.models.upkeep import (
    CollectResourceCitizenRequest,
    ConstructionItemExpiryResponse,
    GetConstructionItemExpiryRequest,
    ResourcePoolResponse,
)
from empire_core.castle.models.villages import (
    BuyPrivateVillageRequest,
    GetVillageListRequest,
    RemovePrivateVillageRequest,
    UpgradePrivateVillageRequest,
    VillageListResponse,
)
from empire_core.enums import (
    BuildingState,
    CatalystConversion,
    CollectableKind,
    ConstructionItemMode,
    CurrencyId,
    DecorationStorageId,
    ExpansionType,
    JudgementOption,
    Kingdom,
    KingdomDirection,
    MapItemType,
    MercenaryMissionState,
    ResourceCartType,
)
from empire_core.exceptions import CommandError, EmpireError, PacketError, ReplyMismatchError, UnknownCastleError
from empire_core.gamedata import BuildingDef, Currency, HorseStats, Research
from empire_core.map.models.items import MapAreaItem
from empire_core.protocol.base import BaseResponse
from empire_core.protocol.js import js_truthy
from empire_core.services.base import BaseService
from empire_core.utils.callbacks import Event

if TYPE_CHECKING:
    from empire_core.castle.models.collect import MineStatus, ResourceCart
    from empire_core.castle.models.permanent import PermanentCastle
    from empire_core.castle.models.wishing_well import WishingWellResponse
    from empire_core.client.client import EmpireClient
    from empire_core.gamedata import Building, ConstructionItem
    from empire_core.state.models import Castle, JoinedArea

_ConstructionResponse = TypeVar("_ConstructionResponse", bound=BaseResponse)

# PlayerConst.CHANGE_CASTLE_NAME_C2 (dll line 19599)
_RENAME_RUBIES = 2500
# ConstructionConst.FREE_SKIP_TIME (dll line 18962)
_FREE_SKIP_SECONDS = 240
_BUILDING = (BuildingState.BUILD_STOPPED, BuildingState.BUILD_IN_PROGRESS)
_UPGRADING = (BuildingState.UPGRADE_STOPPED, BuildingState.UPGRADE_IN_PROGRESS)
# RelocationConst.RELOCATION_COST_C2 (dll line 19674), by relocations made, the last for any more
_RELOCATION_RUBIES = (0, 5000, 20000, 35000)
# CastleListVO.getMainCastleByKingdomID (bundle line 13864)
_MAIN_CASTLE_TYPES = (MapItemType.CASTLE, MapItemType.KINGDOM_CASTLE)
_LANDMARK_PROGRESS: dict[
    MapItemType, tuple[type[GetLaboratoryProgressRequest | GetMonumentProgressRequest], type[LandmarkProgress]]
] = {
    MapItemType.LABORATORY: (GetLaboratoryProgressRequest, LaboratoryProgressResponse),
    MapItemType.MONUMENT: (GetMonumentProgressRequest, MonumentProgressResponse),
}


# MercenaryConst.REFRESH_MISSION_COST (dll line 19511)
_REFRESH_MISSION_RUBIES = 240

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

    def __init__(self, client: EmpireClient) -> None:
        super().__init__(client)
        self.on_response("ghw", self._handle_joined_area_moved)
        self.on_response("fbe", self._handle_building_finished)
        self.on_response("cbx", self._handle_building_xp)
        self.on_response("gdb", self._handle_buildings_changed)
        self.on_response("gcb", self._handle_buildings_changed)
        self.on_response("gca", self._handle_castle_buildings)

    on_joined_area_moved = Event[JoinedAreaMoved]()
    """Register a callback for the castle you have joined moving on the map (``ghw``).

    Called with its new position, after :attr:`joined_area` has it, and also when no area is
    joined, which the push leaves alone. Callbacks run on the receive thread: they must not
    block, and a call that waits for a reply raises ``ReceiveThreadError``.

    Client: ``GHWCommand.executeCommand`` (bundle line 129574)
    """

    on_building_finished = Event[BuildingFinished]()
    """Register a callback for a building in the joined castle that finished (``fbe``), with the
    building's object id and the XP it gave. Runs on the receive thread, as :attr:`on_joined_area_moved`.

    Client: ``FBECommand.exec`` (bundle line 122879), ``AreaDataUpdater.parseCBX`` (bundle line 131521)
    """

    on_building_xp = Event[BuildingXP]()
    """Register a callback for XP a building in the joined castle gave (``cbx``). Runs on the
    receive thread, as :attr:`on_joined_area_moved`.

    Client: ``CBXCommand.executeCommand`` (bundle line 123345)
    """

    on_buildings_changed = Event[DamagedBuildings]()
    """Register a callback for buildings of the joined castle that were damaged (``gdb``) or
    whose efficiency changed (``gcb``, a :class:`BuildingEfficiencyChanged`), with their new rows.
    State does not keep the joined castle's buildings: the build, upgrade and repair replies change
    them too. Runs on the receive thread, as :attr:`on_joined_area_moved`.

    Client: ``GDBCommand`` and ``GCBCommand`` (bundle lines 122998, 122968),
    ``IsoUpdaterData.updateMultipleObjectInfos`` (bundle line 130259)
    """

    on_castle_buildings = Event[CastleBuildingsPushed]()
    """Register a callback for the joined castle's buildings sent whole (``gca``), called after
    :meth:`get_placed_construction_items` has the construction items they carry; not called while no
    castle is joined. Runs on the receive thread, as :attr:`on_joined_area_moved`.

    Client: ``GCACommand.executeCommand`` (bundle line 122991)
    """

    def _handle_castle_buildings(self, response: BaseResponse) -> None:
        if (
            isinstance(response, CastleBuildingsPushed)
            and response.buildings is not None
            and self.client.state.joined_area is not None
        ):
            self._fire(self.on_castle_buildings, response)

    def _handle_joined_area_moved(self, response: BaseResponse) -> None:
        if isinstance(response, JoinedAreaMoved):
            self._fire(self.on_joined_area_moved, response)

    def _handle_building_finished(self, response: BaseResponse) -> None:
        if isinstance(response, BuildingFinished):
            self._fire(self.on_building_finished, response)

    def _handle_building_xp(self, response: BaseResponse) -> None:
        if isinstance(response, BuildingXP):
            self._fire(self.on_building_xp, response)

    def _handle_buildings_changed(self, response: BaseResponse) -> None:
        if isinstance(response, DamagedBuildings):
            self._fire(self.on_buildings_changed, response)

    @property
    def construction_items(self) -> ConstructionItemInventory | None:
        """The last construction inventory received; None before the first inventory reply."""
        return self.client.state.get_construction_items()

    def get_construction_items(self, *, timeout: float = 5.0) -> ConstructionItemInventory:
        """Request all construction items in storage, including an empty inventory.

        Client: ``C2SGetContructionItemsInventoryVO`` and ``GIICommand``
        (bundle lines 28546, 123270).
        """
        return self.request(GetConstructionItemsRequest(), ConstructionItemInventory, timeout=timeout)

    @property
    def placed_construction_items(self) -> tuple[BuildingConstructionItems, ...] | None:
        """Items on the joined castle's buildings; None before joining or after a map read."""
        return self.client.state.get_placed_construction_items()

    def _refresh_construction_items(self, timeout: float) -> None:
        self.client.state.invalidate_construction_items()
        try:
            self.get_construction_items(timeout=timeout)
        except EmpireError as error:
            logging.getLogger(__name__).warning(
                "Construction inventory refresh failed after accepted action: %s", error
            )

    def _request_construction_action(
        self,
        request: EquipConstructionItemRequest
        | RemoveConstructionItemRequest
        | DisassembleConstructionItemRequest
        | BoostConstructionItemRequest,
        response_type: type[_ConstructionResponse],
        timeout: float,
        *,
        area_revision: int | None = None,
    ) -> tuple[_ConstructionResponse, object]:
        packet = self.client.request_packet(request, request.get_response_command(), timeout=timeout)
        if packet.error_code != 0:
            raise CommandError(request.command, packet.error_code, packet.payload)
        if request.command != "ubc":
            self.client.state.invalidate_construction_items()
        if area_revision is not None:
            self.client.state.apply_placed_construction_items(
                None,
                castle_id=request.castle_id,
                kingdom_id=request.kingdom_id,
                area_revision=area_revision,
                command=request.command,
                response_payload=packet.payload,
            )
        try:
            result = response_type.model_validate(packet.payload)
        except ValidationError as error:
            raise PacketError(f"Could not parse '{request.command}' response: {error}") from error
        return result, packet.payload

    def _join_construction_area(self, castle_id: int, kingdom: Kingdom, timeout: float) -> int:
        self.join(castle_id, timeout=timeout)
        revision = self.client.state.area_revision
        area = self.client.state.get_joined_area()
        if area is None or area.castle_id != castle_id or area.kingdom_id != kingdom:
            raise ReplyMismatchError(castle_id, area.castle_id if area and area.castle_id is not None else -1)
        return revision

    def equip_construction_item(
        self,
        castle_id: int,
        object_id: int,
        construction_item_id: ConstructionItem | int,
        slot: int,
        *,
        mode: ConstructionItemMode = ConstructionItemMode.ADD,
        timeout: float = 5.0,
    ) -> EquipConstructionItemResponse:
        """Join a castle and equip an item, returning the server's complete placement.

        ADD fills an empty slot. REPLACE keeps the old item for its coin removal
        cost; OVERWRITE discards it. A failed inventory refresh is logged and
        leaves ``construction_items`` unknown after the accepted placement.

        Client: ``AConstructionItemsActionDialog.sendReplaceCommand`` (bundle 28680),
        ``CastleConstructionItemsOverwriteDialog`` (bundle 79306-79307).
        """
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = EquipConstructionItemRequest(
            object_id=object_id,
            construction_item_id=construction_item_id,
            slot=slot,
            mode=mode,
            kingdom_id=kingdom,
            castle_id=castle_id,
        )
        with (
            self.client.connection.command_lock("jaa", timeout=timeout),
            self.client.connection.command_lock("gaa", timeout=timeout),
        ):
            revision = self._join_construction_area(castle_id, kingdom, timeout)
            result, payload = self._request_construction_action(
                request, EquipConstructionItemResponse, timeout, area_revision=revision
            )
            self.client.state.apply_placed_construction_items(
                result,
                castle_id=castle_id,
                kingdom_id=kingdom,
                area_revision=revision,
                command=request.command,
                response_payload=payload,
            )
            self._refresh_construction_items(timeout)
            return result

    def remove_construction_item(
        self,
        castle_id: int,
        object_id: int,
        construction_item_id: ConstructionItem | int,
        slot: int,
        *,
        timeout: float = 5.0,
    ) -> RemoveConstructionItemResponse:
        """Join a castle and return an equipped item to storage for its coin removal cost.

        Refusals and transport failures propagate. A failed inventory refresh is
        logged and leaves ``construction_items`` unknown after the accepted removal.

        Client: ``CastleConstructionItemsExtractDialog.onClickAccept`` (bundle 79277),
        ``CRICommand.executeCommand`` (bundle 123255-123256).
        """
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = RemoveConstructionItemRequest(
            object_id=object_id,
            construction_item_id=construction_item_id,
            slot=slot,
            kingdom_id=kingdom,
            castle_id=castle_id,
        )
        with (
            self.client.connection.command_lock("jaa", timeout=timeout),
            self.client.connection.command_lock("gaa", timeout=timeout),
        ):
            revision = self._join_construction_area(castle_id, kingdom, timeout)
            result, payload = self._request_construction_action(
                request, RemoveConstructionItemResponse, timeout, area_revision=revision
            )
            self.client.state.apply_placed_construction_items(
                result,
                castle_id=castle_id,
                kingdom_id=kingdom,
                area_revision=revision,
                command=request.command,
                response_payload=payload,
            )
            self._refresh_construction_items(timeout)
            return result

    def disassemble_construction_item(
        self,
        castle_id: int,
        construction_item_id: ConstructionItem | int,
        *,
        amount: int = 1,
        lost_and_found_id: int = -1,
        timeout: float = 5.0,
    ) -> DisassembleConstructionItemResponse:
        """Disassemble stored items and resolve their drawn rewards from game data.

        Items are consumed. ``lost_and_found_id=-1`` selects storage. The reply
        exposes the drawn reward ids and their collectables; permanent items'
        recipe materials are not listed by the server. A failed inventory refresh
        is logged and leaves ``construction_items`` unknown after success.

        Client: ``C2SDisassembleConstructionItemVO`` (bundle 79223-79227),
        ``onClickAccept`` / ``onDCIArrived`` (bundle 35727-35729),
        ``showTempCIDisassembling`` (bundle 48984).
        """
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = DisassembleConstructionItemRequest(
            construction_item_id=construction_item_id,
            kingdom_id=kingdom,
            castle_id=castle_id,
            amount=amount,
            lost_and_found_id=lost_and_found_id,
        )
        game_data = self._require_game_data()
        with (
            self.client.connection.command_lock("jaa", timeout=timeout),
            self.client.connection.command_lock("gaa", timeout=timeout),
        ):
            self._join_construction_area(castle_id, kingdom, timeout)
            result, _ = self._request_construction_action(request, DisassembleConstructionItemResponse, timeout)
            result = result.model_copy(update={"rewards": game_data.reward_list(result.reward_ids, combine=True)})
            self._refresh_construction_items(timeout)
            return result

    @property
    def construction_item_space(self) -> ConstructionItemSpace | None:
        """Free construction storage capacity, from the last inventory or capacity push."""
        return self.client.state.get_construction_item_space()

    def get_construction_item_space(self, *, timeout: float = 5.0) -> ConstructionItemSpace:
        """
        Ask how many more construction items fit in storage; the reply also reaches the state.

        Client: ``C2SConstructionItemInventorySpaceLeftVO`` (bundle line 41293), ``CSPCommand.exec``
        (bundle line 123855)
        """
        return self.request(ConstructionItemSpaceRequest(), ConstructionItemSpace, timeout=timeout)

    def get_construction_item_expiry(self, *, timeout: float = 5.0) -> ConstructionItemExpiryResponse:
        """
        Ask when the next of your construction items expires; the reply also reaches the state.

        Client: ``ConstructionItemData.onCIExpiration`` (bundle line 22993) sends
        ``C2SGetNextExpiringConstructionItemVO``; ``NECCommand.executeCommand`` (bundle line 123336)
        """
        return self.request(GetConstructionItemExpiryRequest(), ConstructionItemExpiryResponse, timeout=timeout)

    @property
    def expired_construction_items(self) -> ExpiredConstructionItemsResponse | None:
        """The last complete list of expired items; None before a successful read."""
        return self.client.state.get_expired_construction_items()

    def get_expired_construction_items(self, *, timeout: float = 5.0) -> ExpiredConstructionItemsResponse:
        """Request expired items across your castles.

        Client: ``C2SGetAllExpiredConstructionItemsVO`` / ``AECCommand`` (bundle 79379 / 123264).
        """
        return self.request(GetExpiredConstructionItemsRequest(), ExpiredConstructionItemsResponse, timeout=timeout)

    def mark_expired_construction_items_seen(
        self, castle_id: int, *, timeout: float = 5.0
    ) -> MarkExpiredConstructionItemsSeenResponse:
        """Mark a castle's expired items as viewed, as closing their list does.

        This acknowledgement does not remove expired records from the cached list.
        Client: assign sublayer hide / switchCastle (bundle 77574 / 77583), MECCommand (123308).
        """
        self._require_own_castle(castle_id)
        return self.request(
            MarkExpiredConstructionItemsSeenRequest(castle_id=castle_id),
            MarkExpiredConstructionItemsSeenResponse,
            timeout=timeout,
        )

    def move_construction_slot(
        self, castle_id: int, old_position: int, new_position: int, *, timeout: float = 5.0
    ) -> ConstructionList:
        """Move a building in its construction queue and read the resulting queue.

        Both positions must contain a building. The move acknowledgement carries no queue;
        a failed follow-up read propagates after the accepted move.
        Client: ``CastleBuildingListComponent`` (bundle 108280-108281), ``MCICommand`` (123383).
        """
        if old_position < 0 or new_position < 0:
            raise ValueError("Queue positions must be nonnegative")
        kingdom = self._require_own_castle(castle_id).kingdom_id
        with (
            self.client.connection.command_lock("jaa", timeout=timeout),
            self.client.connection.command_lock("gaa", timeout=timeout),
        ):
            revision = self._join_construction_area(castle_id, kingdom, timeout)
            queue = self._construction_queue_for_move(timeout)
            if any(
                position >= len(queue.slots) or queue.slots[position].object_id <= 0
                for position in (old_position, new_position)
            ):
                raise ValueError("Both construction queue positions must contain buildings")
            self._check_construction_area(castle_id, kingdom, revision)
            if old_position == new_position:
                return queue
            self.request(
                MoveConstructionSlotRequest(object_id=queue.slots[old_position].object_id, new_position=new_position),
                MoveConstructionSlotResponse,
                timeout=timeout,
            )
            self._check_construction_area(castle_id, kingdom, revision)
            result = self._construction_queue_for_move(timeout)
            self._check_construction_area(castle_id, kingdom, revision)
            return result

    def _construction_queue_for_move(self, timeout: float) -> ConstructionList:
        packet = self.client.request_packet(ShowConstructionListRequest(), "scl", timeout=timeout)
        if packet.error_code != 0:
            raise CommandError("scl", packet.error_code, packet.payload)
        if not isinstance(packet.payload, dict) or not isinstance(packet.payload.get("OIDL"), list):
            raise PacketError("The construction queue reply must contain a building list")
        if any(isinstance(entry, (dict, list)) for entry in packet.payload["OIDL"]):
            raise PacketError("The construction queue reply must contain scalar building ids")
        try:
            return ShowConstructionListResponse.model_validate(packet.payload)
        except ValidationError as error:
            raise PacketError(f"Could not parse construction queue: {error}") from error

    def _check_construction_area(self, castle_id: int, kingdom: Kingdom, revision: int) -> None:
        area = self.client.state.get_joined_area()
        if (
            area is None
            or area.castle_id != castle_id
            or area.kingdom_id != kingdom
            or self.client.state.area_revision != revision
        ):
            raise ReplyMismatchError(castle_id, area.castle_id if area and area.castle_id is not None else -1)

    def boost_construction_item(
        self,
        castle_id: int,
        object_id: int,
        construction_item_id: ConstructionItem | int,
        slot: int,
        *,
        consumable: CurrencyId,
        timeout: float = 5.0,
    ) -> BoostConstructionItemResponse:
        """Consume one selected inventory booster on a temporary equipped item.

        Select currency id 2000 (rare), 2001 (epic) or 2002 (legendary).
        The item must still have time remaining and the selected booster must improve its rarity.
        Client: ``updateBoosterButton`` / ``boostConstructionItem`` (bundle 77588-77591 / 77624-77625),
        ``ConstructionItemConst`` (dll 18989). This command has no ruby purchase branch.
        """
        targets = {2000: 2, 2001: 3, 2002: 4}
        if consumable not in targets:
            raise ValueError("Select a rare, epic or legendary construction item inventory booster")
        if slot < 0 or object_id <= 0:
            raise ValueError("The building and slot must identify an equipped construction item")
        game_data = self._require_game_data()
        item = game_data.construction_items.get(construction_item_id)
        if item is None or item.duration_seconds <= 0 or item.rareness_id >= targets[consumable]:
            raise ValueError("The selected booster must improve a known temporary construction item")
        currency = game_data.currencies.get(consumable)
        if currency is None or self.client.state.get_special_currencies().get(currency.json_key, 0) <= 0:
            raise ValueError("The selected construction item booster is not in inventory")
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = BoostConstructionItemRequest(
            object_id=object_id,
            consumable_id=consumable,
            slot=slot,
            kingdom_id=kingdom,
            castle_id=castle_id,
            construction_item_id=construction_item_id,
        )
        with (
            self.client.connection.command_lock("jaa", timeout=timeout),
            self.client.connection.command_lock("gaa", timeout=timeout),
        ):
            revision = self._join_construction_area(castle_id, kingdom, timeout)
            placement = self.placed_construction_items
            equipped = next(
                (
                    entry
                    for building in placement or ()
                    if building.object_id == object_id
                    for entry in building.items
                    if entry.slot == slot and entry.construction_item_id == construction_item_id
                ),
                None,
            )
            if equipped is None or equipped.remaining_seconds <= 0:
                raise ValueError("The selected temporary construction item is not equipped or has expired")
            result, payload = self._request_construction_action(
                request, BoostConstructionItemResponse, timeout, area_revision=revision
            )
            self.client.state.apply_placed_construction_items(
                result,
                castle_id=castle_id,
                kingdom_id=kingdom,
                area_revision=revision,
                command=request.command,
                response_payload=payload,
            )
            return result

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
    def judgement_id(self) -> int | None:
        """The open citizen judgement's row in the judgements table, from the last ``sjc``; None while none is open."""
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
        kingdom_id: Kingdom,
        prebuilt_castle_id: int,
        direction: KingdomDirection | None = None,
        *,
        ruby_castle: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> None:
        """
        Unlock a kingdom with one of its prebuilt castles.

        Each kingdom offers prebuilt castles in the items ``prebuiltcastles`` table, whose ``spaceIDs``
        name the kingdom: a cheap one, one priced in resources and one whose only price is rubies.
        ``ruby_castle`` takes that last one and needs ``spend_rubies``; otherwise ``spend_rubies`` pays
        any missing resources with rubies.

        Args:
            kingdom_id: The kingdom to unlock
            prebuilt_castle_id: The prebuilt castle's ``preBuiltCastleID``
            direction: The side of the map to place the castle on; only the Storm Islands may go without
            ruby_castle: The castle is the one priced in rubies only
            spend_rubies: Allow spending rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: No direction outside the Storm Islands, or ``ruby_castle`` without ``spend_rubies``
            CommandError: The server refused

        Client: ``AUnlockPrebuiltCastle.buyPrebuiltCastle`` (bundle line 55479) asks the direction
        (``CastleKingdomChooseLocalizationDialog``) and ``getCosts`` prices it; the Storm Islands castle
        choice sends a direction of 0 (``CastleSpecialServerPreBuildCastleSelectionDialog.onConfirmed``,
        bundle line 27956); ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (bundle line 35239)
        sends ``PWR``; ``PrebuiltCastleItemVO.isPremium`` (bundle line 142354)
        """
        if direction is None and kingdom_id != Kingdom.STORM:
            raise ValueError(f"unlocking {Kingdom(kingdom_id).name} needs a direction")
        self._require_spend_rubies(spend_rubies, "the ruby castle costs rubies" if ruby_castle else None)
        request = SelectKingdomCastleRequest(
            prebuilt_castle_id=prebuilt_castle_id,
            direction=0 if direction is None else direction,
            pay_with_rubies=spend_rubies and not ruby_castle,
            ruby_castle=ruby_castle,
            kingdom_id=kingdom_id,
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

    def abandon_castle(self, castle_id: int, *, timeout: float = 5.0) -> AbandonCastleResponse:
        """
        Start abandoning one of your castles; it is given up a day later unless cancelled.

        Looks the castle up in the castle list for its kingdom, as :meth:`rename`
        does. Any castle may be abandoned but the kingdom's main castle; a
        faction event's main camp, which the client also counts as one, is
        left to the server. It is free.
        The castle goes after ``OutpostConst.ABANDON_TIME`` (86400 s) and
        :meth:`cancel_abandon` keeps it within ``ABANDON_CANCEL_TIME`` (10800 s).

        Args:
            castle_id: One of your castles, from ``client.castle.get_all()``
                (``CastleInfo.castle_id``)
            timeout: Timeout in seconds

        Raises:
            ValueError: ``castle_id`` is the main castle of its kingdom
            UnknownCastleError: ``castle_id`` is not one of your castles.
            CommandError: The server refused, as for a castle held too briefly
                (``CastleInfo.no_abandon_seconds`` above 0), which the client
                refuses itself with ``NOT_OWNED_LONG_ENOUGH``

        Client: ``CastleManagementDialog.setDeleteOutpostAndRelocateButton`` (bundle line 24592)
        offers it for any castle but ``CastleListVO.getMainCastleByKingdomID`` (bundle line
        13864), the kingdom's castle of type ``CASTLE`` or ``KINGDOM_CASTLE``;
        ``onAbandonOutpost`` (bundle line 24630) sends ``C2SAbandonOutpostStartVO``;
        ``OutpostConst`` (dll line 19530)

        Example:
            reply = client.castle.abandon_castle(12345)
            print(f"Abandoned in {reply.abandon_seconds} s")
        """
        castles = self.get_all(timeout=timeout)
        castle = next((c for c in castles if c.castle_id == castle_id), None)
        if castle is None:
            raise UnknownCastleError(castle_id)
        main = next(
            (c for c in castles if c.kingdom_id == castle.kingdom_id and c.castle_type in _MAIN_CASTLE_TYPES), None
        )
        if main is castle:
            raise ValueError(f"castle {castle_id} is the main castle of its kingdom and cannot be abandoned")
        return self.request(
            AbandonCastleRequest(castle_id=castle_id, kingdom_id=castle.kingdom_id),
            AbandonCastleResponse,
            timeout=timeout,
        )

    def cancel_abandon(self, castle_id: int, *, timeout: float = 5.0) -> None:
        """
        Keep a castle :meth:`abandon_castle` started to give up.

        Looks the castle up in the castle list for its kingdom. The client
        offers it while ``CastleInfo.cancel_abandon_seconds`` is above 0.

        Args:
            castle_id: One of your castles, from ``client.castle.get_all()``
                (``CastleInfo.castle_id``)
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not one of your castles.
            CommandError: The server refused.

        Client: ``CastleManagementDialog.onDeleteOutpostClick`` and ``onCancelAbandoning``
        (bundle lines 24624, 24629) send ``C2SAbandonOutpostCancelVO``

        Example:
            client.castle.cancel_abandon(12345)
        """
        castle = next((c for c in self.get_all(timeout=timeout) if c.castle_id == castle_id), None)
        if castle is None:
            raise UnknownCastleError(castle_id)
        self.execute(CancelAbandonCastleRequest(castle_id=castle_id, kingdom_id=castle.kingdom_id), timeout=timeout)

    def relocate(self, x: int, y: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Move your main castle in the green kingdom to a new position.

        The client offers it on the green kingdom's map, at a free position or a ruin. The first
        relocation is free; the next cost ``RelocationConst.RELOCATION_COST_C2`` (5000, 20000, then
        35000 rubies each), less any ruby discount, and need ``spend_rubies``, as does any relocation
        while no ``gri`` has said how many were made. The cooldown
        (``client.player.relocation``) is left to the server.

        Args:
            x: Map x of the new position
            y: Map y of the new position
            spend_rubies: Allow a relocation that costs rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: The relocation costs rubies, or its price is not known, and ``spend_rubies`` is False
            CommandError: The server refused, as with ``CASTLE_HAS_MOVEMENTS`` while armies are on the way

        Client: ``CastleRelocateDialog.getCost`` and ``onClick`` (bundle line 109656),
        ``SwitchToRelocateWorldmapCommand.execute`` (bundle line 100959), ``RSTCommand.executeCommand``
        (bundle line 126855); ``RelocationConst.getRelocationCost`` (dll line 19674)
        """
        relocation = self.client.state.get_relocation()
        if relocation is None:
            cost = "no relocation count is known yet, so the relocation may cost rubies"
        elif price := _RELOCATION_RUBIES[min(relocation.relocation_count, len(_RELOCATION_RUBIES) - 1)]:
            cost = f"this relocation costs {price} rubies"
        else:
            cost = None
        self._require_spend_rubies(spend_rubies, cost)
        self.execute(RelocateCastleRequest(x=x, y=y), timeout=timeout)

    def leave_area(self) -> None:
        """
        Leave the area you joined last, as the client does when it opens the kingdom overview.

        The client has no handler for a reply, so none is waited for.

        Client: ``CastleKingdomOverviewScreen.show`` (bundle line 108518) sends ``C2SLeaveAreaVO``
        """
        self.send(LeaveAreaRequest())

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
    # Decoration storage
    # =========================================================================

    @property
    def decoration_storages(self) -> dict[int, DecorationStorage]:
        """The decoration storages by storage id, from the last ``sin`` that named each; empty until one arrived."""
        return self.client.state.get_decoration_storages()

    def get_decoration_storages(self, *, timeout: float = 5.0) -> list[DecorationStorage]:
        """
        Read the decoration storages; they also reach :attr:`decoration_storages`.

        Client: ``CastleDecoShopPanel.show`` (bundle line 9302) sends ``C2SShowInventoryVO`` with no
        parameter; ``SINCommand.exec`` (bundle line 124638)
        """
        return self.request(ShowInventoryRequest(), DecorationStorageResponse, timeout=timeout).storages

    def mark_storage_seen(self, storage_id: DecorationStorageId | int, *, timeout: float = 5.0) -> None:
        """
        Mark a storage's new decorations as seen.

        Args:
            storage_id: A ``DecorationStorage.storage_id``

        Client: ``SendMarkedBuildingsInStorage.execute`` (bundle line 101099) sends
        ``C2SMarkBuildingInStorageVO`` for each storage shown
        """
        self.execute(MarkStorageSeenRequest(storage_id=storage_id), timeout=timeout)

    def store_decoration(self, object_id: int, *, timeout: float = 5.0) -> StoreBuildingResponse:
        """
        Put a decoration of the joined castle into the storage.

        Returns:
            The stored object's id and the storages after, which also reach :attr:`decoration_storages`

        Client: ``IsoServerCommands.storeBuildingToLocalInventory`` (bundle line 63795) sends
        ``C2SIsoStoreObjectVO``; ``SOBCommand.executeCommand`` (bundle line 124651)
        """
        return self.request(StoreBuildingRequest(object_id=object_id), StoreBuildingResponse, timeout=timeout)

    def sell_stored_decoration(
        self, wod_id: Building | int, amount: int = 1, *, unique_id: int = -1, timeout: float = 5.0
    ) -> SellStoredDecorationResponse:
        """
        Sell decorations from the storage for coins; they are gone for good.

        Args:
            wod_id: The decoration's type, a stored decoration's ``wod_id``
            amount: How many to sell
            unique_id: A unique decoration's ``unique_id``, -1 for regular ones

        Returns:
            Coins and rubies, and the storages after, which also reach :attr:`decoration_storages`

        Raises:
            ValueError: ``amount`` is below 1

        Client: ``CastleConstructionSellDialog.onClick`` (bundle line 28636) sends ``C2SellStoredDeco``;
        ``SDSCommand.executeCommand`` (bundle line 131786)
        """
        if amount < 1:
            raise ValueError(f"amount must be at least 1, got {amount}")
        request = SellStoredDecorationRequest(wod_id=wod_id, amount=amount, unique_id=unique_id)
        return self.request(request, SellStoredDecorationResponse, timeout=timeout)

    def place_stored_decoration(
        self, decoration_id: int, x: int, y: int, rotation: int = 0, *, timeout: float = 5.0
    ) -> PlaceStoredDecorationResponse:
        """
        Place a custom or unique decoration from the storage in the joined castle.

        A regular stored decoration is placed with :meth:`build` of its type, as the client does.

        Args:
            decoration_id: A stored ``custom_id`` or ``unique_id``

        Returns:
            The placed decoration and the storages after, which also reach :attr:`decoration_storages`

        Client: ``IsoServerCommands.placeCustomInventoryObject`` (bundle line 63790), sent for a decoration
        with a ``uniqueBuildingId`` (bundle line 64041); ``PIOCommand.executeCommand`` (bundle line 123181)
        """
        request = PlaceStoredDecorationRequest(decoration_id=decoration_id, x=x, y=y, rotation=rotation)
        return self.request(request, PlaceStoredDecorationResponse, timeout=timeout)

    # =========================================================================
    # Brewery
    # =========================================================================

    def get_brewery_production(
        self, castle_id: int, brewery: BuildingRow, *, timeout: float = 5.0
    ) -> BreweryProductionResponse:
        """
        Read one of your castles' brewery production.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            brewery: The brewery's row, from ``join(castle_id).buildings``

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list

        Client: ``CastleBreweryShortageDialog.showLoaded`` (bundle line 138227) sends
        ``C2SGetAreaBuildingProductionVO``; ``ABPICommand.executeCommand`` (bundle line 122711)
        """
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = GetBreweryProductionRequest(
            kingdom_id=kingdom, castle_id=castle_id, wod_id=brewery.wod_id, object_id=brewery.object_id
        )
        return self.request(request, BreweryProductionResponse, timeout=timeout)

    def set_brewery_production(
        self,
        castle_id: int,
        brewery: BuildingRow,
        mead_percent: int,
        *,
        stop_at_food: int = 0,
        stop_at_honey: int = 0,
        timeout: float = 5.0,
    ) -> BreweryProductionResponse:
        """
        Set how much of one of your castles' brewery makes mead, and the stocks at which it stops.

        Args:
            castle_id: One of your castles, a ``Castle.id`` from ``client.state.get_castles()``
            brewery: The brewery's row, from ``join(castle_id).buildings``
            mead_percent: The share of the brewery producing mead, in percent
            stop_at_food: Food left at which production stops
            stop_at_honey: Honey left at which production stops

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list

        Client: the brewery dialog's save button (bundle line 36458) sends ``C2SSetBreweryProductionVO``;
        ``ABPICommand.executeCommand`` (bundle line 122711)
        """
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = SetBreweryProductionRequest(
            kingdom_id=kingdom,
            castle_id=castle_id,
            wod_id=brewery.wod_id,
            object_id=brewery.object_id,
            share=MeadShare(mead_percent=mead_percent),
            stops=BreweryStops(food=stop_at_food, honey=stop_at_honey),
        )
        return self.request(request, BreweryProductionResponse, timeout=timeout)

    def set_mead_priority(self, castle_id: int, enabled: bool, *, timeout: float = 5.0) -> None:
        """
        Give one of your castles' mead production priority, or take it away.

        Raises:
            UnknownCastleError: ``castle_id`` is not in your castle list

        Client: the brewery dialog's priority checkbox (bundle line 36462) sends ``C2SSetMeadPrioVO``
        for the active castle; ``BFLCommand.executeCommand`` (bundle line 122726)
        """
        kingdom = self._require_own_castle(castle_id).kingdom_id
        self.execute(SetMeadPriorityRequest(kingdom_id=kingdom, castle_id=castle_id, enabled=enabled), timeout=timeout)

    # =========================================================================
    # Private resource villages
    # =========================================================================

    def buy_private_village(self, village_type_id: int, *, timeout: float = 5.0) -> None:
        """
        Buy a private resource village with resource village tokens.

        Args:
            village_type_id: The village type's id in the game data's ``privateVillages`` table

        Client: ``PrivateResourceVillageBuyDialog.onConfirm`` (bundle line 81673) sends
        ``C2SBuyPrivateResourceVillageVO`` once ``APrivateResourceVillageActionDialog.onClick`` (bundle line
        36219) found the tokens; ``BPVCommand.exec`` (bundle line 126459)
        """
        self.execute(BuyPrivateVillageRequest(village_type_id=village_type_id), timeout=timeout)

    def upgrade_private_village(self, village_type_id: int, village_id: int, *, timeout: float = 5.0) -> None:
        """
        Upgrade one of your private resource villages to the next level, with resource village tokens.

        Args:
            village_type_id: The type of the village's current level, in the game data's ``privateVillages``
            village_id: Your private village's id, ``PrivateVillage.village_id``

        Client: ``PrivateResourceVillageUpgradeDialog.onConfirm`` (bundle line 81600) sends
        ``C2SUpgradePrivateResourceVillageVO``; ``UPVCommand.exec`` (bundle line 126489)
        """
        request = UpgradePrivateVillageRequest(village_type_id=village_type_id, village_id=village_id)
        self.execute(request, timeout=timeout)

    def remove_private_village(self, village_id: int, *, timeout: float = 5.0) -> None:
        """
        Remove one of your private resource villages; it is gone for good, its tokens are not returned.

        Args:
            village_id: Your private village's id, ``PrivateVillage.village_id``

        Client: ``PrivateResourceVillageDestroyDialog.onConfirm`` (bundle line 81568) sends
        ``C2SRemovePrivateResourceVillageVO``; ``RPVCommand.exec`` (bundle line 126474)
        """
        self.execute(RemovePrivateVillageRequest(village_id=village_id), timeout=timeout)

    # =========================================================================
    # Lookups
    # =========================================================================

    def get_upgradable_buildings(
        self, wod_id: Building | int, *, prime_sale_upgrade: bool = True, timeout: float = 5.0
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

    def bribe_tax_collector(
        self, *, spend_rubies: bool = False, private_offer_id: int = -1, timeout: float = 5.0
    ) -> BribeTaxCollectorResponse:
        """
        Bribe the tax collector, a tax booster bought with rubies; see "Spending rubies" in the guides.

        Its price comes with the boosters and is not worked out here, so this always needs ``spend_rubies``.

        Args:
            spend_rubies: Allow the rubies it costs; without it nothing is sent
            private_offer_id: The booster sale the bribe uses, -1 for none

        Returns:
            Coins and rubies, and the tax status after; the booster reaches ``client.state.get_boosts()``

        Raises:
            ValueError: ``spend_rubies`` is False

        Client: ``CastleBribeDialog.onClick`` (bundle line 90878) sends it once the rubies are there, with
        ``CastleBoosterSaleData.getOfferId`` (bundle line 9696); ``BTXCommand.executeCommand`` (bundle line 128770)
        """
        self._require_spend_rubies(spend_rubies, "bribing the tax collector costs rubies")
        request = BribeTaxCollectorRequest(private_offer_id=private_offer_id)
        return self.request(request, BribeTaxCollectorResponse, timeout=timeout)

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

    def get_research(self, *, timeout: float = 5.0) -> ResearchInfoResponse:
        """
        Read your research; the reply also reaches :attr:`research`.

        Client: ``CastleResearchDialog.showLoaded`` (bundle line 16731) sends ``C2SResearchInfoVO``;
        ``REICommand.executeCommand`` (bundle line 126899)
        """
        return self.request(ResearchInfoRequest(), ResearchInfoResponse, timeout=timeout)

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
        79679-79680), and ``AResearchVO.getBaseCosts`` takes the Outer Realms' costs there (bundle
        line 61530); ``RESCommand`` (bundle line 126872)
        """
        game_data = self._require_game_data()
        row = game_data.researches.get(research)
        if row is None:
            raise ValueError(f"the game data has no research {research!r}")
        costs = (*row.costs, *row.outer_realms_costs)
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

    def refresh_mission(self, mission_id: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Swap an open mercenary mission for another, for ``REFRESH_MISSION_COST`` (240) rubies; see
        "Spending rubies" in the guides.

        Lists the missions first and decides from that reply, as the client decides from its mission
        state: only an open mission is swapped, and only while no mission waits to be collected.

        Args:
            mission_id: A ``MercenaryMission.mission_id`` from :meth:`list_missions`
            spend_rubies: Allow the rubies it costs; without it nothing is sent
            timeout: Timeout in seconds, for each request

        Raises:
            ValueError: ``spend_rubies`` is False, the missions list no such mission, it is not open, or a
                mission waits to be collected

        Client: ``CastleMercenaryMissionItem.updateButtons`` and ``showStartAndRefreshButton`` (bundle lines
        87390, 87396), ``refreshMissionCallback`` (bundle line 87416); ``RMMCommand.executeCommand`` (bundle
        line 125166); ``MercenaryConst.REFRESH_MISSION_COST`` (dll line 19511)
        """
        self._require_spend_rubies(spend_rubies, f"refreshing a mission costs {_REFRESH_MISSION_RUBIES} rubies")
        missions = self.list_missions(timeout=timeout)
        mission = self._mission(missions, mission_id)
        if mission.current_state() != MercenaryMissionState.OPEN:
            raise ValueError(f"mercenary mission {mission_id} is not open")
        if missions.current_mission_state() >= MercenaryMissionState.COLLECTABLE:
            raise ValueError("a mercenary mission waits to be collected")
        self.execute(RefreshMercenaryMissionRequest(mission_id=mission_id), timeout=timeout)

    @staticmethod
    def _mission(missions: MercenaryMissionsResponse, mission_id: int) -> MercenaryMission:
        mission = missions.get_mission(mission_id)
        if mission is None:
            raise ValueError(f"no mercenary mission {mission_id}")
        return mission

    # =========================================================================
    # Crafting
    # =========================================================================

    @property
    def crafting_queues(self) -> tuple[CraftingQueue, ...] | None:
        """Every crafting queue known, as the last ``crin`` or crafting action left it; None until one arrived."""
        return self.client.state.get_crafting_queues()

    def get_crafting_queues(self, *, timeout: float = 5.0) -> tuple[CraftingQueue, ...]:
        """
        The crafting queues of the refinery and toolsmith in every castle, as the crafting dialog asks for them.

        The reply also reaches :attr:`crafting_queues`.

        Client: ``CastleCraftingData.getCraftingInfo`` (bundle line 111423), from
        ``CastleRefineryToolsmithDialog.showLoaded`` (bundle line 29337)
        """
        return self.request(GetCraftingInfoRequest(), CraftingInfoResponse, timeout=timeout).queues

    def start_crafting(self, queue: CraftingQueue, recipe_id: int, *, timeout: float = 5.0) -> CraftingQueue:
        """
        Start a recipe in a crafting queue, paying its costs.

        The recipe must be one the queue's building crafts, with a free unlocked slot; the queue after
        reaches :attr:`crafting_queues`.

        Args:
            queue: A queue of :attr:`crafting_queues` or :meth:`get_crafting_queues`
            recipe_id: The crafting recipe
            timeout: Timeout in seconds

        Raises:
            ValueError: The building is not working (``CraftingQueue.is_working``)
            CommandError: The server refused, ``NO_FREE_CONSTRUCTION_SLOT`` for a full queue

        Client: ``CastleCraftingData.startCrafting`` (bundle line 111424)
        """
        self._require_working(queue)
        request = StartCraftingRequest(
            kingdom=queue.kingdom, castle_id=queue.castle_id, object_id=queue.object_id, recipe_id=recipe_id
        )
        return self.request(request, StartCraftingResponse, timeout=timeout)

    def cancel_crafting(self, queue: CraftingQueue, slot: CraftingSlot, *, timeout: float = 5.0) -> CraftingQueue:
        """
        Cancel the craft in one slot of a crafting queue.

        Args:
            queue: A queue of :attr:`crafting_queues`
            slot: One of its ``production`` or ``queue`` slots
            timeout: Timeout in seconds

        Raises:
            ValueError: The building is not working (``CraftingQueue.is_working``)

        Client: ``CastleCraftingData.cancelCrafting`` (bundle line 111426)
        """
        self._require_working(queue)
        request = CancelCraftingRequest(
            kingdom=queue.kingdom,
            castle_id=queue.castle_id,
            object_id=queue.object_id,
            slot_index=slot.index,
            slot_type=slot.slot_type,
        )
        return self.request(request, CancelCraftingResponse, timeout=timeout)

    def move_crafting_slot(
        self, queue: CraftingQueue, slot: CraftingSlot, to_index: int, *, timeout: float = 5.0
    ) -> CraftingQueue:
        """
        Move a waiting craft to another waiting slot.

        Args:
            queue: A queue of :attr:`crafting_queues`
            slot: One of its ``queue`` slots
            to_index: Where the craft goes, from 0
            timeout: Timeout in seconds

        Raises:
            ValueError: The building is not working (``CraftingQueue.is_working``)

        Client: ``CastleCraftingData.moveQueueSlot`` (bundle line 111433)
        """
        self._require_working(queue)
        request = MoveCraftingSlotRequest(
            kingdom=queue.kingdom,
            castle_id=queue.castle_id,
            object_id=queue.object_id,
            from_index=slot.index,
            to_index=to_index,
        )
        return self.request(request, MoveCraftingSlotResponse, timeout=timeout)

    def skip_crafting(
        self,
        queue: CraftingQueue,
        slot: CraftingSlot,
        price: int,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> CraftingQueue:
        """
        Finish the craft in one slot for rubies.

        The client prices the skip as the recipe's ``skipCostC2`` times the share of its time left, rounded
        up, and sends that price; the game data here has no crafting recipes to price it.

        Args:
            queue: A queue of :attr:`crafting_queues`
            slot: One of its ``production`` or ``queue`` slots
            price: The rubies the skip costs
            spend_rubies: Allow spending them
            timeout: Timeout in seconds

        Raises:
            ValueError: The building is not working, or ``spend_rubies`` is False

        Client: ``CastleCraftingData.skipCrafting`` (bundle line 111428), ``CraftingSlotVO.getAdjustedSkipCostC2``
        (bundle line 17012)
        """
        self._require_working(queue)
        self._require_spend_rubies(spend_rubies, f"skipping the craft costs {price} rubies")
        request = SkipCraftingRequest(
            kingdom=queue.kingdom,
            castle_id=queue.castle_id,
            object_id=queue.object_id,
            slot_index=slot.index,
            slot_type=slot.slot_type,
            price=price,
        )
        return self.request(request, SkipCraftingResponse, timeout=timeout)

    def unlock_crafting_slot(self, queue: CraftingQueue, slot: CraftingSlot, *, timeout: float = 5.0) -> CraftingQueue:
        """
        Unlock a temporary slot of a crafting queue for coins.

        Every locked slot right before it is unlocked with it, as the client buys them
        (``CraftingQueue.unlock_indices``).

        Args:
            queue: A queue of :attr:`crafting_queues`
            slot: One of its locked temporary slots
            timeout: Timeout in seconds

        Raises:
            ValueError: The building is not working (``CraftingQueue.is_working``)

        Client: ``CastleCraftingData.buySlot`` (bundle line 111430), ``CraftingSlotVO.getUnlockCostC1``
        (bundle line 17009)
        """
        self._require_working(queue)
        request = UnlockCraftingSlotsRequest(
            kingdom=queue.kingdom,
            castle_id=queue.castle_id,
            object_id=queue.object_id,
            slot_indices=queue.unlock_indices(slot),
            slot_type=slot.slot_type,
        )
        return self.request(request, UnlockCraftingSlotsResponse, timeout=timeout)

    @staticmethod
    def _require_working(queue: CraftingQueue) -> None:
        if not queue.is_working:
            raise ValueError(f"crafting building {queue.object_id} is {queue.building_state.name}, not working")

    def get_construction_crafting(self, *, timeout: float = 5.0) -> ConstructionCraftingResponse:
        """
        The construction item being crafted and the time left; both None while nothing is crafted.

        Client: ``CastleConstructionItemsCraftingSublayer.onGCCArrived`` (bundle line 79577)
        """
        return self.request(GetConstructionCraftingRequest(), ConstructionCraftingResponse, timeout=timeout)

    def craft_construction_item(self, castle_id: int, recipe_id: int, *, timeout: float = 5.0) -> None:
        """
        Craft a construction item from a recipe, paying its costs; one craft runs at a time.

        Args:
            castle_id: One of your castles; the client crafts in the joined castle, else the kingdom's main castle
            recipe_id: A ``ConstructionItemRecipeDef.recipe_id`` of the game data
            timeout: Timeout in seconds

        Raises:
            UnknownCastleError: ``castle_id`` is not one of your castles
            CommandError: The server refused

        Client: ``CastleConstructionItemsCraftingSublayerProgress.onClick`` (bundle line 79926)
        """
        castle = self._require_own_castle(castle_id)
        request = CraftConstructionItemRequest(recipe_id=recipe_id, kingdom=castle.kingdom_id, castle_id=castle_id)
        self.request(request, CraftConstructionItemResponse, timeout=timeout)

    def skip_construction_crafting_time(
        self, castle_id: int, minute_skip: Currency | str, *, timeout: float = 5.0
    ) -> None:
        """
        Shorten the running construction item craft with a minute skip.

        Args:
            castle_id: The castle the craft runs in
            minute_skip: The minute skip to use, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``;
                its key (``"MS1"``) also works, for a skip newer than the generated enum
            timeout: Timeout in seconds

        Raises:
            ValueError: ``minute_skip`` is no minute skip, or the special currencies hold none of it
            UnknownCastleError: ``castle_id`` is not one of your castles

        Client: ``ConstructionItemCraftingMinuteSkipProperties.getMinuteSkipCommand`` (bundle line 79954)
        """
        castle = self._require_own_castle(castle_id)
        self._require_minute_skip(minute_skip)
        request = SkipConstructionCraftingRequest(
            kingdom=castle.kingdom_id, castle_id=castle_id, minute_skip=minute_skip
        )
        self.request(request, SkipConstructionCraftingResponse, timeout=timeout)

    def finish_construction_crafting(self, castle_id: int, *, spend_rubies: bool = False, timeout: float = 5.0) -> None:
        """
        Finish the running construction item craft for rubies.

        The price falls with the time left (``ConstructionConst.getFastCompleteCostC2``) and is not checked
        here, so the call always needs ``spend_rubies``.

        Raises:
            ValueError: ``spend_rubies`` is False
            UnknownCastleError: ``castle_id`` is not one of your castles

        Client: ``CastleConstructionItemsCraftingSublayerProgress.onClick`` (bundle line 79930),
        ``craftingTimer`` (bundle line 79907)
        """
        castle = self._require_own_castle(castle_id)
        self._require_spend_rubies(spend_rubies, "finishing the construction item craft costs rubies")
        request = SkipConstructionCraftingRequest(
            kingdom=castle.kingdom_id, castle_id=castle_id, finish_for_rubies=True, minute_skip=FULL_SKIP
        )
        self.request(request, SkipConstructionCraftingResponse, timeout=timeout)

    # =========================================================================
    # Fusion forge
    # =========================================================================

    @property
    def fusion_forges(self) -> dict[int, FusionForge] | None:
        """The fusion forges by id, as the last ``ffi`` left them; None until one arrived."""
        return self.client.state.get_fusion_forges()

    def get_fusion_forges(
        self, forge_ids: Sequence[int] = (DECORATION_FORGE_ID,), *, timeout: float = 5.0
    ) -> tuple[FusionForge, ...]:
        """
        Fusion forges' level and energy; the reply also reaches :attr:`fusion_forges`.

        Client: ``FusionForgeData.onGbdArrived`` (bundle line 142012), ``FusionForgeVO.requestDataFromServer``
        (bundle line 142199)
        """
        request = GetFusionForgesRequest(forge_ids=tuple(forge_ids))
        return self.request(request, FusionForgesResponse, timeout=timeout).forges

    def level_up_fusion_forge(self, forge_id: int = DECORATION_FORGE_ID, *, timeout: float = 5.0) -> int:
        """
        Level a fusion forge up for decoration dust, and return its new level.

        Client: ``DecorationForgeUpgradeDialog.onLevelUpButtonClicked`` (bundle line 78274),
        ``FusionForgeVO.getCostForForgeLevelUp`` (bundle line 142209)
        """
        request = LevelUpFusionForgeRequest(forge_id=forge_id)
        return self.request(request, LevelUpFusionForgeResponse, timeout=timeout).level

    def refill_fusion_forge(
        self, forge_id: int = DECORATION_FORGE_ID, *, spend_rubies: bool = False, timeout: float = 5.0
    ) -> int:
        """
        Refill a fusion forge's energy for rubies, and return the energy added.

        The price rises with each refill (``FusionForge.used_ruby_refills``) by the game data's fusion
        system, which the library does not load.

        Raises:
            ValueError: ``spend_rubies`` is False

        Client: ``DecorationForgeRechargeEnergyDialog`` (bundle line 35619),
        ``FusionForgeVO.getC2PriceForEnergyPremiumSkip`` (bundle line 142206)
        """
        self._require_spend_rubies(spend_rubies, "refilling the fusion forge's energy costs rubies")
        request = RefillFusionForgeRequest(forge_id=forge_id)
        return self.request(request, RefillFusionForgeResponse, timeout=timeout).energy

    def convert_catalysts(
        self,
        catalyst_id: CurrencyId | int,
        amount: int,
        direction: CatalystConversion,
        forge_id: int = DECORATION_FORGE_ID,
        *,
        timeout: float = 5.0,
    ) -> ConvertCatalystResponse:
        """
        Assemble fusion catalysts, or disassemble them into decoration dust.

        Client: ``ADecorationForgeCatalystConversionDialogInfoBox.onConfirmButtonClicked`` (bundle line 48367)
        """
        request = ConvertCatalystRequest(forge_id=forge_id, direction=direction, catalyst_id=catalyst_id, amount=amount)
        return self.request(request, ConvertCatalystResponse, timeout=timeout)

    def get_fusion_targets(self, *, timeout: float = 5.0) -> tuple[FusionTargetArea, ...]:
        """
        Your areas with the placed decorations a fusion can target.

        Client: ``DecoStorageData.requestGTD`` (bundle line 141447)
        """
        return self.request(GetFusionTargetsRequest(), FusionTargetsResponse, timeout=timeout).areas

    def fuse_decoration(
        self,
        source_wod_id: int,
        source_unique_id: int,
        target_area: FusionTargetArea,
        target: FusionDecoration,
        catalyst_id: CurrencyId | int,
        *,
        pay_with_rubies: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> FuseDecorationResponse:
        """
        Fuse a stored decoration into a placed one. The stored decoration is used up.

        The fusion spends the forge's energy and the catalyst, and the fusion currency, or rubies with
        ``pay_with_rubies`` (the premium fusion).

        Args:
            source_wod_id: The stored decoration's building type
            source_unique_id: The stored decoration's unique id
            target_area: The area of :meth:`get_fusion_targets` the target stands in
            target: One of ``target_area.decorations``
            catalyst_id: The catalyst used, a currency
            pay_with_rubies: The premium fusion
            spend_rubies: Allow the premium fusion's rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: ``target`` is not in ``target_area``, or rubies are spent without ``spend_rubies``

        Client: ``DecorationForgeMainDialog.onFuseButtonClicked`` (bundle line 35455)
        """
        if target not in target_area.decorations:
            raise ValueError(f"decoration {target.object_id} is not in area {target_area.castle_id}")
        self._require_spend_rubies(spend_rubies, "the premium fusion costs rubies" if pay_with_rubies else None)
        request = FuseDecorationRequest(
            catalyst_id=catalyst_id,
            pay_with_rubies=pay_with_rubies,
            source_unique_id=source_unique_id,
            source_wod_id=source_wod_id,
            target_object_id=target.object_id,
            target_kingdom=target_area.kingdom,
            target_castle_id=target_area.castle_id,
            target_unique_id=target.unique_id,
            target_wod_id=target.wod_id,
        )
        return self.request(request, FuseDecorationResponse, timeout=timeout)


__all__ = ["CastleService"]
