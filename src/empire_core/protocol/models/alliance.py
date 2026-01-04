"""
Alliance protocol models.

Commands:
- ahc: Help a specific member (heal/repair/recruit)
- aha: Help all members
- ahr: Request help from alliance
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from .base import BaseRequest, BaseResponse, HelpType

# =============================================================================
# AHC - Help Member
# =============================================================================


class HelpMemberRequest(BaseRequest):
    """
    Help a specific alliance member.

    Command: ahc
    Payload: {"PID": player_id, "CID": castle_id, "HT": help_type}

    Help types (HT):
    - 2: Heal wounded soldiers
    - 3: Repair building
    - 6: Recruit soldiers
    """

    command = "ahc"

    player_id: int = Field(alias="PID")
    castle_id: int = Field(alias="CID")
    help_type: int = Field(alias="HT")

    @classmethod
    def heal(cls, player_id: int, castle_id: int) -> "HelpMemberRequest":
        """Create a heal help request."""
        return cls(PID=player_id, CID=castle_id, HT=HelpType.HEAL)

    @classmethod
    def repair(cls, player_id: int, castle_id: int) -> "HelpMemberRequest":
        """Create a repair help request."""
        return cls(PID=player_id, CID=castle_id, HT=HelpType.REPAIR)

    @classmethod
    def recruit(cls, player_id: int, castle_id: int) -> "HelpMemberRequest":
        """Create a recruit help request."""
        return cls(PID=player_id, CID=castle_id, HT=HelpType.RECRUIT)


class HelpMemberResponse(BaseResponse):
    """
    Response to helping a member.

    Command: ahc
    """

    command = "ahc"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# AHA - Help All
# =============================================================================


class HelpAllRequest(BaseRequest):
    """
    Help all alliance members who need help.

    Command: aha
    Payload: {} (empty) or {"HT": help_type}
    """

    command = "aha"

    help_type: int | None = Field(alias="HT", default=None)


class HelpAllResponse(BaseResponse):
    """
    Response to helping all members.

    Command: aha
    """

    command = "aha"

    helped_count: int = Field(alias="HC", default=0)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# AHR - Ask for Help
# =============================================================================


class AskHelpRequest(BaseRequest):
    """
    Request help from alliance members.

    Command: ahr
    Payload: {"CID": castle_id, "HT": help_type, "BID": building_id}

    Help types (HT):
    - 2: Heal wounded soldiers
    - 3: Repair building (requires BID)
    - 6: Recruit soldiers
    """

    command = "ahr"

    castle_id: int = Field(alias="CID")
    help_type: int = Field(alias="HT")
    building_id: int | None = Field(alias="BID", default=None)

    @classmethod
    def heal(cls, castle_id: int) -> "AskHelpRequest":
        """Request heal help."""
        return cls(CID=castle_id, HT=HelpType.HEAL)

    @classmethod
    def repair(cls, castle_id: int, building_id: int) -> "AskHelpRequest":
        """Request repair help for a building."""
        return cls(CID=castle_id, HT=HelpType.REPAIR, BID=building_id)

    @classmethod
    def recruit(cls, castle_id: int) -> "AskHelpRequest":
        """Request recruit help."""
        return cls(CID=castle_id, HT=HelpType.RECRUIT)


class AskHelpResponse(BaseResponse):
    """
    Response to asking for help.

    Command: ahr
    """

    command = "ahr"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# Alliance Help Notification (received when someone asks for help)
# =============================================================================


class HelpRequestNotification(BaseResponse):
    """
    Notification received when an alliance member asks for help.

    This is a push notification from the server.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    player_id: int = Field(alias="PID")
    player_name: str = Field(alias="PN")
    castle_id: int = Field(alias="CID")
    help_type: int = Field(alias="HT")
    building_id: int | None = Field(alias="BID", default=None)


__all__ = [
    # AHC - Help Member
    "HelpMemberRequest",
    "HelpMemberResponse",
    # AHA - Help All
    "HelpAllRequest",
    "HelpAllResponse",
    # AHR - Ask Help
    "AskHelpRequest",
    "AskHelpResponse",
    # Notifications
    "HelpRequestNotification",
]
