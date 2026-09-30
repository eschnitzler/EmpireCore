"""
Message and report protocol models.

Commands:
- sne: System notification event
- bsd: Spy report (the client's S2C_SPY_LOG_DETAIL)
- mfs: Forward a spy report
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import Field, ValidatorFunctionWrapHandler, field_validator, model_validator

from empire_core.army.models.units import SpyPositions
from empire_core.commanders.models.roster import Castellan
from empire_core.enums import Kingdom, MapItemType, SpyLogResult, SpyLogType
from empire_core.map.models import MapObject
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    enum_or_none,
    list_or_empty,
    object_or_none,
    read_or_none,
    readable_list,
)
from empire_core.protocol.js import ClientInt, js_int, js_loose_equals, js_parse_int, js_truthy

if TYPE_CHECKING:
    from empire_core.army.spy_army import SpyArmy

logger = logging.getLogger(__name__)

MESSAGE_TYPE_SPY_PLAYER = 3
"""``MessageConst.MESSAGE_TYPE_SPY_PLAYER`` (dll line 19516): a spy log about a player's area."""

MESSAGE_TYPE_SPY_NPC = 4
"""``MessageConst.MESSAGE_TYPE_SPY_NPC`` (dll line 19516): a spy log about an NPC's area."""

SPY_VALIDITY = 172800
"""``SpyConst.SPY_VALIDITY`` (dll line 19739): seconds a spy report's army stays current."""

# =============================================================================
# SNE - System Notification Event
# =============================================================================


_MESSAGE_ROW = (
    "message_id",
    "message_type",
    "header",
    "sender_name",
    "sender_id",
    "seconds_since_sent",
    "is_read",
    "is_archived",
    "is_forwarded",
)


class MessageInfo(BasePayload):
    """One mailbox message: an entry of ``sne``'s ``MSG``.

    Client: ``AMessageVO.loadFromParamArray`` (bundle line 3808), reached through
    ``CastleMessageData.parse_SNE`` and ``CastleMessageFactory.parseMessage`` (bundle line 135102).
    """

    message_id: int = Field(description="Message id")
    message_type: ClientInt = Field(description="Message type id")
    header: str = Field(
        default="",
        description="Message header; its layout depends on message_type",
    )
    sender_name: str = Field(default="", description="Sender's name")
    sender_id: ClientInt = Field(default=-1, description="Sender's player id")
    seconds_since_sent: int | float = Field(default=0, description="Seconds since the message was sent")
    is_read: bool = Field(default=False, description="The message has been read")
    is_archived: bool = Field(default=False, description="The message is archived")
    is_forwarded: bool = Field(default=False, description="The message was forwarded")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list) and len(data) >= 2:
            return dict(zip(_MESSAGE_ROW, data, strict=False))
        return data

    @field_validator("header", "sender_name", mode="before")
    @classmethod
    def _no_text(cls, value: Any) -> Any:
        return "" if value is None else value

    @field_validator("is_read", "is_archived", mode="before")
    @classmethod
    def _one_flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    @field_validator("is_forwarded", mode="before")
    @classmethod
    def _int_one_flag(cls, value: Any) -> bool:
        return js_int(value) == 1

    @property
    def is_spy_log(self) -> bool:
        """A spy log: a message of type 3 (a player's area) or 4 (an NPC's)."""
        return self.message_type in (MESSAGE_TYPE_SPY_PLAYER, MESSAGE_TYPE_SPY_NPC)

    def spy_log_header(self) -> SpyLogHeader | None:
        """This message's spy log header, or None when it is no readable spy log."""
        return SpyLogHeader.from_message(self)


@dataclass(frozen=True)
class SpyLogHeader:
    """
    What a spy log's header says: ``subtypeSpy+subtypeResult+areaType#kingdomID+ownerID+areaName``.

    The part after ``#`` is ``areaName+areaID`` instead for a sabotage or
    plague monk log about a player's area that ended in the attacker's
    success or the defender's failure. A number the header lacks, or that
    ``parseInt`` cannot read, is None; so is a subtype or result the client
    defines no constant for.

    Client: ``CastleMessageFactory.parseMessage`` (bundle line 135102),
    ``MessageSpyPlayerVO.parseMessageHeader`` (bundle lines 137651-137653),
    ``MessageSpyNpcVO.parseMessageHeader`` (bundle lines 137635-137636)
    """

    log_type: SpyLogType | None
    result: SpyLogResult | None
    area_type: int | None = None
    kingdom_id: int | None = None
    owner_id: int | None = None
    area_name: str | None = None
    area_id: int | None = None

    @classmethod
    def from_message(cls, message: MessageInfo) -> SpyLogHeader | None:
        """
        The header of a spy log, or None when the message is no spy log or its header has no ``#`` part.

        ``MessageSpyPlayerVO`` reads nothing from a header without the part
        after ``#``, and ``MessageSpyNpcVO`` throws on one.
        """
        if not message.is_spy_log:
            return None
        head, _, meta = message.header.partition("#")
        if not meta:
            return None
        subtypes = head.split("+")
        area = meta.split("+")
        raw_type = js_parse_int(subtypes[0])
        raw_result = js_parse_int(subtypes[1]) if len(subtypes) > 1 else None
        log_type = None if raw_type is None else enum_or_none(SpyLogType, raw_type)
        result = None if raw_result is None else enum_or_none(SpyLogResult, raw_result)
        area_type = js_parse_int(subtypes[2]) if len(subtypes) > 2 else None
        if (
            message.message_type == MESSAGE_TYPE_SPY_PLAYER
            and raw_type in (SpyLogType.SABOTAGE, SpyLogType.PLAGUE_MONK)
            and raw_result in (SpyLogResult.ATTACKER_SUCCESS, SpyLogResult.DEFENDER_FAILED)
        ):
            return cls(
                log_type,
                result,
                area_type,
                area_name=area[0],
                area_id=js_parse_int(area[1]) if len(area) > 1 else None,
            )
        return cls(
            log_type,
            result,
            area_type,
            kingdom_id=js_parse_int(area[0]),
            owner_id=js_parse_int(area[1]) if len(area) > 1 else None,
            area_name=area[2] if len(area) > 2 else None,
        )

    @property
    def spies_lost(self) -> bool:
        """
        The mission failed: the attacker failed or the defender succeeded.

        Client: ``AMessageSpyVO.isFailedSpyLog`` (bundle line 40204)
        """
        return self.result in (SpyLogResult.ATTACKER_FAILED, SpyLogResult.DEFENDER_SUCCESS)

    @property
    def has_army_report(self) -> bool:
        """
        A military mission that succeeded, whose report lists the spied army.

        Client: ``MessageSpyPlayerVO.hasDetailedSpyLog`` (bundle line 137672),
        ``MessageSpyNpcVO.hasDetailedSpyLog`` (bundle line 137642)
        """
        return self.log_type == SpyLogType.DEFENCE and self.result == SpyLogResult.ATTACKER_SUCCESS


class SystemNotificationEvent(BaseResponse):
    """
    New mailbox messages, pushed by the server.

    Command: sne

    Client: ``SNECommand.exec`` (bundle line 125499), ``CastleMessageData.parse_SNE`` (bundle line 134961).
    """

    command = "sne"

    messages: list[MessageInfo] = Field(alias="MSG", default_factory=list, description="The new messages")

    @field_validator("messages", mode="before")
    @classmethod
    def _readable_rows(cls, value: Any) -> Any:
        return readable_list(MessageInfo, value)


# =============================================================================
# BSD - Spy Log Detail
# =============================================================================


class GetSpyReportRequest(BaseRequest):
    """
    Request a spy report from the mailbox.

    Command: bsd
    Payload: {"MID": message_id}

    Client: ``C2SGetSpyLog`` (bundle line 139994), sent by
    ``CastleSpyData.getSpyLog`` (bundle line 139963) for every spy log opened
    """

    command = "bsd"

    message_id: int = Field(
        alias="MID",
        description="The report's message id: MessageInfo.message_id of a spy log, or SpyResult.message_id",
    )


class ForwardSpyLogRequest(BaseRequest):
    """
    Forward a spy report to other players.

    Command: mfs
    Payload: {"MID": message_id, "PID": [player_id, ...]}

    The server answers error 167 (ALREADY_HAS_SPY_REPORT) when a recipient
    has the report already, which the client takes as done.

    Client: ``C2SForwardSpyLogVO`` (bundle lines 128594-128595), whose
    constructor sets ``MID`` before ``PID``; ``MFSCommand.executeCommand``
    (bundle line 125409)
    """

    command = "mfs"

    message_id: int = Field(
        alias="MID",
        description="The report's message id: MessageInfo.message_id of a spy log, or SpyResult.message_id",
    )
    player_ids: list[int] = Field(
        alias="PID",
        description=(
            "Recipients, e.g. your alliance's other members: AllianceMember.player_id from "
            "client.alliance.get_local_members()"
        ),
    )


class SpyReportArea(BasePayload):
    """
    The spied area, a spy report's ``AI`` block.

    Which of the optional keys the client reads depends on the area's type:
    ``RT`` for an outpost, village, monument or resource isle, ``DL`` for a
    dungeon or an NPC owner, ``SPC`` for a faction area, ``DAR`` and ``DDCID``
    for a daimyo castle or township, ``ACVC`` and ``AID`` for an alliance
    battle ground tower.

    Client: ``InteractiveMapobjectVO.parseAreaInfoBattleLog`` (bundle line 3638)
    and its overrides: ``OutpostMapobjectVO`` (18787), ``DaimyoCastleMapObjectVO``
    (19652), ``FactionInteractiveMapobjectVO`` (21579), ``MonumentMapobjectVO``
    (21656), ``DaimyoTownshipMapObjectVO`` (21739), ``DungeonMapobjectVO``
    (22058), ``VillageMapobjectVO`` (22627), ``ABGAllianceTowerMapobjectVO``
    (32282), ``ResourceIsleMapobjectVO`` (34610), ``AAlienInvasionMapobjectVO``
    (41548); ``CastleSpyLogVO.parseSpyLog`` (bundle line 60579) for ``DP``,
    ``DL`` and ``RT``
    """

    area_type: MapItemType = Field(alias="AT", description="The area's type")
    x: int = Field(alias="X", description="Map x")
    y: int = Field(alias="Y", description="Map y")
    kingdom: Kingdom = Field(alias="K", default=Kingdom.GREEN, description="The area's kingdom")
    name: str = Field(alias="N", default="", description="The area's name; empty for an NPC area the game names")
    map_id: int | None = Field(alias="MID", default=None, description="Map id")
    skin_id: ClientInt = Field(alias="EID", default=0, description="Unique id of the castle skin item, 0 for none")
    owner_id: int | None = Field(
        alias="DP",
        default=None,
        description="The owner's player id, below 0 for an NPC; for a faction invasion camp, its dungeon type",
    )
    level: int | None = Field(alias="DL", default=None, description="The NPC's level, when owner_id is below 0")
    keep_level: ClientInt = Field(alias="KL", default=0, description="Keep level")
    wall_level: ClientInt = Field(alias="WL", default=0, description="Wall level")
    gate_level: ClientInt = Field(alias="GL", default=0, description="Gate level")
    tower_level: ClientInt = Field(alias="TL", default=0, description="Tower level")
    moat_level: ClientInt = Field(alias="ML", default=0, description="Moat level")
    area_subtype: int | None = Field(
        alias="RT",
        default=None,
        description="Outpost type, village type or monument type, or a resource isle's isle id",
    )
    special_camp_id: int | None = Field(alias="SPC", default=None, description="A faction area's special camp id")
    daimyo_rank: int | None = Field(alias="DAR", default=None, description="A daimyo castle's or township's rank")
    daimyo_camp_id: int | None = Field(
        alias="DDCID", default=None, description="A daimyo castle's or township's difficulty camp id"
    )
    victory_count: int | None = Field(alias="ACVC", default=None, description="An alliance tower's victory count")
    alliance_id: int | None = Field(alias="AID", default=None, description="The alliance holding an alliance tower")

    @field_validator("name", mode="before")
    @classmethod
    def _no_name(cls, value: Any) -> Any:
        return "" if value is None else value


class SpyReportResponse(BaseResponse):
    """
    A spy report.

    Command: bsd
    Payload::

        {"MID": message_id, "CID": area_object_id, "SID": spy_owner_id, "PID": owner_id,
         "SC": spies, "GC": guards, "SA": accuracy_or_damage, "SR": risk,
         "S": [left, middle, right, keep, stronghold, support, reserve], "AS": seconds_since_spy,
         "B": {castellan}, "LS": [legend_skill_id, ...], "R": [collectables], "RS": cooldown_seconds,
         "OI": {owner record}, "SO": {owner record}, "AI": {area}, "DAR": daimyo_rank}

    An ``AI`` block whose ``AT``, ``X`` or ``Y`` is missing or not one the
    library knows reads as ``area`` None, where the client builds an empty
    map object or fails: deliberately more lenient, so the rest of the report
    still parses.

    A report with no army lists no defenders because the mission brought
    none back, not because the area is empty. The server answers error 130
    (NO_SPY_DATA) or 66 (NO_SUCH_MESSAGE) when there is no report, which the
    client shows as "no spy data".

    Client: ``BSDCommand.executeCommand`` (bundle lines 125223-125226),
    ``CastleSpyLogVO.parseSpyLog`` (bundle line 60579),
    ``CastleSpyArmyInfoVO.parseArmyInfo`` (bundle line 30699)
    """

    command = "bsd"

    message_id: int | None = Field(alias="MID", default=None, description="The report's message id")
    area_object_id: ClientInt = Field(
        alias="CID", default=0, description="The spied area's object id, -1 when it has none"
    )
    spy_owner_id: ClientInt = Field(alias="SID", default=0, description="Player id of whoever sent the spies")
    owner_id: ClientInt = Field(
        alias="PID", default=0, description="Player id of the spied area's owner; below 0 for an NPC"
    )
    spy_count: ClientInt = Field(alias="SC", default=0, description="Spies sent")
    guard_count: ClientInt = Field(alias="GC", default=0, description="Guards at the spied area")
    accuracy_or_damage: ClientInt = Field(
        alias="SA", default=0, description="Accuracy percent, or damage percent for sabotage and plague monks"
    )
    risk: ClientInt = Field(alias="SR", default=0, description="Risk of being caught, percent")
    spy_data: SpyPositions = Field(
        alias="S",
        default_factory=list,
        description="Spied defenders as [wod_id, amount] pairs per position: left, middle, right, keep, "
        "stronghold, support, then an optional reserve",
    )
    seconds_since_spy: int = Field(
        alias="AS", default=-1, description="Seconds between the spying and this reply; -1 without an army"
    )
    defending_castellan: Castellan | None = Field(
        alias="B",
        default=None,
        description="The castellan defending the spied area, without its equipment; None when there is none",
    )
    legend_skill_ids: list[int] = Field(alias="LS", default_factory=list, description="The defender's legend skill ids")
    resources: list[Any] = Field(
        alias="R",
        default_factory=list,
        description="What an economy mission saw, as the server's collectable list rows",
    )
    dungeon_cooldown_seconds: int | None = Field(
        alias="RS",
        default=None,
        description="Seconds until the spied dungeon can be attacked again; 0 or less when it can be now",
    )
    owner: MapObject | None = Field(alias="OI", default=None, description="The spied area owner's record")
    spy_owner: MapObject | None = Field(alias="SO", default=None, description="The spy owner's record")
    area: SpyReportArea | None = Field(alias="AI", default=None, description="The spied area")

    @model_validator(mode="before")
    @classmethod
    def _daimyo_rank_into_the_area(cls, data: Any) -> Any:
        # Client: e.DAR&&(e.AI.DAR=e.DAR)
        if isinstance(data, dict) and js_truthy(data.get("DAR")) and isinstance(data.get("AI"), dict):
            data = {**data, "AI": {**data["AI"], "DAR": data["DAR"]}}
        return data

    @field_validator("legend_skill_ids", "resources", mode="before")
    @classmethod
    def _list_or_empty(cls, value: Any) -> Any:
        return list_or_empty(value)

    @field_validator("defending_castellan", mode="wrap")
    @classmethod
    def _castellan_or_none(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Castellan | None:
        # Client: e.B&&LordFactory.createLord(e.B,!0,!0)
        if not js_truthy(value):
            return None
        return read_or_none(handler, value, warn=logger, what="the defending castellan of a spy report")

    @field_validator("owner", "spy_owner", mode="wrap")
    @classmethod
    def _owner_or_none(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> MapObject | None:
        value = object_or_none(value)
        if value is None:
            return None
        return read_or_none(handler, value, warn=logger, what="an owner record of a spy report")

    @field_validator("area", mode="wrap")
    @classmethod
    def _area_or_none(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> SpyReportArea | None:
        value = object_or_none(value)
        if value is None:
            return None
        return read_or_none(handler, value, warn=logger, what="the spied area of a spy report")

    @model_validator(mode="after")
    def _no_age_without_an_army(self) -> SpyReportResponse:
        # Client: parseArmyInfo keeps AS only for a non-empty S, else sets -1
        if not self.spy_data:
            self.seconds_since_spy = -1
        return self

    @property
    def has_army(self) -> bool:
        """Whether the report lists the spied army."""
        return bool(self.spy_data)

    def army(self) -> SpyArmy | None:
        """The spied defenders, split by the position they hold, or None when the report has no army."""
        from empire_core.army.spy_army import SpyArmy

        if not self.spy_data:
            return None
        return SpyArmy.from_spy_data(self.spy_data)

    @property
    def remaining_validity_seconds(self) -> int:
        """
        Seconds the army stays current, counted from this reply; 0 without an army.

        Client: ``CastleSpyArmyInfoVO.remainingSpyInfoTime`` (bundle line 30702),
        ``SpyConst.SPY_VALIDITY`` (dll line 19739)
        """
        if self.seconds_since_spy == -1:
            return 0
        return max(0, SPY_VALIDITY - self.seconds_since_spy)

    @property
    def is_fresh(self) -> bool:
        """Whether the army was still current when the report was read."""
        return self.remaining_validity_seconds > 0


__all__ = [
    "ForwardSpyLogRequest",
    "GetSpyReportRequest",
    "MESSAGE_TYPE_SPY_NPC",
    "MESSAGE_TYPE_SPY_PLAYER",
    "MessageInfo",
    "SPY_VALIDITY",
    "SpyLogHeader",
    "SpyReportArea",
    "SpyReportResponse",
    "SystemNotificationEvent",
]
