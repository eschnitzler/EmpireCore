"""Alliance info models.

Commands:
- ain: Get alliance info (includes member list)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BeforeValidator, Field, PrivateAttr, field_validator, model_validator

from empire_core.enums import AllianceRank, DiplomacyStatus, OnlineState
from empire_core.gamedata import EnumOrInt
from empire_core.map.models.items import MapAreaItem, parse_area_rows
from empire_core.map.models.owners import AllianceCrest
from empire_core.player.models.profile import PlayerProfileBase
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    enum_or_none,
    object_or_none,
    readable_list,
)
from empire_core.protocol.js import (
    ClientInt,
    ParseInt,
    js_floor,
    js_int,
    js_loose_equals,
    js_number_or_none,
    js_truthy,
)
from empire_core.protocol.text import decode_json_text

if TYPE_CHECKING:
    from empire_core.gamedata import AllianceCrestColor, AllianceCrestLayout

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

    _member_info: Any = PrivateAttr(default=None)

    @property
    def member_info(self) -> AllianceMemberInfo | None:
        """
        The member's ``AMI`` row: donations, login activity and landmark counts; None when the reply has none.

        Client: ``AllianceInfoVO.getAdditionalMemberInfos`` (bundle line 25979)
        """
        return self._member_info

    @property
    def activity_tier(self) -> int | None:
        """The member's login activity, an :class:`OnlineState` value; None when the reply has no ``AMI`` row."""
        return self._member_info.login_activity if self._member_info is not None else None

    @property
    def is_online(self) -> bool:
        """
        Whether the member is online now.

        Client: ``AllianceInfoVO.getOnlineUserList`` (bundle line 25980)
        """
        return self.activity_tier == OnlineState.ONLINE


# =============================================================================
# Alliance Building Model
# =============================================================================


class AllianceBuilding(BasePayload):
    """Alliance building info from ABL array."""

    building_type: int = Field(validation_alias="BT", serialization_alias="BT", default=0)
    level: int = Field(validation_alias="L", serialization_alias="L", default=0)
    cooldown: int = Field(validation_alias="CD", serialization_alias="CD", default=-1)


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

    wood: StorageAmount = Field(validation_alias="W", serialization_alias="W", default=0, description="Wood")
    stone: StorageAmount = Field(validation_alias="S", serialization_alias="S", default=0, description="Stone")
    coins: StorageAmount = Field(validation_alias="C1", serialization_alias="C1", default=0, description="Coins")
    rubies: StorageAmount = Field(validation_alias="C2", serialization_alias="C2", default=0, description="Rubies")
    iron: StorageAmount = Field(validation_alias="I", serialization_alias="I", default=0, description="Iron")
    oil: StorageAmount = Field(validation_alias="O", serialization_alias="O", default=0, description="Olive oil")
    glass: StorageAmount = Field(validation_alias="G", serialization_alias="G", default=0, description="Glass")
    coal: StorageAmount = Field(validation_alias="C", serialization_alias="C", default=0, description="Charcoal")
    fury_doubloons: StorageAmount = Field(
        validation_alias="FD", serialization_alias="FD", default=0, description="Fury doubloons"
    )
    time_doubloons: StorageAmount = Field(
        validation_alias="TD", serialization_alias="TD", default=0, description="Time doubloons"
    )
    spirit_doubloons: StorageAmount = Field(
        validation_alias="SD", serialization_alias="SD", default=0, description="Spirit doubloons"
    )
    vigor_doubloons: StorageAmount = Field(
        validation_alias="VD", serialization_alias="VD", default=0, description="Vigor doubloons"
    )
    bastion_doubloons: StorageAmount = Field(
        validation_alias="BD", serialization_alias="BD", default=0, description="Bastion doubloons"
    )
    rampart_doubloons: StorageAmount = Field(
        validation_alias="RD", serialization_alias="RD", default=0, description="Rampart doubloons"
    )
    alliance_coins: StorageAmount = Field(
        validation_alias="AC", serialization_alias="AC", default=0, description="Alliance coins"
    )
    rift_coins: StorageAmount = Field(
        validation_alias="RC", serialization_alias="RC", default=0, description="Rift coins"
    )
    legendary_rift_coins: StorageAmount = Field(
        validation_alias="LRC", serialization_alias="LRC", default=0, description="Legendary rift coins"
    )
    alliance_influence: StorageAmount = Field(
        validation_alias="AIN",
        serialization_alias="AIN",
        default=0,
        description="Alliance influence; only on alliance battle ground servers",
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

    alliance_id: ClientInt = Field(
        validation_alias="AID", serialization_alias="AID", default=0, description="The other alliance"
    )
    alliance_name: str | None = Field(
        validation_alias="AN", serialization_alias="AN", default=None, description="The other alliance's name"
    )
    status: ClientInt = Field(
        validation_alias="AS",
        serialization_alias="AS",
        default=0,
        description="0 at war, 1 neutral, 2 soft allied, 3 real allied",
    )
    status_confirmed: ClientInt = Field(
        validation_alias="AC",
        serialization_alias="AC",
        default=0,
        description="1 once agreed, 0 while only requested",
    )

    @property
    def status_enum(self) -> DiplomacyStatus | None:
        """``status`` as a :class:`DiplomacyStatus`, None for a value the client does not define."""
        return enum_or_none(DiplomacyStatus, self.status)


class PeaceOffer(BasePayload):
    """
    An open peace offer between this alliance and yours: the ain block's ``PO``.

    Client: ``AllianceInfoVO.fillFromParamObject`` (bundle line 25928) reads ``T``
    and ``TS`` into a ``PeaceOfferVO`` (bundle line 42688)
    """

    tribute: ClientInt = Field(
        validation_alias="T",
        serialization_alias="T",
        default=0,
        description="The tribute percentage, negative when demanded",
    )
    remaining_seconds: int | float = Field(
        validation_alias="TS", serialization_alias="TS", default=0, description="Seconds until the offer ends"
    )

    @field_validator("remaining_seconds", mode="before")
    @classmethod
    def _seconds(cls, value: Any) -> Any:
        return js_number_or_none(value) or 0

    @property
    def is_demanded(self) -> bool:
        """Whether the tribute is demanded rather than offered: a negative ``T``."""
        return self.tribute < 0

    @property
    def tribute_percentage(self) -> int:
        """The tribute offered or demanded, as a positive percentage."""
        return abs(self.tribute)


class CrestLayout(BasePayload):
    """
    One crest layout the alliance holds: an entry of the ain block's ``ACLS``.

    The client stores the colours from ``ACLCS`` and never reads them; live replies have been
    seen carrying ``ACCS`` there instead, which stays in the extra fields.

    Client: ``AllianceInfoVO.fillFromParamObject`` (bundle line 25932)
    """

    layout_id: EnumOrInt["AllianceCrestLayout"] | None = Field(
        validation_alias="ACLI",
        serialization_alias="ACLI",
        default=None,
        description="The crest layout; None when the entry names none",
    )
    seconds_left: int | float = Field(
        validation_alias="ACLET", serialization_alias="ACLET", default=0, description="Seconds until the layout ends"
    )
    is_active: bool = Field(
        validation_alias="ACIA", serialization_alias="ACIA", default=False, description="The layout is the one in use"
    )
    color_ids: tuple[Annotated[EnumOrInt["AllianceCrestColor"], BeforeValidator(js_int)], ...] | None = Field(
        validation_alias="ACLCS",
        serialization_alias="ACLCS",
        default=None,
        description="The layout's colours, as ACCS names them; None when unsent",
    )

    @field_validator("layout_id", mode="before")
    @classmethod
    def _layout(cls, value: Any) -> Any:
        # Client: keys _crestLayoutEndTimeStamps by ACLI as sent (bundle line 25936) and reads it by int layout id
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @field_validator("seconds_left", mode="before")
    @classmethod
    def _seconds(cls, value: Any) -> Any:
        return js_number_or_none(value) or 0

    @field_validator("color_ids", mode="before")
    @classmethod
    def _colors(cls, value: Any) -> Any:
        return value if isinstance(value, list) else None

    @field_validator("is_active", mode="before")
    @classmethod
    def _one_flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)


class AllianceCrests(BasePayload):
    """
    The alliance's crest and its fallback: the ain block's ``aee``.

    Client: ``CastleAllianceData.parseAllianceCrestForAlliance`` (bundle line 11589);
    ``AllianceInfoVO.parseFallbackCrest`` (bundle line 26146) keeps ``ACFB`` only
    when it has both ``ACLI`` and ``ACCS``
    """

    crest: AllianceCrest | None = Field(
        validation_alias="ACCA",
        serialization_alias="ACCA",
        default=None,
        description="The current crest; None when unsent, where the client draws a random one",
    )
    fallback_crest: AllianceCrest | None = Field(
        validation_alias="ACFB", serialization_alias="ACFB", default=None, description="The fallback crest"
    )

    @field_validator("crest", mode="before")
    @classmethod
    def _crest(cls, value: Any) -> Any:
        return value if js_truthy(value) and isinstance(value, dict) else None

    @field_validator("fallback_crest", mode="before")
    @classmethod
    def _fallback(cls, value: Any) -> Any:
        ok = isinstance(value, dict) and js_truthy(value.get("ACLI")) and js_truthy(value.get("ACCS"))
        return value if ok else None


# =============================================================================
# Alliance Info Model
# =============================================================================


def _rank_order(member: AllianceMember) -> tuple[bool, int]:
    """
    ``AllianceInfoVO.sortOnRank`` (bundle line 25978): highest rank first.

    A rank the client reads as NaN compares as neither above nor below any
    other, so its order there depends on the browser's sort; here such
    members go last, in the order they came.
    """
    return (member.alliance_rank is None, member.alliance_rank or 0)


class AllianceInfo(BasePayload):
    """
    Full alliance information from ain response.

    Contains alliance details, member list, buildings, storage, etc.

    Client: ``AllianceInfoVO.fillFromParamObject`` (bundle line 25928), ``parseMemberList`` (bundle line 25968),
    ``parseStorageFromServer`` (bundle line 25940), ``parseBuffList`` (bundle line 25955);
    ``CastleAllianceData.parseAllianceInfo`` (bundle line 11609) for ``RT``
    """

    alliance_id: ParseInt = Field(
        validation_alias="AID", serialization_alias="AID", default=0, description="Alliance id"
    )
    name: str = Field(validation_alias="N", serialization_alias="N", default="", description="Alliance name")
    members: list[AllianceMember] = Field(
        validation_alias="M", serialization_alias="M", default_factory=list, description="Members, highest rank first"
    )

    @field_validator("members", mode="before")
    @classmethod
    def _member_records(cls, value: Any) -> Any:
        # parseOwnerInfo reads no record without an OID; parseMemberList sorts by rank
        members = readable_list(
            AllianceMember,
            value,
            accept=lambda e: isinstance(e, dict),
            keep=lambda e: js_truthy(e.get("OID")),
            warn=logger,
            what="alliance members",
        )
        return sorted(members, key=_rank_order)

    fame_points: ClientInt = Field(
        validation_alias="CF", serialization_alias="CF", default=0, description="Alliance fame points"
    )
    highest_fame_points: ParseInt = Field(
        validation_alias="HF", serialization_alias="HF", default=0, description="Highest fame points reached"
    )
    might: ParseInt = Field(
        validation_alias="MP", serialization_alias="MP", default=0, description="Alliance might points"
    )
    highest_alliance_might: ParseInt = Field(
        validation_alias="HAMP", serialization_alias="HAMP", default=0, description="Highest might points reached"
    )
    description: str = Field(
        validation_alias="D",
        serialization_alias="D",
        default="",
        description="The alliance's description, decoded as chat text",
    )
    announcement: str = Field(
        validation_alias="A",
        serialization_alias="A",
        default=" ",
        description='The alliance\'s announcement; " " when it has none',
    )
    language: str = Field(
        validation_alias="ALL", serialization_alias="ALL", default="en", description="The alliance's language code"
    )
    external_member_level: ParseInt = Field(
        validation_alias="ML", serialization_alias="ML", default=0, description="External member level"
    )
    status_to_own_alliance: ParseInt = Field(
        validation_alias="DOA",
        serialization_alias="DOA",
        default=0,
        description="Diplomacy status towards the player's own alliance, a DiplomacyStatus value",
    )
    is_searching_members: bool = Field(
        validation_alias="IS",
        serialization_alias="IS",
        default=False,
        description="The alliance is looking for players",
    )
    is_accepting_members: bool = Field(
        validation_alias="IA", serialization_alias="IA", default=False, description="Players may apply to join"
    )
    application_count: ParseInt = Field(
        validation_alias="AA", serialization_alias="AA", default=12, description="Pending applications"
    )
    auto_war: bool = Field(validation_alias="AW", serialization_alias="AW", default=False, description="Auto war is on")
    aqua_points: int | float = Field(
        validation_alias="AP", serialization_alias="AP", default=0, description="Aqua points"
    )
    free_renames: ClientInt = Field(
        validation_alias="FR", serialization_alias="FR", default=0, description="Free alliance renames left"
    )
    can_be_invited_to_hard_pact: bool = Field(
        validation_alias="HP", serialization_alias="HP", default=False, description="Open to hard pact invitations"
    )
    can_be_invited_to_soft_pact: bool = Field(
        validation_alias="SP", serialization_alias="SP", default=False, description="Open to soft pact invitations"
    )
    is_able_to_forge: bool = Field(
        validation_alias="MF", serialization_alias="MF", default=False, description="The alliance forge can be used"
    )
    is_forge_inventory_full: bool = Field(
        validation_alias="IF",
        serialization_alias="IF",
        default=False,
        description="The alliance forge inventory is full",
    )
    soft_relic_forge_uses: ClientInt = Field(
        validation_alias="SRFU", serialization_alias="SRFU", default=0, description="Soft relic forge uses"
    )
    hard_relic_forge_uses: ClientInt = Field(
        validation_alias="HRFU", serialization_alias="HRFU", default=0, description="Hard relic forge uses"
    )
    is_king_alliance: bool = Field(
        validation_alias="KA", serialization_alias="KA", default=False, description="The alliance holds the king title"
    )
    refresh_seconds: ClientInt = Field(
        validation_alias="RT",
        serialization_alias="RT",
        default=0,
        description="Seconds until the alliance should be requested again; 0 when none is set",
    )

    @field_validator("application_count", mode="before")
    @classmethod
    def _applications(cls, value: Any) -> Any:
        # fillFromParamObject keeps its 12 unless AA is sent
        return 12 if value is None else value

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

    peace_offer: PeaceOffer | None = Field(
        validation_alias="PO",
        serialization_alias="PO",
        default=None,
        description="The open peace offer with your alliance; None when there is none",
    )
    crest_layouts: list[CrestLayout] = Field(
        validation_alias="ACLS",
        serialization_alias="ACLS",
        default_factory=list,
        description="The crest layouts the alliance holds",
    )
    crests: AllianceCrests | None = Field(
        validation_alias="aee", serialization_alias="aee", default=None, description="The alliance's crest"
    )

    @field_validator("peace_offer", "crests", mode="before")
    @classmethod
    def _object_block(cls, value: Any) -> Any:
        return object_or_none(value)

    @field_validator("crest_layouts", mode="before")
    @classmethod
    def _crest_layouts(cls, value: Any) -> Any:
        return readable_list(
            CrestLayout, value, accept=lambda e: isinstance(e, dict), warn=logger, what="crest layouts"
        )

    storage: AllianceStorage | None = Field(
        validation_alias="STO",
        serialization_alias="STO",
        default=None,
        description="Alliance storage",
    )
    buildings: list[AllianceBuilding] = Field(
        validation_alias="ABL", serialization_alias="ABL", default_factory=list, description="Alliance buffs"
    )

    member_info: list[AllianceMemberInfo] = Field(
        validation_alias="AMI",
        serialization_alias="AMI",
        default_factory=list,
        description="Donations, activity and landmark counts per member",
    )
    alliance_diplomacy: list[AllianceDiplomacyStatus] = Field(
        validation_alias="ADL",
        serialization_alias="ADL",
        default_factory=list,
        description="The alliance's standing with other alliances",
    )
    capitals: list[MapAreaItem] = Field(
        validation_alias="ACA",
        serialization_alias="ACA",
        default_factory=list,
        description="Map rows of the alliance's capitals",
    )
    metropolises: list[MapAreaItem] = Field(
        validation_alias="ATC",
        serialization_alias="ATC",
        default_factory=list,
        description="Map rows of the alliance's metropolises",
    )
    kings_towers: list[MapAreaItem] = Field(
        validation_alias="AKT",
        serialization_alias="AKT",
        default_factory=list,
        description="Map rows of the alliance's kings towers",
    )
    monuments: list[MapAreaItem] = Field(
        validation_alias="AMO",
        serialization_alias="AMO",
        default_factory=list,
        description="Map rows of the alliance's monuments",
    )
    laboratories: list[MapAreaItem] = Field(
        validation_alias="ALA",
        serialization_alias="ALA",
        default_factory=list,
        description="Map rows of the alliance's laboratories",
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

    def model_post_init(self, __context: Any) -> None:
        """
        Give each member its AMI row.

        Client: ``AllianceInfoVO.parseAMI`` (bundle line 25947) keys the rows by player id; a later row wins.
        """
        rows = {info.player_id: info for info in self.member_info}
        for member in self.members:
            member._member_info = rows.get(member.player_id)

    @property
    def leader(self) -> AllianceMember | None:
        """
        The member with rank 0, None when there is none.

        Client: ``AllianceInfoVO.allianceLeader`` (bundle line 25986)
        """
        return next((m for m in self.members if m.alliance_rank == AllianceRank.LEADER), None)


def alliance_block(value: Any) -> Any:
    """
    An alliance block to read, or None: one without an ``AID`` is not read.

    Client: ``CastleAllianceData.parseAllianceInfo`` (bundle line 11605)
    """
    block = object_or_none(value)
    return block if isinstance(block, dict) and block.get("AID") is not None else None


def alliance_of_ain(value: Any) -> Any:
    """
    The alliance block of an ain reply nested in another reply, or None.

    Client: ``CastleAllianceData.parse_AIN`` (bundle line 11560)
    """
    block = object_or_none(value)
    return alliance_block(block.get("A")) if isinstance(block, dict) else None


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

    Client: ``C2SGetAllianceInfoVO`` (bundle line 9760)
    """

    command = "ain"

    alliance_id: int = Field(
        validation_alias="AID",
        serialization_alias="AID",
        description=(
            "Your own is client.alliance.local_alliance_id; another is an AllianceSearchResult.alliance_id "
            "from client.alliance.search_alliances()"
        ),
    )

    def accepts_reply(self, payload: Any) -> bool:
        """Whether an ain reply is about this alliance: its ``A.AID``, when sent, is ``AID``.

        Client: ``AINCommand`` (bundle line 121461) hands ``A`` to
        ``CastleAllianceData.parseAllianceInfo`` (bundle line 11605), which keys it
        by ``int(A.AID)`` and reads nothing without one.
        """
        alliance = payload.get("A") if isinstance(payload, dict) else None
        if not isinstance(alliance, dict) or "AID" not in alliance:
            return True
        return js_int(alliance["AID"]) == self.alliance_id


class GetAllianceInfoResponse(BaseResponse):
    """
    Response containing alliance information.

    Command: ain
    Payload: {"A": {"AID": ..., "N": ..., "M": [...], ...}}

    Client: ``AINCommand.executeCommand`` (bundle line 121461)
    """

    command = "ain"

    alliance: AllianceInfo | None = Field(
        validation_alias="A", serialization_alias="A", default=None, description="The alliance; None without an AID"
    )

    @field_validator("alliance", mode="before")
    @classmethod
    def _needs_an_alliance_id(cls, value: Any) -> Any:
        return alliance_block(value)

    @property
    def members(self) -> list[AllianceMember]:
        """Convenience accessor for alliance members."""
        return self.alliance.members if self.alliance else []

    @property
    def online_members(self) -> list[AllianceMember]:
        """Get list of currently online members."""
        return self.alliance.online_members if self.alliance else []


__all__ = [
    "AllianceCrests",
    "CrestLayout",
    "PeaceOffer",
    "AllianceMember",
    "AllianceInfo",
    "AllianceBuilding",
    "AllianceStorage",
    "AllianceMemberInfo",
    "AllianceDiplomacyStatus",
    "GetAllianceInfoRequest",
    "GetAllianceInfoResponse",
]
