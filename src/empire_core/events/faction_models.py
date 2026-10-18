"""Battle for Berimond target eligibility and faction population reads."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import Field, field_validator

from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse


class BerimondTarget(BasePayload):
    """An attackable special camp; its id is opaque, not a map area id or coordinate.

    Client: ``FactionEventVO.parse_AFD`` (bundle 7369), ``FactionLaneRenderHelper.showLane``
    (40075) compares each AC integer with a tower's specialCampID.
    """

    special_camp_id: int = Field(description="Attackable special camp id")


class GetBerimondTargetsRequest(BaseRequest):
    """Client: ``C2SGetAttackableFactionDataVO`` (bundle 47388-47392), empty request."""

    command: ClassVar[str] = "afd"


class GetBerimondTargetsResponse(BaseResponse):
    """Client: ``AFDCommand.executeCommand`` (127742-127743), ``parse_AFD`` (7369)."""

    command: ClassVar[str] = "afd"
    targets: tuple[BerimondTarget, ...] = Field(
        validation_alias="AC", description="Attackable special camps in server order"
    )

    @field_validator("targets", mode="before")
    @classmethod
    def _targets(cls, value: Any) -> Any:
        if not isinstance(value, (tuple, list)) or any(type(item) is not int for item in value):
            raise ValueError("Expected a list of special camp ids")
        return tuple(BerimondTarget(special_camp_id=item) for item in value)


class GetBerimondBalanceRequest(BaseRequest):
    """Client: ``C2SGetFactionBalance`` (bundle 77727-77731), empty request."""

    command: ClassVar[str] = "fgb"


class BerimondBalance(BaseResponse):
    """Faction populations, clamped at zero as in the client.

    Client: ``FactionEventVO.parse_FGB`` (bundle 7368), ``FGBCommand.executeCommand``
    (127789-127791). No faction share is inferred when both populations are zero:
    the client retains its previous share in that case.
    """

    command: ClassVar[str] = "fgb"
    red_players: int = Field(validation_alias="RP", description="Players in the red faction")
    blue_players: int = Field(validation_alias="BP", description="Players in the blue faction")

    @field_validator("red_players", "blue_players")
    @classmethod
    def _population(cls, value: int) -> int:
        return max(value, 0)
