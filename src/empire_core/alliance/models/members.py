"""Alliance member management.

Commands:
- akm: Kick a member
- arm: Change a member's rank
- aip: Invite a player
- aal: The alliance's applications
- aaa: Answer an application
- aqi: Leave the alliance
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, field_validator

from empire_core.enums import AllianceRank
from empire_core.player.models.profile import PlayerProfileBase
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, object_or_none, readable_list
from empire_core.protocol.js import ClientInt, js_number_or_none, js_truthy
from empire_core.protocol.text import decode_json_text

from .info import AllianceInfo

logger = logging.getLogger(__name__)


def _ain_alliance(value: Any) -> Any:
    """The alliance of a nested ain reply, read as ``CastleAllianceData.parse_AIN`` (bundle line 11560) reads it."""
    block = object_or_none(value)
    alliance = object_or_none(block.get("A")) if isinstance(block, dict) else None
    return alliance if isinstance(alliance, dict) and alliance.get("AID") is not None else None


class _AllianceEcho(BaseResponse):
    """A reply that carries the updated alliance as a nested ain reply."""

    alliance: AllianceInfo | None = Field(alias="ain", default=None, description="The alliance after the change")

    @field_validator("alliance", mode="before")
    @classmethod
    def _alliance(cls, value: Any) -> Any:
        return _ain_alliance(value)


# =============================================================================
# AKM - Kick a member
# =============================================================================


class KickMemberRequest(BaseRequest):
    """
    Remove a member from your alliance.

    Command: akm
    Payload: {"PID": player_id}

    Client: ``C2SAllianceKickMemberVO`` (bundle line 70354), sent by
    ``CastleAllianceMemberSettingsDialog.onKickMember`` (bundle line 70332)
    """

    command = "akm"

    player_id: int = Field(alias="PID", description="The member's AllianceMember.player_id")


class KickMemberResponse(_AllianceEcho):
    """
    The alliance after a kick.

    Command: akm

    Client: ``AKMCommand.executeCommand`` (bundle line 121513)
    """

    command = "akm"


# =============================================================================
# ARM - Change a member's rank
# =============================================================================


class RerankMemberRequest(BaseRequest):
    """
    Give a member another rank; rank 0 hands over the leadership.

    Command: arm
    Payload: {"PID": player_id, "R": rank}

    Client: ``C2SAllianceRerankMemberVO`` (bundle line 70363), sent by
    ``CastleAllianceMemberSettingsDialog.changeMemberRank`` (bundle line 70333) and
    ``sendNewLeader`` (bundle line 70320)
    """

    command = "arm"

    player_id: int = Field(alias="PID", description="The member's AllianceMember.player_id")
    rank: AllianceRank = Field(alias="R", description="The new rank")


class RerankMemberResponse(_AllianceEcho):
    """
    The alliance after a rank change.

    Command: arm

    Client: ``ARMCommand.executeCommand`` (bundle line 121589); it takes error 15
    (``NO_CHANGE``) as nothing to do
    """

    command = "arm"


# =============================================================================
# AIP - Invite a player
# =============================================================================


class InvitePlayerRequest(BaseRequest):
    """
    Invite a player to your alliance.

    Command: aip
    Payload: {"SV": "player_id"}

    Both call sites send the player's id as a string, not a name.

    Client: ``C2SAllianceInvitePlayerVO`` (bundle line 42819), sent by
    ``CastlePlayerInfoDialog.onInvitePlayerToAlliance`` (bundle line 3928) and
    ``CastleMapobjectInfoComponent.onInvitePlayerToAlliance`` (bundle line 66485)
    """

    command = "aip"

    search_value: str = Field(alias="SV", description="The player's id, as a string")

    @classmethod
    def for_player(cls, player_id: int) -> InvitePlayerRequest:
        """Invite the player ``player_id``."""
        return cls(SV=str(player_id))


class InvitePlayerResponse(BaseResponse):
    """
    The answer to an invitation; error 65 (``INVALID_PLAYER_ID``) when there is no such player.

    Command: aip

    Client: ``AIPCommand.executeCommand`` (bundle line 121476)
    """

    command = "aip"


# =============================================================================
# AAL - Applications
# =============================================================================


class AllianceApplicationListRequest(BaseRequest):
    """
    Ask for your alliance's applications.

    Command: aal
    Payload: {}

    Client: ``C2SAllianceApplicationListVO`` (bundle line 70138)
    """

    command = "aal"


class AllianceApplication(BasePayload):
    """
    One application to join your alliance.

    Client: ``AllianceApplicationListItemVO.parseItem`` (bundle line 66522)
    """

    player_id: ClientInt = Field(alias="PID", default=0, description="The applying player's id")
    distance: ClientInt = Field(alias="D", default=0, description="Distance to the applicant")
    text: str = Field(alias="AT", default="", description="The application's text, decoded")
    seconds_since_applied: int | float = Field(alias="AA", default=0, description="Seconds since the application")

    @field_validator("text", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return decode_json_text(value) if isinstance(value, str) else ""

    @field_validator("seconds_since_applied", mode="before")
    @classmethod
    def _seconds(cls, value: Any) -> Any:
        return js_number_or_none(value) or 0


class AllianceApplicationListResponse(BaseResponse):
    """
    Your alliance's applications, with the applicants' owner records.

    Command: aal

    Client: ``AALCommand.executeCommand`` (bundle line 121217) reads ``OI``
    with ``parseOwnerInfoArray`` and ``AL`` with ``CastleAllianceData.parse_AAL``
    (bundle line 11590), which sorts the applications by distance
    """

    command = "aal"

    applications: list[AllianceApplication] = Field(
        alias="AL", default_factory=list, description="The applications, nearest first"
    )
    owners: list[PlayerProfileBase] = Field(alias="OI", default_factory=list, description="The applicants")

    @field_validator("applications", mode="before")
    @classmethod
    def _applications(cls, value: Any) -> Any:
        rows = readable_list(
            AllianceApplication, value, accept=lambda e: isinstance(e, dict), warn=logger, what="applications"
        )
        return sorted(rows, key=lambda a: a.distance)

    @field_validator("owners", mode="before")
    @classmethod
    def _owners(cls, value: Any) -> Any:
        return readable_list(
            PlayerProfileBase,
            value,
            accept=lambda e: isinstance(e, dict),
            keep=lambda e: js_truthy(e.get("OID")),
            warn=logger,
            what="applicant records",
        )

    def owner_of(self, application: AllianceApplication) -> PlayerProfileBase | None:
        """The applicant's owner record, None when the reply has none."""
        return next((o for o in self.owners if o.player_id == application.player_id), None)


# =============================================================================
# AAA - Answer an application
# =============================================================================


class AnswerApplicationRequest(BaseRequest):
    """
    Accept or refuse an application.

    Command: aaa
    Payload: {"PID": player_id, "A": 1 or 0}

    Client: ``C2SAllianceAnswerApplicationVO`` (bundle line 70244), sent by
    ``CastleAllianceReadApplicationDialog.onAcceptApplication`` and
    ``onDenyApplication`` (bundle line 70231)
    """

    command = "aaa"

    player_id: int = Field(alias="PID", description="The applicant's AllianceApplication.player_id")
    accept: int = Field(alias="A", description="1 to accept, 0 to refuse")

    @classmethod
    def create(cls, player_id: int, accept: bool) -> AnswerApplicationRequest:
        return cls(PID=player_id, A=1 if accept else 0)


class AnswerApplicationResponse(BaseResponse):
    """
    The answer to answering an application; the client reads nothing from it.

    Command: aaa

    Client: ``AAACommand.executeCommand`` (bundle line 121191)
    """

    command = "aaa"


# =============================================================================
# AQI - Leave the alliance
# =============================================================================


class QuitAllianceRequest(BaseRequest):
    """
    Leave your alliance.

    Command: aqi
    Payload: {}

    Client: ``C2SAllianceQuitVO`` (bundle line 69639), sent by
    ``CastleAllianceDialogManagement.quitAlliance`` (bundle line 69616)
    """

    command = "aqi"


class QuitAllianceResponse(BaseResponse):
    """
    The answer to leaving; its ``gal`` block stays in the extra fields.

    Command: aqi

    Client: ``AQICommand.executeCommand`` (bundle line 121556)
    """

    command = "aqi"


__all__ = [
    "KickMemberRequest",
    "KickMemberResponse",
    "RerankMemberRequest",
    "RerankMemberResponse",
    "InvitePlayerRequest",
    "InvitePlayerResponse",
    "AllianceApplicationListRequest",
    "AllianceApplication",
    "AllianceApplicationListResponse",
    "AnswerApplicationRequest",
    "AnswerApplicationResponse",
    "QuitAllianceRequest",
    "QuitAllianceResponse",
]
