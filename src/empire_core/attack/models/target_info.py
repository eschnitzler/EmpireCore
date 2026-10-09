"""Attack pre-calculation for other targets, and conquest pre-calculation.

Commands:
- adi, abi, ali, avi, aii: Attack pre-calculation per kind of target
- coi, cci, cti: Conquest pre-calculation
"""

from __future__ import annotations

from pydantic import Field

from empire_core.enums import Kingdom
from empire_core.protocol.base import BaseRequest

from .info import AttackInfoResponse, GetAttackInfoResponse

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

    source_x: int = Field(validation_alias="SX", serialization_alias="SX", description="Attacking castle's map x")
    source_y: int = Field(validation_alias="SY", serialization_alias="SY", description="Attacking castle's map y")
    target_x: int = Field(validation_alias="TX", serialization_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", serialization_alias="TY", description="Target map y")
    kingdom_id: Kingdom = Field(
        validation_alias="KID", serialization_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target"
    )


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

    kingdom_id: Kingdom = Field(
        validation_alias="KID", serialization_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target"
    )
    source_x: int = Field(validation_alias="SX", serialization_alias="SX", description="Attacking castle's map x")
    source_y: int = Field(validation_alias="SY", serialization_alias="SY", description="Attacking castle's map y")
    target_x: int = Field(validation_alias="TX", serialization_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", serialization_alias="TY", description="Target map y")


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

    kingdom_id: Kingdom = Field(
        validation_alias="KID", serialization_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target"
    )
    target_x: int = Field(validation_alias="TX", serialization_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", serialization_alias="TY", description="Target map y")
    source_x: int = Field(validation_alias="SX", serialization_alias="SX", description="Attacking castle's map x")
    source_y: int = Field(validation_alias="SY", serialization_alias="SY", description="Attacking castle's map y")


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

    kingdom_id: Kingdom = Field(
        validation_alias="KID", serialization_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target"
    )
    target_x: int = Field(validation_alias="TX", serialization_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", serialization_alias="TY", description="Target map y")


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

    kingdom_id: Kingdom = Field(
        validation_alias="KID", serialization_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target"
    )
    target_x: int = Field(validation_alias="TX", serialization_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", serialization_alias="TY", description="Target map y")


class GetIslandAttackInfoResponse(GetAttackInfoResponse):
    """
    The attack pre-calculation for an isle resource.

    Command: aii

    Client: ``AIICommand.executeCommand`` (bundle line 122204), ``CastleAttackData.parse_AII`` (133834).
    """

    command = "aii"


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

    kingdom_id: Kingdom = Field(
        validation_alias="KID", serialization_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target"
    )
    target_x: int = Field(validation_alias="TX", serialization_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", serialization_alias="TY", description="Target map y")


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

    available_barons: int = Field(
        validation_alias="AB", serialization_alias="AB", default=0, description="Barons free to lead the conquest"
    )
    max_barons: int = Field(
        validation_alias="MB", serialization_alias="MB", default=0, description="Most barons the player may hold"
    )


class GetCapitalConquerInfoRequest(BaseRequest):
    """
    Ask for the conquest pre-calculation against a capital.

    Command: cci
    Payload: {"KID": kingdom_id, "TX": target_x, "TY": target_y}

    Client: ``C2SGetConquerCapitalInfosVO`` (bundle line 72042),
    ``CastleStartAttackDialog.conquerCapital`` (bundle line 14842).
    """

    command = "cci"

    kingdom_id: Kingdom = Field(
        validation_alias="KID", serialization_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target"
    )
    target_x: int = Field(validation_alias="TX", serialization_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", serialization_alias="TY", description="Target map y")


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

    kingdom_id: Kingdom = Field(
        validation_alias="KID", serialization_alias="KID", default=Kingdom.GREEN, description="Kingdom id of the target"
    )
    target_x: int = Field(validation_alias="TX", serialization_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", serialization_alias="TY", description="Target map y")


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
]
