"""Season event maps (the Thornking, the Sea Queen, the Underworld): entering the map, its camp and transfers.

Commands:
- jea: Enter a season event's map at your camp there
- csc: Start on a season event's map with one of its prebuilt camps
- msm: Shorten a transfer to a season event's map with a minute skip
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field, field_serializer

from empire_core.enums import KingdomTransferType
from empire_core.gamedata import EnumOrStr
from empire_core.protocol.base import BaseRequest, BaseResponse

if TYPE_CHECKING:
    from empire_core.gamedata import Currency


class JoinSeasonCampRequest(BaseRequest):
    """
    Enter a season event's map at your camp there.

    Command: jea
    Payload: {"MID": map_id}

    Client: ``C2SJoinCampVO`` (bundle line 21312), sent with the running season event's map by
    ``SeasonCampPanelButton.onButtonClicked`` (bundle line 108195) and
    ``StartCampSeasonMapScreenItem.onClickMapItem`` (bundle line 57878)
    """

    command = "jea"

    map_id: int = Field(validation_alias="MID", description="The event's treasure map, SeasonEvent.map_id")


class JoinSeasonCampResponse(BaseResponse):
    """
    The map entered.

    Command: jea

    Client: ``JEACommand.executeCommand`` (bundle line 131625) reads nothing from the reply
    """

    command = "jea"


class SelectSeasonCampRequest(BaseRequest):
    """
    Start on a season event's map with one of its prebuilt camps.

    Command: csc
    Payload: {"ID": prebuilt_camp_id, "PWR": 0 or 1, "OC2": 0 or 1, "SID": space_id}

    Keys follow the client's order. ``OC2`` takes the camp whose only price is rubies; ``PWR`` pays the
    missing resources with rubies, which the client sends only from its resource wait dialog.

    Client: ``C2SSelectSeasonCampVO`` (bundle line 47722), sent by ``AUnlockPrebuiltCastle.buyPrebuiltCastle``
    (bundle line 55482) with the camp's first ``spaceIDs`` entry, and by
    ``CastleResourceWaitDialogProperties.getResourceSkipCommand`` (bundle line 35238)
    """

    command = "csc"

    prebuilt_camp_id: int = Field(
        validation_alias="ID", description="The prebuilt camp, a row of the items prebuiltcastles table"
    )
    pay_with_rubies: bool = Field(
        validation_alias="PWR", default=False, description="Pay the missing resources with rubies"
    )
    ruby_camp: bool = Field(validation_alias="OC2", default=False, description="The camp is the one bought with rubies")
    space_id: int = Field(validation_alias="SID", description="The first of the camp's spaceIDs in that table")

    @field_serializer("pay_with_rubies", "ruby_camp")
    def _flag(self, value: bool) -> int:
        return int(value)


class SelectSeasonCampResponse(BaseResponse):
    """
    The camp taken.

    Command: csc

    Client: ``CSCCommand.executeCommand`` (bundle line 128343) reads nothing from the reply
    """

    command = "csc"


class MinuteSkipSeasonTransferRequest(BaseRequest):
    """
    Shorten the units or goods on their way to a season event's map with a minute skip.

    Command: msm
    Payload: {"MID": map_id, "TT": transfer_type, "MST": minute_skip}

    Keys follow the client's order: the constructor sets ``MID`` and ``TT`` before ``MST``.

    Client: ``C2SMinuteSkipMapTransferVO`` (bundle line 55843), built by
    ``SeasonTravelGoodsMinuteSkipProperties.getMinuteSkipCommand`` and
    ``SeasonTravelUnitsMinuteSkipProperties.getMinuteSkipCommand`` (bundle lines 99612, 99644)
    """

    command = "msm"

    map_id: int = Field(validation_alias="MID", description="The event's treasure map, SeasonEvent.map_id")
    transfer_type: KingdomTransferType = Field(
        validation_alias="TT", description="Whether the transfer carries units or goods"
    )
    minute_skip: EnumOrStr["Currency"] = Field(
        validation_alias="MST",
        description="The minute skip used, ``Currency.SKIP_1_MINUTE`` to ``SKIP_24_HOURS``",
    )


class MinuteSkipSeasonTransferResponse(BaseResponse):
    """
    The transfer shortened.

    Command: msm
    Payload: {"tmp": {...}}

    The reply model reads nothing; its ``tmp``, the treasure maps, reaches ``client.map.treasure_maps``.

    Client: ``MSMCommand.executeCommand`` (bundle line 125852), which hands ``tmp`` to
    ``CastleTreasureMapData.parse_TMP``
    """

    command = "msm"


__all__ = [
    "JoinSeasonCampRequest",
    "JoinSeasonCampResponse",
    "MinuteSkipSeasonTransferRequest",
    "MinuteSkipSeasonTransferResponse",
    "SelectSeasonCampRequest",
    "SelectSeasonCampResponse",
]
