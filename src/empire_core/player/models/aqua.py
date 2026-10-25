"""The Storm Islands: aqua points, your and your alliance's standing, and the islands' reset.

Commands:
- gap: Your and your alliance's aqua points
- sii: Your and your alliance's standing on the Storm Islands
- ikr: The Storm Islands reset, pushed
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.protocol.js import ClientInt, ClientNumber, js_loose_equals


class GetAquaPointsRequest(BaseRequest):
    """
    Ask for your and your alliance's aqua points.

    Command: gap
    Payload: {}

    Client: ``C2SGetAquaPoints`` (bundle line 51668), sent by ``CastleListDetailOverviewDialog.getData``
    (bundle line 36787) and by ``CastleEilandPanel`` (bundle line 56736) while it knows none
    """

    command = "gap"


class AquaPointsResponse(BaseResponse):
    """
    Your and your alliance's aqua points, as a reply or pushed when a building yields some.

    Command: gap
    Payload: {"P": player_points, "A": alliance_points, "O": building_id, "DP": gained}

    Client: ``GAPCommand.executeCommand`` (bundle line 122976), ``CastleUserData.parse_GAP`` (bundle line
    9881), which keeps ``P`` and ``A`` as sent and, for an ``O`` above 0, shows ``DP`` rising from that
    building (``IsoUpdaterData.spawnAquaPointsEffect``, bundle line 130337)
    """

    command = "gap"

    player_points: ClientNumber = Field(validation_alias="P", default=0, description="Your aqua points")
    alliance_points: ClientNumber = Field(validation_alias="A", default=0, description="Your alliance's aqua points")
    building_id: ClientNumber = Field(
        validation_alias="O", default=0, description="The building that yielded the points; 0 or less for none"
    )
    gained_points: ClientNumber = Field(
        validation_alias="DP", default=0, description="The points that building yielded"
    )


class StormIslandsInfoRequest(BaseRequest):
    """
    Ask for your and your alliance's standing on the Storm Islands.

    Command: sii
    Payload: {}

    Client: ``C2SStormIslandsInfoVO`` (bundle line 105780), sent by ``CastleStormIslandsMainDialog.showLoaded``
    (bundle line 17524) while you are in an alliance
    """

    command = "sii"


class StormIslandsInfo(BaseResponse):
    """
    Your and your alliance's standing on the Storm Islands.

    Command: sii
    Payload: {"IR": rank, "AP": aqua_points, "AR": alliance_rank, "KA": 0 or 1, "AE": 0 or 1}

    Client: ``SIICommand.executeCommand`` (bundle line 127742) keeps ``IR`` and ``AP`` on the player and
    hands the rest to ``AllianceInfoVO.parse_SII`` (bundle line 26188), which takes each flag as ``1 == value``
    """

    command = "sii"

    rank: ClientInt = Field(validation_alias="IR", default=0, description="Your rank in your alliance's contest")
    aqua_points: ClientNumber = Field(validation_alias="AP", default=0, description="Your aqua points")
    alliance_rank: ClientInt = Field(
        validation_alias="AR", default=0, description="Your alliance's rank among the alliances on the islands"
    )
    alliance_is_island_king: bool = Field(
        validation_alias="KA", default=False, description="Your alliance holds the Storm Islands king title"
    )
    alliance_entered_islands: bool = Field(
        validation_alias="AE", default=False, description="Your alliance has entered the Storm Islands"
    )

    @field_validator("alliance_is_island_king", "alliance_entered_islands", mode="before")
    @classmethod
    def _flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)


class StormIslandsReset(BaseResponse):
    """
    The Storm Islands reset: their kingdom locks again and every aqua point is gone.

    Command: ikr, pushed

    Client: ``IKRCommand.executeCommand`` (bundle line 127728) reads nothing from the push; it locks the
    islands' kingdom (``CastleKingdomData.resetEilandData``, bundle line 134673), sets your and your
    alliance's aqua points to 0, drops the movements there
    (``CastleArmyData.removeAllMovementsByKingdomID``, bundle line 133728) and asks for ``kpi`` and the
    bookmarks again
    """

    command = "ikr"


__all__ = [
    "AquaPointsResponse",
    "GetAquaPointsRequest",
    "StormIslandsInfo",
    "StormIslandsInfoRequest",
    "StormIslandsReset",
]
