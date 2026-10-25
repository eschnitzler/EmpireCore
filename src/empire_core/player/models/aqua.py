"""Aqua points, collected on the Storm Islands.

Commands:
- gap: Your and your alliance's aqua points
"""

from __future__ import annotations

from pydantic import Field

from empire_core.protocol.base import BaseRequest, BaseResponse
from empire_core.protocol.js import ClientNumber


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


__all__ = ["AquaPointsResponse", "GetAquaPointsRequest"]
