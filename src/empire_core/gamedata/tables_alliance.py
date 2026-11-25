"""
Typed rows of the alliance tables: ranks and their rights, glory levels, help requests, the Grand Tournament's
quests, the forge, the treasury's donatables, and Beyond the Horizon's alliance towers, robber barons, phase
triggers and rank rewards.

Each model reads the columns its client value object reads, with the same defaults.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, NewType

from pydantic import Field, field_validator, model_validator

from empire_core.enums import AllianceRank, AllianceRight, CollectableKind, HelpType, HorizonPhaseTriggerType
from empire_core.protocol.js import js_int32, js_parse_float, js_parse_int, js_truthy

from .collectables import Collectable
from .lenient import GameDataId
from .models import _parse_int_or_default, _Row
from .tables import HorizonScoringId, RewardId, _client_bool, _text, row_id

if TYPE_CHECKING:
    from .ids import CurrencyId, Event, QuestId

GrandTournamentQuestId = NewType("GrandTournamentQuestId", int)
"""The id of an ``allianceQuests`` row, a Grand Tournament quest that :attr:`GameData.grand_tournament_quests`
describes."""

AllianceTreasuryDonatableId = NewType("AllianceTreasuryDonatableId", int)
"""The id of an ``allianceFundsDonatables`` row, a good :attr:`GameData.alliance_treasury_donatables` describes."""

AllianceTowerId = NewType("AllianceTowerId", int)
"""The id of an ``allianceTowers`` row, an alliance tower level that :attr:`GameData.alliance_towers` describes."""

AllianceTowerEffectActivationId = NewType("AllianceTowerEffectActivationId", int)
"""The id of an ``allianceTowerEffectsActivations`` row, one price step of activating an alliance tower's buffs."""

HorizonDungeonId = NewType("HorizonDungeonId", int)
"""The id of an ``allianceBattleGroundDungeons`` row, a Beyond the Horizon robber baron level."""

HorizonPhaseTriggerId = NewType("HorizonPhaseTriggerId", int)
"""The id of an ``allianceBattleGroundPhaseTriggers`` row, what starts a Beyond the Horizon phase."""

HorizonRankRewardId = NewType("HorizonRankRewardId", int)
"""The id of an ``allianceBattleGroundRankRewards`` row, one rank's rewards at the end of Beyond the Horizon."""

HorizonRewardSetId = NewType("HorizonRewardSetId", int)
"""The reward set that groups :attr:`GameData.horizon_rank_rewards` rows. Not a ``rewards`` row."""


def _parse_int(value: object) -> int:
    """``parseInt(row.column || "")``; a value with no leading integer, NaN to the client, fails the row."""
    parsed = js_parse_int(value if js_truthy(value) else "")
    if parsed is None:
        raise ValueError(f"{value!r} has no leading integer")
    return parsed


def _parse_float(value: object) -> float:
    """``parseFloat(row.column || "")``; a value with no leading number, NaN to the client, fails the row."""
    number = js_parse_float(value if js_truthy(value) else "")
    if math.isnan(number):
        raise ValueError(f"{value!r} has no leading number")
    return number


class AllianceRankDef(_Row):
    """
    An alliance rank, and the right a member needs to give a member that rank or take it away.

    Client: ``CastleAllianceData.parseXML`` (split.js line 61612) keeps ``rerankRight`` by ``rankID``
    """

    rank: GameDataId[AllianceRank] = Field(validation_alias="rankID", description="The rank")
    rerank_right: GameDataId[AllianceRight] = Field(
        validation_alias="rerankRight", description="The right needed to give or take away this rank"
    )

    @field_validator("rank", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("rerank_right", mode="before")
    @classmethod
    def _right(cls, value: object) -> int:
        return _parse_int(value)


class AllianceRightDef(_Row):
    """
    An alliance right, and the lowest rank that has it.

    Client: ``CastleAllianceData.parseXML`` (split.js line 61612) keeps ``neededMemberRank`` by ``rankRightID``
    """

    right: GameDataId[AllianceRight] = Field(validation_alias="rankRightID", description="The right")
    needed_rank: GameDataId[AllianceRank] = Field(
        validation_alias="neededMemberRank",
        description="The lowest rank with the right; every rank above it has it too",
    )

    @field_validator("right", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("needed_rank", mode="before")
    @classmethod
    def _rank(cls, value: object) -> int:
        return _parse_int(value)


class AllianceGloryLevelDef(_Row):
    """
    An alliance glory level: the glory points it starts at and the goods each member gets for reaching it.

    A goods column with no leading integer, a NaN amount to the client, is left out of ``rewards``.

    Client: ``AllianceFameLevelVO.fillFromParamXML`` (split.js line 667068), the goods read with
    ``createGoodsListSave``, which leaves out an amount of 0 (split.js line 211857)
    """

    level: int = Field(validation_alias="fameLevel", description="The glory level")
    threshold: float = Field(validation_alias="threshold", description="The glory points the level starts at")
    rewards: tuple[Collectable, ...] = Field(default=(), description="The goods for reaching the level")

    @model_validator(mode="before")
    @classmethod
    def _read_rewards(cls, row: object) -> object:
        if not isinstance(row, dict) or "rewards" in row:
            return row
        rewards = []
        for column, kind in _GLORY_REWARD_COLUMNS.items():
            amount = js_parse_int(row.get(column) if js_truthy(row.get(column)) else "")
            if amount:
                rewards.append(Collectable(kind=kind, key=kind.server_key, amount=amount))
        return {**row, "rewards": tuple(rewards)}

    @field_validator("level", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("threshold", mode="before")
    @classmethod
    def _threshold(cls, value: object) -> float:
        return _parse_float(value)


_GLORY_REWARD_COLUMNS = {
    "wood": CollectableKind.WOOD,
    "stone": CollectableKind.STONE,
    "currency1": CollectableKind.COINS,
    "currency2": CollectableKind.RUBIES,
}


def is_glory_reward_column(column: str) -> bool:
    """Whether an ``alliancefameranks`` column is one of the goods :class:`AllianceGloryLevelDef` reads."""
    return column in _GLORY_REWARD_COLUMNS


class AllianceHelpRequestDef(_Row):
    """
    A kind of alliance help request: how many members can help, and what healing and building help gives.

    Client: ``AllianceHelpRequestData.parseNeededProgressValues`` (split.js line 666133) reads
    ``unitHealTimeReduction`` of the ``HEAL_UNIT`` row and ``decreaseBuildingTimeAbsolute`` of the ``BUILD`` row only
    """

    help_type: GameDataId[HelpType] = Field(validation_alias="allianceHelpRequestID", description="The kind of help")
    max_helpers: int = Field(validation_alias="maxHelpersCount", description="How many members can help")
    heal_time_reduction: int | None = Field(
        validation_alias="unitHealTimeReduction",
        default=None,
        description="What a help cuts off the healing time, as the hospital's help button shows it; "
        "None for every kind but HEAL_UNIT",
    )
    build_time_reduction_seconds: int | None = Field(
        validation_alias="decreaseBuildingTimeAbsolute",
        default=None,
        description="Seconds a help cuts off the building time; None for every kind but BUILD",
    )

    @field_validator("help_type", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("max_helpers", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int(value)

    @field_validator("heal_time_reduction", "build_time_reduction_seconds", mode="before")
    @classmethod
    def _reduction(cls, value: object) -> int | None:
        return None if value is None else js_parse_int(value if js_truthy(value) else "")

    @model_validator(mode="after")
    def _only_for_its_kind(self) -> AllianceHelpRequestDef:
        if self.help_type != HelpType.HEAL_UNIT:
            self.heal_time_reduction = None
        if self.help_type != HelpType.BUILD:
            self.build_time_reduction_seconds = None
        return self


class GrandTournamentQuestDef(_Row):
    """
    A quest the Grand Tournament can put in an alliance's quest slots.

    A row without a ``questType`` fails, as the client fails capitalising its first letter.

    Client: ``AllianceQuestVO.fillFromParamXML`` (split.js line 573015), kept by ``allianceQuestID`` in
    ``AllianceQuestData`` (split.js line 572978)
    """

    quest_id: GrandTournamentQuestId = Field(validation_alias="allianceQuestID", description="The tournament quest")
    duration_seconds: int = Field(validation_alias="duration", default=0, description="Seconds it can be played")
    quest: GameDataId["QuestId"] = Field(
        validation_alias="questID", default=-1, description="The quest whose conditions it plays; -1 for none"
    )
    reward_points: int = Field(validation_alias="rewardPoints", default=0, description="Points it gives")
    quest_type: str = Field(validation_alias="questType", description="What it asks for, with a capital first letter")
    cancel_cost_rubies: int = Field(validation_alias="cancelCostC2", default=199, description="Rubies to cancel it")
    event_id: GameDataId["Event"] = Field(
        validation_alias="eventID", default=-1, description="The event it belongs to; -1 for none named"
    )

    @field_validator("quest_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("duration_seconds", "reward_points", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("quest", "event_id", mode="before")
    @classmethod
    def _id_column(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)

    @field_validator("cancel_cost_rubies", mode="before")
    @classmethod
    def _cancel_cost(cls, value: object) -> int:
        return _parse_int_or_default(value, 199)

    @field_validator("quest_type", mode="before")
    @classmethod
    def _quest_type(cls, value: object) -> str:
        text = _text(value)
        if not text:
            raise ValueError("no questType")
        return text[0].upper() + text[1:]


class AllianceForgeLevelDef(_Row):
    """
    A level of the alliance forge, and the coins a craft costs at it.

    Client: ``AllianceForgeVO`` (split.js line 465089), kept by ``level`` in ``AllianceBuffData`` (split.js line 271309)
    """

    level: int = Field(validation_alias="level", description="The forge level")
    forge_id: int = Field(validation_alias="allianceForgeID", description="The row's own id")
    forging_cost_coins: int = Field(
        validation_alias="forgingCostC1", description="Coins a craft costs, before cost reductions"
    )

    @field_validator("level", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("forge_id", "forging_cost_coins", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int(value)


class AllianceTreasuryDonatableDef(_Row):
    """
    A good the alliance treasury takes: a resource or a currency, and whether a member may donate it.

    ``resource_id`` names a ``resources`` row, which the game data does not load yet.

    Client: ``AllianceFundsDonatableVO.fillFromXML`` (split.js line 342439)
    """

    donatable_id: AllianceTreasuryDonatableId = Field(
        validation_alias="allianceFundsDonatableID", description="The donatable"
    )
    resource_id: int = Field(validation_alias="resourceID", default=-1, description="The resource; -1 for a currency")
    currency_id: GameDataId["CurrencyId"] = Field(
        validation_alias="currencyID", default=-1, description="The currency; -1 for a resource"
    )
    directly_by_player: bool = Field(
        validation_alias="directlyByPlayer", default=False, description="Members can donate it themselves"
    )

    @field_validator("donatable_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("resource_id", "currency_id", mode="before")
    @classmethod
    def _id_column(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)

    @field_validator("directly_by_player", mode="before")
    @classmethod
    def _bool(cls, value: object) -> bool:
        return _client_bool(value, False)


class AllianceTowerDef(_Row):
    """
    A level of a Beyond the Horizon alliance tower: the victories it takes, its defence and what defeating it gives.

    Client: ``ABGAllianceTowerInfoVO.parseXML`` (split.js line 716516)
    """

    tower_id: AllianceTowerId = Field(validation_alias="allianceTowerID", description="The tower level row")
    victory_count: int = Field(
        validation_alias="countVictory", default=0, description="The victories the level starts at"
    )
    level: int = Field(validation_alias="level", default=0, description="The tower level")
    commander_id: int = Field(
        validation_alias="lordID", default=0, description="Its defending commander, a GameData.default_commanders id"
    )
    unit_capacity: int = Field(validation_alias="unitCapacity", default=0, description="How many units it holds")
    defeated_pvp_base_points: int = Field(
        validation_alias="defeatedPVPBasePoints", default=0, description="Base points for defeating it"
    )
    level_multiplier: int = Field(
        validation_alias="allianceTowerLevelMultiplier", default=0, description="Its level's points multiplier"
    )
    add_statuette: int = Field(
        validation_alias="addStatuette",
        default=0,
        description="Points defeating it gives while none of its connections is defeated",
    )

    @field_validator("tower_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "victory_count", "level", "commander_id", "unit_capacity", "defeated_pvp_base_points", "level_multiplier",
        "add_statuette", mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    def points_to_loot(self, defeated_connections: int) -> int:
        """
        The points defeating the tower gives with ``defeated_connections`` of its connections defeated.

        Client: ``AllianceBattleGroundConst.calculateAllianceTowerPointsToLoot`` (ggs.dll.js line 237)
        """
        if defeated_connections == 0:
            return self.add_statuette
        return (self.add_statuette + self.defeated_pvp_base_points * js_int32(2 ** min(defeated_connections, 32))) * (
            self.level_multiplier
        )


class AllianceTowerEffectActivationDef(_Row):
    """
    One price step of activating an alliance tower's buffs: the price while the tower's revival is under its time.

    Client: ``ABGAllianceTowerEffectActivationVO.parseXML`` (split.js line 716276)
    """

    activation_id: AllianceTowerEffectActivationId = Field(
        validation_alias="allianceTowerEffectsActivationID", description="The price step"
    )
    remaining_seconds: int = Field(
        validation_alias="remainingTime", default=0, description="Seconds until revival the step applies under"
    )
    cost_rubies: int = Field(validation_alias="cost", default=0, description="Rubies the activation costs")

    @field_validator("activation_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("remaining_seconds", "cost_rubies", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)


class HorizonDungeonDef(_Row):
    """
    A level of a Beyond the Horizon robber baron in one scoring: the victories it takes, its cooldown and defence.

    Client: ``AllianceBattleGroundDungeonVO.parseXML`` (split.js line 716990)
    """

    dungeon_id: HorizonDungeonId = Field(validation_alias="allianceBattleGroundDungeonID", description="The row")
    scoring_id: HorizonScoringId = Field(
        validation_alias="allianceBattleGroundScoringID",
        default=HorizonScoringId(0),
        description="The scoring it is played in, a GameData.horizon_scorings row",
    )
    level: int = Field(validation_alias="dungeonlevel", default=0, description="The robber baron's level")
    victory_count: int = Field(
        validation_alias="countVictory", default=0, description="Your victories over it that reach this level"
    )
    skip_cost: int = Field(
        validation_alias="skipCost", default=0, description="Rubies to skip three hours of its cooldown"
    )
    cooldown_seconds: int = Field(validation_alias="coolDown", default=0, description="Seconds of cooldown")
    wall_bonus: int = Field(validation_alias="wallBonus", default=0, description="Wall protection, in percent")
    gate_bonus: int = Field(validation_alias="gateBonus", default=0, description="Gate protection, in percent")

    @field_validator("dungeon_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "scoring_id", "level", "victory_count", "skip_cost", "cooldown_seconds", "wall_bonus", "gate_bonus",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)


class HorizonPhaseTriggerDef(_Row):
    """
    What starts the next phase of a Beyond the Horizon run: a timer, or a citadel condition.

    Client: ``ABGPhaseTriggerVO.parseXML`` (split.js line 156036)
    """

    phase_trigger_id: HorizonPhaseTriggerId = Field(validation_alias="phaseTriggerID", description="The trigger")
    trigger_type: GameDataId[HorizonPhaseTriggerType] = Field(
        validation_alias="type", default=0, description="What kind of trigger it is"
    )
    timer_offset_seconds: int = Field(
        validation_alias="timerOffset", default=0, description="A timer trigger's offset in seconds"
    )
    warning_lead_seconds: int = Field(
        validation_alias="warningLeadTime", default=-1, description="Seconds of warning before it fires; -1 for none"
    )
    citadel_level: int = Field(validation_alias="citadelLevel", default=0, description="The citadel level it needs")
    alliance_share: int = Field(
        validation_alias="allianceShare", default=0, description="The share of alliances it needs, in percent"
    )
    warning_share: int = Field(
        validation_alias="warningShare", default=0, description="The share of alliances its warning starts at"
    )
    min_alliances: int = Field(validation_alias="minAlliances", default=0, description="The fewest alliances it needs")
    evaluation_delay_seconds: int = Field(
        validation_alias="evaluationDelay", default=0, description="Seconds before it is evaluated"
    )

    @field_validator("phase_trigger_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "trigger_type", "timer_offset_seconds", "citadel_level", "alliance_share", "warning_share", "min_alliances",
        "evaluation_delay_seconds", mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("warning_lead_seconds", mode="before")
    @classmethod
    def _warning_lead(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)

    @property
    def has_warning_lead_time(self) -> bool:
        """Whether it warns before it fires (``hasWarningLeadTime``)."""
        return self.warning_lead_seconds > -1


class HorizonRankRewardDef(_Row):
    """
    The rewards for one alliance rank, or for reaching some participation points, at the end of Beyond the Horizon.

    The client takes the rank when it is above 0, else the participation points when those are.

    Client: ``AllianceBattlegroundRewardVO.parseXML`` (split.js line 717072)
    """

    rank_reward_id: HorizonRankRewardId = Field(
        validation_alias="allianceBattleGroundRankRewardID", description="The row"
    )
    reward_set_id: HorizonRewardSetId = Field(
        validation_alias="rewardSetID", default=HorizonRewardSetId(0), description="The reward set it belongs to"
    )
    reward_id: RewardId = Field(
        validation_alias="rewardID", default=RewardId(0), description="What it gives, a GameData.rewards row"
    )
    rank: int = Field(validation_alias="rank", default=0, description="The rank it rewards; 0 for none")
    participation_points: int = Field(
        validation_alias="participationPoints",
        default=0,
        description="The participation points it rewards, when it rewards no rank; 0 for none",
    )

    @field_validator("rank_reward_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("reward_set_id", "reward_id", "rank", "participation_points", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)


__all__ = [
    "AllianceForgeLevelDef",
    "AllianceGloryLevelDef",
    "AllianceHelpRequestDef",
    "AllianceRankDef",
    "AllianceRightDef",
    "AllianceTowerDef",
    "AllianceTowerEffectActivationDef",
    "AllianceTowerEffectActivationId",
    "AllianceTowerId",
    "AllianceTreasuryDonatableDef",
    "AllianceTreasuryDonatableId",
    "GrandTournamentQuestDef",
    "GrandTournamentQuestId",
    "HorizonDungeonDef",
    "HorizonDungeonId",
    "HorizonPhaseTriggerDef",
    "HorizonPhaseTriggerId",
    "HorizonRankRewardDef",
    "HorizonRankRewardId",
    "HorizonRewardSetId",
    "is_glory_reward_column",
]
