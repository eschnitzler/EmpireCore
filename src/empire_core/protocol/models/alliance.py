"""
Alliance protocol models.

Commands:
- ain: Get alliance info (includes member list)
- ahc: Help a specific member (heal/repair/recruit)
- aha: Help all members
- ahr: Request help from alliance
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from .base import BasePayload, BaseRequest, BaseResponse, HelpType

# =============================================================================
# Alliance Member Model
# =============================================================================


class MemberEmblem(BasePayload):
    """Member's emblem/avatar configuration."""

    background_type: int = Field(alias="BGT", default=0)
    background_color1: int = Field(alias="BGC1", default=0)
    background_color2: int = Field(alias="BGC2", default=0)
    symbol_type: int = Field(alias="SPT", default=0)
    symbol1: int = Field(alias="S1", default=0)
    symbol_color1: int = Field(alias="SC1", default=0)
    symbol2: int = Field(alias="S2", default=0)
    symbol_color2: int = Field(alias="SC2", default=0)
    icon_style: int = Field(alias="IS", default=0)


class MemberCastle(BasePayload):
    """
    Member castle position info from AP array.

    AP array format: [[kingdom, area_id, x, y, castle_type], ...]
    """

    kingdom: int = 0
    area_id: int = 0
    x: int = 0
    y: int = 0
    castle_type: int = 0  # 1=main castle, 4=outpost

    @classmethod
    def from_list(cls, data: list) -> "MemberCastle":
        """Parse from AP array entry."""
        return cls(
            kingdom=data[0] if len(data) > 0 else 0,
            area_id=data[1] if len(data) > 1 else 0,
            x=data[2] if len(data) > 2 else 0,
            y=data[3] if len(data) > 3 else 0,
            castle_type=data[4] if len(data) > 4 else 0,
        )


class AllianceMember(BasePayload):
    """
    Alliance member information from ain response.

    Server field mapping:
    - OID: Player/Object ID
    - N: Player Name
    - L: Level
    - LL: Legendary Level
    - H: Hours since last seen (0 = currently online)
    - AR: Alliance Rank (0=member, 8=leader, etc.)
    - CF: Castle count (main castles)
    - HF: Total castles including outposts
    - MP: Might/Power points
    - E: Emblem configuration
    - DUM: Is dummy/inactive account
    - AVP: Avatar points
    - PRE: Title prefix
    - SUF: Title suffix
    - R: Global rank
    - AID: Alliance ID
    - AN: Alliance Name
    - AP: Castle positions [[kingdom, area_id, x, y, type], ...]
    - SA: Special ability/status
    - VF: VIP flag
    - PF: Premium flag
    """

    player_id: int = Field(alias="OID", default=0)
    name: str = Field(alias="N", default="Unknown")
    level: int = Field(alias="L", default=0)
    legendary_level: int = Field(alias="LL", default=0)
    hours_since_online: int = Field(alias="H", default=0)
    alliance_rank: int = Field(alias="AR", default=0)
    castle_count: int = Field(alias="CF", default=0)
    total_castles: int = Field(alias="HF", default=0)
    might: int = Field(alias="MP", default=0)

    # Additional fields
    is_dummy: bool = Field(alias="DUM", default=False)
    avatar_points: int = Field(alias="AVP", default=0)
    title_prefix: int = Field(alias="PRE", default=0)
    title_suffix: int = Field(alias="SUF", default=-1)
    global_rank: int = Field(alias="R", default=0)
    alliance_id: int = Field(alias="AID", default=0)
    alliance_name: str = Field(alias="AN", default="")
    special_ability: int = Field(alias="SA", default=0)
    vip_flag: int = Field(alias="VF", default=0)
    premium_flag: int = Field(alias="PF", default=0)
    top_ranking: int = Field(alias="TOPX", default=-1)
    report_type: int = Field(alias="RPT", default=0)
    resource_request_date: int = Field(alias="RRD", default=0)
    title_index: int = Field(alias="TI", default=-1)

    # Emblem
    emblem: MemberEmblem | None = Field(alias="E", default=None)

    # Castle positions (raw - can be parsed with MemberCastle.from_list)
    castle_positions: list = Field(alias="AP", default_factory=list)
    village_positions: list = Field(alias="VP", default_factory=list)

    @property
    def is_online(self) -> bool:
        """Check if the member is currently online (H=0 means online)."""
        return self.hours_since_online == 0

    @property
    def last_seen_hours(self) -> int:
        """Get hours since the member was last online."""
        return self.hours_since_online

    @property
    def castles(self) -> list[MemberCastle]:
        """Parse castle positions into MemberCastle objects."""
        return [MemberCastle.from_list(pos) for pos in self.castle_positions]

    @property
    def is_leader(self) -> bool:
        """Check if member is alliance leader (AR=8)."""
        return self.alliance_rank == 8

    @property
    def is_officer(self) -> bool:
        """Check if member is an officer (AR > 0 and < 8)."""
        return 0 < self.alliance_rank < 8


# =============================================================================
# Alliance Building Model
# =============================================================================


class AllianceBuilding(BasePayload):
    """Alliance building info from ABL array."""

    building_type: int = Field(alias="BT", default=0)
    level: int = Field(alias="L", default=0)
    cooldown: int = Field(alias="CD", default=-1)


# =============================================================================
# Alliance Storage Model
# =============================================================================


class AllianceStorage(BasePayload):
    """Alliance storage/treasury from STO object."""

    stone: int = Field(alias="S", default=0)
    wood: int = Field(alias="W", default=0)
    food: int = Field(alias="O", default=0)  # O for food? might be oil
    coins1: int = Field(alias="C1", default=0)
    gold: int = Field(alias="G", default=0)
    coins2: int = Field(alias="C2", default=0)
    coins: int = Field(alias="C", default=0)
    iron: int = Field(alias="I", default=0)


# =============================================================================
# Alliance Info Model
# =============================================================================


class AllianceInfo(BasePayload):
    """
    Full alliance information from ain response.

    Contains alliance details, member list, buildings, storage, etc.
    """

    alliance_id: int = Field(alias="AID", default=0)
    name: str = Field(alias="N", default="")
    members: list[AllianceMember] = Field(alias="M", default_factory=list)

    # Alliance stats
    castle_count: int = Field(alias="CF", default=0)
    total_castles: int = Field(alias="HF", default=0)
    might: int = Field(alias="MP", default=0)
    highest_alliance_might: int = Field(alias="HAMP", default=0)
    description: str = Field(alias="D", default="")
    language: str = Field(alias="ALL", default="en")

    # Alliance settings
    homepage: int = Field(alias="HP", default=0)
    invite_only: int = Field(alias="IS", default=0)
    ignore_applications: int = Field(alias="IA", default=0)
    kick_applications: int = Field(alias="KA", default=0)
    abbreviation: str = Field(alias="A", default="")
    friendly_raids: int = Field(alias="FR", default=0)
    support_priority: int = Field(alias="SP", default=0)
    auto_accept: int = Field(alias="AA", default=0)
    alliance_war: int = Field(alias="AW", default=0)
    member_limit: int = Field(alias="ML", default=0)
    attack_protection: int = Field(alias="AP", default=0)
    required_trust: int = Field(alias="RT", default=-1)
    message_filter: int = Field(alias="MF", default=0)
    invite_friends: int = Field(alias="IF", default=0)

    # Alliance resources
    storage: AllianceStorage | None = Field(alias="STO", default=None)

    # Alliance buildings
    buildings: list[AllianceBuilding] = Field(alias="ABL", default_factory=list)

    # Member info arrays (for donation tracking etc)
    # AMI: [[player_id, donations...], ...]
    member_info: list = Field(alias="AMI", default_factory=list)

    # Alliance diplomacy lists
    alliance_diplomacy: list = Field(alias="ADL", default_factory=list)
    alliance_contracts: list = Field(alias="ACA", default_factory=list)
    alliance_truces: list = Field(alias="ATC", default_factory=list)
    alliance_kingdoms: list = Field(alias="AKT", default_factory=list)
    alliance_monuments: list = Field(alias="AMO", default_factory=list)
    alliance_landmarks: list = Field(alias="ALA", default_factory=list)

    # Resource usage flags
    spend_resources_food_upgrade: int = Field(alias="SRFU", default=0)
    help_resources_food_upgrade: int = Field(alias="HRFU", default=0)

    @property
    def member_count(self) -> int:
        """Get the number of members."""
        return len(self.members)

    @property
    def online_members(self) -> list[AllianceMember]:
        """Get list of currently online members."""
        return [m for m in self.members if m.is_online]

    @property
    def online_count(self) -> int:
        """Get count of online members."""
        return len(self.online_members)


# =============================================================================
# AIN - Get Alliance Info
# =============================================================================


class GetAllianceInfoRequest(BaseRequest):
    """
    Request alliance information including member list.

    Command: ain
    Payload: {"AID": alliance_id}

    Returns full alliance info with all members, their online status
    (via hours_since_online), level, rank, castle count, and might.
    """

    command = "ain"

    alliance_id: int = Field(alias="AID")


class GetAllianceInfoResponse(BaseResponse):
    """
    Response containing alliance information.

    Command: ain
    Payload: {"A": {"AID": ..., "N": ..., "M": [...], ...}}
    """

    command = "ain"

    alliance: AllianceInfo = Field(alias="A")
    error_code: int = Field(alias="E", default=0)

    @property
    def members(self) -> list[AllianceMember]:
        """Convenience accessor for alliance members."""
        return self.alliance.members

    @property
    def online_members(self) -> list[AllianceMember]:
        """Get list of currently online members."""
        return self.alliance.online_members


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
    # Alliance Member
    "AllianceMember",
    "AllianceInfo",
    "AllianceBuilding",
    "AllianceStorage",
    "MemberEmblem",
    "MemberCastle",
    # AIN - Get Alliance Info
    "GetAllianceInfoRequest",
    "GetAllianceInfoResponse",
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
