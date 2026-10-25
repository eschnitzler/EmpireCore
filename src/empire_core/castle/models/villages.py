"""
Your villages: the resource villages and islands you hold, and your private resource villages.

Commands:
- kgv: Your villages, a login section of ``gbd`` and a reply
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


__all__ = ["GetVillageListRequest", "OwnVillage", "PrivateVillage", "VillageListResponse"]
