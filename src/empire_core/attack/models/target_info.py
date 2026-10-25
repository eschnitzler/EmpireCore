"""Attack pre-calculation for other targets, and conquest pre-calculation.

Commands:
- adi, abi, ali, avi, aii, gti: Attack pre-calculation per kind of target
- acc: Collector attack pre-calculation
- tai: Treasure map node attack pre-calculation
- coi, cci, cti, cfi: Conquest pre-calculation
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import Field, ValidatorFunctionWrapHandler, field_validator, model_validator

from empire_core.army.models.units import UnitInventory
from empire_core.army.spy_army import SpyArmyBlock
from empire_core.commanders.models.roster import Commander
from empire_core.enums import Kingdom
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BaseRequest, BaseResponse, int_entries, read_or_none

from .info import AttackInfoResponse, GetAttackInfoResponse

if TYPE_CHECKING:
    from empire_core.gamedata import LegendSkill

logger = logging.getLogger(__name__)

# =============================================================================
# ADI / ABI / ALI / AVI / AII - Attack pre-calculation for other targets
# =============================================================================


class GetDungeonAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation against an NPC camp.

    Every target whose map object attacks as a dungeon answers this command:
    robber baron camps, event and isle dungeons, invasion and alien camps, the
    wolf king and the alliance raid portal. The server refuses ``aci`` for a
    camp with INVALID_AREA.

    Command: adi
    Payload: {"SX": source_x, "SY": source_y, "TX": target_x, "TY": target_y, "KID": kingdom_id}

    Client: ``C2SGetAttackDungeonInfosVO`` (bundle line 72024), whose key order the fields follow;
    ``CastleStartAttackDialog.attackDungeon`` (bundle line 14834).
    """

    command = "adi"

    source_x: int = Field(validation_alias="SX", description="Attacking castle's map x")
    source_y: int = Field(validation_alias="SY", description="Attacking castle's map y")
    target_x: int = Field(validation_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", description="Target map y")
    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target")


class GetDungeonAttackInfoResponse(GetAttackInfoResponse):
    """
    The attack pre-calculation for an NPC camp.

    Command: adi

    Client: ``ADICommand.executeCommand`` (bundle line 122187), ``CastleAttackData.parse_ADI`` (133830).
    """

    command = "adi"


class GetBossDungeonAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation against a boss dungeon.

    Command: abi
    Payload: {"KID": kingdom_id, "SX": source_x, "SY": source_y, "TX": target_x, "TY": target_y}

    Client: ``C2SAttackInfoBossDungeonVO`` (bundle line 71970),
    ``CastleStartAttackDialog.attackBossDungeon`` (bundle line 14837).
    """

    command = "abi"

    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target")
    source_x: int = Field(validation_alias="SX", description="Attacking castle's map x")
    source_y: int = Field(validation_alias="SY", description="Attacking castle's map y")
    target_x: int = Field(validation_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", description="Target map y")


class GetBossDungeonAttackInfoResponse(GetAttackInfoResponse):
    """
    The attack pre-calculation for a boss dungeon.

    Command: abi

    Client: ``ABICommand.executeCommand`` (bundle line 122128), ``CastleAttackData.parse_ABI`` (133827).
    """

    command = "abi"


class GetLandmarkAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation against a kings tower, monument or laboratory.

    Command: ali
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y, "SX": source_x, "SY": source_y}

    Client: ``C2SAttackInfoLandmarkVO`` (bundle line 71988),
    ``CastleStartAttackDialog.attackLandmark`` (bundle line 14846).
    """

    command = "ali"

    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target")
    target_x: int = Field(validation_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", description="Target map y")
    source_x: int = Field(validation_alias="SX", description="Attacking castle's map x")
    source_y: int = Field(validation_alias="SY", description="Attacking castle's map y")


class GetLandmarkAttackInfoResponse(GetAttackInfoResponse):
    """
    The attack pre-calculation for a landmark.

    Command: ali

    Client: ``ALICommand.executeCommand`` (bundle line 122227), ``CastleAttackData.parse_ALI`` (133836).
    """

    command = "ali"


class GetVillageAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation against a village.

    The client sends no source castle for it.

    Command: avi
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y}

    Client: ``C2SAttackInfoVillageVO`` (bundle line 71997),
    ``CastleStartAttackDialog.attackVillage`` (bundle line 14844).
    """

    command = "avi"

    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target")
    target_x: int = Field(validation_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", description="Target map y")


class GetVillageAttackInfoResponse(GetAttackInfoResponse):
    """
    The attack pre-calculation for a village.

    Command: avi

    Client: ``AVICommand.executeCommand`` (bundle line 122244), ``CastleAttackData.parse_AVI`` (133832).
    """

    command = "avi"


class GetIslandAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation against an isle resource.

    An isle dungeon attacks as a dungeon and answers ``adi`` instead.

    Command: aii
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y}

    Client: ``C2SAttackInfoIslandVO`` (bundle line 71979),
    ``CastleStartAttackDialog.attackIsland`` (bundle line 14845).
    """

    command = "aii"

    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target")
    target_x: int = Field(validation_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", description="Target map y")


class GetIslandAttackInfoResponse(GetAttackInfoResponse):
    """
    The attack pre-calculation for an isle resource.

    Command: aii

    Client: ``AIICommand.executeCommand`` (bundle line 122204), ``CastleAttackData.parse_AII`` (133834).
    """

    command = "aii"


class GetAllianceTowerAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation against a Beyond the Horizon tower.

    ``C2S_GET_TREASURE_INFO`` shares the ``gti`` id; the client builds no request for it.

    Command: gti
    Payload: {"TX": target_x, "TY": target_y, "SX": source_x, "SY": source_y, "KID": kingdom_id}

    Client: ``C2SGetAttackABGTowerInfosVO`` (bundle line 72033),
    ``CastleStartAttackDialog.attackABGTower`` (bundle line 14834),
    ``ABGAllianceTowerMapobjectVO.attackType`` (bundle line 32324).
    """

    command = "gti"

    target_x: int = Field(validation_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", description="Target map y")
    source_x: int = Field(validation_alias="SX", description="Attacking castle's map x")
    source_y: int = Field(validation_alias="SY", description="Attacking castle's map y")
    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target")


class GetAllianceTowerAttackInfoResponse(GetAttackInfoResponse):
    """
    The attack pre-calculation for a Beyond the Horizon tower, read as a castle's is.

    The server refuses it with PLAYER_HAS_NOOB_PROTECTION, TARGET_HAS_PEACE or
    SPECIALCAMP_PROTECTED besides the usual errors.

    Command: gti

    Client: ``GTICommand.executeCommand`` (bundle line 122350), ``CastleAttackData.parse_GTI`` (133873).
    """

    command = "gti"


class GetCollectorAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation of a collector attack, the attack the collector events add to a castle.

    Command: acc
    Payload: {"TX": target_x, "TY": target_y, "SX": source_x, "SY": source_y, "KID": kingdom_id}

    Client: ``C2SGetCollectorAttackInfoVO`` (bundle line 72060),
    ``CastleStartAttackDialog.attackCollector`` (bundle line 14836).
    """

    command = "acc"

    target_x: int = Field(validation_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", description="Target map y")
    source_x: int = Field(validation_alias="SX", description="Attacking castle's map x")
    source_y: int = Field(validation_alias="SY", description="Attacking castle's map y")
    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target")


class GetCollectorAttackInfoResponse(GetAttackInfoResponse):
    """
    The pre-calculation of a collector attack, with the collector currency the target holds.

    Command: acc

    Client: ``ACCCommand.executeCommand`` (bundle line 122185), ``CastleAttackData.parse_ACC`` (133893).
    """

    command = "acc"

    collector_currency_amount: int = Field(
        validation_alias="CCA", default=0, description="Collector currency the target holds"
    )


# =============================================================================
# TAI - Treasure map node attack pre-calculation
# =============================================================================


class GetTreasureNodeAttackInfoRequest(BaseRequest):
    """
    Ask for the attack pre-calculation against a node of a treasure map.

    Command: tai
    Payload: {"MID": map_id, "NID": node_id}

    Client: ``C2SAttackInfoTreasureDungeonVO`` (bundle line 33261), sent by the ``onClickMapItem`` of
    ``DungeonSeasonMapScreenItem``, ``VillageSeasonMapScreenItem`` and ``CastleTreasureMapItemDungeon``
    (bundle lines 39521, 39550, 67766).
    """

    command = "tai"

    map_id: int = Field(validation_alias="MID", description="The treasure map")
    node_id: int = Field(validation_alias="NID", description="The node on the treasure map")


class GetTreasureNodeAttackInfoResponse(BaseResponse):
    """
    The attack pre-calculation for a treasure map node: your units and the spy report.

    The target's level, walls and gates come from the treasure map's own data, not the reply.

    Command: tai

    Client: ``TAICommand.executeCommand`` (bundle line 129012), ``CastleTreasureMapData.parse_TAI``
    (140468), ``CastleTreasureHuntFightscreenVO.fillFromParamObject`` (140505), which reads only these
    keys and passes ``S``, ``AS``, ``B`` and ``LS`` to ``CastleSpyArmyInfoVO.parseArmyInfo`` (24515).
    """

    command = "tai"

    map_id: int = Field(validation_alias="MID", description="The treasure map")
    node_id: int = Field(validation_alias="NID", description="The node on the treasure map")
    spy_army: SpyArmyBlock = Field(
        validation_alias="S",
        default=None,
        description="The spied defenders by the position they hold; None without a spy report",
    )
    spy_age_seconds: int = Field(
        validation_alias="AS",
        default=-1,
        description="Seconds since the target was spied; -1 when there is no spy report",
    )
    spied_castellan: Commander | None = Field(
        validation_alias="B", default=None, description="The castellan defending the node, from the spy report"
    )
    defender_legend_skill_ids: tuple[EnumOrInt["LegendSkill"], ...] = Field(
        validation_alias="LS",
        default=(),
        description="The defender's legend skills, part of the spy report",
    )
    unit_inventory: UnitInventory = Field(
        validation_alias="gui",
        default_factory=UnitInventory,
        description="The attacker's units and tools, and its stronghold units",
    )

    @field_validator("spied_castellan", mode="wrap")
    @classmethod
    def _castellan_or_none(cls, value: object, handler: ValidatorFunctionWrapHandler) -> Commander | None:
        if not value:
            return None
        return read_or_none(handler, value, warn=logger, what="the defending castellan of a treasure node")

    @field_validator("defender_legend_skill_ids", mode="before")
    @classmethod
    def _legend_skills(cls, value: object) -> list[int]:
        return int_entries(value, warn=logger, what="legend skills of a treasure node pre-calculation")

    @model_validator(mode="after")
    def _no_spy_report_without_an_army(self) -> "GetTreasureNodeAttackInfoResponse":
        """Client: ``CastleSpyArmyInfoVO.parseArmyInfo`` reads the rest only when S is not empty."""
        if self.spy_army is None:
            self.spy_age_seconds = -1
            self.spied_castellan = None
            self.defender_legend_skill_ids = ()
        return self


# =============================================================================
# COI / CCI / CTI - Conquest pre-calculation
# =============================================================================


class GetOutpostConquerInfoRequest(BaseRequest):
    """
    Ask for the conquest pre-calculation against an outpost.

    Command: coi
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y}

    Client: ``C2SGetConquerOutpostInfosVO`` (bundle line 72060),
    ``CastleStartAttackDialog.conquerOutpost`` (bundle line 14839).
    """

    command = "coi"

    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target")
    target_x: int = Field(validation_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", description="Target map y")


class GetOutpostConquerInfoResponse(AttackInfoResponse):
    """
    The conquest pre-calculation for an outpost, with the barons it can use.

    The client reads ``MB`` twice here: as the morality in the shared parse
    and as the maximum barons in ``parseBarons``. This model keeps the
    conquest meaning only.

    Command: coi

    Client: ``COICommand.executeCommand`` (bundle line 122278), ``CastleAttackData.parse_COI`` (133838),
    ``CastleConquerInfoVO.fillFromParamObject`` / ``parseBarons`` (bundle lines 133904-133907).
    """

    command = "coi"

    available_barons: int = Field(validation_alias="AB", default=0, description="Barons free to lead the conquest")
    max_barons: int = Field(validation_alias="MB", default=0, description="Most barons the player may hold")


class GetFactionCampConquerInfoRequest(BaseRequest):
    """
    Ask for the conquest pre-calculation against a Berimond faction camp.

    Command: cfi
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y, "SX": source_x, "SY": source_y}

    Client: ``C2SConquerInfoFactioncampVO`` (bundle line 72096),
    ``CastleStartAttackDialog.conquerFactionCamp`` (bundle line 14848).
    """

    command = "cfi"

    kingdom_id: Kingdom = Field(validation_alias="KID", description="Kingdom id of the target")
    target_x: int = Field(validation_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", description="Target map y")
    source_x: int = Field(validation_alias="SX", description="Attacking camp's map x")
    source_y: int = Field(validation_alias="SY", description="Attacking camp's map y")


class GetFactionCampConquerInfoResponse(GetOutpostConquerInfoResponse):
    """
    The conquest pre-calculation for a faction camp, read as the outpost one is.

    Command: cfi

    Client: ``CFICommand.executeCommand`` (bundle line 127772), ``CastleAttackData.parse_COI`` (133887).
    """

    command = "cfi"


class GetCapitalConquerInfoRequest(BaseRequest):
    """
    Ask for the conquest pre-calculation against a capital.

    Command: cci
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y}

    Client: ``C2SGetConquerCapitalInfosVO`` (bundle line 72042),
    ``CastleStartAttackDialog.conquerCapital`` (bundle line 14842).
    """

    command = "cci"

    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target")
    target_x: int = Field(validation_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", description="Target map y")


class GetCapitalConquerInfoResponse(GetAttackInfoResponse):
    """
    The conquest pre-calculation for a capital. The client reads no barons from it.

    Command: cci

    Client: ``CCICommand.executeCommand`` (bundle line 122261), ``CastleAttackData.parse_CCI`` (133840),
    ``CastleConquerInfoVO.fillFromParamObject``
    (bundle line 133904).
    """

    command = "cci"


class GetMetropolConquerInfoRequest(BaseRequest):
    """
    Ask for the conquest pre-calculation against a metropolis.

    Command: cti
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y}

    Client: ``C2SGetConquerMetropolInfosVO`` (bundle line 72051),
    ``CastleStartAttackDialog.conquerMetropol`` (bundle line 14843).
    """

    command = "cti"

    kingdom_id: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target")
    target_x: int = Field(validation_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", description="Target map y")


class GetMetropolConquerInfoResponse(GetAttackInfoResponse):
    """
    The conquest pre-calculation for a metropolis. The client reads no barons from it.

    Command: cti

    Client: ``CTICommand.executeCommand`` (bundle line 122295), ``CastleAttackData.parse_CTI`` (133842),
    ``CastleConquerInfoVO.fillFromParamObject``
    (bundle line 133904).
    """

    command = "cti"


__all__ = [
    "GetDungeonAttackInfoRequest",
    "GetDungeonAttackInfoResponse",
    "GetBossDungeonAttackInfoRequest",
    "GetBossDungeonAttackInfoResponse",
    "GetLandmarkAttackInfoRequest",
    "GetLandmarkAttackInfoResponse",
    "GetVillageAttackInfoRequest",
    "GetVillageAttackInfoResponse",
    "GetIslandAttackInfoRequest",
    "GetIslandAttackInfoResponse",
    "GetOutpostConquerInfoRequest",
    "GetOutpostConquerInfoResponse",
    "GetCapitalConquerInfoRequest",
    "GetCapitalConquerInfoResponse",
    "GetMetropolConquerInfoRequest",
    "GetMetropolConquerInfoResponse",
    "GetFactionCampConquerInfoRequest",
    "GetFactionCampConquerInfoResponse",
    "GetAllianceTowerAttackInfoRequest",
    "GetAllianceTowerAttackInfoResponse",
    "GetCollectorAttackInfoRequest",
    "GetCollectorAttackInfoResponse",
    "GetTreasureNodeAttackInfoRequest",
    "GetTreasureNodeAttackInfoResponse",
]
