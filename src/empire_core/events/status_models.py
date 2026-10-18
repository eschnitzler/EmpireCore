"""Read-only alliance mobilisation and raid status protocols."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import ConfigDict, Field, field_validator, model_validator

from empire_core.enums.events import RaidBossCardStatus
from empire_core.gamedata import EnumOrInt
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, js_int, js_loose_equals, js_string, js_truthy

if TYPE_CHECKING:
    from empire_core.gamedata import RaidBoss

logger = logging.getLogger(__name__)


class AllianceQuestProgress(BasePayload):
    """Progress of the quest occupying a slot; its quest definition is in game data.

    Client: ``AllianceQuestSlotVO.fillFromParams`` (bundle 34950-34951) delegates the first QL
    entry to ``CastleQuestVO.fillFromParams`` (52463-52466). No quest id is invented from QL.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")
    counters: tuple[ClientInt, ...] = Field(default=(), validation_alias="P", description="Quest condition counters")
    remaining_seconds: ClientInt = Field(
        default=-1, validation_alias="RS", description="Quest seconds at receipt; -1 without a time limit"
    )
    campaign_quest_id: ClientInt = Field(default=0, validation_alias="CQID", description="Quest's place in a campaign")
    campaign_timestamp: ClientInt | None = Field(
        default=None, validation_alias="ST", description="Campaign quest opening timestamp"
    )
    completed: bool = Field(default=False, description="Whether the quest is complete")
    failed: bool = Field(default=False, description="Whether the quest failed")
    locked: bool = Field(default=False, description="Whether the quest is locked")

    @model_validator(mode="before")
    @classmethod
    def _status(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        result = dict(value)
        if "S" in value:
            result["completed"] = js_loose_equals(value["S"], 1)
            result["failed"] = js_loose_equals(value["S"], 0)
        elif "QCS" in value:
            result.update(completed=value["QCS"] == "C", failed=value["QCS"] == "F", locked=value["QCS"] == "N")
        return result


class AllianceQuestSlot(BasePayload):
    """Client: ``AllianceQuestSlotVO.fillFromParams`` (bundle lines 34949-34951).

    Keys: ``CommKeys`` (dll.pretty lines 80007,79871,80180,79617).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")
    slot_id: int = Field(description="Zero-based slot position")
    alliance_quest_id: ClientInt = Field(validation_alias="QID", description="Alliance quest definition id")
    player_id: ClientInt = Field(validation_alias="PID", description="Assigned player id; nonpositive when unassigned")
    player_name: str = Field(default="", validation_alias="PN", description="Assigned player's name")
    remaining_seconds: ClientInt = Field(validation_alias="RS", description="Quest or cooldown seconds at receipt")
    progress: AllianceQuestProgress | None = Field(
        default=None, validation_alias="QL", description="Assigned quest progress"
    )

    @field_validator("player_name", mode="before")
    @classmethod
    def _name(cls, value: Any) -> str:
        return js_string(value) if js_truthy(value) else ""

    @field_validator("progress", mode="before")
    @classmethod
    def _progress(cls, value: Any) -> Any:
        if isinstance(value, AllianceQuestProgress) or value is None:
            return value
        if not isinstance(value, list):
            raise ValueError("Expected quest progress list")
        return value[0] if value else None


class GetMobilizationStatusRequest(BaseRequest):
    """Client: ``C2SAllianceQuestStatusVO`` (bundle lines 75687-75691)."""

    command: ClassVar[str] = "aqs"
    event_id: int = Field(validation_alias="EID", description="Alliance mobilisation event")

    def accepts_reply(self, payload: Any) -> bool:
        """AQSCommand looks up EID as a numeric Map key (bundle 127419-127420)."""
        return (
            isinstance(payload, dict) and type(payload.get("EID")) in (int, float) and payload["EID"] == self.event_id
        )


class MobilizationQuestStatus(BaseResponse):
    """Client: ``AQSCommand`` (bundle 127419-127420), ``parseQuestSlots`` (5104-5110)."""

    command: ClassVar[str] = "aqs"
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")
    event_id: ClientInt = Field(validation_alias="EID", description="Alliance mobilisation event")
    participants: ClientInt = Field(validation_alias="APC", description="Participating alliance members")
    slots: tuple[AllianceQuestSlot, ...] = Field(validation_alias="AQS", description="Alliance quest slots")

    @field_validator("slots", mode="before")
    @classmethod
    def _slots(cls, value: Any) -> tuple[AllianceQuestSlot, ...]:
        if not isinstance(value, list):
            raise ValueError("Expected alliance quest slot list")
        entries = [
            {**entry, "slot_id": index} if isinstance(entry, dict) else {"slot_id": index}
            for index, entry in enumerate(value)
        ]
        return tuple(readable_list(AllianceQuestSlot, entries, warn=logger, what="alliance quest slots"))


class MobilizationContribution(BasePayload):
    """Client: ``AllianceMobilizationEventDialogContributionItem.update`` (bundle 76178)."""

    rank: ClientInt = Field(validation_alias="R", description="Contribution rank")
    player_name: str = Field(validation_alias="PN", description="Contributing player's name")
    points: ClientInt = Field(validation_alias="OP", description="Contributed event points")


class GetMobilizationContributionsRequest(BaseRequest):
    """Client: ``C2SAllianceDivisionPlayerContributionVO`` (bundle 75678-75682)."""

    command: ClassVar[str] = "aqpc"
    event_id: int = Field(validation_alias="EID", description="Alliance mobilisation event")


class GetMobilizationContributionsResponse(BaseResponse):
    """Client: ``AQPCCommand`` (bundle 127404-127405)."""

    command: ClassVar[str] = "aqpc"
    contributions: tuple[MobilizationContribution, ...] = Field(
        validation_alias="AQPC", description="Player contributions in server order"
    )

    @field_validator("contributions", mode="before")
    @classmethod
    def _contributions(cls, value: Any) -> tuple[MobilizationContribution, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("Expected mobilisation contributions list")
        entries = [{} if entry is None else entry for entry in value]
        return tuple(readable_list(MobilizationContribution, entries, warn=logger, what="mobilisation contributions"))


class RaidBossWall(BasePayload):
    """Client: ``AllianceRaidbossServerDataVO.parseActiveBlock`` (bundle 76195-76196)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")
    regeneration_seconds: float = Field(validation_alias="RT", description="Seconds until wall regeneration at receipt")
    percent_left: float = Field(validation_alias="PL", description="Wall health percentage left")


class RaidBossWalls(BasePayload):
    """Client: ``AllianceRaidbossServerDataVO.parseActiveBlock`` (bundle 76195-76196)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")
    left: RaidBossWall = Field(validation_alias="L", description="Left wall status")
    middle: RaidBossWall = Field(validation_alias="M", description="Middle wall status")
    right: RaidBossWall = Field(validation_alias="R", description="Right wall status")


class RaidBossCard(BasePayload):
    """Client: ``AllianceRaidBossCardVO.parse`` (bundle 76258); CommKeys dll.pretty 81112-81115."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")
    boss_id: EnumOrInt["RaidBoss"] = Field(validation_alias="BID", description="Boss represented by the card")
    status: EnumOrInt[RaidBossCardStatus] = Field(validation_alias="CST", description="Boss card status")
    unlocked_level: ClientInt = Field(validation_alias="ULV", description="Unlocked boss level")


class RaidBossStatus(BasePayload):
    """Current boss and cards; wall timers are snapshots at receipt.

    Client: ``AllianceRaidbossServerDataVO.parse_bse``, ``parse_bbs``, ``parseActiveBlock``,
    ``parseBossCards``, ``hasActiveBlock`` and ``clearActiveRaidState`` (bundle 76190-76205).
    Keys: ``CommKeys`` (dll.pretty 81112-81125). Health: ``MathBase.ceil`` (dll.pretty 23328-23330).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")
    boss_id: EnumOrInt["RaidBoss"] = Field(default=0, validation_alias="BID", description="Current boss; 0 without one")
    level_id: ClientInt = Field(default=0, validation_alias="BLID", description="Current boss level id; 0 without one")
    health: float = Field(
        default=0, validation_alias="HP", description="Current boss health, rounded up to two decimals"
    )
    revive_unit_percent: float = Field(default=0, validation_alias="RUP", description="Percentage of units revived")
    stage_id: ClientInt = Field(default=0, validation_alias="BS", description="Current boss stage id; 0 without one")
    walls: RaidBossWalls | None = Field(default=None, validation_alias="WI", description="Latest wall status")
    cards: tuple[RaidBossCard, ...] = Field(default=(), validation_alias="BCDS", description="Available boss cards")

    @model_validator(mode="before")
    @classmethod
    def _active(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if "raw" in value:
            raise ValueError("Unreadable raid status packet")
        active = (
            js_int(value.get("BID", value.get("boss_id"))) > 0 or js_int(value.get("BLID", value.get("level_id"))) > 0
        )
        if not active:
            cleared = {**value, "BID": 0, "BLID": 0, "HP": 0, "RUP": 0, "BS": 0}
            cleared.pop("WI", None)
            cleared.pop("walls", None)
            return cleared
        if not all(
            wire in value or name in value
            for wire, name in (("BLID", "level_id"), ("HP", "health"), ("RUP", "revive_unit_percent"))
        ):
            raise ValueError("Active raid status requires level, health and revival percentage")
        return value

    @field_validator("health")
    @classmethod
    def _health(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Raid health must be finite")
        return math.ceil(value * 100) / 100

    @field_validator("walls", mode="before")
    @classmethod
    def _walls(cls, value: Any) -> Any:
        return value if js_truthy(value) else None

    @field_validator("cards", mode="before")
    @classmethod
    def _cards(cls, value: Any) -> tuple[RaidBossCard, ...]:
        if not js_truthy(value):
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("Expected raid boss card list")
        entries = [{} if entry is None else entry for entry in value]
        return tuple(readable_list(RaidBossCard, entries, warn=logger, what="raid boss cards"))

    @property
    def active(self) -> bool:
        """Whether the response includes a current boss or boss level."""
        return self.boss_id > 0 or self.level_id > 0

    def with_previous(self, previous: RaidBossStatus | None) -> RaidBossStatus:
        """Retain identity, stage and walls for fields the client updates only when supplied."""
        if previous is None:
            return self
        updates: dict[str, Any] = {}
        if self.active:
            if self.boss_id <= 0:
                updates["boss_id"] = previous.boss_id
            if "stage_id" not in self.model_fields_set:
                updates["stage_id"] = previous.stage_id
        if "walls" not in self.model_fields_set or self.walls is None:
            updates["walls"] = previous.walls
        return self.model_copy(update=updates)


class GetRaidBossStatusRequest(BaseRequest):
    """Client: ``C2SGetAllianceRaidBossStatus`` (bundle 47183-47187)."""

    command: ClassVar[str] = "bse"


class GetRaidBossStatusResponse(BaseResponse):
    """Client: ``BSECommand`` (bundle 127537-127538)."""

    command: ClassVar[str] = "bse"
    status: RaidBossStatus = Field(description="Boss status supplied by the server")

    @model_validator(mode="before")
    @classmethod
    def _status(cls, value: Any) -> Any:
        return {"status": value} if isinstance(value, dict) and "status" not in value else value


class RaidBossStatusBroadcast(GetRaidBossStatusResponse):
    """Client: ``BBSCommand`` (bundle 127522-127523), parsed like bse."""

    command: ClassVar[str] = "bbs"
