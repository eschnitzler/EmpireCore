"""
Your villages: the resource villages and islands you hold, and your private resource villages,
villages bought with resource village tokens and held off the world map. A private village type
is named by its id in the game data's ``privateVillages`` table.

Commands:
- kgv: Your villages, a login section of ``gbd`` and a reply
- bpv: buy a private resource village
- upv: upgrade one to the next level
- rpv: remove one
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_validator

from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt

from .landmarks import OwnArea

logger = logging.getLogger(__name__)


class GetVillageListRequest(BaseRequest):
    """
    Ask for your villages.

    Command: kgv
    Payload: {}

    Client: ``C2SKingdomGetVillageListVO`` (bundle line 50165), sent by
    ``CastleResourceVillageOverviewDialog.showLoaded`` (bundle line 50126) and
    ``CastleListVillagesOverviewDialog.getData`` (bundle line 108009)
    """

    command = "kgv"


class OwnVillage(OwnArea):
    """
    One of your villages: a resource village or, on the Storm Islands, a resource island.

    Client: ``CastleKingdomVillageInfoVO.parseParamObject`` (bundle line 73469), which reads a row of
    type ``ISLE_RESOURCE`` as a ``ResourceIsleMapobjectVO`` and any other as a ``VillageMapobjectVO``
    """


class PrivateVillage(BasePayload):
    """
    One of your private resource villages.

    Client: ``CastleDetailedVillageList.parseKGV`` (bundle line 73373) reads ``VID`` and ``XID``
    (``CommKeys.VILLAGE_ID``, ``XML_VILLAGE_ID``, dll line 18946); it leaves out a village whose
    ``XID`` the items ``privateVillages`` table lacks, which this keeps
    """

    village_id: ClientInt = Field(validation_alias="VID", description="The village's own id")
    village_type_id: ClientInt = Field(
        validation_alias="XID", description="The village's row in the items privateVillages table"
    )


class VillageListResponse(BaseResponse):
    """
    Your villages and private resource villages, listed whole.

    Command: kgv, as a login section of ``gbd`` and a reply
    Payload: {"VI": [[map_row, [[wod_id, amount], ...]], ...], "PV": [{"VID": id, "XID": type_id}, ...]}

    Another player's villages in a ``gdi`` are read there, not here.

    Client: ``KGVCommand.executeCommand`` (bundle line 124711), which applies it only after the login
    data; ``CastleUserData.parse_KGV`` (bundle line 9889) and ``CastleDetailedVillageList.parseKGV``
    (bundle line 73373), which replace both lists
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "kgv"

    villages: list[OwnVillage] = Field(
        validation_alias="VI", default_factory=list, description="Your resource villages and resource islands"
    )
    private_villages: list[PrivateVillage] = Field(
        validation_alias="PV", default_factory=list, description="Your private resource villages"
    )

    @field_validator("villages", mode="before")
    @classmethod
    def _villages(cls, value: Any) -> Any:
        return readable_list(OwnVillage, value, accept=lambda row: isinstance(row, list), warn=logger, what="villages")

    @field_validator("private_villages", mode="before")
    @classmethod
    def _private_villages(cls, value: Any) -> Any:
        return readable_list(
            PrivateVillage, value, accept=lambda row: isinstance(row, dict), warn=logger, what="private villages"
        )


_VILLAGE_TYPE = "The village type's id in the game data's privateVillages table"
_VILLAGE = "Your private village's id, as in PrivateVillage.village_id"


class BuyPrivateVillageRequest(BaseRequest):
    """
    Buy a private resource village.

    Command: bpv
    Payload: {"XID": village_type_id}

    Client: ``C2SBuyPrivateResourceVillageVO`` (bundle line 81682), sent by
    ``PrivateResourceVillageBuyDialog.onConfirm`` (bundle line 81673)
    """

    command = "bpv"

    village_type_id: int = Field(validation_alias="XID", description=_VILLAGE_TYPE)


class BuyPrivateVillageResponse(BaseResponse):
    """
    The village was bought; the client reads nothing from the reply.

    Command: bpv

    Client: ``BPVCommand.exec`` (bundle line 126459)
    """

    command = "bpv"


class UpgradePrivateVillageRequest(BaseRequest):
    """
    Upgrade a private resource village to the next level.

    Command: upv
    Payload: {"XID": village_type_id, "VID": village_id}

    The client sends the type of the village's current level, not of the next.

    Client: ``C2SUpgradePrivateResourceVillageVO`` (bundle line 81609), sent by
    ``PrivateResourceVillageUpgradeDialog.onConfirm`` (bundle line 81600)
    """

    command = "upv"

    village_type_id: int = Field(validation_alias="XID", description=f"{_VILLAGE_TYPE}, of its current level")
    village_id: int = Field(validation_alias="VID", description=_VILLAGE)


class UpgradePrivateVillageResponse(BaseResponse):
    """
    The village was upgraded; the client reads nothing from the reply.

    Command: upv

    Client: ``UPVCommand.exec`` (bundle line 126489)
    """

    command = "upv"


class RemovePrivateVillageRequest(BaseRequest):
    """
    Remove a private resource village.

    Command: rpv
    Payload: {"VID": village_id}

    Client: ``C2SRemovePrivateResourceVillageVO`` (bundle line 81575), sent by
    ``PrivateResourceVillageDestroyDialog.onConfirm`` (bundle line 81568)
    """

    command = "rpv"

    village_id: int = Field(validation_alias="VID", description=_VILLAGE)


class RemovePrivateVillageResponse(BaseResponse):
    """
    The village was removed; the client reads nothing from the reply.

    Command: rpv

    Client: ``RPVCommand.exec`` (bundle line 126474)
    """

    command = "rpv"


__all__ = [
    "BuyPrivateVillageRequest",
    "BuyPrivateVillageResponse",
    "GetVillageListRequest",
    "OwnVillage",
    "PrivateVillage",
    "RemovePrivateVillageRequest",
    "RemovePrivateVillageResponse",
    "UpgradePrivateVillageRequest",
    "UpgradePrivateVillageResponse",
    "VillageListResponse",
]
