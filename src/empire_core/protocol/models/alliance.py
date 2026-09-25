"""
Alliance protocol models.

Commands:
- ain: Get alliance info (includes member list)
- ahc: Help a specific member (heal/repair/recruit)
- aha: Help all members
- ahr: Request help from alliance
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator

from .base import BasePayload, BaseRequest, BaseResponse, ClientInt, HelpType
from .map import MapAreaItem, MapObject, parse_area_rows
from .profile import PlayerProfileBase

logger = logging.getLogger(__name__)

# =============================================================================
# Alliance Member Model
# =============================================================================


class AllianceMember(PlayerProfileBase):
    """
    Alliance member information from ain response.

    Common profile fields (OID/N/L/LL/H/AR/CF/HF/MP/DUM/AVP/PRE/SUF/TOPX/
    SA/VF/PF/RRD/TI/RPT/AID/AN/AP/VP/E) are inherited from PlayerProfileBase.

    Note: Activity status comes from the AMI array in AllianceInfo
    (``AllianceMemberInfo.login_activity``), not the H field.
    Activity tiers: 0=online, 1=<12hrs, 2=<48hrs, 3=<7days, 4=7+days offline.
    """

    name: str = Field(alias="N", default="Unknown")

    # The meaning of "R" is unverified: an earlier docstring called it "Global rank",
    # while the field name says ruins. Kept as-is to preserve current behavior.
    is_in_ruins: bool = Field(alias="R", default=False)

    # Activity tier (populated from AMI array, not from server directly)
    # None means unknown, 0-4 are the activity tiers from the server
    _activity_tier: int | None = None

    @property
    def activity_tier(self) -> int | None:
        """
        Get the member's activity tier from AMI array (index 4).

        Activity tiers:
        - 0: Online now
        - 1: Offline < 12 hours
        - 2: Offline < 48 hours
        - 3: Offline < 7 days
        - 4: Offline 7+ days

        Returns None if activity status is unknown.
        """
        return self._activity_tier

    @property
    def is_online(self) -> bool:
        """
        Check if the member is currently online.

        Returns True only if activity_tier == 0.
        Returns False if offline or unknown.
        """
        return self._activity_tier == 0


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


_MEMBER_INFO_FIELDS = (
    "player_id",
    "given_c1",
    "given_c2",
    "given_resources",
    "login_activity",
    "capital_count",
    "metropolis_count",
    "kings_tower_count",
    "monument_count",
    "laboratory_count",
    "daily_fame",
)


class AllianceMemberInfo(BasePayload):
    """
    A member's extra alliance info: one ``AMI`` row.

    Client: ``AdditionalMemberInfoVO.parseAMI`` (bundle line 66296) shifts the
    fields off in this order and reads each with ``int``, so a missing field is 0.
    """

    player_id: ClientInt = Field(default=0, description="row[0]")
    given_c1: ClientInt = Field(default=0, description="row[1]: C1 the member donated to the alliance (givenC1)")
    given_c2: ClientInt = Field(default=0, description="row[2]: C2 the member donated to the alliance (givenC2)")
    given_resources: ClientInt = Field(default=0, description="row[3]: resources the member donated")
    login_activity: ClientInt = Field(
        default=0,
        description="row[4]: AllianceConst.ONLINESTATE_*: 0 online, 1 last 12 hours, 2 last 48 hours, "
        "3 last week, 4 longer ago",
    )
    capital_count: ClientInt = Field(default=0, description="row[5]: capitals the member holds")
    metropolis_count: ClientInt = Field(default=0, description="row[6]: metropolises the member holds")
    kings_tower_count: ClientInt = Field(default=0, description="row[7]: kings towers the member holds")
    monument_count: ClientInt = Field(default=0, description="row[8]: monuments the member holds")
    laboratory_count: ClientInt = Field(default=0, description="row[9]: laboratories the member holds")
    daily_fame: ClientInt = Field(default=0, description="row[10]: fame gained today")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list):
            return dict(zip(_MEMBER_INFO_FIELDS, data, strict=False))
        return data


class AllianceDiplomacyStatus(BasePayload):
    """
    The alliance's standing with one other alliance: an ``ADL`` entry.

    Client: ``AllianceInfoVO.parseStatusList`` (bundle line 25973) into an
    ``OtherAllianceStatusListItemVO`` (bundle line 66330).
    """

    alliance_id: ClientInt = Field(alias="AID", default=0, description="The other alliance")
    alliance_name: str | None = Field(alias="AN", default=None, description="The other alliance's name")
    status: ClientInt = Field(
        alias="AS",
        default=0,
        description="AllianceConst.DIPLOMACY_*: 0 at war, 1 neutral, 2 soft allied, 3 real allied",
    )
    status_confirmed: ClientInt = Field(
        alias="AC",
        default=0,
        description="AllianceConst.DIPLOMACY_CONFIRMED (1) once agreed, DIPLOMACY_REQUEST (0) while only requested",
    )


# =============================================================================
# Alliance Info Model
# =============================================================================


class AllianceInfo(BasePayload):
    """
    Full alliance information from ain response.

    Contains alliance details, member list, buildings, storage, etc.

    Client: ``AllianceInfoVO.fillFromParamObject`` (bundle line 25928)
    """

    alliance_id: int = Field(alias="AID", default=0)
    name: str = Field(alias="N", default="")
    members: list[AllianceMember] = Field(alias="M", default_factory=list)

    fame_points: ClientInt = Field(alias="CF", default=0, description="Alliance fame points")
    highest_fame_points: ClientInt = Field(alias="HF", default=0, description="Highest fame points reached")
    might: ClientInt = Field(alias="MP", default=0)
    highest_alliance_might: ClientInt = Field(alias="HAMP", default=0)
    description: str = Field(alias="D", default="")
    announcement: str = Field(alias="A", default="", description="The alliance's announcement")
    language: str = Field(alias="ALL", default="en")
    external_member_level: ClientInt = Field(alias="ML", default=0)
    status_to_own_alliance: ClientInt = Field(
        alias="DOA",
        default=0,
        description="Diplomacy status towards the player's own alliance (AllianceConst.DIPLOMACY_*)",
    )
    is_searching_members: bool = Field(alias="IS", default=False, description="The alliance is looking for players")
    is_accepting_members: bool = Field(alias="IA", default=False, description="Players may apply to join")
    application_count: ClientInt = Field(alias="AA", default=0, description="Pending applications")
    auto_war: bool = Field(alias="AW", default=False)
    aqua_points: int | float = Field(alias="AP", default=0)
    free_renames: ClientInt = Field(alias="FR", default=0)
    can_be_invited_to_hard_pact: bool = Field(alias="HP", default=False)
    can_be_invited_to_soft_pact: bool = Field(alias="SP", default=False)
    is_able_to_forge: bool = Field(alias="MF", default=False)
    is_forge_inventory_full: bool = Field(alias="IF", default=False)
    soft_relic_forge_uses: ClientInt = Field(alias="SRFU", default=0)
    hard_relic_forge_uses: ClientInt = Field(alias="HRFU", default=0)
    is_king_alliance: bool = Field(alias="KA", default=False)

    @field_validator("is_searching_members", "is_accepting_members", mode="before")
    @classmethod
    def _truthy_flag(cls, value: Any) -> bool:
        return bool(value)

    @field_validator(
        "auto_war", "can_be_invited_to_hard_pact", "can_be_invited_to_soft_pact", "is_able_to_forge",
        "is_forge_inventory_full", "is_king_alliance", mode="before",
    )  # fmt: skip
    @classmethod
    def _one_flag(cls, value: Any) -> bool:
        return value == 1

    @field_validator("description", "announcement", mode="before")
    @classmethod
    def _text(cls, value: Any) -> Any:
        return "" if value is None else value

    # Alliance resources
    storage: AllianceStorage | None = Field(alias="STO", default=None)

    # Alliance buildings
    buildings: list[AllianceBuilding] = Field(alias="ABL", default_factory=list)

    member_info: list[AllianceMemberInfo] = Field(
        alias="AMI", default_factory=list, description="Donations, activity and landmark counts per member"
    )
    alliance_diplomacy: list[AllianceDiplomacyStatus] = Field(
        alias="ADL", default_factory=list, description="The alliance's standing with other alliances"
    )
    capitals: list[MapAreaItem] = Field(
        alias="ACA", default_factory=list, description="Map rows of the alliance's capitals (CapitalMapobjectVO)"
    )
    metropolises: list[MapAreaItem] = Field(
        alias="ATC", default_factory=list, description="Map rows of the alliance's metropolises (MetropolMapobjectVO)"
    )
    kings_towers: list[MapAreaItem] = Field(
        alias="AKT", default_factory=list, description="Map rows of the alliance's kings towers (KingstowerMapobjectVO)"
    )
    monuments: list[MapAreaItem] = Field(
        alias="AMO", default_factory=list, description="Map rows of the alliance's monuments (MonumentMapobjectVO)"
    )
    laboratories: list[MapAreaItem] = Field(
        alias="ALA", default_factory=list, description="Map rows of the alliance's laboratories (LaboratoryMapobjectVO)"
    )

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

    @field_validator("member_info", mode="before")
    @classmethod
    def _member_info_rows(cls, value: Any) -> Any:
        # The client shifts fields off each row; one that is not a row is skipped here instead of failing the reply
        if not isinstance(value, list):
            return []
        rows = [row for row in value if isinstance(row, list)]
        if len(rows) < len(value):
            logger.warning(
                f"Skipped {len(value) - len(rows)}/{len(value)} malformed AMI entries; "
                "member activity status may be incomplete"
            )
        return rows

    @field_validator("alliance_diplomacy", mode="before")
    @classmethod
    def _diplomacy_entries(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return []
        return [entry for entry in value if isinstance(entry, dict)]

    @field_validator("capitals", "metropolises", "kings_towers", "monuments", "laboratories", mode="before")
    @classmethod
    def _landmark_rows(cls, value: Any) -> Any:
        """Client: ``AllianceLandmarksList.parseCompleteLandmarksList`` (bundle line 42738)."""
        items, skipped = parse_area_rows(value)
        if skipped:
            logger.warning(f"Skipped {skipped}/{len(value)} unparseable alliance landmark rows")
        return items

    def model_post_init(self, __context) -> None:
        """Populate member activity tier from AMI array after parsing."""
        self._populate_activity_tier()

    def _populate_activity_tier(self) -> None:
        """
        Give each member the login activity of its AMI row.

        Client: ``AllianceInfoVO.parseAMI`` (bundle line 25947) keys the rows by
        player id, and ``getOnlineUserList`` reads ``loginActivity`` from them.
        """
        activity_lookup = {info.player_id: info.login_activity for info in self.member_info}
        for member in self.members:
            if member.player_id in activity_lookup:
                member._activity_tier = activity_lookup[member.player_id]


# =============================================================================
# AIN - Get Alliance Info
# =============================================================================


class GetAllianceInfoRequest(BaseRequest):
    """
    Request alliance information including member list.

    Command: ain
    Payload: {"AID": alliance_id}

    Returns full alliance info with all members, their online status
    (via AMI array), level, rank, castle count, and might.
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

    alliance: AllianceInfo | None = Field(alias="A", default=None)

    @property
    def members(self) -> list[AllianceMember]:
        """Convenience accessor for alliance members."""
        return self.alliance.members if self.alliance else []

    @property
    def online_members(self) -> list[AllianceMember]:
        """Get list of currently online members."""
        return self.alliance.online_members if self.alliance else []


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


# =============================================================================
# Alliance Help Notification (received when someone asks for help)
# =============================================================================


class HelpRequestNotification(BaseResponse):
    """
    Notification received when an alliance member asks for help.

    This is a push notification from the server.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    player_id: int = Field(alias="PID", default=0)
    player_name: str = Field(alias="PN", default="")
    castle_id: int = Field(alias="CID", default=0)
    help_type: int = Field(alias="HT", default=0)
    building_id: int | None = Field(alias="BID", default=None)


# =============================================================================
# GBL - Get Alliance Bookmarks
# =============================================================================


class GetAllianceBookmarksRequest(BaseRequest):
    """
    Request alliance bookmarks.

    Command: gbl
    Payload: {} (empty)
    """

    command = "gbl"


class AllianceBookmark(BasePayload):
    """
    Alliance bookmark information from GBL response.

    Client: ``CastleBookmarkData.parseBookmarkObject`` (bundle line 33427) and
    ``CastleWorldmapBookmarkVO.parseParamObject`` (bundle line 68469).
    """

    name: str = Field(alias="N", default="")
    owner: MapObject | None = Field(
        alias="OI",
        default=None,
        description="The owner record of the bookmarked target, which the client parses with parseOwnerInfoArray",
    )

    @field_validator("owner", mode="before")
    @classmethod
    def _owner_needs_an_object(cls, value: Any) -> Any:
        return value if isinstance(value, dict) else None


class GetAllianceBookmarksResponse(BaseResponse):
    """
    Response containing alliance bookmarks.

    Command: gbl
    Payload: {"ABL": [{"N": "name", "OI": {...}}, ...]}
    """

    command = "gbl"

    bookmarks: list[AllianceBookmark] = Field(alias="ABL", default_factory=list)


# =============================================================================
# HGH - Search Alliance (Highscore/Search)
# =============================================================================


class AllianceSearchResult(BasePayload):
    """
    One row of an alliance highscore list: ``[rank, score, [alliance_id, name, member_count, fame_points]]``.

    Client: ``CastleHighscoreDialog.onGetHighscoreData`` (bundle line 27538)
    shifts rank and score off an alliance list's row and fills an
    ``AllianceHighscoreInfoVO`` (bundle line 27680) from the third field, which
    it ignores unless that is an array. Every number is read with ``int``.
    """

    rank: ClientInt = Field(default=0, description="row[0]")
    score: ClientInt = Field(default=0, description="row[1]: the listed value, the alliance's might for LT 11")
    alliance_id: ClientInt = Field(default=0, description="row[2][0]")
    name: str = Field(default="", description="row[2][1]")
    member_count: ClientInt = Field(default=0, description="row[2][2]")
    fame_points: ClientInt = Field(default=0, description="row[2][3]: the alliance's current fame")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        fields: dict[str, Any] = dict(zip(("rank", "score"), data[:2], strict=False))
        info = data[2] if len(data) > 2 else None
        if isinstance(info, list):
            fields.update(zip(("alliance_id", "name", "member_count", "fame_points"), info, strict=False))
            if "name" in fields:
                fields["name"] = "" if fields["name"] is None else str(fields["name"])
        return fields


class SearchAllianceRequest(BaseRequest):
    """
    Search for an alliance.

    Command: hgh
    Payload: {"LT": 11, "LID": 6, "SV": name_query}
    """

    command = "hgh"

    list_type: int = Field(alias="LT", default=11)  # 11 = Alliance Highscore
    list_id: int = Field(alias="LID", default=6)  # 6 = Search?
    search_value: str = Field(alias="SV")

    @classmethod
    def create(cls, query: str) -> "SearchAllianceRequest":
        return cls(SV=query)


class SearchAllianceResponse(BaseResponse, register=False):
    """
    Response to alliance search.

    Command: hgh — shared with GetHighscoreResponse, which owns the registry
    entry; this model is instantiated manually by AllianceService.

    Not registered: see class docstring.
    """

    command = "hgh"

    results: list[AllianceSearchResult] = Field(alias="L", default_factory=list, description="The matching rows")

    @field_validator("results", mode="before")
    @classmethod
    def _rows(cls, value: Any) -> Any:
        # The client shifts fields off each row; one that is not a row is skipped instead of failing the reply
        if not isinstance(value, list):
            return []
        rows = []
        for row in value:
            if not isinstance(row, list):
                continue
            try:
                rows.append(AllianceSearchResult.model_validate(row))
            except ValidationError:
                continue
        if len(rows) < len(value):
            logger.warning(f"Skipped {len(value) - len(rows)}/{len(value)} malformed alliance search rows")
        return rows


__all__ = [
    # Alliance Member
    "AllianceMember",
    "AllianceInfo",
    "AllianceBuilding",
    "AllianceStorage",
    "AllianceMemberInfo",
    "AllianceDiplomacyStatus",
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
    # ABO - Alliance Bookmarks
    "GetAllianceBookmarksRequest",
    "GetAllianceBookmarksResponse",
    "AllianceBookmark",
    # Notifications
    "HelpRequestNotification",
]
