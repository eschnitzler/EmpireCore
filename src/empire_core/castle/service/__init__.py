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

from typing import TYPE_CHECKING

from empire_core.castle.models.updates import (
    BuildingFinished,
    BuildingXP,
    CastleBuildingsPushed,
    DamagedBuildings,
    JoinedAreaMoved,
)
from empire_core.castle.service.buildings import BuildingsMixin
from empire_core.castle.service.castles import CastlesMixin
from empire_core.castle.service.construction_items import ConstructionItemsMixin
from empire_core.castle.service.crafting import CraftingMixin
from empire_core.castle.service.decorations import DecorationsMixin
from empire_core.castle.service.economy import EconomyMixin
from empire_core.castle.service.mercenaries import MercenaryCampMixin
from empire_core.castle.service.modification import CastleModificationMixin
from empire_core.castle.service.research import ResearchMixin
from empire_core.protocol.base import BaseResponse
from empire_core.services.base import BaseService
from empire_core.utils.callbacks import Event

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient


class CastleService(
    ConstructionItemsMixin,
    CastleModificationMixin,
    BuildingsMixin,
    CastlesMixin,
    DecorationsMixin,
    EconomyMixin,
    ResearchMixin,
    MercenaryCampMixin,
    CraftingMixin,
    BaseService,
):
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


__all__ = ["CastleService"]
