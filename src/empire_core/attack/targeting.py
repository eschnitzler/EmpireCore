"""
Reading an attack's target from the server: its map tile, the attack
pre-calculation and its owner's record.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from empire_core.army.spy_army import SpyArmy
from empire_core.attack.models.info import AttackInfoResponse, GetAttackInfoRequest, GetAttackInfoResponse
from empire_core.attack.models.target_info import (
    GetBossDungeonAttackInfoRequest,
    GetBossDungeonAttackInfoResponse,
    GetCapitalConquerInfoRequest,
    GetCapitalConquerInfoResponse,
    GetDungeonAttackInfoRequest,
    GetDungeonAttackInfoResponse,
    GetIslandAttackInfoRequest,
    GetIslandAttackInfoResponse,
    GetLandmarkAttackInfoRequest,
    GetLandmarkAttackInfoResponse,
    GetMetropolConquerInfoRequest,
    GetMetropolConquerInfoResponse,
    GetOutpostConquerInfoRequest,
    GetOutpostConquerInfoResponse,
    GetVillageAttackInfoRequest,
    GetVillageAttackInfoResponse,
)
from empire_core.combat import Bonus, TargetRead, invasion_camp_level, owner_id_from_row
from empire_core.commanders.models.roster import Commander
from empire_core.enums import Kingdom, MapItemType
from empire_core.exceptions import CommandError
from empire_core.map.models.areas import GetMapAreaResponse, MapObject
from empire_core.map.models.items import MapAreaItem
from empire_core.protocol.base import BaseRequest
from empire_core.protocol.errors import GGEError

if TYPE_CHECKING:
    from empire_core.attack.service import AttackService

logger = logging.getLogger(__name__)


_Precalculation = tuple[type[BaseRequest], type[AttackInfoResponse]]

_ACI: _Precalculation = (GetAttackInfoRequest, GetAttackInfoResponse)
_ADI: _Precalculation = (GetDungeonAttackInfoRequest, GetDungeonAttackInfoResponse)
_ALI: _Precalculation = (GetLandmarkAttackInfoRequest, GetLandmarkAttackInfoResponse)

_ATTACK_PRECALCULATION: dict[int, _Precalculation] = {
    # ACTION_TYPE_ATTACK: CastleMapobjectVO, and KingdomCastleMapobjectVO extends it
    MapItemType.CASTLE: _ACI,
    MapItemType.KINGDOM_CASTLE: _ACI,
    MapItemType.FACTION_VILLAGE: _ACI,
    MapItemType.FACTION_TOWER: _ACI,
    MapItemType.FACTION_CAPITAL: _ACI,
    # ACTION_TYPE_OUTPOSTATTACK: OutpostMapobjectVO, extended by CapitalMapobjectVO and MetropolMapobjectVO
    MapItemType.OUTPOST: _ACI,
    MapItemType.CAPITAL: _ACI,
    MapItemType.METROPOL: _ACI,
    # ACTION_TYPE_DUNGEONATTACK
    MapItemType.DUNGEON: _ADI,
    MapItemType.EVENT_DUNGEON: _ADI,
    MapItemType.ISLE_DUNGEON: _ADI,
    MapItemType.ALIEN_CAMP: _ADI,
    MapItemType.RED_ALIEN_CAMP: _ADI,
    MapItemType.NOMAD_CAMP: _ADI,
    MapItemType.SAMURAI_CAMP: _ADI,
    MapItemType.FACTION_INVASION_CAMP: _ADI,
    MapItemType.ALLIANCE_NOMAD_CAMP: _ADI,
    MapItemType.DAIMYO_CASTLE: _ADI,
    MapItemType.ALLIANCE_BATTLE_GROUND_RESOURCE_TOWER: _ADI,
    MapItemType.WOLF_KING: _ADI,
    MapItemType.ARE_PORTAL: _ADI,
    # ACTION_TYPE_BOSSDUNGEONATTACK
    MapItemType.BOSS_DUNGEON: (GetBossDungeonAttackInfoRequest, GetBossDungeonAttackInfoResponse),
    # ACTION_TYPE_LANDMARK_ATTACK
    MapItemType.KINGS_TOWER: _ALI,
    MapItemType.MONUMENT: _ALI,
    MapItemType.LABORATORY: _ALI,
    # ACTION_TYPE_VILLAGE_ATTACK
    MapItemType.VILLAGE: (GetVillageAttackInfoRequest, GetVillageAttackInfoResponse),
    # ACTION_TYPE_ISLAND_ATTACK
    MapItemType.ISLE_RESOURCE: (GetIslandAttackInfoRequest, GetIslandAttackInfoResponse),
}

_CONQUER_PRECALCULATION: dict[int, _Precalculation] = {
    MapItemType.OUTPOST: (GetOutpostConquerInfoRequest, GetOutpostConquerInfoResponse),
    MapItemType.CAPITAL: (GetCapitalConquerInfoRequest, GetCapitalConquerInfoResponse),
    MapItemType.METROPOL: (GetMetropolConquerInfoRequest, GetMetropolConquerInfoResponse),
}


def _precalculation(area_type: int, conquer: bool) -> _Precalculation:
    """
    The request and reply the client uses to pre-calculate an attack on an area type.

    An attack follows the ``attackType`` of the map object the client builds
    for the area type: ``ACTION_TYPE_ATTACK`` and ``ACTION_TYPE_OUTPOSTATTACK``
    ask ``aci``, ``ACTION_TYPE_DUNGEONATTACK`` ``adi``, and so on. A conquest
    asks ``cci`` for a capital, ``cti`` for a metropolis and ``coi`` for an
    outpost.

    Not modelled, so refused before sending: the alliance battleground tower
    (``gti``), the collector attack (``acc``), the faction camp conquest, map
    objects that define no ``attackType`` of their own and only inherit
    ``InteractiveMapobjectVO``'s, and area types the client builds no map
    object for.

    Client: ``CastleStartAttackDialog.onClickYes`` (bundle line 14802) and its
    senders ``attackCastle`` (14824), ``attackDungeon`` (14834),
    ``attackBossDungeon`` (14837), ``conquerOutpost`` (14839),
    ``conquerCapital`` (14842), ``conquerMetropol`` (14843), ``attackVillage``
    (14844), ``attackIsland`` (14845), ``attackLandmark`` (14846);
    ``WorldmapObjectFactory.__initialize_static_members`` (bundle line 5356).
    The ``attackType`` getters: ``AInvasionEventMapObjectVO`` (18505),
    ``OutpostMapobjectVO`` (18850), ``CastleMapobjectVO`` (18941),
    ``KingstowerMapobjectVO`` (19088), ``MonumentMapobjectVO`` (21668),
    ``DungeonMapobjectVO`` (22091), ``VillageMapobjectVO`` (22684),
    ``FactionCapitalMapobjectVO`` (22789), ``FactionTowerMapobjectVO`` (22837),
    ``LaboratoryMapobjectVO`` (25913), ``FactionVillageMapobjectVO`` (28515),
    ``WolfkingCastleMapObjectVO`` (34420), ``BossdungeonMapobjectVO`` (34466),
    ``EventdungeonMapobjectVO`` (34516), ``ResourceIsleMapobjectVO`` (34652),
    ``AAlienInvasionMapobjectVO`` (41553), ``AllianceRaidEventPortalMapobjectVO``
    (41611), ``DungeonIsleMapobjectVO`` (76310). Inherited ones:
    ``CapitalMapobjectVO`` (18760) and ``MetropolMapobjectVO`` (21637) extend
    ``OutpostMapobjectVO``; ``TreasureDungeonMapObjectVO`` (22033) extends
    ``DungeonMapobjectVO``; ``KingdomCastleMapobjectVO`` (32706) extends
    ``CastleMapobjectVO``; ``AlienInvasionMapobjectVO`` (65057) and
    ``RedAlienInvasionMapobjectVO`` (76481) extend ``AAlienInvasionMapobjectVO``;
    ``DaimyoCastleMapObjectVO`` (19689), ``FactionInvasionCampMapObjectVO``
    (76367), ``NomadCampMapObjectVO`` (76420), ``SamuraiCampMapObjectVO``
    (76536) and ``AAllianceInvasionCampMapObjectVO`` (47418) extend
    ``AInvasionEventMapObjectVO``, and ``NomadKhanCampMapObjectVO`` (76447) and
    ``ABGResourceTowerMapobjectVO`` (47447) extend
    ``AAllianceInvasionCampMapObjectVO``. Area type values from ``WorldConst``
    (dll line 237).
    """
    table = _CONQUER_PRECALCULATION if conquer else _ATTACK_PRECALCULATION
    found = table.get(area_type)
    if found is None:
        kind = "conquest" if conquer else "attack"
        raise ValueError(f"No {kind} pre-calculation is modelled for area type {area_type}")
    return found


def _row_item(row: list | None) -> MapAreaItem | None:
    """A target's map row as the client reads it, or None when there is none it can read."""
    if not row:
        return None
    try:
        return MapAreaItem.from_list(row)
    except ValueError:
        return None


@dataclass
class _Target:
    """
    What an attack needs to know about where it is going.

    Every field is either supplied by the caller or read from the server, and
    :func:`_read_target` only ever fills the gaps.
    """

    x: int
    y: int
    kingdom_id: Kingdom | None = None
    source_x: int | None = None
    source_y: int | None = None
    row: list | None = None
    area_type: int | None = None
    level: int | None = None
    owner_legend_level: int | None = None
    is_player: bool = False
    camp_victories: int | None = None
    camp_kingdom_id: Kingdom = Kingdom.GREEN
    spy_army: SpyArmy | None = None
    castellan: Commander | None = None
    defender_legend_skill_ids: Sequence[int] | None = None
    area_bonuses: list[Bonus] | None = None
    conquer: bool = False
    inventory: dict[int, int] | None = None
    unread: dict[TargetRead, CommandError] = field(default_factory=dict)

    def wants_precalculation(self) -> bool:
        """Whether the pre-calculation would answer anything still missing."""
        return any(value is None for value in (self.row, self.spy_army, self.castellan, self.area_bonuses))


def _merged(*inventories: dict[int, int]) -> dict[int, int]:
    """Inventories added together, as ``AUnitInventory.addAll`` adds each unit's amount."""
    total: dict[int, int] = {}
    for inventory in inventories:
        for wod_id, amount in inventory.items():
            total[wod_id] = total.get(wod_id, 0) + amount
    return total


def _read_target(service: AttackService, target: "_Target", *, castle_id: int, timeout: float) -> None:
    """
    Fill in whatever the caller did not supply about a target.

    Each request is made only when something it would answer is still
    missing, so a fully specified target costs nothing.

    Raises:
        UnknownCastleError: The kingdom or source position is missing and
            ``castle_id`` is not in your castle list
    """
    if target.kingdom_id is None or target.source_x is None or target.source_y is None:
        source = service._require_own_castle(castle_id)
        if target.kingdom_id is None:
            target.kingdom_id = source.kingdom_id
        if target.source_x is None:
            target.source_x = source.x
        if target.source_y is None:
            target.source_y = source.y

    if target.area_type is None and target.row:
        row_item = _row_item(target.row)
        target.area_type = row_item.item_type if row_item is not None else None

    area = None
    scanned = False
    if target.wants_precalculation():
        if target.area_type is None:
            # Each kind of target answers its own pre-calculation, so the
            # tile is read first to learn which.
            area = _scan_tile(service, target, timeout=timeout)
            scanned = True
            _take_scanned_row(target, area)
        _read_precalculation(service, target, timeout=timeout)

    if target.row is None and not scanned:
        # The server refuses the pre-calculation for a target this player
        # may not hit, but the map still describes the tile, and that is
        # all the level and the fortification need.
        area = _scan_tile(service, target, timeout=timeout)
        _take_scanned_row(target, area)

    item = _row_item(target.row)
    if item is None:
        return
    if target.area_type is None:
        target.area_type = item.item_type
    if item.item_type == MapItemType.DUNGEON:
        # A camp's level follows from how often it has been beaten, and the
        # row carries the count.
        if target.camp_victories is None:
            target.camp_victories = item.victory_count
        if target.camp_kingdom_id == Kingdom.GREEN:
            target.camp_kingdom_id = item.kingdom
    elif item.is_invasion_camp:
        if target.level is None and service.client.game_data is not None:
            player = service.client.state.get_local_player()
            target.level = invasion_camp_level(service.client.game_data, item, player.level if player else 0)
    elif item.dungeon_level is not None and item.dungeon_level > 0:
        # A camp whose row gives its level (an alien camp, the wolf king, an event
        # or boss dungeon, a faction object) has an NPC owner and no record to read;
        # an alien camp at level 0 or below is not on the map (bundle line 41545)
        if target.level is None:
            target.level = item.dungeon_level
    elif target.level is None or target.owner_legend_level is None:
        # A player's level is not in the row; it sits in the owner records a
        # scan returns beside it.
        if area is None:
            area = _scan_tile(service, target, timeout=timeout)
        owner = _owner_record(area, item.owner_id, target)
        if target.level is None:
            target.level = owner.level if owner is not None else None
            target.is_player = target.is_player or target.level is not None
        if target.owner_legend_level is None and owner is not None:
            target.owner_legend_level = owner.legendary_level


def _take_scanned_row(target: "_Target", area: GetMapAreaResponse | None) -> None:
    """Take the target's row, and so its area type, from a scan of its tile."""
    if area is None or target.row is not None:
        return
    target.row = next(
        (item.raw_data for item in area.items if (item.x, item.y) == (target.x, target.y)),
        None,
    )
    row_item = _row_item(target.row)
    if row_item is not None and target.area_type is None:
        target.area_type = row_item.item_type


def _scan_tile(service: AttackService, target: "_Target", *, timeout: float) -> GetMapAreaResponse | None:
    """The map's own record of the target's tile; None, noted in ``target.unread``, when the server refuses it."""
    try:
        return service.client.map.scan_map_area(
            target.x,
            target.y,
            target.x,
            target.y,
            kingdom=Kingdom.GREEN if target.kingdom_id is None else target.kingdom_id,
            timeout=timeout,
        )
    except CommandError as e:
        logger.warning(f"Could not scan the map at {target.x}:{target.y}, filling without it: {e}")
        target.unread[TargetRead.TILE] = e
        return None


def _read_precalculation(service: AttackService, target: "_Target", *, timeout: float) -> None:
    """Take the target's row, defenders, castellan, legend skills and area effects from its pre-calculation.

    The defender's legend skills come with the spy report only, as in
    ``CastleSpyArmyInfoVO.parseArmyInfo``, which sets them when ``S`` is not empty.

    The server refuses the pre-calculation of a target it will not let this player
    hit; ``INVALID_AREA`` is logged at info level, any other refusal as a warning.

    Raises:
        ValueError: ``target.area_type`` is not an area type, or one with no pre-calculation modelled
    """
    area_type = MapItemType(target.area_type) if target.area_type is not None else MapItemType.CASTLE
    try:
        info = service.get_attack_info(
            target_x=target.x,
            target_y=target.y,
            source_x=target.source_x or 0,
            source_y=target.source_y or 0,
            kingdom_id=Kingdom.GREEN if target.kingdom_id is None else target.kingdom_id,
            area_type=area_type,
            conquer=target.conquer,
            timeout=timeout,
        )
    except CommandError as e:
        level = logging.INFO if e.error is GGEError.INVALID_AREA else logging.WARNING
        logger.log(
            level, f"Could not read the attack pre-calculation for {target.x}:{target.y}, filling without it: {e}"
        )
        target.unread[TargetRead.PRECALCULATION] = e
        return
    if target.row is None:
        target.row = info.target_row() or None
    if "unit_inventory" in getattr(info, "model_fields_set", ()):
        # CastleAttackInfoVO.fillFromParamObject fills gui.I and gui.SHI, and the dialog's
        # AttackDialogUnitPicker adds the stronghold units into the same inventory it fills from
        target.inventory = _merged(info.inventory(), info.stronghold_inventory())
    if target.spy_army is None:
        target.spy_army = info.spy_army()
    if target.castellan is None:
        target.castellan = info.defending_castellan()
    if target.level is None or target.owner_legend_level is None:
        # The owner records (gaa.OI) carry the owner's level (L) and legend
        # level (LL), as WorldMapOwnerInfoVO reads them, so no scan is needed
        owner_id = owner_id_from_row(target.row)
        record = next((r for r in info.owner_records() if owner_id is not None and r.owner_id == owner_id), None)
        if record is not None:
            if target.level is None and record.level > 0:
                target.level = record.level
                target.is_player = True
            if target.owner_legend_level is None and "legendary_level" in record.model_fields_set:
                target.owner_legend_level = record.legendary_level
    if target.defender_legend_skill_ids is None and info.spy_army() is not None:
        target.defender_legend_skill_ids = info.defender_legend_skill_ids
    if target.area_bonuses is None:
        target.area_bonuses = info.attacker_bonuses()


def _owner_record(area: GetMapAreaResponse | None, owner_id: int | None, target: "_Target") -> MapObject | None:
    """The owner record of whoever owns a tile, from the scan of that tile."""
    if area is None:
        return None
    # The row's owner id is the owner record's OID; failing that, settle
    # for the only record a one-tile scan returned.
    owner = next(
        (o for o in area.owners if owner_id == o.owner_id and o.level),
        None,
    )
    if owner is None and len(area.owners) == 1 and area.owners[0].level:
        owner = area.owners[0]
    if owner is None:
        logger.debug(f"No owner level came back for {target.x}:{target.y}")
        return None
    return owner
