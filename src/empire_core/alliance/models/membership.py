"""Applying to and joining alliances."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_serializer, field_validator, model_validator

from empire_core.alliance.models.info import AllianceInfo
from empire_core.enums import AllianceRank
from empire_core.gamedata.lenient import EnumOrInt
from empire_core.player.models.profile import PlayerProfileBase
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, js_parse_int, js_same_number, js_truthy
from empire_core.protocol.text import encode_json_text

logger = logging.getLogger(__name__)


class AllianceMembership(BasePayload):
    """Membership status. Client: ``CastleUserData.parse_GAL`` (bundle line 9869)."""

    alliance_id: ClientInt = Field(validation_alias="AID", description="Alliance id")
    rank: EnumOrInt[AllianceRank] = Field(default=AllianceRank.LEADER, validation_alias="R", description="Member rank")
    name: str = Field(default="", validation_alias="AN", description="Alliance name")
    current_fame: ClientInt = Field(default=0, validation_alias="ACF", description="Alliance fame")
    looking_for_alliance: bool = Field(default=False, validation_alias="SA", description="Looking for an alliance")

    @field_validator("looking_for_alliance", mode="before")
    @classmethod
    def _looking(cls, value: Any) -> bool:
        return js_parse_int(value) == 1

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, value: Any) -> Any:
        return value or ""


class ApplyToAllianceRequest(BaseRequest):
    """Send an application. Client: ``C2SAllianceSendApplicationVO`` (bundle line 72553)."""

    command = "saa"
    alliance_id: int = Field(validation_alias="AID", description="Alliance id")
    text: str = Field(validation_alias="AT", description="Application text")

    @field_serializer("text")
    def _text(self, value: str) -> str:
        return encode_json_text(value)


class ApplyToAllianceResponse(BaseResponse):
    """Application accepted. Client: ``SAACommand.executeCommand`` (bundle line 121965)."""

    command = "saa"


class JoinOpenAllianceRequest(BaseRequest):
    """Join an open alliance. Client: ``C2SJoinOpenAllianceVO`` (bundle line 72504)."""

    command = "joa"
    alliance_id: int = Field(validation_alias="AID", description="Alliance id")

    def accepts_reply(self, payload: Any) -> bool:
        """Correlate an echoed alliance id; malformed replies remain available for validation."""
        block = payload.get("A") if isinstance(payload, dict) else None
        return not isinstance(block, dict) or "AID" not in block or js_same_number(block["AID"], self.alliance_id)


class JoinOpenAllianceResponse(BaseResponse):
    """Joined alliance. Client: ``JOACommand.executeCommand`` (bundle line 121934)."""

    command = "joa"
    membership: AllianceMembership = Field(validation_alias="gal", description="Your new membership")
    alliance: AllianceInfo = Field(validation_alias="A", description="Joined alliance")

    @field_validator("alliance", mode="before")
    @classmethod
    def _alliance(cls, value: Any) -> Any:
        if isinstance(value, AllianceInfo):
            return value
        if not isinstance(value, dict) or value.get("AID") is None:
            raise ValueError("joined alliance has no id")
        return value

    @model_validator(mode="after")
    def _same_alliance(self) -> JoinOpenAllianceResponse:
        if self.membership.alliance_id != self.alliance.alliance_id:
            raise ValueError("membership and alliance details name different alliances")
        return self


class GetAllianceInvitationRequest(BaseRequest):
    """Read an invitation. Client: ``C2SGetAllianceInvitationVO`` (bundle line 69387)."""

    command = "bai"
    message_id: int = Field(validation_alias="MID", description="Invitation message id")


class GetAllianceInvitationResponse(BaseResponse):
    """Inviting alliance. Client: ``CastleAllianceData.parse_BAI`` (bundle line 11562)."""

    command = "bai"
    alliance: AllianceInfo | None = Field(default=None, validation_alias="A", description="Inviting alliance")

    @field_validator("alliance", mode="before")
    @classmethod
    def _alliance(cls, value: Any) -> Any:
        if isinstance(value, AllianceInfo):
            return value
        return value if isinstance(value, dict) and value.get("AID") is not None else None


class AcceptAllianceInvitationRequest(BaseRequest):
    """Answer an invitation. Client: ``C2SAllianceAcceptInviteVO`` (bundle line 69378).

    ``CastleAllianceInvitationDialog.onAccept/onRefuse`` (bundle lines 44828–44829)
    send the invitation's message id and decision 1/0.
    """

    command = "aai"
    message_id: int = Field(validation_alias="MID", description="Invitation message id")
    accept: bool = Field(validation_alias="D", description="Whether to accept the invitation")

    @field_serializer("accept")
    def _decision(self, value: bool) -> int:
        return int(value)


class AcceptAllianceInvitationResponse(BaseResponse):
    """Membership after a decision. Client: ``AAICommand.executeCommand`` (bundle line 121202)."""

    command = "aai"
    membership: AllianceMembership | None = Field(
        default=None, validation_alias="gal", description="Updated membership"
    )
    alliance: AllianceInfo | None = Field(default=None, validation_alias="A", description="Joined alliance")

    @field_validator("alliance", mode="before")
    @classmethod
    def _alliance(cls, value: Any) -> Any:
        if isinstance(value, AllianceInfo):
            return value
        return value if isinstance(value, dict) and value.get("AID") is not None else None

    @model_validator(mode="after")
    def _same_alliance(self) -> AcceptAllianceInvitationResponse:
        if self.membership is not None and self.alliance is not None:
            if self.membership.alliance_id != self.alliance.alliance_id:
                raise ValueError("membership and alliance details name different alliances")
        return self


class AllianceRecruit(BasePayload):
    """Recruit search row. Client: ``SearchMemberListItemVO.parseItem`` (bundle line 66552)."""

    player_id: ClientInt = Field(default=0, validation_alias="PID", description="Player id")
    distance: ClientInt = Field(default=0, validation_alias="D", description="Distance to the player")


class FindAllianceRecruitsRequest(BaseRequest):
    """Find recruits. Client: ``C2SAllianceSearchMemberListVO`` (bundle line 70146)."""

    command = "sml"


class FindAllianceRecruitsResponse(BaseResponse):
    """Nearby recruits and owners. Client: ``SMLCommand.executeCommand`` (bundle line 122040),
    ``CastleAllianceData.parse_SML`` (bundle line 11580), and
    ``WorldMapOwnerInfoVO.fillFromParamObject`` (bundle line 10794).
    """

    command = "sml"
    recruits: list[AllianceRecruit] = Field(validation_alias="PL", description="Recruits, nearest first")
    owners: list[PlayerProfileBase] = Field(
        default_factory=list, validation_alias="OI", description="Recruit owner records"
    )

    @field_validator("recruits", mode="before")
    @classmethod
    def _recruits(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError("recruits must be an array")
        return sorted(
            readable_list(
                AllianceRecruit, value, accept=lambda row: isinstance(row, dict), warn=logger, what="alliance recruits"
            ),
            key=lambda row: row.distance,
        )

    @field_validator("owners", mode="before")
    @classmethod
    def _owners(cls, value: Any) -> Any:
        return readable_list(
            PlayerProfileBase,
            value,
            accept=lambda row: isinstance(row, dict),
            keep=lambda row: js_truthy(row.get("OID")),
            warn=logger,
            what="recruit owners",
        )

    def owner_of(self, recruit: AllianceRecruit) -> PlayerProfileBase | None:
        """The recruit's owner record, or None when absent."""
        return next((owner for owner in self.owners if owner.player_id == recruit.player_id), None)


class SetLookingForMembersRequest(BaseRequest):
    """Recruitment flags. Client: ``C2SAllianceSetSearchMemberVO`` (bundle line 70154)."""

    command = "asm"
    enabled: bool = Field(validation_alias="IS", description="Whether the alliance is looking for members")
    open_join: bool = Field(validation_alias="IA", description="Whether players may join without an invitation")

    @field_serializer("enabled", "open_join")
    def _flag(self, value: bool) -> int:
        return int(value)


class SetLookingForMembersResponse(BaseResponse):
    """Flags accepted. Client: ``ASMCommand.executeCommand`` (bundle line 121623)."""

    command = "asm"


class SetLookingForAllianceRequest(BaseRequest):
    """Player search flag. Client: ``C2SAllianceSetSearchAllianceVO`` (bundle line 72562)."""

    command = "asa"
    enabled: bool = Field(validation_alias="IS", description="Whether the player is looking for an alliance")

    @field_serializer("enabled")
    def _flag(self, value: bool) -> int:
        return int(value)


class SetLookingForAllianceResponse(BaseResponse):
    """Flag accepted. Client: ``ASACommand.executeCommand`` (bundle line 121609)."""

    command = "asa"
