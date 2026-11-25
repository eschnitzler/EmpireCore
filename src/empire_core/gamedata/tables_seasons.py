"""
Typed rows of the special server and season tables: the Outer Realms' rank points and rewards, the Storm Islands'
isles and rewards, the Kingdom's League's settings, ranks, medals and rewards, the daimyo's end rewards, the division
rounds of the Grand Tournament and the Rift Raid, and the Rift Raid's boss levels and stages.

Each model reads the columns its client value object reads, with the same defaults.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, NewType

from pydantic import Field, field_validator

from empire_core.enums import DivisionRoundType
from empire_core.protocol.js import js_falsy, js_parse_float, js_parse_int

from .lenient import GameDataId, GameDataKey
from .models import EffectValue, _parse_int_or_default, _Row
from .stacks import WodAmount
from .tables import OuterRealmsRewardSetId, RewardId, _client_bool, _int_list, _text, row_id

if TYPE_CHECKING:
    from .collectables import Collectable
    from .data import GameData
    from .ids import Effect, Event, General, LeagueType, RaidBoss


OuterRealmsRankId = NewType("OuterRealmsRankId", int)
"""The id of a ``tempServerRankPoints`` row, a band of Outer Realms ranks that
:attr:`GameData.outer_realms_rank_points` describes."""

OuterRealmsRankRewardId = NewType("OuterRealmsRankRewardId", int)
"""The id of a ``tempServerRankRewards`` row, one rank reward of one reward set that
:attr:`GameData.outer_realms_rank_rewards` describes."""

OuterRealmsDailyTaskRewardId = NewType("OuterRealmsDailyTaskRewardId", int)
"""The id of a ``tempServerDailyTaskRewards`` row, an Outer Realms daily task reward step that
:attr:`GameData.outer_realms_daily_task_rewards` describes."""

IsleId = NewType("IsleId", int)
"""The id of an ``isles`` row, a Storm Islands isle that :attr:`GameData.storm_isles` describes."""

StormIslandsRewardSetId = NewType("StormIslandsRewardSetId", int)
"""The reward set the Storm Islands kingdom runs with: which :attr:`GameData.storm_islands_alliance_rewards` and
:attr:`GameData.storm_islands_player_rewards` rows it gives. Not a ``rewards`` row."""

StormIslandsAllianceRewardId = NewType("StormIslandsAllianceRewardId", int)
"""The id of an ``islandrewardranks`` row, a Storm Islands alliance reward that
:attr:`GameData.storm_islands_alliance_rewards` describes."""

StormIslandsPlayerRewardId = NewType("StormIslandsPlayerRewardId", int)
"""The id of an ``islandPlayerRewards`` row, a Storm Islands player reward that
:attr:`GameData.storm_islands_player_rewards` describes."""

KingdomsLeagueSettingId = NewType("KingdomsLeagueSettingId", int)
"""The id of a ``seasonSettings`` row, the Kingdom's League's season pass prices that
:attr:`GameData.kingdoms_league_settings` describes."""

KingdomsLeagueRankId = NewType("KingdomsLeagueRankId", int)
"""The id of a ``seasonRanks`` row, a Kingdom's League rank that :attr:`GameData.kingdoms_league_ranks` describes."""

KingdomsLeagueMedalId = NewType("KingdomsLeagueMedalId", int)
"""The id of a ``seasonMedals`` row, a Kingdom's League medal that :attr:`GameData.kingdoms_league_medals`
describes."""

KingdomsLeagueRewardSetId = NewType("KingdomsLeagueRewardSetId", int)
"""The reward set a Kingdom's League names in its ``RSID``: which end, event and promotion reward rows it gives. Not a
``rewards`` row."""

KingdomsLeagueEndRewardId = NewType("KingdomsLeagueEndRewardId", int)
"""The id of a ``seasonEndRewards`` row, a Kingdom's League end reward band that
:attr:`GameData.kingdoms_league_end_rewards` describes."""

KingdomsLeagueEventRewardId = NewType("KingdomsLeagueEventRewardId", int)
"""The id of a ``seasonEventRewards`` row, a Kingdom's League season event reward that
:attr:`GameData.kingdoms_league_event_rewards` describes."""

KingdomsLeaguePromotionRewardId = NewType("KingdomsLeaguePromotionRewardId", int)
"""The id of a ``seasonPromotionRewards`` row, a Kingdom's League rank-up reward that
:attr:`GameData.kingdoms_league_promotion_rewards` describes."""

DaimyoRewardSetId = NewType("DaimyoRewardSetId", int)
"""The reward set of a Samurai Invasion's daimyo: which :attr:`GameData.daimyo_end_rewards` rows it gives. Not a
``rewards`` row."""

DaimyoEndRewardId = NewType("DaimyoEndRewardId", int)
"""The id of a ``daimyoEndRewards`` row, a daimyo end reward band that :attr:`GameData.daimyo_end_rewards`
describes."""

DivisionRoundId = NewType("DivisionRoundId", int)
"""The id of a ``divisionRounds`` row, a division round of the Grand Tournament or the Rift Raid that
:attr:`GameData.division_rounds` describes."""

RaidBossLevelId = NewType("RaidBossLevelId", int)
"""The id of a ``raidBossLevels`` row, a level of a Rift Raid boss that :attr:`GameData.raid_boss_levels`
describes."""

RaidBossStageId = NewType("RaidBossStageId", int)
"""The id of a ``raidBossStages`` row, a stage of a Rift Raid boss level that :attr:`GameData.raid_boss_stages`
describes."""


def _int_attribute(value: object, default: int) -> int:
    """
    ``int(CastleXMLUtils.getIntAttribute(key, row, default))`` (split.js line 5862): a missing or empty value reads
    as the default, text with no leading integer as ``int(NaN)``, 0.
    """
    if js_falsy(value):
        return default
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    parsed = js_parse_int(value)
    return 0 if parsed is None else parsed


def _reward_ids(value: object) -> list[int]:
    """
    ``CollectableParser.createListFromRewardIdsString`` (split.js line 211806) of a text column: the ``,`` parts whose
    ``parseInt`` is above 0.
    """
    return [reward_id for reward_id in _int_list(value) if reward_id > 0]


def _game_data(game_data: GameData | None) -> GameData:
    from .data import GameData

    return game_data if game_data is not None else GameData.require()


class _RewardsRow(_Row):
    """A row whose ``rewardIDs`` name ``rewards`` rows."""

    reward_ids: tuple[RewardId, ...] = Field(validation_alias="rewardIDs", default=(), description="Its rewards")

    def rewards(self, *, game_data: GameData | None = None) -> tuple[Collectable, ...]:
        """What it gives, the rewards one after the other."""
        return _game_data(game_data).reward_list(self.reward_ids)


class OuterRealmsRankPointsDef(_Row):
    """
    The daily rank points of one band of Outer Realms ranks.

    The client keeps the rows as a list and reads no id; the row's ``tempServerRankID`` keys it here, the id its
    rank rewards name.

    Client: ``TempServerRankRangeVO.parseXML`` (split.js line 304136), listed by ``CastleTempServerData.parseXML``
    (split.js line 697687); ``getDailyRankPointsByRank`` (split.js line 697873)
    """

    rank_id: OuterRealmsRankId = Field(validation_alias="tempServerRankID", description="The band")
    min_rank: int = Field(
        validation_alias="minRank", default=0, description="The band's worst rank, the highest number in it"
    )
    max_rank: int = Field(
        validation_alias="maxRank", default=0, description="The band's best rank, the lowest number in it"
    )
    rank_points: int = Field(validation_alias="rankPoints", default=0, description="The points a rank in it earns")

    @field_validator("rank_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("min_rank", "max_rank", "rank_points", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    def covers(self, rank: int) -> bool:
        """Whether ``rank`` is in the band."""
        return self.max_rank <= rank <= self.min_rank


class OuterRealmsRankRewardDef(_Row):
    """
    One reward of an Outer Realms reward set: for a rank, or for reaching some points.

    The client keeps the rows as a list and reads neither of the row's ids as one; the row's
    ``tempServerRankRewardID`` keys it here. A row with a rank above 0 rewards that rank, else one with participation
    points above 0 rewards those points, else the client builds no reward for it.

    Client: ``CastleTempServerRewardVO.parseXML`` (split.js line 698347), listed by ``CastleTempServerData.parseXML``
    (split.js line 697680); ``getRewardsByRewardSetID`` (split.js line 697811)
    """

    rank_reward_id: OuterRealmsRankRewardId = Field(validation_alias="tempServerRankRewardID", description="The row")
    rank_id: OuterRealmsRankId = Field(
        validation_alias="tempServerRankID",
        default=OuterRealmsRankId(0),
        description="The band of ranks it names, the id of a tempServerRankPoints row",
    )
    reward_id: RewardId = Field(validation_alias="rewardID", default=RewardId(0), description="Its reward")
    participation_points: int = Field(
        validation_alias="participationPoints", default=0, description="The points it rewards; 0 for a rank reward"
    )
    rank: int = Field(default=0, description="The rank it rewards; 0 for a points reward")
    reward_set_id: OuterRealmsRewardSetId = Field(
        validation_alias="rewardSetID", default=OuterRealmsRewardSetId(0), description="The set it belongs to"
    )

    @field_validator("rank_reward_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("rank_id", "reward_id", "participation_points", "rank", "reward_set_id", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @property
    def uses_points(self) -> bool:
        """Whether it rewards points rather than a rank."""
        return self.rank <= 0 < self.participation_points

    @property
    def gives_reward(self) -> bool:
        """Whether the client builds a reward for it: it names a rank or points above 0."""
        return self.rank > 0 or self.participation_points > 0

    def rewards(self, *, game_data: GameData | None = None) -> tuple[Collectable, ...]:
        """What it gives; nothing for a reward id of 0 or less."""
        return _game_data(game_data).reward_list([self.reward_id] if self.reward_id > 0 else [])


class OuterRealmsDailyTaskRewardDef(_Row):
    """
    A step of the Outer Realms' daily task rewards: what reaching some daily task points in a day gives.

    Client: ``CastleTempServerDailyTaskRewardVO.parseXML`` (split.js line 698297), listed by
    ``CastleTempServerData.parseXML`` (split.js line 697702); ``getDailyTaskRewardsByPoints`` (split.js line 697737)
    """

    daily_task_reward_id: OuterRealmsDailyTaskRewardId = Field(
        validation_alias="tempServerDailyTaskRewardID", description="The step"
    )
    reward_id: RewardId = Field(validation_alias="rewardID", default=RewardId(0), description="Its reward")
    min_daily_task_points: int = Field(
        validation_alias="minDailyTaskPointsPerDay", default=0, description="The daily task points a day needs"
    )

    @field_validator("daily_task_reward_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("reward_id", "min_daily_task_points", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    def rewards(self, *, game_data: GameData | None = None) -> tuple[Collectable, ...]:
        """What it gives; nothing for a reward id of 0 or less."""
        return _game_data(game_data).reward_list([self.reward_id] if self.reward_id > 0 else [])


class StormIsleDef(_Row):
    """
    An isle of the Storm Islands: a resource village or a dungeon, its loot, defence and occupation time.

    Client: ``CastleIsleBlueprintVO.fillFromParamXML`` (split.js line 703403), keyed by ``IsleID`` in
    ``CastleEilandData.parseIslandBlueprints`` (split.js line 703346)
    """

    isle_id: IsleId = Field(validation_alias="IsleID", description="The isle")
    isle_type: str = Field(
        validation_alias="type",
        default="UNKNOWN",
        description="What the isle is, e.g. VILLAGEWOOD or DUNGEON; a VILLAGE prefix marks a resource village",
    )
    dungeon_level: int = Field(validation_alias="dungeonlevel", default=0, description="Its level")
    max_victories: int = Field(
        validation_alias="maxCountVictories", default=-1, description="The most victories it counts; -1 for none"
    )
    loot_wood: int = Field(validation_alias="lootWood", default=-1, description="Wood an attack loots; -1 for none")
    loot_stone: int = Field(validation_alias="lootStone", default=-1, description="Stone an attack loots; -1 for none")
    loot_food: int = Field(validation_alias="lootFood", default=-1, description="Food an attack loots; -1 for none")
    loot_aquamarine: int = Field(
        validation_alias="lootAquamarine", default=-1, description="Aquamarine an attack loots; -1 for none"
    )
    fixed_loot_wood: int = Field(
        validation_alias="fixedLootWood", default=-1, description="Wood it gives as fixed loot; -1 for none"
    )
    fixed_loot_stone: int = Field(
        validation_alias="fixedLootStone", default=-1, description="Stone it gives as fixed loot; -1 for none"
    )
    fixed_loot_food: int = Field(
        validation_alias="fixedLootFood", default=-1, description="Food it gives as fixed loot; -1 for none"
    )
    fixed_loot_aquamarine: int = Field(
        validation_alias="fixedLootAquamarine", default=-1, description="Aquamarine it gives as fixed loot; -1 for none"
    )
    occupation_seconds: int = Field(
        validation_alias="occupationTime", default=0, description="Seconds an occupier has to hold it"
    )
    wall_bonus: int = Field(validation_alias="wallBonus", default=0, description="Its walls' defence bonus")
    gate_bonus: int = Field(validation_alias="gateBonus", default=0, description="Its gate's defence bonus")
    moat_bonus: int = Field(validation_alias="moatBonus", default=0, description="Its moat's defence bonus")
    wall_level: int = Field(validation_alias="wallLevel", default=0, description="Its walls' level")
    gate_level: int = Field(validation_alias="gateLevel", default=0, description="Its gate's level")
    moat_level: int = Field(validation_alias="moatLevel", default=0, description="Its moat's level")
    tower_level: int = Field(validation_alias="towerLevel", default=0, description="Its towers' level")

    @field_validator("isle_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("isle_type", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value, "UNKNOWN")

    @field_validator(
        "dungeon_level", "occupation_seconds", "wall_bonus", "gate_bonus", "moat_bonus", "wall_level", "gate_level",
        "moat_level", "tower_level", mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator(
        "max_victories", "loot_wood", "loot_stone", "loot_food", "loot_aquamarine", "fixed_loot_wood",
        "fixed_loot_stone", "fixed_loot_food", "fixed_loot_aquamarine", mode="before",
    )  # fmt: skip
    @classmethod
    def _int_or_none(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)

    @property
    def is_village(self) -> bool:
        """Whether it is a resource village. Client: ``getVillageResourceType`` (split.js line 703471)."""
        return "VILLAGE" in self.isle_type


class _StormIslandsRewardDef(_RewardsRow):
    """
    What the client reads of a Storm Islands reward row.

    Client: ``CastleEilandRewardsVO.fillFromParamXML`` (split.js line 128903), each row a
    ``CastleEilandRewardItemVO`` (split.js line 503296)
    """

    cargo_points_needed: int = Field(
        validation_alias="cargoPointRequirement", default=0, description="The cargo points it needs"
    )
    top_x: int = Field(
        validation_alias="topXValue", default=-1, description="The top ranks it goes to; -1 for a cargo points reward"
    )
    reward_set_id: StormIslandsRewardSetId = Field(
        validation_alias="islandRewardSetID",
        default=StormIslandsRewardSetId(-1),
        description="The set it belongs to",
    )

    @field_validator("cargo_points_needed", mode="before")
    @classmethod
    def _cargo_points(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("top_x", "reward_set_id", mode="before")
    @classmethod
    def _int_or_none(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)

    @field_validator("reward_ids", mode="before")
    @classmethod
    def _rewards(cls, value: object) -> list[int]:
        return _reward_ids(value)

    @property
    def is_top_x_reward(self) -> bool:
        """Whether it goes to the top ranks rather than for cargo points."""
        return self.top_x > 0


class StormIslandsAllianceRewardDef(_StormIslandsRewardDef):
    """
    A Storm Islands alliance reward (``islandrewardranks``).

    Client: ``CastleEilandRewardsVO.fillFromParamXML`` (split.js line 128903); ``getActiveRewardItems`` (split.js
    line 128959) shows the rows of the Storm Islands kingdom's reward set
    """

    alliance_reward_id: StormIslandsAllianceRewardId = Field(
        validation_alias="islandRewardRankID", description="The reward"
    )

    @field_validator("alliance_reward_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)


class StormIslandsPlayerRewardDef(_StormIslandsRewardDef):
    """
    A Storm Islands player reward (``islandPlayerRewards``).

    Client: ``CastleEilandRewardsVO.fillFromParamXML`` (split.js line 128935); ``getActivePlayerRewardItems``
    (split.js line 128969) shows the rows of the Storm Islands kingdom's reward set
    """

    player_reward_id: StormIslandsPlayerRewardId = Field(
        validation_alias="islandPlayerRewardID", description="The reward"
    )

    @field_validator("player_reward_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)


class KingdomsLeagueSettingDef(_Row):
    """
    The Kingdom's League's season pass prices and discounts.

    Client: ``XmlSeasonSettingVO.parseXml`` (split.js line 708015), keyed by ``settingID`` in
    ``SeasonLeagueXml.parseXml`` (split.js line 707283); ``SeasonLeagueData.currentSetting`` (split.js line 706588)
    reads setting 1
    """

    setting_id: KingdomsLeagueSettingId = Field(validation_alias="settingID", description="The settings")
    promotion_pass_price: int = Field(
        validation_alias="seasonPassPromotionPrice", default=0, description="The price of a rank's season pass"
    )
    event_end_pass_price: int = Field(
        validation_alias="seasonPassEventEndPrice", default=0, description="The price of the season pass"
    )
    full_discount: int = Field(
        validation_alias="seasonPassFullDiscount", default=0, description="The season pass's full discount"
    )
    single_discount: int = Field(
        validation_alias="seasonPassSingleDiscount", default=0, description="The single pass discount, in percent"
    )

    @field_validator("setting_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("promotion_pass_price", "event_end_pass_price", "full_discount", "single_discount", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _int_attribute(value, 0)

    @property
    def event_pass_sale_price(self) -> int:
        """The season pass's price after the single discount. Client: ``seasonPassEventSalePrice`` (split.js line
        708034)."""
        return math.ceil(self.event_end_pass_price * (1 - self.single_discount / 100))

    @property
    def promotion_pass_sale_price(self) -> int:
        """A rank's season pass price after the single discount. Client: ``seasonPassPromotionSalePrice``
        (split.js line 708048)."""
        return math.ceil(self.promotion_pass_price * (1 - self.single_discount / 100))


class KingdomsLeagueRankDef(_Row):
    """
    A Kingdom's League rank: the medal points that unlock it.

    Client: ``XmlSeasonPromotionVO.parseXml`` (split.js line 707944), keyed by ``rankID`` in
    ``SeasonLeagueXml.parseXml`` (split.js line 707262)
    """

    rank_id: KingdomsLeagueRankId = Field(validation_alias="rankID", description="The rank")
    min_medal_points: int = Field(
        validation_alias="minMedalPointsForUnlock", default=-1, description="The medal points that unlock it"
    )
    major_rank: int = Field(validation_alias="majorRank", default=-1, description="Its major rank")
    minor_rank: int = Field(validation_alias="minorRank", default=-1, description="Its minor rank within the major one")

    @field_validator("rank_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("min_medal_points", "major_rank", "minor_rank", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _int_attribute(value, -1)

    @property
    def text_id(self) -> str:
        """The id of its name in the game's texts. Client: ``getNameTextId`` (split.js line 707962)."""
        return f"seasonLeague_rank_{self.rank_id}"


class KingdomsLeagueMedalDef(_Row):
    """
    A Kingdom's League medal: the ranks that earn it and the medal points it is worth.

    A rank earns the first medal, in the table's order, whose ``min_highscore_rank`` it does not exceed.

    Client: ``XmlSeasonMedalVO.parseXml`` (split.js line 707774), keyed by ``medalID`` in ``SeasonLeagueXml.parseXml``
    (split.js line 707257); ``getSeasonMedalForRank`` (split.js line 707410)
    """

    medal_id: KingdomsLeagueMedalId = Field(validation_alias="medalID", description="The medal")
    medal_type: str = Field(validation_alias="type", default="", description="Its kind, e.g. goldMedal")
    min_highscore_rank: int = Field(
        validation_alias="minHighscoreRank", default=0, description="The worst rank that earns it"
    )
    medal_points: int = Field(validation_alias="medalPoints", default=0, description="The medal points it is worth")

    @field_validator("medal_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("medal_type", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)

    @field_validator("min_highscore_rank", "medal_points", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _int_attribute(value, 0)


class _KingdomsLeagueRewardDef(_RewardsRow):
    """A Kingdom's League reward row's set and ``rewardIDs``, read with ``createIntListFromAttribute``."""

    reward_set_id: KingdomsLeagueRewardSetId = Field(
        validation_alias="rewardSetID",
        default=KingdomsLeagueRewardSetId(-1),
        description="The set it belongs to",
    )

    @field_validator("reward_set_id", mode="before")
    @classmethod
    def _reward_set(cls, value: object) -> int:
        return _int_attribute(value, -1)

    @field_validator("reward_ids", mode="before")
    @classmethod
    def _rewards(cls, value: object) -> list[int]:
        return _int_list(value)


class _LeagueTypeRow(_Row):
    league_type_id: GameDataId["LeagueType"] = Field(
        validation_alias="leaguetypeID", default=0, description="The league it is for; 0 for every league"
    )

    @field_validator("league_type_id", mode="before")
    @classmethod
    def _league_type(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    def matches_league_type(self, league_type_id: int) -> bool:
        """Whether it is for that league."""
        return self.league_type_id in (0, league_type_id)


class KingdomsLeagueEndRewardDef(_KingdomsLeagueRewardDef, _LeagueTypeRow):
    """
    A band of the Kingdom's League's end rewards, from its first rank up to the next band's.

    Client: ``XmlSeasonEndRewardVO.parseXml`` (split.js line 707603), keyed by ``id`` in ``SeasonLeagueXml.parseXml``
    (split.js line 707278); ``getSeasonEndRewards`` (split.js line 707288)
    """

    end_reward_id: KingdomsLeagueEndRewardId = Field(validation_alias="id", description="The band")
    min_highscore_rank: int = Field(
        validation_alias="minHighscoreRank", default=-1, description="The band's best rank, the lowest number in it"
    )

    @field_validator("end_reward_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("min_highscore_rank", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _int_attribute(value, -1)


class KingdomsLeagueEventRewardDef(_KingdomsLeagueRewardDef):
    """
    What reaching a Kingdom's League rank in one of some season events gives, with or without the season pass.

    Client: ``XmlSeasonEventRewardVO.parseXml`` (split.js line 707687), keyed by ``id`` in ``SeasonLeagueXml.parseXml``
    (split.js line 707273); ``getSeasonEventRewards`` (split.js line 707433)
    """

    event_reward_id: KingdomsLeagueEventRewardId = Field(validation_alias="id", description="The reward")
    event_ids: tuple[GameDataId["Event"], ...] = Field(
        validation_alias="eventIDs", default=(), description="The season events it is for"
    )
    rank_id: KingdomsLeagueRankId = Field(
        validation_alias="rankID",
        default=KingdomsLeagueRankId(-1),
        description="The rank it is for, a GameData.kingdoms_league_ranks row",
    )
    needs_season_pass: bool = Field(
        validation_alias="needsSeasonPass", default=False, description="Whether only the season pass gives it"
    )

    @field_validator("event_reward_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("event_ids", mode="before")
    @classmethod
    def _events(cls, value: object) -> list[int]:
        return _int_list(value)

    @field_validator("rank_id", mode="before")
    @classmethod
    def _rank(cls, value: object) -> int:
        return _int_attribute(value, -1)

    @field_validator("needs_season_pass", mode="before")
    @classmethod
    def _flag(cls, value: object) -> bool:
        return _client_bool(value, False)


class KingdomsLeaguePromotionRewardDef(_KingdomsLeagueRewardDef, _LeagueTypeRow):
    """
    What reaching a Kingdom's League rank gives, with or without the season pass.

    Client: ``XmlSeasonPromotionRewardVO.parseXml`` (split.js line 707837), keyed by ``id`` in
    ``SeasonLeagueXml.parseXml`` (split.js line 707268); ``getPromotionRewards`` (split.js line 707490)
    """

    promotion_reward_id: KingdomsLeaguePromotionRewardId = Field(validation_alias="id", description="The reward")
    rank_id: KingdomsLeagueRankId = Field(
        validation_alias="rankID",
        default=KingdomsLeagueRankId(-1),
        description="The rank it is for, a GameData.kingdoms_league_ranks row",
    )
    needs_season_pass: bool = Field(
        validation_alias="needsSeasonPass", default=False, description="Whether only the season pass gives it"
    )

    @field_validator("promotion_reward_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("rank_id", mode="before")
    @classmethod
    def _rank(cls, value: object) -> int:
        return _int_attribute(value, -1)

    @field_validator("needs_season_pass", mode="before")
    @classmethod
    def _flag(cls, value: object) -> bool:
        return _client_bool(value, False)


class DaimyoEndRewardDef(_RewardsRow):
    """
    A band of the daimyo's end rewards, up to its last rank.

    A rank gets the first band of its set, in the table's order, whose ``min_highscore_rank`` it does not exceed.

    Client: ``XmlSamuraiDaimyoRewardVO.parseXml`` (split.js line 341610), keyed by ``id`` in
    ``SamuraiDaimyoDataXml.parseXml`` (split.js line 73916); ``getEndReward`` (split.js line 73988)
    """

    end_reward_id: DaimyoEndRewardId = Field(validation_alias="id", description="The band")
    reward_set_id: DaimyoRewardSetId = Field(
        validation_alias="rewardSetID", default=DaimyoRewardSetId(-1), description="The set it belongs to"
    )
    min_highscore_rank: int = Field(
        validation_alias="minHighscoreRank", default=-1, description="The band's worst rank, the highest number in it"
    )

    @field_validator("end_reward_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("reward_set_id", "min_highscore_rank", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _int_attribute(value, -1)

    @field_validator("reward_ids", mode="before")
    @classmethod
    def _rewards(cls, value: object) -> list[int]:
        return _int_list(value)


def _per_division(counts: tuple[int, ...], division: int) -> int:
    if division < 1:
        raise ValueError(f"division {division} is below 1; divisions count from 1")
    return counts[division - 1] if division <= len(counts) else 0


class DivisionRoundDef(_Row):
    """
    A division round of the Grand Tournament or the Rift Raid: its divisions, their sizes and who moves up or down.

    Client: ``DivisonRoundVO.fillFromParamXML`` (split.js line 579875), keyed by ``divisionRoundID`` in
    ``DivisionData`` (split.js line 579846)
    """

    division_round_id: DivisionRoundId = Field(validation_alias="divisionRoundID", description="The round")
    round_type: GameDataKey[DivisionRoundType] = Field(
        validation_alias="type", default="", description="What the round does with the alliances in it"
    )
    divisions: int = Field(default=-1, description="How many divisions it has")
    subdivisions: tuple[int, ...] = Field(default=(), description="Each division's number of subdivisions, in order")
    subdivision_sizes: tuple[int, ...] = Field(
        validation_alias="subdivisionSizes", default=(), description="Each division's subdivision size, in order"
    )
    promotes: tuple[int, ...] = Field(default=(), description="How many move up from each division, in order")
    demotes: tuple[int, ...] = Field(default=(), description="How many move down from each division, in order")

    @field_validator("division_round_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("round_type", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)

    @field_validator("divisions", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)

    @field_validator("subdivisions", "subdivision_sizes", "promotes", "demotes", mode="before")
    @classmethod
    def _ints(cls, value: object) -> list[int]:
        return _int_list(value)

    def promotes_for_division(self, division: int) -> int:
        """
        How many move up from a division, counted from 1; 0 past the last.

        Raises:
            ValueError: ``division`` is below 1, which the client reads as no number

        Client: ``getPromotesForDivision`` (split.js line 579953)
        """
        return _per_division(self.promotes, division)

    def demotes_for_division(self, division: int) -> int:
        """
        How many move down from a division, counted from 1; 0 past the last.

        Raises:
            ValueError: ``division`` is below 1, which the client reads as no number

        Client: ``getDemotesForDivision`` (split.js line 579958)
        """
        return _per_division(self.demotes, division)

    @property
    def total_promotes(self) -> int:
        """How many move up in all. Client: ``getTotalPromotes`` (split.js line 579963)."""
        return sum(self.promotes)

    def qualification_division(self, rank: int) -> int:
        """
        The division a qualification round's rank qualifies for, counted from 1; 1 for a rank outside them all.

        Client: ``getQualificationNewDivison`` (split.js line 579968)
        """
        remaining = [sum(self.promotes[index:]) for index in range(len(self.promotes))]
        for index, total in enumerate(remaining):
            below = remaining[index + 1] if index + 1 < len(remaining) else 0
            if below < rank <= total:
                return index + 1
        return 1


def _courtyard_units(value: object) -> object:
    """``courtyardReserveUnits``: ``wodID+amount`` pairs joined by ``#``."""
    if not isinstance(value, str):
        return () if value is None else value
    pairs = []
    for part in value.split("#"):
        wod_id, amount, *_ = [*part.split("+"), "", ""]
        pairs.append((js_parse_int(wod_id), js_parse_int(amount) or 0))
    return [pair for pair in pairs if pair[0] is not None]


class RaidBossLevelDef(_RewardsRow):
    """
    A level of a Rift Raid boss: its courtyard, wall regeneration and rewards.

    The client reads ``courtyardMeleeRatio``, which the items do not have (their column is ``courtyardMeleePercent``),
    so it is 0 on every row.

    Client: ``AllianceRaidbossLevelVO.parseXML`` (split.js line 582671), keyed by ``raidBossLevelID`` in
    ``RaidBossData`` (split.js line 582532)
    """

    raid_boss_level_id: RaidBossLevelId = Field(validation_alias="raidBossLevelID", description="The level")
    raid_boss_id: GameDataId["RaidBoss"] = Field(validation_alias="raidBossID", default=0, description="The boss")
    level: int = Field(default=0, description="The boss's level")
    wall_regeneration_seconds: int = Field(
        validation_alias="wallRegenerationTime", default=0, description="Seconds the walls take to regenerate"
    )
    courtyard_melee_ratio: float = Field(
        validation_alias="courtyardMeleeRatio", default=0, description="The courtyard's melee ratio"
    )
    courtyard_size: int = Field(validation_alias="courtyardSize", default=0, description="The courtyard's size")
    min_points_for_boss_rewards: int = Field(
        validation_alias="minPointsForBossRewards", default=0, description="The points the boss rewards need"
    )
    courtyard_reserve_units: tuple[WodAmount, ...] = Field(
        validation_alias="courtyardReserveUnits", default=(), description="The courtyard's reserve units"
    )

    @field_validator("raid_boss_level_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "raid_boss_id", "level", "wall_regeneration_seconds", "courtyard_size", "min_points_for_boss_rewards",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("courtyard_melee_ratio", mode="before")
    @classmethod
    def _ratio(cls, value: object) -> float:
        ratio = js_parse_float("0" if js_falsy(value) else value)
        return 0.0 if math.isnan(ratio) else ratio

    @field_validator("courtyard_reserve_units", mode="before")
    @classmethod
    def _units(cls, value: object) -> object:
        return _courtyard_units(value)

    @field_validator("reward_ids", mode="before")
    @classmethod
    def _rewards(cls, value: object) -> list[int]:
        return _int_list(value)

    def stages(self, *, game_data: GameData | None = None) -> tuple[RaidBossStageDef, ...]:
        """
        Its stages, the healthiest first.

        Client: ``RaidBossData`` (split.js line 582551) adds each stage to its level, ``addStage`` (split.js line
        582731) sorts them by health
        """
        rows = [
            row
            for row in _game_data(game_data).raid_boss_stages.values()
            if row.raid_boss_level_id == self.raid_boss_level_id
        ]
        return tuple(sorted(rows, key=lambda row: -row.health))


class RaidBossStageDef(_Row):
    """
    A stage of a Rift Raid boss level: the health it starts at and the effects on each side.

    Client: ``AllianceRaidbossStageVO.parseXML`` (split.js line 582899), keyed by ``raidBossStageID`` in
    ``RaidBossData`` (split.js line 582532); ``parseEffects`` (split.js line 582991)
    """

    raid_boss_stage_id: RaidBossStageId = Field(validation_alias="raidBossStageID", description="The stage")
    raid_boss_level_id: RaidBossLevelId = Field(
        validation_alias="raidBossLevelID",
        default=RaidBossLevelId(0),
        description="The level it is a stage of, a GameData.raid_boss_levels row",
    )
    health: int = Field(default=0, description="The boss health the stage starts at")
    general_id: GameDataId["General"] = Field(validation_alias="generalID", default=0, description="The boss's general")
    defender_stage_effects: tuple[EffectValue, ...] = Field(
        validation_alias="defenderStageEffects", default=(), description="The defender's effects during the stage"
    )
    attacker_stage_effects: tuple[EffectValue, ...] = Field(
        validation_alias="attackerStageEffects", default=(), description="The attacker's effects during the stage"
    )
    defender_battle_effects: tuple[EffectValue, ...] = Field(
        validation_alias="defenderBattleEffects", default=(), description="The defender's effects in battle"
    )
    attacker_battle_effects: tuple[EffectValue, ...] = Field(
        validation_alias="attackerBattleEffects", default=(), description="The attacker's effects in battle"
    )
    defender_post_battle_effects: tuple[EffectValue, ...] = Field(
        validation_alias="defenderPostBattleEffects", default=(), description="The defender's effects after battle"
    )
    attacker_post_battle_effects: tuple[EffectValue, ...] = Field(
        validation_alias="attackerPostBattleEffects", default=(), description="The attacker's effects after battle"
    )
    defender_wall_regeneration_effects: tuple[EffectValue, ...] = Field(
        validation_alias="defenderWallRegenerationEffects",
        default=(),
        description="The defender's effects when the walls regenerate",
    )
    highlighted_effects: tuple[GameDataId["Effect"], ...] = Field(
        validation_alias="HighlightEffectIcon", default=(), description="The effects the stage highlights"
    )
    courtyard_point_factor: int = Field(
        validation_alias="courtyardPointFactor", default=0, description="The stage's courtyard point factor"
    )
    wall_point_factor: int = Field(
        validation_alias="wallPointFactor", default=0, description="The stage's wall point factor"
    )

    @field_validator("raid_boss_stage_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "raid_boss_level_id", "health", "general_id", "courtyard_point_factor", "wall_point_factor", mode="before"
    )
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator(
        "defender_stage_effects", "attacker_stage_effects", "defender_battle_effects", "attacker_battle_effects",
        "defender_post_battle_effects", "attacker_post_battle_effects", "defender_wall_regeneration_effects",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _effects(cls, value: object) -> object:
        return EffectValue.parse_list(value)

    @field_validator("highlighted_effects", mode="before")
    @classmethod
    def _highlighted(cls, value: object) -> list[int]:
        return _int_list(value)


__all__ = [
    "DaimyoEndRewardDef",
    "DaimyoEndRewardId",
    "DaimyoRewardSetId",
    "DivisionRoundDef",
    "DivisionRoundId",
    "IsleId",
    "KingdomsLeagueEndRewardDef",
    "KingdomsLeagueEndRewardId",
    "KingdomsLeagueEventRewardDef",
    "KingdomsLeagueEventRewardId",
    "KingdomsLeagueMedalDef",
    "KingdomsLeagueMedalId",
    "KingdomsLeaguePromotionRewardDef",
    "KingdomsLeaguePromotionRewardId",
    "KingdomsLeagueRankDef",
    "KingdomsLeagueRankId",
    "KingdomsLeagueRewardSetId",
    "KingdomsLeagueSettingDef",
    "KingdomsLeagueSettingId",
    "OuterRealmsDailyTaskRewardDef",
    "OuterRealmsDailyTaskRewardId",
    "OuterRealmsRankId",
    "OuterRealmsRankPointsDef",
    "OuterRealmsRankRewardDef",
    "OuterRealmsRankRewardId",
    "OuterRealmsRewardSetId",
    "RaidBossLevelDef",
    "RaidBossLevelId",
    "RaidBossStageDef",
    "RaidBossStageId",
    "StormIsleDef",
    "StormIslandsAllianceRewardDef",
    "StormIslandsAllianceRewardId",
    "StormIslandsPlayerRewardDef",
    "StormIslandsPlayerRewardId",
    "StormIslandsRewardSetId",
]
