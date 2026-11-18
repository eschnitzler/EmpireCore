"""
Holding a feast for faster recruitment in every castle.

Commands:
- bfs: Hold a feast, or extend the one you hold
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field, field_serializer

from empire_core.enums import Kingdom
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BaseRequest, BaseResponse

from .progress import ActiveFeast

if TYPE_CHECKING:
    from empire_core.gamedata import Feast


class HoldFeastRequest(BaseRequest):
    """
    Hold a feast paid from one of your castles, or extend the feast you hold.

    Command: bfs
    Payload: {"T": feast, "CID": castle, "KID": kingdom, "PO": offer_id, "PWR": 0 or 1}

    The feast dialogs send PO -1 and PWR 0; after a refusal for missing food, the resource dialog sends it
    again with the private offer and PWR 1, paying the missing food with rubies.

    Client: ``C2SFestivalStartVO`` (split.js line 169260), sent by ``CastleFestivalDialog.onClick`` (split.js line
    334522), ``CastleExtendFestivalDialog.onClick`` (split.js line 334119) and
    ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (split.js line 183792), which
    ``CastleHandleServerErrorCommand.handleGameSpecificServerError`` (split.js line 616535) opens on
    ``NOT_ENOUGH_RESOURCES``
    """

    command = "bfs"

    feast_id: EnumOrInt["Feast"] = Field(validation_alias="T", description="The feast")
    castle_id: int = Field(validation_alias="CID", description="The castle's object id")
    kingdom: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")
    private_offer_id: int = Field(
        validation_alias="PO", default=-1, description="The private offer the feast uses, -1 for none"
    )
    pay_with_rubies: bool = Field(validation_alias="PWR", default=False, description="Pay the missing food with rubies")

    @field_serializer("pay_with_rubies")
    def _flag(self, value: bool) -> int:
        return 1 if value else 0


class HoldFeastResponse(BaseResponse, ActiveFeast):
    """
    The feast you hold after holding or extending one; it also reaches ``client.player.boosts``.

    Command: bfs
    Payload: {"T": feast, "RT": seconds_left}

    Client: ``BFSCommand.executeCommand`` (split.js line 627488) hands it to
    ``CastlePremiumBoostData.parse_bfs`` (split.js line 81585)
    """

    command = "bfs"


__all__ = ["HoldFeastRequest", "HoldFeastResponse"]
