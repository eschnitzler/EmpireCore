"""
The free rewards: the login bonus, the startup bonus, lost and found, the activity chest, the weekly
honour reward, the patch note rewards, and the pending rewards count.

Commands:
- alb / clb: The daily login bonus and picking one of its rewards
- sli / slc: The startup (beginner) login bonus and collecting it
- lfe / clf: Lost and found and collecting an item from it
- uac / uoa: The activity chest (pushed) and opening it
- gwh / rwb: Your weekly honour rank and redeeming its reward
- gpn / cpn: A patch note's rewards and collecting them
- pre: How many rewards wait in the reward hub (pushed)

None of these requests carries a cost: each VO holds only the ids below, and the one reply with
coins and rubies (rwb) brings the totals after the reward.
"""

from __future__ import annotations

import logging
import time
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_validator, model_validator

from empire_core.army.models.units import UnitInventoryBlock
from empire_core.enums import CollectableKind, LoginBonusSpecial
from empire_core.gamedata import Collectable, CollectableObject
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, CurrencyBlock, readable_list
from empire_core.protocol.js import ClientInt, ParseInt, js_loose_equals, js_number, js_number_or_none

logger = logging.getLogger(__name__)


def _picked(value: Any) -> Collectable | None:
    """The first collectable of a ``PICK``, ``ALLI`` or ``VIP`` block, or None when nothing was collected.

    A key the client has no type for counts as nothing, as the client drops it.

    Client: ``CastleLoginBonusData.collectReward`` (bundle lines 39142-39151) reads the block as a
    reward object (``R`` is no collectable key), else its first ``[key, value]`` pair under ``R``
    """
    if not isinstance(value, list) or not value:
        return None
    block = value[0]
    known = [item for item in Collectable.from_object(block) if item.kind is not CollectableKind.OTHER]
    if not known and isinstance(block, dict) and isinstance(block.get("R"), list):
        pair = next((p for p in block["R"] if isinstance(p, list) and len(p) > 1), None)
        if pair is not None and isinstance(pair[0], str):
            fallback = Collectable.from_object({pair[0]: [pair[1]]})
            known = [item for item in fallback if item.kind is not CollectableKind.OTHER]
    return known[0] if known else None


# =============================================================================
# ALB / CLB - Daily login bonus
# =============================================================================


LOGIN_BONUS_REQUIRED_XP = 1200
"""The XP from which the client asks for the login bonus.

Client: ``CastleLoginBonusData.REQUIRED_XP`` (bundle line 39163), ``GBDCommand`` (bundle line 129389)
"""


class GetLoginBonusRequest(BaseRequest):
    """
    Ask for the daily login bonus.

    Command: alb
    Payload: {}

    Client: ``C2SGetLoginBonusVO`` (bundle line 39171), sent by ``GBDCommand.checkLoginBonus``
    (bundle line 129391) after a login with at least ``LOGIN_BONUS_REQUIRED_XP`` XP
    """

    command = "alb"


class LoginBonusDay(BasePayload):
    """
    One day of the login bonus week: the rewards to pick one from, and what was collected.

    Client: ``CastleLoginBonusData.parseALB`` (bundle line 39138) reads ``R[d]["D"+(d+1)]`` as
    ``[{REW}, {PICK}, {ALLI}, {VIP}]``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    day: int = Field(description="The day of the week, 0 to 6")
    rewards: tuple[Collectable, ...] = Field(default=(), description="The rewards to pick one from (REW)")
    picked: Collectable | None = Field(default=None, description="The reward picked (PICK); None while none was")
    alliance_reward: Collectable | None = Field(
        default=None, description="The alliance bonus collected (ALLI); None while it was not"
    )
    vip_reward: Collectable | None = Field(
        default=None, description="The VIP bonus collected (VIP); None while it was not"
    )


class LoginBonus(BasePayload):
    """
    The daily login bonus: the day it is, and the week's rewards.

    Client: ``CastleLoginBonusData.parseALB`` (bundle lines 39133-39139)
    """

    day_index: ClientInt = Field(
        validation_alias="D",
        serialization_alias="D",
        default=0,
        description="Days of the bonus so far; today is day_index % 7",
    )
    days: tuple[LoginBonusDay, ...] = Field(
        validation_alias="R", serialization_alias="R", default=(), description="The week's days, in order"
    )

    @field_validator("days", mode="before")
    @classmethod
    def _days(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return ()
        days = []
        for index, entry in enumerate(value):
            parts = entry.get(f"D{index + 1}") if isinstance(entry, dict) else None
            if not isinstance(parts, list):
                continue
            block = [part if isinstance(part, dict) else {} for part in parts[:4]] + [{}] * (4 - len(parts[:4]))
            rew = block[0].get("REW")
            days.append(
                LoginBonusDay(
                    day=index,
                    rewards=Collectable.from_object(rew[0]) if isinstance(rew, list) and rew else (),
                    picked=_picked(block[1].get("PICK")),
                    alliance_reward=_picked(block[2].get("ALLI")),
                    vip_reward=_picked(block[3].get("VIP")),
                )
            )
        return tuple(days)

    @property
    def today(self) -> LoginBonusDay | None:
        """Today's day of the week, None when the reply has no such day."""
        return next((day for day in self.days if day.day == self.day_index % 7), None)

    def has_anything_to_collect(self, *, in_alliance: bool = False, vip_active: bool = False) -> bool:
        """
        Whether today has a reward left: no pick yet, or the alliance or VIP bonus where you may have one.

        Client: ``CastleLoginBonusData.parseALB`` (bundle line 39138) sets ``hasAnythingToCollect``
        """
        today = self.today
        if today is None:
            return False
        return (
            today.picked is None
            or (in_alliance and today.alliance_reward is None)
            or (vip_active and today.vip_reward is None)
        )


class GetLoginBonusResponse(BaseResponse, LoginBonus):
    """
    The daily login bonus.

    Command: alb

    Client: ``ALBCommand.executeCommand`` (bundle line 124772)
    """

    command = "alb"


class CollectLoginBonusRequest(BaseRequest):
    """
    Collect today's login bonus: one of its rewards, or its alliance or VIP bonus.

    Command: clb
    Payload: {"ID": unit id or -1, "I": reward key or null, "SP": "ALLI", "VIP" or null}

    The client's object sends its nulls, so they go out here too.

    Client: ``C2SCatchLoginBonusVO`` (bundle line 104761), from
    ``CastleDailyLoginBonusDialog.performDailyRewardButtonSelection`` (bundle line 39228) for a
    reward and ``performDailySpecialBonusButtonSelection`` (bundle line 39237) for a bonus
    """

    command = "clb"

    unit_id: int = Field(
        validation_alias="ID",
        serialization_alias="ID",
        default=-1,
        description="The unit's id for a units reward, else -1",
    )
    reward_key: str | None = Field(
        validation_alias="I",
        serialization_alias="I",
        default=None,
        description="The picked reward's Collectable.send_key",
    )
    special: LoginBonusSpecial | None = Field(
        validation_alias="SP",
        serialization_alias="SP",
        default=None,
        description="The alliance or VIP bonus instead of a reward",
    )

    def to_payload(self) -> dict[str, Any]:
        special = None if self.special is None else self.special.value
        return {"ID": self.unit_id, "I": self.reward_key, "SP": special}


class CollectLoginBonusResponse(BaseResponse):
    """
    The login bonus after a pick.

    Command: clb

    Client: ``CLBCommand.executeCommand`` (bundle line 124790) passes ``alb`` to ``parseALB``
    """

    command = "clb"

    login_bonus: LoginBonus | None = Field(
        validation_alias="alb", serialization_alias="alb", default=None, description="The login bonus after the pick"
    )

    @field_validator("login_bonus", mode="before")
    @classmethod
    def _block(cls, value: Any) -> Any:
        return value if isinstance(value, dict) else None


# =============================================================================
# SLI / SLC - Startup login bonus
# =============================================================================


class GetStartupBonusRequest(BaseRequest):
    """
    Ask for the startup (beginner) login bonus.

    Command: sli
    Payload: {}

    Client: ``C2SGetSLI`` (bundle line 54338), sent by ``GBDCommand`` after every login (bundle
    line 129389) and on reaching level 6 (bundle line 13066)
    """

    command = "sli"


class GetStartupBonusResponse(BaseResponse):
    """
    The startup login bonus: the next reward and whether it can be collected now.

    Command: sli

    Client: ``SLICommand.executeCommand`` (bundle line 129798), ``CastleStartUpBonusData.parse_SLI``
    (bundle line 113943); the dialog's collect button (bundle line 57258)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "sli"

    next_reward_id: ClientInt = Field(
        validation_alias="NRR",
        serialization_alias="NRR",
        default=0,
        description="The next reward's beginnerLoginRewardID; -1 once all are collected",
    )
    can_collect: bool = Field(
        validation_alias="CC",
        serialization_alias="CC",
        default=False,
        description="Whether the next reward can be collected now",
    )

    @field_validator("can_collect", mode="before")
    @classmethod
    def _collectable(cls, value: Any) -> Any:
        return js_loose_equals(value, 1)

    @property
    def collectable(self) -> bool:
        """Whether there is a next reward and it can be collected now, as the dialog enables its button."""
        return self.can_collect and self.next_reward_id >= 0


class CollectStartupBonusRequest(BaseRequest):
    """
    Collect the next startup login bonus reward.

    Command: slc
    Payload: {}

    Client: ``C2SStartupLoginBonusCollectVO`` (bundle line 104974), sent by
    ``CastleStartupLoginBonusDialog.onClick`` (bundle line 57261)
    """

    command = "slc"


class CollectStartupBonusResponse(BaseResponse):
    """
    Acknowledgement of a collected startup bonus; the client reads nothing from it.

    Command: slc
    Client: ``SLCCommand.executeCommand`` (bundle line 129785)
    """

    command = "slc"


# =============================================================================
# LFE / CLF - Lost and found
# =============================================================================


class LostAndFoundItem(BasePayload):
    """
    An item in lost and found: one that found no room in its inventory, kept until it expires.

    Client: ``LostAndFoundListItemVO.parseData`` and ``remainingTimeInSeconds`` (bundle lines 144545-144549)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    item_id: ClientInt = Field(
        validation_alias="LFID", serialization_alias="LFID", default=0, description="The entry's id, to collect it"
    )
    reward: Collectable = Field(description="The item, from its server key (ROT) and entry (ROV)")
    seconds: int | float = Field(
        validation_alias="ET", serialization_alias="ET", default=0, description="Seconds until it expires, when read"
    )
    received_time: int | float | None = Field(
        validation_alias="CT",
        serialization_alias="CT",
        default=None,
        description="When it arrived, unix seconds; None when not sent",
    )
    equipment_elapsed: ClientInt = Field(
        validation_alias="LFES",
        serialization_alias="LFES",
        default=0,
        description="Seconds a timed equipment has run while here",
    )
    received_at: float = Field(
        default_factory=time.monotonic, description="When the values were read, in time.monotonic() seconds"
    )

    @model_validator(mode="before")
    @classmethod
    def _reward(cls, data: Any) -> Any:
        if isinstance(data, dict) and "reward" not in data:
            key = data.get("ROT")
            return {**data, "reward": Collectable.from_entry(key if isinstance(key, str) else "", data.get("ROV"))}
        return data

    @field_validator("received_time", mode="before")
    @classmethod
    def _received(cls, value: Any) -> Any:
        return js_number_or_none(value)

    @field_validator("seconds", mode="before")
    @classmethod
    def _seconds(cls, value: Any) -> Any:
        return js_number(value)

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds until it expires, 0 once it has."""
        return max(0.0, self.seconds - ((time.monotonic() if now is None else now) - self.received_at))


class GetLostAndFoundRequest(BaseRequest):
    """
    Ask for lost and found.

    Command: lfe
    Payload: {}

    Client: ``C2SGetLostAndFoundListVO`` (bundle line 107124), sent when the inventory dialog
    opens (bundle line 107082)
    """

    command = "lfe"


class GetLostAndFoundResponse(BaseResponse):
    """
    Lost and found.

    Command: lfe

    Client: ``LFECommand.executeCommand`` (bundle line 125350), ``CastleLostAndFoundData.parse_LFE``
    (bundle line 144517), which sorts the items by arrival and then expiry for display
    """

    command = "lfe"

    items: list[LostAndFoundItem] = Field(
        validation_alias="lfe",
        serialization_alias="lfe",
        default_factory=list,
        description="The items, in the order sent",
    )

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, value: Any) -> Any:
        return readable_list(LostAndFoundItem, value, warn=logger, what="lost and found items")


class CollectLostAndFoundRequest(BaseRequest):
    """
    Collect an item from lost and found.

    Command: clf
    Payload: {"LFID": item id}

    Client: ``C2SCollectLostAndFoundItemVO`` (bundle line 107195), sent by
    ``LostAndFoundListItem.onCollect`` (bundle line 107151); the button is disabled while the
    item's inventory is full (bundle line 107139)
    """

    command = "clf"

    item_id: int = Field(
        validation_alias="LFID", serialization_alias="LFID", description="The item's LostAndFoundItem.item_id"
    )


class CollectLostAndFoundResponse(BaseResponse):
    """
    Acknowledgement of a collected item; the client reads nothing from it.

    Command: clf
    Client: ``CLFCommand.executeCommand`` (bundle line 125256)
    """

    command = "clf"


# =============================================================================
# UAC / UOA - Activity chest
# =============================================================================


class ActivityChestInfo(BaseResponse):
    """
    The activity chest: the next one and how long until it opens. The server pushes it; nothing asks for it.

    Command: uac

    Client: ``UACCommand.executeCommand`` (bundle line 129828), ``CastleActivityBonusData.parse_UAC``,
    ``isActive`` and ``remainingTimeTillNextActivityBonus`` (bundle lines 110921-110932)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "uac"

    next_reward_id: ClientInt = Field(
        validation_alias="CID",
        serialization_alias="CID",
        default=0,
        description="The next chest's activityRewardID; -1 without one",
    )
    seconds: int | float = Field(
        validation_alias="TTU",
        serialization_alias="TTU",
        default=0,
        description="Seconds until it can be opened, when read",
    )
    received_at: float = Field(
        default_factory=time.monotonic, description="When the values were read, in time.monotonic() seconds"
    )

    @field_validator("seconds", mode="before")
    @classmethod
    def _seconds(cls, value: Any) -> Any:
        return js_number(value)

    @property
    def is_active(self) -> bool:
        """Whether there is a next chest."""
        return self.next_reward_id >= 0

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds until the chest can be opened, 0 once it can."""
        return max(0.0, self.seconds - ((time.monotonic() if now is None else now) - self.received_at))

    def is_ready(self, now: float | None = None) -> bool:
        """Whether there is a chest and it can be opened now, as the dialog enables its button."""
        return self.is_active and self.remaining_seconds(now) <= 0


class OpenActivityChestRequest(BaseRequest):
    """
    Open the activity chest.

    Command: uoa
    Payload: {}

    Client: ``C2SOpenActivityChest`` (bundle line 104948), sent by ``CastleActivityBonusDialog.onClick``
    (bundle line 104934) once no time is left
    """

    command = "uoa"


class OpenActivityChestResponse(BaseResponse):
    """
    A reply to opening the chest, should one come: none did live, and the client registers no command for it.

    Command: uoa
    Client: ``ClientConstSF.S2C_OPEN_ACTIVITY_CHEST`` (bundle line 71), absent from the command
    table (bundle line 120368)
    """

    command = "uoa"


# =============================================================================
# GWH / RWB - Weekly honour reward
# =============================================================================


class GetWeeklyHonorRequest(BaseRequest):
    """
    Ask for your weekly honour rank.

    Command: gwh
    Payload: {}

    Client: ``C2SGetWeeklyHonorRankVO`` (bundle line 69926), sent when
    ``CastleWeeklyHighscoreRewardDialog`` opens (bundle line 45344)
    """

    command = "gwh"


class GetWeeklyHonorResponse(BaseResponse):
    """
    Your weekly honour rank, and when the next reward comes.

    Command: gwh

    Client: ``GWHCommand.executeCommand`` (bundle line 124364), ``CastleHighscoreData.parseGWH``,
    ``isReadyToCollect`` and ``nextRewardRemainingTime`` (bundle lines 111899-111912)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gwh"

    last_week_rank: ParseInt = Field(
        validation_alias="LWR",
        serialization_alias="LWR",
        default=0,
        description="Last week's rank, whose reward waits; 0 when none waits",
    )
    current_rank: ParseInt = Field(
        validation_alias="CWR", serialization_alias="CWR", default=0, description="This week's rank so far"
    )
    seconds: ParseInt = Field(
        validation_alias="RT",
        serialization_alias="RT",
        default=0,
        description="Seconds until the next reward, when read",
    )
    league_id: ParseInt = Field(validation_alias="LID", serialization_alias="LID", default=0, description="Your league")
    received_at: float = Field(
        default_factory=time.monotonic, description="When the values were read, in time.monotonic() seconds"
    )

    @property
    def is_ready(self) -> bool:
        """Whether last week's reward waits to be redeemed."""
        return self.last_week_rank > 0

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds until the next reward, 0 once it is due."""
        return max(0.0, self.seconds - ((time.monotonic() if now is None else now) - self.received_at))


class RedeemWeeklyHonorRequest(BaseRequest):
    """
    Redeem last week's honour reward.

    Command: rwb
    Payload: {}

    Client: ``C2SRedeemWeeklyHonorBonus`` (bundle line 69934), sent by
    ``CastleWeeklyHighscoreRewardDialog.collect`` (bundle line 45392); the button is enabled only
    with honour and a waiting reward (bundle line 45347)
    """

    command = "rwb"


class RedeemWeeklyHonorResponse(BaseResponse):
    """
    Your coins, rubies and units after the reward.

    Command: rwb

    Client: ``RWBCommand.executeCommand`` (bundle line 124426), ``CastleHighscoreData.parseRWB``
    (bundle line 111900) reads ``gcu`` and ``gui``
    """

    command = "rwb"

    currencies: CurrencyBlock = Field(
        validation_alias="gcu", serialization_alias="gcu", default=None, description="Coins and rubies after the reward"
    )
    unit_inventory: UnitInventoryBlock = Field(
        validation_alias="gui", serialization_alias="gui", default=None, description="Units after the reward"
    )


# =============================================================================
# GPN / CPN - Patch note rewards
# =============================================================================


class GetPatchNoteRewardsRequest(BaseRequest):
    """
    Ask for a patch note's rewards.

    Command: gpn
    Payload: {"PNID": patch note id}

    Client: ``C2SGetPatchNoteRewardsVO`` (bundle line 136140), sent by
    ``CastleChangelistDialog.requestRewards`` (bundle line 136088) when the patch note's dialog opens
    """

    command = "gpn"

    patch_note_id: int = Field(
        validation_alias="PNID",
        serialization_alias="PNID",
        description="The patch note's PatchNoteHeader.patch_note_id",
    )


class GetPatchNoteRewardsResponse(BaseResponse):
    """
    A patch note's rewards.

    Command: gpn

    Client: ``GPNCommand.executeCommand`` (bundle line 125302) reads ``R`` with
    ``CollectableParserS2CParamObject.createList``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "gpn"

    rewards: CollectableObject = Field(
        validation_alias="R", serialization_alias="R", default=(), description="The rewards, in the order sent"
    )


class CollectPatchNoteRewardsRequest(BaseRequest):
    """
    Collect a patch note's rewards.

    Command: cpn
    Payload: {"PNID": patch note id, "MID": message id}

    Client: ``C2SCollectPatchNoteRewardsVO`` (bundle line 136131), sent by
    ``CastleChangelistDialog.collectRewards`` (bundle line 136119)
    """

    command = "cpn"

    patch_note_id: int = Field(
        validation_alias="PNID",
        serialization_alias="PNID",
        description="The patch note's PatchNoteHeader.patch_note_id",
    )
    message_id: int = Field(
        validation_alias="MID", serialization_alias="MID", description="The patch note message's MessageInfo.message_id"
    )


class CollectPatchNoteRewardsResponse(BaseResponse):
    """
    Acknowledgement of collected patch note rewards; the client reads nothing from it.

    Command: cpn
    Client: ``CPNCommand.executeCommand`` (bundle line 125269)
    """

    command = "cpn"


# =============================================================================
# PRE - Pending rewards
# =============================================================================


class PendingRewardsInfo(BaseResponse):
    """
    How many rewards wait in the reward hub. The server pushes it; nothing asks for it.

    The rewards themselves are listed and collected over the reward hub's web service, not
    over this connection.

    Command: pre

    Client: ``PRECommand.executeCommand`` (bundle line 120837) passes ``AMT`` (``CommKeys.AMOUNT``,
    dll line 18945; read at bundle line 120838) to ``RewardHubData.setAmountOfPendingRewards`` (bundle line 29786);
    ``CastleRewardHubMicroservice`` (bundle line 12885) fetches the rewards themselves
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "pre"

    amount: ClientInt = Field(
        validation_alias="AMT", serialization_alias="AMT", default=0, description="How many rewards wait"
    )


__all__ = [
    "LOGIN_BONUS_REQUIRED_XP",
    "ActivityChestInfo",
    "CollectLoginBonusRequest",
    "CollectLoginBonusResponse",
    "CollectLostAndFoundRequest",
    "CollectLostAndFoundResponse",
    "CollectPatchNoteRewardsRequest",
    "CollectPatchNoteRewardsResponse",
    "CollectStartupBonusRequest",
    "CollectStartupBonusResponse",
    "GetLoginBonusRequest",
    "GetLoginBonusResponse",
    "GetLostAndFoundRequest",
    "GetLostAndFoundResponse",
    "GetPatchNoteRewardsRequest",
    "GetPatchNoteRewardsResponse",
    "GetStartupBonusRequest",
    "GetStartupBonusResponse",
    "GetWeeklyHonorRequest",
    "GetWeeklyHonorResponse",
    "LoginBonus",
    "LoginBonusDay",
    "LostAndFoundItem",
    "OpenActivityChestRequest",
    "OpenActivityChestResponse",
    "PendingRewardsInfo",
    "RedeemWeeklyHonorRequest",
    "RedeemWeeklyHonorResponse",
]
