"""The joined area: the jaa reply, its mines (gsm) and resource carts (rci), slum level (csl),
builder discount (gab) and position (ghw); and the world map's size (nfo)."""

import logging
import time
from typing import Any

from empire_core.castle.models.actions import SelectCastleResponse
from empire_core.castle.models.castles import PlayerCastle
from empire_core.castle.models.collect import MineStatus, MineStatusList, ResourceCart, ResourceCartInfo
from empire_core.castle.models.updates import (
    AreaBooster,
    CastleBuildingsPushed,
    JoinedAreaMoved,
    SlumLevel,
)
from empire_core.enums import Kingdom, ResourceCartType
from empire_core.map.models.world import MapSize, ServerInfoResponse
from empire_core.protocol.base import enum_or_none, read_or_none
from empire_core.state.base import StateBase, loaded
from empire_core.state.models import JoinedArea

logger = logging.getLogger(__name__)

# CastleResourceCartsData.RESOURCE_TYPE_COUNT (bundle line 28813)
_CART_COUNT = 3


class AreaState(StateBase):
    def _handle_jaa(self, data: Any) -> None:
        """Apply a join's reply: the joined area, and its mines and resource carts when it sends them.

        A reply without ``gsm`` or ``rci`` leaves the mines or carts as they were, as the client does. It
        drops the resource citizen's goods (``CastleResourcePoolData.reset``).

        Client: ``JAACommand.executeCommand`` (bundle line 130190), ``AreaFactory.parseAreaInfo``
        (bundle line 130226), ``AreaDataUpdater.parseJAA`` (bundle line 131496)
        """
        if not isinstance(data, dict):
            return
        reply = read_or_none(SelectCastleResponse.model_validate, data, warn=logger, what="a jaa reply")
        if reply is None:
            return
        self.area_revision += 1
        self._placed_construction_item_sequence = self._packet_sequence
        self.placed_construction_items = reply.buildings.construction_items if reply.buildings is not None else None
        self.resource_pool = None
        kingdom = enum_or_none(Kingdom, reply.kingdom_id)
        castle_id = x = y = None
        area = data.get("gca")
        row = area.get("A") if isinstance(area, dict) else None
        try:
            parsed = PlayerCastle.from_list(row, Kingdom.GREEN if kingdom is None else kingdom)
            castle_id, x, y = parsed.location_id, parsed.x, parsed.y
            if kingdom is not None:
                kingdom = parsed.kingdom
        except (ValueError, TypeError):
            pass
        now = time.time()
        self.joined_area = JoinedArea(
            kingdom_id=kingdom,
            castle_id=castle_id,
            x=x,
            y=y,
            slum_level=reply.slum_level.level if reply.slum_level else -1,
            builder_discount=reply.area_booster.builder_discount if reply.area_booster else 0,
        )
        if reply.slum_level:
            self._packet_times["csl"] = now
        if reply.area_booster:
            self._packet_times["gab"] = now
        if reply.mines is not None:
            self._apply_mines(reply.mines)
        if reply.resource_carts is not None:
            self._apply_resource_carts(reply.resource_carts)

    def _handle_gsm(self, data: Any) -> None:
        """Apply a ``gsm`` push: the joined castle's mines.

        Client: ``GSMCommand.executeCommand`` (bundle line 125752)
        """
        if isinstance(data, dict):
            mines = read_or_none(MineStatusList.model_validate, data, warn=logger, what="a gsm push")
            if mines is not None:
                self._apply_mines(mines)

    def _handle_cmr(self, data: Any) -> None:
        """Apply a mine collect's reply: the mines (``gsm``), then coins and rubies (``gcu``).

        Client: ``CMRCommand.executeCommand`` (bundle line 125737)
        """
        if not isinstance(data, dict) or not isinstance(data.get("gsm"), dict):
            return
        self._handle_gsm(data["gsm"])
        if isinstance(gcu := data.get("gcu"), dict):
            self._handle_gbd({"gcu": gcu})

    def _apply_mines(self, mines: MineStatusList) -> None:
        """Replace every mine, keyed by object id.

        Client: ``CastleMineData.parse_GSM`` (bundle line 50363)
        """
        self.mines = {mine.object_id: mine for mine in mines.mines}
        self._packet_times["gsm"] = time.time()

    def _handle_rci(self, data: Any) -> None:
        """Apply an ``rci`` push: the joined castle's resource carts.

        Client: ``RCICommand.executeCommand`` (bundle line 123196)
        """
        if isinstance(data, dict):
            carts = read_or_none(ResourceCartInfo.model_validate, data, warn=logger, what="an rci push")
            if carts is not None:
                self._apply_resource_carts(carts)

    def _handle_rcc(self, data: Any) -> None:
        """Apply a resource cart collect's reply: its carts (``rci``).

        Client: ``CastleResourceCartsData.parse_RCC`` (bundle line 28796)
        """
        if isinstance(data, dict) and isinstance(data.get("rci"), dict):
            self._handle_rci(data["rci"])

    def _apply_resource_carts(self, carts: ResourceCartInfo) -> None:
        """Replace the carts with the first three, wood, stone and food.

        Client: ``CastleResourceCartsData.parse_RCI`` (bundle line 28798)
        """
        self.resource_carts = list(carts.carts[:_CART_COUNT])
        self._packet_times["rci"] = time.time()

    def _handle_gaa(self, data: Any) -> None:
        """A map read: forget the joined castle's mines, as the client does on the world map.

        The client asks for map areas only on the world map (``CastleWorldmapData.updateAreaRange``,
        bundle line 19006), and switching there drops the mines (``SwitchToWorldmapCommand.execute``,
        bundle line 100945). It keeps its active area, which ``csl`` and ``gab`` still update, and
        the resource carts, so state keeps ``joined_area`` and the carts too.
        """
        self.mines = {}
        self.area_revision += 1
        self._placed_construction_item_sequence = self._packet_sequence
        self.placed_construction_items = None

    def _handle_csl(self, data: Any) -> None:
        """Apply a ``csl`` push to the joined area: its slum level.

        Client: ``AreaDataUpdater.parseCSL`` (bundle line 131498)
        """
        if isinstance(data, dict) and self.joined_area is not None:
            slum = read_or_none(SlumLevel.model_validate, data, warn=logger, what="a csl push")
            if slum is not None:
                self.joined_area = self.joined_area.model_copy(update={"slum_level": slum.level})

    def _handle_gab(self, data: Any) -> None:
        """Apply a ``gab`` push to the joined area: its builder discount.

        Client: ``AreaDataCommonInfo.parseGAB`` (bundle line 130992)
        """
        if isinstance(data, dict) and self.joined_area is not None:
            booster = read_or_none(AreaBooster.model_validate, data, warn=logger, what="a gab push")
            if booster is not None:
                self.joined_area = self.joined_area.model_copy(update={"builder_discount": booster.builder_discount})

    def _handle_ghw(self, data: Any) -> None:
        """Apply a ``ghw`` push: the joined area's new position.

        Client: ``GHWCommand.executeCommand`` (bundle line 129574) moves the active area only,
        ``AreaDataModel.changePosOfOwnArea`` (bundle line 131929)
        """
        if isinstance(data, dict) and self.joined_area is not None:
            moved = read_or_none(JoinedAreaMoved.model_validate, data, warn=logger, what="a ghw push")
            if moved is not None:
                self.joined_area = self.joined_area.model_copy(update={"x": moved.x, "y": moved.y})

    def _handle_gca(self, data: Any) -> None:
        """Apply a ``gca`` push to the joined castle: the construction items on its buildings.

        Client: ``GCACommand.executeCommand`` (bundle line 122991) hands the block to the active area,
        ``AreaDataUpdater.parseGCA`` (bundle line 131546)
        """
        if not isinstance(data, dict) or self.joined_area is None:
            return
        pushed = read_or_none(CastleBuildingsPushed.model_validate, data, warn=logger, what="a gca push")
        if pushed is None or pushed.buildings is None:
            return
        self._placed_construction_item_sequence = self._packet_sequence
        self.placed_construction_items = pushed.buildings.construction_items

    def _handle_nfo(self, data: Any) -> None:
        """Keep the server info pushed when the connection opens: the world map's size in sectors.

        Client: ``NFOCastleCommand.executeCommand`` (bundle line 120801)
        """
        if isinstance(data, dict):
            info = read_or_none(ServerInfoResponse.model_validate, data, warn=logger, what="an nfo push")
            if info is not None:
                self.server_info = info

    def get_map_size(self, kingdom: Kingdom) -> MapSize:
        """``kingdom``'s map in tiles, from the server info the connection opened with.

        Raises:
            StateNotLoadedError: No connection has brought it
        """
        with self._lock:
            return loaded(self.server_info, "Server info").map_size(kingdom)

    def get_joined_area(self) -> JoinedArea | None:
        """The area joined, with its slum level and builder discount; ``None`` before any join.

        ``client.castle.join`` joins one. Login joins none. A map read (``gaa``) moves the session
        off the castle but keeps this, as the client keeps its active area; join again before
        anything castle-scoped.
        """
        with self._lock:
            return self.joined_area

    def get_mines(self) -> dict[int, MineStatus]:
        """The joined castle's mines by object id, as the last ``gsm`` sent them.

        ``next_collect_seconds`` counted from :meth:`get_last_packet_time` ``("gsm")``:
        the client counts it down from then. Empty before any ``gsm`` and after a map read
        (``gaa``); refreshed by ``client.castle.join`` and ``client.castle.collect_mine``.
        """
        with self._lock:
            return dict(self.mines)

    def get_resource_carts(self) -> list[ResourceCart]:
        """The joined castle's resource carts, wood, stone and food, as the last ``rci`` sent them.

        ``remaining_seconds`` counts from :meth:`get_last_packet_time` ``("rci")``. Empty
        before any ``rci``; a map read keeps them, as the client does; refreshed by ``client.castle.join`` and
        ``client.castle.collect_resource_cart``.
        """
        with self._lock:
            return list(self.resource_carts)

    def get_resource_cart(self, cart_type: ResourceCartType) -> ResourceCart | None:
        """The cart of one resource in the last ``rci``; ``None`` before any.

        The client looks a cart up by its place in ``RC``; this matches each
        cart's own ``RT``, so an entry that could not be read moves no other cart.

        Client: ``CastleResourceCartsData.getResourceCartData`` (bundle line 28802)
        """
        with self._lock:
            return next((cart for cart in self.resource_carts if cart.cart_type is cart_type), None)
