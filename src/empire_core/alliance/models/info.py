"""Alliance info models.

Commands:
- ain: Get alliance info (includes member list)
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, field_validator, model_validator

from empire_core.enums import DiplomacyStatus, OnlineState
from empire_core.map.models.items import MapAreaItem, parse_area_rows
from empire_core.player.models.profile import PlayerProfileBase
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, enum_or_none
from empire_core.protocol.js import ClientInt, ParseInt, js_floor, js_loose_equals, js_truthy
from empire_core.protocol.text import decode_json_text

logger = logging.getLogger(__name__)


# =============================================================================
# Alliance Member Model
# =============================================================================


class AllianceMember(PlayerProfileBase):
    """
    One member of an ain reply's ``M`` list: an owner record.

    The member's login activity comes from the alliance's ``AMI`` row for it
    (``AllianceMemberInfo.login_activity``), an :class:`OnlineState` value.

    Client: ``AllianceInfoVO.parseMemberList`` (bundle line 25968) reads each
    entry with ``CastleOtherPlayerData.parseOwnerInfo`` (bundle line 138996)
    """

    # Activity tier (populated from AMI array, not from server directly)
    # None means unknown, otherwise an OnlineState value
    _activity_tier: int | None = None

    @property
    def activity_tier(self) -> int | None:
        """
        Get the member's activity tier from AMI array (index 4), an
        :class:`OnlineState` value.

        Returns None if activity status is unknown.
        """
        return self._activity_tier

    @property
    def is_online(self) -> bool:
        """
        Check if the member is currently online.

        Returns True only if activity_tier is OnlineState.ONLINE.
        Returns False if offline or unknown.
        """
        return self._activity_tier == OnlineState.ONLINE


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

StorageAmount = Annotated[int, BeforeValidator(js_floor)]


class AllianceStorage(BasePayload):
    """
    The alliance treasury, the ``STO`` block.

    The client reads one key per ``allianceFundsDonatables`` row of the item
    data, so a later items version can add keys; these are the rows of v786.03.
    On an alliance battle ground server it reads the event's alliance currency
    instead of ``AIN``; that key stays in the model's extra fields.

    Client: ``AllianceInfoVO.parseStorageFromServer`` (bundle line 25940), each key from
    ``CollectableHelper.getServerKeyByCollectable`` (bundle line 1646) over
    ``AllianceFundsDonatableVO`` (bundle line 66532); amounts floored by
    ``ACollectableItemVO.amount`` (bundle line 3575)
    """

    wood: StorageAmount = Field(alias="W", default=0, description="Wood")
    stone: StorageAmount = Field(alias="S", default=0, description="Stone")
    coins: StorageAmount = Field(alias="C1", default=0, description="Coins")
    rubies: StorageAmount = Field(alias="C2", default=0, description="Rubies")
    iron: StorageAmount = Field(alias="I", default=0, description="Iron")
    oil: StorageAmount = Field(alias="O", default=0, description="Olive oil")
    glass: StorageAmount = Field(alias="G", default=0, description="Glass")
    coal: StorageAmount = Field(alias="C", default=0, description="Charcoal")
    fury_doubloons: StorageAmount = Field(alias="FD", default=0, description="Fury doubloons")
    time_doubloons: StorageAmount = Field(alias="TD", default=0, description="Time doubloons")
    spirit_doubloons: StorageAmount = Field(alias="SD", default=0, description="Spirit doubloons")
    vigor_doubloons: StorageAmount = Field(alias="VD", default=0, description="Vigor doubloons")
    bastion_doubloons: StorageAmount = Field(alias="BD", default=0, description="Bastion doubloons")
    rampart_doubloons: StorageAmount = Field(alias="RD", default=0, description="Rampart doubloons")
    alliance_coins: StorageAmount = Field(alias="AC", default=0, description="Alliance coins")
    rift_coins: StorageAmount = Field(alias="RC", default=0, description="Rift coins")
    legendary_rift_coins: StorageAmount = Field(alias="LRC", default=0, description="Legendary rift coins")
    alliance_influence: StorageAmount = Field(
        alias="AIN", default=0, description="Alliance influence; only on alliance battle ground servers"
    )


_MEMBER_INFO_FIELDS = (
    "player_id",
    "given_coins",
    "given_rubies",
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

    player_id: ClientInt = Field(default=0, description="The member's player id")
    given_coins: ClientInt = Field(default=0, description="Coins the member donated to the alliance")
    given_rubies: ClientInt = Field(default=0, description="Rubies the member donated to the alliance")
    given_resources: ClientInt = Field(default=0, description="Resources the member donated")
    login_activity: ClientInt = Field(
        default=0,
        description="0 online, 1 last 12 hours, 2 last 48 hours, 3 last week, 4 longer ago",
    )
    capital_count: ClientInt = Field(default=0, description="Capitals the member holds")
    metropolis_count: ClientInt = Field(default=0, description="Metropolises the member holds")
    kings_tower_count: ClientInt = Field(default=0, description="Kings towers the member holds")
    monument_count: ClientInt = Field(default=0, description="Monuments the member holds")
    laboratory_count: ClientInt = Field(default=0, description="Laboratories the member holds")
    daily_fame: ClientInt = Field(default=0, description="Fame gained today")

    @property
    def login_activity_enum(self) -> OnlineState | None:
        """``login_activity`` as an :class:`OnlineState`, None for a value the client does not define."""
        return enum_or_none(OnlineState, self.login_activity)

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
        description="0 at war, 1 neutral, 2 soft allied, 3 real allied",
    )
    status_confirmed: ClientInt = Field(
        alias="AC",
        default=0,
        description="1 once agreed, 0 while only requested",
    )

    @property
    def status_enum(self) -> DiplomacyStatus | None:
        """``status`` as a :class:`DiplomacyStatus`, None for a value the client does not define."""
        return enum_or_none(DiplomacyStatus, self.status)


# =============================================================================
# Alliance Info Model
# =============================================================================


class AllianceInfo(BasePayload):
    """
    Full alliance information from ain response.

    Contains alliance details, member list, buildings, storage, etc.

    Client: ``AllianceInfoVO.fillFromParamObject`` (bundle line 25928), ``parseMemberList`` (bundle line 25968),
    ``parseStorageFromServer`` (bundle line 25940), ``parseBuffList`` (bundle line 25955);
    ``CastleAllianceData.parseAllianceInfo`` (bundle line 11609) for ``RT``
    """

    alliance_id: ParseInt = Field(alias="AID", default=0, description="Alliance id")
    name: str = Field(alias="N", default="", description="Alliance name")
    members: list[AllianceMember] = Field(
        alias="M",
        default_factory=list,
        description="Members",
    )

    fame_points: ClientInt = Field(alias="CF", default=0, description="Alliance fame points")
    highest_fame_points: ClientInt = Field(alias="HF", default=0, description="Highest fame points reached")
    might: ParseInt = Field(alias="MP", default=0, description="Alliance might points")
    highest_alliance_might: ParseInt = Field(alias="HAMP", default=0, description="Highest might points reached")
    description: str = Field(alias="D", default="", description="The alliance's description, decoded as chat text")
    announcement: str = Field(alias="A", default=" ", description='The alliance\'s announcement; " " when it has none')
    language: str = Field(alias="ALL", default="en", description="The alliance's language code")
    external_member_level: ParseInt = Field(alias="ML", default=0, description="External member level")
    status_to_own_alliance: ParseInt = Field(
        alias="DOA",
        default=0,
        description="Diplomacy status towards the player's own alliance, a DiplomacyStatus value",
    )
    is_searching_members: bool = Field(alias="IS", default=False, description="The alliance is looking for players")
    is_accepting_members: bool = Field(alias="IA", default=False, description="Players may apply to join")
    application_count: ParseInt = Field(alias="AA", default=0, description="Pending applications")
    auto_war: bool = Field(alias="AW", default=False, description="Auto war is on")
    aqua_points: int | float = Field(alias="AP", default=0, description="Aqua points")
    free_renames: ClientInt = Field(alias="FR", default=0, description="Free alliance renames left")
    can_be_invited_to_hard_pact: bool = Field(alias="HP", default=False, description="Open to hard pact invitations")
    can_be_invited_to_soft_pact: bool = Field(alias="SP", default=False, description="Open to soft pact invitations")
    is_able_to_forge: bool = Field(alias="MF", default=False, description="The alliance forge can be used")
    is_forge_inventory_full: bool = Field(alias="IF", default=False, description="The alliance forge inventory is full")
    soft_relic_forge_uses: ClientInt = Field(alias="SRFU", default=0, description="Soft relic forge uses")
    hard_relic_forge_uses: ClientInt = Field(alias="HRFU", default=0, description="Hard relic forge uses")
    is_king_alliance: bool = Field(alias="KA", default=False, description="The alliance holds the king title")
    refresh_seconds: ClientInt = Field(
        alias="RT",
        default=0,
        description="Seconds until the alliance should be requested again; 0 when none is set",
    )

    @field_validator("is_searching_members", "is_accepting_members", mode="before")
    @classmethod
    def _truthy_flag(cls, value: Any) -> bool:
        return js_truthy(value)

    @field_validator(
        "auto_war", "can_be_invited_to_hard_pact", "can_be_invited_to_soft_pact", "is_able_to_forge",
        "is_forge_inventory_full", "is_king_alliance", mode="before",
    )  # fmt: skip
    @classmethod
    def _one_flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    @model_validator(mode="before")
    @classmethod
    def _forge_fields_come_together(cls, data: Any) -> Any:
        # The client reads MF, IF, SRFU and HRFU only when both MF and IF are sent
        if isinstance(data, dict) and (data.get("MF") is None or data.get("IF") is None):
            return {k: v for k, v in data.items() if k not in ("MF", "IF", "SRFU", "HRFU")}
        return data

    @field_validator("description", "announcement", mode="before")
    @classmethod
    def _chat_text(cls, value: Any) -> Any:
        return decode_json_text(value) if isinstance(value, str) else ""

    @field_validator("announcement", mode="after")
    @classmethod
    def _empty_announcement(cls, value: str) -> str:
        # fillFromParamObject turns an empty announcement into " "
        return value or " "

    storage: AllianceStorage | None = Field(
        alias="STO",
        default=None,
        description="Alliance storage",
    )
    buildings: list[AllianceBuilding] = Field(alias="ABL", default_factory=list, description="Alliance buffs")

    member_info: list[AllianceMemberInfo] = Field(
        alias="AMI", default_factory=list, description="Donations, activity and landmark counts per member"
    )
    alliance_diplomacy: list[AllianceDiplomacyStatus] = Field(
        alias="ADL", default_factory=list, description="The alliance's standing with other alliances"
    )
    capitals: list[MapAreaItem] = Field(
        alias="ACA", default_factory=list, description="Map rows of the alliance's capitals"
    )
    metropolises: list[MapAreaItem] = Field(
        alias="ATC", default_factory=list, description="Map rows of the alliance's metropolises"
    )
    kings_towers: list[MapAreaItem] = Field(
        alias="AKT", default_factory=list, description="Map rows of the alliance's kings towers"
    )
    monuments: list[MapAreaItem] = Field(
        alias="AMO", default_factory=list, description="Map rows of the alliance's monuments"
    )
    laboratories: list[MapAreaItem] = Field(
        alias="ALA", default_factory=list, description="Map rows of the alliance's laboratories"
    )

    @property
    def status_to_own_alliance_enum(self) -> DiplomacyStatus | None:
        """``status_to_own_alliance`` as a :class:`DiplomacyStatus`, None for a value the client does not define."""
        return enum_or_none(DiplomacyStatus, self.status_to_own_alliance)

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

    alliance_id: int = Field(
        alias="AID",
        description=(
            "Your own is client.alliance.local_alliance_id; another is an AllianceSearchResult.alliance_id "
            "from client.alliance.search_alliances()"
        ),
    )


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


__all__ = [
    "AllianceMember",
    "AllianceInfo",
    "AllianceBuilding",
    "AllianceStorage",
    "AllianceMemberInfo",
    "AllianceDiplomacyStatus",
    "GetAllianceInfoRequest",
    "GetAllianceInfoResponse",
]
