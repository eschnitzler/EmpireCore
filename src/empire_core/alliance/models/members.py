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
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, js_number_or_none, js_truthy
from empire_core.protocol.text import decode_json_text

from .info import AllianceInfo, alliance_of_ain

logger = logging.getLogger(__name__)


class _AllianceEcho(BaseResponse):
    """A reply that carries the updated alliance as a nested ain reply."""

    alliance: AllianceInfo | None = Field(
        validation_alias="ain", serialization_alias="ain", default=None, description="The alliance after the change"
    )

    @field_validator("alliance", mode="before")
    @classmethod
    def _alliance(cls, value: Any) -> Any:
        return alliance_of_ain(value)


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

    player_id: int = Field(
        validation_alias="PID", serialization_alias="PID", description="The member's AllianceMember.player_id"
    )


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

    player_id: int = Field(
        validation_alias="PID", serialization_alias="PID", description="The member's AllianceMember.player_id"
    )
    rank: AllianceRank = Field(validation_alias="R", serialization_alias="R", description="The new rank")


class RerankMemberResponse(_AllianceEcho):
    """
    The alliance after a rank change.

    Command: arm

    Client: ``ARMCommand.executeCommand`` (bundle line 121589); it takes ``NO_CHANGE``
    as nothing to do
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

    search_value: str = Field(
        validation_alias="SV", serialization_alias="SV", description="The player's id, as a string"
    )

    @classmethod
    def for_player(cls, player_id: int) -> InvitePlayerRequest:
        """Invite the player ``player_id``."""
        return cls(search_value=str(player_id))


class InvitePlayerResponse(BaseResponse):
    """
    The answer to an invitation; ``INVALID_PLAYER_ID`` when there is no such player.

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

    player_id: ClientInt = Field(
        validation_alias="PID", serialization_alias="PID", default=0, description="The applying player's id"
    )
    distance: ClientInt = Field(
        validation_alias="D", serialization_alias="D", default=0, description="Distance to the applicant"
    )
    text: str = Field(
        validation_alias="AT", serialization_alias="AT", default="", description="The application's text, decoded"
    )
    seconds_since_applied: int | float = Field(
        validation_alias="AA", serialization_alias="AA", default=0, description="Seconds since the application"
    )

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
        validation_alias="AL",
        serialization_alias="AL",
        default_factory=list,
        description="The applications, nearest first",
    )
    owners: list[PlayerProfileBase] = Field(
        validation_alias="OI", serialization_alias="OI", default_factory=list, description="The applicants"
    )

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

    player_id: int = Field(
        validation_alias="PID", serialization_alias="PID", description="The applicant's AllianceApplication.player_id"
    )
    accept: int = Field(validation_alias="A", serialization_alias="A", description="1 to accept, 0 to refuse")

    @classmethod
    def create(cls, player_id: int, accept: bool) -> AnswerApplicationRequest:
        return cls(player_id=player_id, accept=1 if accept else 0)


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
