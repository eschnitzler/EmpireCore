"""Battle for Berimond: targets, faction balance and points, joining, the kingdom status and your Berimond standing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import Field, field_serializer, field_validator

from empire_core.enums import BerimondFaction, BerimondProtectionStatus, Kingdom
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, enum_or_none
from empire_core.protocol.js import ClientInt, ClientNumber, js_loose_equals

if TYPE_CHECKING:
    from empire_core.gamedata import BerimondSpecialCamp, PrebuiltCastle


class BerimondTarget(BasePayload):
    """An attackable special camp, a ``GameData.berimond_special_camps`` row; not a map area id or coordinate.

    Client: ``FactionEventVO.parse_AFD`` (bundle 7369), ``FactionLaneRenderHelper.showLane``
    (40075) compares each AC integer with a tower's specialCampID.
    """

    special_camp_id: EnumOrInt["BerimondSpecialCamp"] = Field(description="The attackable special camp")


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
    gerbrandt_players: int = Field(validation_alias="RP", description="Players in the House of Gerbrandt")
    ursidae_players: int = Field(validation_alias="BP", description="Players in the House of Ursidae")

    @field_validator("gerbrandt_players", "ursidae_players")
    @classmethod
    def _population(cls, value: int) -> int:
        return max(value, 0)


class GetBerimondPointsRequest(BaseRequest):
    """Client: ``C2SGetFactionPointsVO`` (bundle 66177), empty request, sent by the world map (66094)."""

    command: ClassVar[str] = "gfp"


class BerimondPoints(BaseResponse):
    """The House of Gerbrandt's and the House of Ursidae's points.

    Client: ``GFPCommand.executeCommand`` (bundle 127917), which reads them only when either is set,
    ``FactionEventVO.parseFactionPointsFromParamObject`` (7376).
    """

    command: ClassVar[str] = "gfp"
    gerbrandt_points: ClientInt = Field(validation_alias="RFP", default=0, description="Gerbrandt's points")
    ursidae_points: ClientInt = Field(validation_alias="BFP", default=0, description="Ursidae's points")


class SelectBerimondCampRequest(BaseRequest):
    """Join Battle for Berimond with one of its prebuilt camps.

    Client: ``C2SSelectFactionCampVO`` (bundle 47692), sent by ``FactionEventJoinSublayer.buyCamp``
    (95197) and, paying the missing resources, by ``CastleResourceWaitDialogProperties`` (35237).
    """

    command: ClassVar[str] = "fsc"
    camp_id: EnumOrInt["PrebuiltCastle"] = Field(validation_alias="ID", description="The prebuilt camp to start with")
    pay_with_rubies: bool = Field(
        validation_alias="PWR", default=False, description="Pay the missing resources with rubies"
    )
    ruby_camp: bool = Field(
        validation_alias="OC2", default=False, description="The camp is the one priced in rubies only"
    )
    kingdom_id: Kingdom = Field(validation_alias="SID", default=Kingdom.BERIMOND, description="Berimond's kingdom")

    @field_serializer("pay_with_rubies", "ruby_camp")
    def _flag(self, value: bool) -> int:
        return int(value)


class SelectBerimondCampResponse(BaseResponse):
    """Client: ``FSCCommand.executeCommand`` (bundle 127885) reads nothing from the reply."""

    command: ClassVar[str] = "fsc"


class BerimondKingdomStatus(BaseResponse):
    """Last man standing, your part in the event and which capital each faction can reach.

    Pushed on its own and inside a ``kpi``; the client keeps it on the running event.

    Client: ``FKICommand.executeCommand`` (bundle 127859), ``CastleKingdomData.parse_KPI`` (134604),
    ``FactionEventVO.parse_FKI`` (7365), which takes each flag as ``1 == value``;
    ``isOtherCapitalReachable`` (7430) and ``AFactionAttackBox.updateButton`` (54672) for their meaning.
    """

    command: ClassVar[str] = "fki"
    blue_last_man_standing: bool = Field(
        validation_alias="BFLMS", default=False, description="Last man standing is on for the House of Ursidae"
    )
    red_last_man_standing: bool = Field(
        validation_alias="RFLMS", default=False, description="Last man standing is on for the House of Gerbrandt"
    )
    active_in_event: bool = Field(
        validation_alias="PA",
        default=False,
        description="You may still attack and send troops; False once last man standing shuts you out",
    )
    ursidae_capital_reachable: bool = Field(
        validation_alias="BCR",
        default=False,
        description="Ursidae's capital is open to attack: its towers are down",
    )
    gerbrandt_capital_reachable: bool = Field(
        validation_alias="RCR",
        default=False,
        description="Gerbrandt's capital is open to attack: its towers are down",
    )

    @field_validator(
        "blue_last_man_standing",
        "red_last_man_standing",
        "active_in_event",
        "ursidae_capital_reachable",
        "gerbrandt_capital_reachable",
        mode="before",
    )
    @classmethod
    def _one(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)


class FactionStanding(BasePayload):
    """
    Your faction and its protection in Berimond: an ``FN`` block.

    Client: ``FactionEventVO.loadFactionDataFromParamObject`` (bundle line 7363)
    """

    faction_id: EnumOrInt[BerimondFaction] = Field(
        validation_alias="FID", default=BerimondFaction.URSIDAE, description="Your faction"
    )
    main_camp_id: ClientInt = Field(validation_alias="MC", default=0, description="Your faction's main camp")
    protection_seconds: ClientNumber = Field(
        validation_alias="PMT", default=0, description="Seconds left of the Berimond protection stage"
    )
    protection_status: ClientInt = Field(
        validation_alias="PMS",
        default=0,
        description="The Berimond protection stage, see berimond_protection_status",
    )
    beginner_protection_seconds: ClientNumber = Field(
        validation_alias="NS",
        default=0,
        description="Seconds of beginner protection left in Berimond; 0 when not sent, which leaves it as it was",
    )

    @property
    def berimond_protection_status(self) -> BerimondProtectionStatus | None:
        """``protection_status`` as a stage; None for a value the client does not define."""
        return enum_or_none(BerimondProtectionStatus, self.protection_status)
