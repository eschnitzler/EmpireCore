"""
Static game data from the GGE items payload.

The client builds its combat maths from ``items_v{version}.json`` on the GGE
CDN. That file is ~20 MB, so nothing here is fetched implicitly: call
:meth:`GameData.load` (or :meth:`EmpireClient.load_game_data`) when you want it.
What is parsed is trimmed to the combat-relevant tables, the tables the
id enums name and the rewards, and cached on disk per version, so the download happens once
per game patch.

:meth:`GameData.load` is the only loader: troop counts and the id generator
read the same process-wide copy, so one process downloads the items once.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from empire_core.enums import Kingdom, UnitRole
from empire_core.exceptions import AmbiguousLookupError, NetworkError

from . import cache, cdn
from .collectables import _KINDS_BY_XML_KEY, _XML_ADD_PREFIX, Collectable, is_reward_column
from .lenient import GameDataId
from .models import (
    READING_CACHE,
    AllianceBuffDef,
    AttackSlotDef,
    CastleEffectValue,
    ConstructionItemDef,
    CurrencyDef,
    DefaultLordDef,
    DungeonDefence,
    EffectCapDef,
    EffectDef,
    EffectTypeDef,
    EffectValue,
    EquipmentEffectDef,
    EquipmentEffectValue,
    EquipmentSetDef,
    EventCampDef,
    FortificationDef,
    GemDef,
    GeneralAbilityDef,
    GeneralDef,
    GeneralSkillDef,
    GlobalEffectDef,
    HorseStats,
    LeagueBracketDef,
    LegendSkillDef,
    NpcCampDefence,
    RaidBossDef,
    RelicEffectDef,
    SceatSkillDef,
    ToolCategoryDef,
    ToolStats,
    UnitStats,
    VipLevelDef,
    is_castle_effect_column,
)
from .table import Table
from .tables import (
    AchievementCondition,
    AchievementDef,
    AllianceCrestColorDef,
    AllianceCrestLayoutDef,
    BuildingDef,
    ConstructionItemRecipeDef,
    DailyQuestDef,
    DifficultyTypeDef,
    EquipmentGroupDef,
    EventDef,
    LootBoxDef,
    LootBoxTypeDef,
    QuestCondition,
    QuestDef,
    ResearchDef,
    RewardDef,
    RewardId,
    ScalingCampDef,
    TitleDef,
    row_id,
)

if TYPE_CHECKING:
    from .ids import (
        Achievement,
        AllianceCrestColor,
        AllianceCrestLayout,
        Building,
        ConstructionItem,
        CurrencyId,
        DailyQuestId,
        DifficultyType,
        Effect,
        EffectType,
        EquipmentGroup,
        Event,
        Gem,
        General,
        GeneralAbility,
        GeneralSkill,
        GlobalEffect,
        Horse,
        LegendSkill,
        LootBox,
        LootBoxType,
        QuestId,
        RaidBoss,
        Research,
        SceatSkill,
        Title,
        Tool,
        Unit,
    )

logger = logging.getLogger(__name__)

CACHE_FILENAME_TEMPLATE = "items_v{version}.trimmed.json"


_CACHED_MODELS = (
    UnitStats,
    Collectable,
    ToolStats,
    EffectDef,
    EffectTypeDef,
    EffectCapDef,
    EquipmentEffectDef,
    EquipmentSetDef,
    GemDef,
    RelicEffectDef,
    FortificationDef,
    ConstructionItemDef,
    AllianceBuffDef,
    GlobalEffectDef,
    SceatSkillDef,
    GeneralSkillDef,
    NpcCampDefence,
    DungeonDefence,
    ToolCategoryDef,
    EventCampDef,
    LeagueBracketDef,
    LegendSkillDef,
    AttackSlotDef,
    HorseStats,
    DefaultLordDef,
    GeneralDef,
    GeneralAbilityDef,
    CurrencyDef,
    RaidBossDef,
    VipLevelDef,
    BuildingDef,
    ResearchDef,
    EventDef,
    LootBoxDef,
    LootBoxTypeDef,
    EquipmentGroupDef,
    DifficultyTypeDef,
    QuestDef,
    DailyQuestDef,
    QuestCondition,
    TitleDef,
    ConstructionItemRecipeDef,
    ScalingCampDef,
    AchievementCondition,
    AchievementDef,
    AllianceCrestColorDef,
    AllianceCrestLayoutDef,
    RewardDef,
    EffectValue,
    EquipmentEffectValue,
    CastleEffectValue,
)
"""Every row model the cache stores; the fingerprint covers each one's fields."""


def _schema_fingerprint() -> str:
    """
    A short hash of every field the cache stores.

    The cache holds parsed models keyed by field name, so a model that gains a
    column reads back the old file with that column at its default - silently,
    and wrongly, and a changed default leaves the old default in the file.
    Fingerprinting the field names, aliases and defaults, GameData's own
    tables and how their rows are stored (each table as JSON text, decoded
    the first time it is read, under a digest), means any such change invalidates
    the cache instead. The aliases count because the lazily read tables keep only
    the columns they name, and the reward columns for the same reason: a ``rewards``
    row keeps only the columns :func:`is_reward_column` names.
    """
    tables = [
        f"GameData:{','.join(sorted(GameData.model_fields))}",
        f"tables:{sorted(_TABLES.items())}",
        f"reward_columns:{sorted(_KINDS_BY_XML_KEY)},{_XML_ADD_PREFIX}*",
        "table_rows:json-text,sha256",
    ]
    for model in _CACHED_MODELS:
        fields = ",".join(
            f"{name}={field.alias}={field.default!r}" for name, field in sorted(model.model_fields.items())
        )
        tables.append(f"{model.__name__}:{fields}")
    return hashlib.sha256(";".join(tables).encode()).hexdigest()[:12]


def _tables_digest(texts: Mapping[str, str]) -> str:
    """A hash of the cached tables' JSON text, so a table changed after it was written is caught on load."""
    digest = hashlib.sha256()
    for name in sorted(texts):
        digest.update(f"{name}\0{texts[name]}\0".encode())
    return digest.hexdigest()


def _is_tool(entry: dict[str, Any]) -> bool:
    """A ``units`` row with ``slotTypes`` is a tool, the others are units."""
    return bool(entry.get("slotTypes"))


def _is_unit(entry: dict[str, Any]) -> bool:
    return not _is_tool(entry)


class _TableRows:
    """
    Each lazily read table's rows by id. A table from the cache stays the JSON text it was
    written as until it is first read, so reading the cache costs no row building at all.
    """

    __slots__ = ("_lock", "_rows", "_text")

    def __init__(self, tables: Mapping[str, Mapping[int, dict[str, Any]] | str]) -> None:
        self._rows = {name: rows for name, rows in tables.items() if not isinstance(rows, str)}
        self._text = {name: text for name, text in tables.items() if isinstance(text, str)}
        self._lock = threading.Lock()

    def __getitem__(self, name: str) -> Mapping[int, dict[str, Any]]:
        with self._lock:
            text = self._text.pop(name, None)
            if text is not None:
                self._rows[name] = {int(key): row for key, row in json.loads(text).items()}
            return self._rows.get(name, {})

    def as_text(self) -> dict[str, str]:
        """Each table as JSON text, the way the cache stores it."""
        with self._lock:
            return {
                **{name: json.dumps(rows, separators=(",", ":")) for name, rows in self._rows.items()},
                **self._text,
            }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _TableRows):
            return NotImplemented
        names = {*self._rows, *self._text, *other._rows, *other._text}
        return all(self[name] == other[name] for name in names)

    __hash__ = None  # type: ignore[assignment]


class _TableSource(NamedTuple):
    """Where a lazily read table's rows come from."""

    items_table: str
    model: type[BaseModel]
    id_field: str
    where: Callable[[dict[str, Any]], bool] | None = None
    """Keeps only the items rows it is true for, when the table is part of an items table."""
    reads: Callable[[str], bool] | None = None
    """The columns the model reads beyond its fields, for a row whose columns are not fixed."""

    def __repr__(self) -> str:
        where = f" where {self.where.__name__}" if self.where else ""
        reads = f" reading {self.reads.__name__}" if self.reads else ""
        return f"{self.items_table}:{self.model.__name__}.{self.id_field}{where}{reads}"

    def rows(self, name: str, entries: object) -> dict[int, dict[str, Any]]:
        """
        The table's rows by id, each trimmed to the columns the model reads (and those ``reads`` names).

        A row whose id is missing or not a number is left out; of two rows with one id, the last is kept,
        as the client's tables keep it. Either is warned once per table.
        """
        fields = self.model.model_fields
        columns = {field.alias or name for name, field in fields.items()}
        id_column = fields[self.id_field].alias or self.id_field
        rows: dict[int, dict[str, Any]] = {}
        without_id: list[object] = []
        replaced: list[int] = []
        for entry in entries if isinstance(entries, list) else ():
            if not isinstance(entry, dict):
                # a non-row reads as an empty row: counted once, by the table an empty row belongs to
                if self.where is None or self.where({}):
                    without_id.append(entry)
                continue
            if self.where is not None and not self.where(entry):
                continue
            try:
                key = row_id(entry.get(id_column))
            except ValueError:
                without_id.append(entry.get(id_column))
                continue
            if key in rows:
                replaced.append(key)
            rows[key] = {
                column: value
                for column, value in entry.items()
                if column in columns or (self.reads is not None and self.reads(column))
            }
        if without_id:
            logger.warning(
                "%s: left out %d rows without a numeric %s (%s)",
                name,
                len(without_id),
                id_column,
                ", ".join(repr(value) for value in without_id[:5]),
            )
        if replaced:
            logger.warning(
                "%s: %d ids have more than one row, the last is kept: %s",
                name,
                len(replaced),
                ", ".join(map(str, sorted(set(replaced))[:10])),
            )
        return rows


_TABLES: dict[str, _TableSource] = {
    "units": _TableSource("units", UnitStats, "wod_id", _is_unit),
    "tools": _TableSource("units", ToolStats, "wod_id", _is_tool),
    "effects": _TableSource("effects", EffectDef, "effect_id"),
    "effect_types": _TableSource("effecttypes", EffectTypeDef, "effect_type_id"),
    "construction_items": _TableSource(
        "constructionItems", ConstructionItemDef, "construction_item_id", reads=is_castle_effect_column
    ),
    "global_effects": _TableSource("globalEffects", GlobalEffectDef, "global_effect_id"),
    "general_skills": _TableSource("generalSkills", GeneralSkillDef, "skill_id"),
    "legend_skills": _TableSource("legendskills", LegendSkillDef, "skill_id"),
    "generals": _TableSource("generals", GeneralDef, "general_id"),
    "general_abilities": _TableSource("generalAbilities", GeneralAbilityDef, "ability_id"),
    "currencies": _TableSource("currencies", CurrencyDef, "currency_id"),
    "raid_bosses": _TableSource("raidBosses", RaidBossDef, "raid_boss_id"),
    "buildings": _TableSource("buildings", BuildingDef, "building_id"),
    "researches": _TableSource("researches", ResearchDef, "research_id"),
    "events": _TableSource("events", EventDef, "event_id"),
    "loot_boxes": _TableSource("lootBoxes", LootBoxDef, "loot_box_id"),
    "loot_box_types": _TableSource("lootBoxTypes", LootBoxTypeDef, "loot_box_type_id"),
    "equipment_groups": _TableSource("equipment_groups", EquipmentGroupDef, "group_id"),
    "difficulty_types": _TableSource("eventAutoScalingDifficultyTypes", DifficultyTypeDef, "difficulty_type_id"),
    "quests": _TableSource("quests", QuestDef, "quest_id"),
    "daily_quests": _TableSource("dailyactivities", DailyQuestDef, "quest_id"),
    "titles": _TableSource("titles", TitleDef, "title_id"),
    "gems": _TableSource("gems", GemDef, "gem_id"),
    "sceat_skills": _TableSource("sceatSkills", SceatSkillDef, "skill_id"),
    "horses": _TableSource("horses", HorseStats, "wod_id"),
    "achievements": _TableSource("achievements", AchievementDef, "achievement_id"),
    "alliance_crest_colors": _TableSource("allianceCoatColors", AllianceCrestColorDef, "color_id"),
    "alliance_crest_layouts": _TableSource("allianceCoatLayouts", AllianceCrestLayoutDef, "layout_id"),
    "construction_item_recipes": _TableSource("constructionItemRecipes", ConstructionItemRecipeDef, "recipe_id"),
    "scaling_camps": _TableSource("eventAutoScalingCamps", ScalingCampDef, "scaling_camp_id"),
    "rewards": _TableSource("rewards", RewardDef, "reward_id", reads=is_reward_column),
}
"""The GameData tables read lazily, by attribute name: each a :class:`Table` built from these rows."""


# Camp tables that share the NpcCampDefence shape.
CAMP_TABLES = (
    "nomadCamps",
    "samuraiCamps",
    "factioninvasioncamps",
    "allianceInvasionCamps",
)

# Rank tables that share the EventCampDef shape.
EVENT_CAMP_TABLES = (
    "daimyoCastles",
    "daimyoTownships",
)

RAW_TABLES = (
    "bossdungeons",
    "specialcamps",
    "eventAutoScalingUnitPairings",
    "eventAutoScalingToolPairings",
    "mainquests",
)
"""
Tables kept verbatim. The client parses no ``bossdungeons``, pairing or ``mainquests`` rows, so their
meaning is the server's; it reads ``specialcamps`` into two value objects by row type
(``FactionEventVO.parseAdditionalXmlFromRoot``, bundle line 7400), which are not modeled yet.
"""

R = TypeVar("R", bound=BaseModel)


_warned_versions: set[str] = set()

_load_lock = threading.Lock()
_loaded: GameData | None = None
_failed_at: float | None = None
"""``time.monotonic()`` of the last failed CDN fetch, None after a success."""


def _check_ids_version(version: str) -> None:
    """Log once per version when the loaded items differ from the ones the id enums came from."""
    from .ids import ITEMS_VERSION

    if version == ITEMS_VERSION or version in _warned_versions:
        return
    _warned_versions.add(version)
    logger.warning(
        f"Loaded items v{version}, but empire_core.gamedata.ids was generated from v{ITEMS_VERSION}; "
        "ids added since may be missing: use the GameData lookups for those, or update empire_core."
    )


def default_cache_dir() -> Path:
    """Where trimmed game data is cached (honours XDG_CACHE_HOME)."""
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "empire_core"


def _rows(entries: object, model: type[R]) -> list[R]:
    """Validate a table, skipping rows that do not fit rather than failing."""
    parsed: list[R] = []
    skipped = 0
    if not isinstance(entries, list):
        return parsed
    for entry in entries:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        try:
            parsed.append(model.model_validate(entry))
        except ValueError:
            skipped += 1
    if skipped:
        logger.debug(f"Skipped {skipped} unparseable {model.__name__} rows")
    return parsed


def _single(what: str, matches: list[R], id_of: Callable[[R], int]) -> R | None:
    """The one match, None for none, and an error naming every id for several."""
    if len(matches) > 1:
        raise AmbiguousLookupError(what, sorted(id_of(r) for r in matches))
    return matches[0] if matches else None


class GameData(BaseModel):
    """
    The combat-relevant tables for one items version.

    Load it explicitly:

        data = GameData.load()
        data.units[Unit.MEAD_RANGER_L6].range_attack
        data.buildings[Building.KEEP_L1].might_value
        data.general("Toril").general_id

    The tables the id enums name are keyed by their enum: a row whose id the enum
    lacks (items newer than the enums) is keyed by its plain int, and as the
    enums are IntEnums, a plain id from a packet indexes every table.

    The tables keyed by id enums, ``titles``, ``construction_item_recipes``, ``scaling_camps`` and ``rewards`` are
    read-only :class:`~empire_core.gamedata.table.Table` mappings that validate a row the
    first time it is read, so loading costs no validation for them.
    """

    model_config = ConfigDict(extra="ignore")

    version: str
    schema_fingerprint: str = ""
    """Hash of the table fields, so a cache from older tables is not reused."""

    effect_caps: dict[int, EffectCapDef] = Field(default_factory=dict)
    equipment_effects: dict[int, EquipmentEffectDef] = Field(default_factory=dict)
    relic_effects: dict[int, RelicEffectDef] = Field(default_factory=dict)
    equipment_sets: dict[int, list[EquipmentSetDef]] = Field(default_factory=dict)
    """Each equipment set's threshold rows by set id, in the order listed."""
    fortifications: dict[GameDataId["Building"], FortificationDef] = Field(default_factory=dict)
    alliance_buffs: dict[int, AllianceBuffDef] = Field(default_factory=dict)
    attack_slots: dict[int, AttackSlotDef] = Field(default_factory=dict)
    tool_categories: dict[int, ToolCategoryDef] = Field(default_factory=dict)
    default_lords: dict[int, DefaultLordDef] = Field(default_factory=dict)
    vip_levels: dict[int, VipLevelDef] = Field(default_factory=dict)
    dungeons: list[DungeonDefence] = Field(default_factory=list)
    camps: dict[str, list[NpcCampDefence]] = Field(default_factory=dict)
    event_camps: dict[str, dict[int, EventCampDef]] = Field(default_factory=dict)
    league_brackets: list[LeagueBracketDef] = Field(default_factory=list)
    raw_tables: dict[str, list] = Field(default_factory=dict)
    _table_rows: _TableRows = PrivateAttr(default_factory=lambda: _TableRows({}))

    def _table(self, name: str, context: dict[str, Any] | None = None) -> Table[Any, Any]:
        source = _TABLES[name]
        return Table(source.model, source.id_field, self._table_rows[name], name=name, context=context)

    @cached_property
    def units(self) -> Table[GameDataId["Unit"], UnitStats]:
        """Combat units by ``Unit``: the ``units`` rows without ``slotTypes``."""
        return self._table("units")

    @cached_property
    def tools(self) -> Table[GameDataId["Tool"], ToolStats]:
        """Siege and defence tools by ``Tool``: the ``units`` rows with ``slotTypes``."""
        return self._table("tools")

    @cached_property
    def effects(self) -> Table[GameDataId["Effect"], EffectDef]:
        """Effects by ``Effect``."""
        return self._table("effects")

    @cached_property
    def effect_types(self) -> Table[GameDataId["EffectType"], EffectTypeDef]:
        """Effect types by ``EffectType``."""
        return self._table("effect_types")

    @cached_property
    def construction_items(self) -> Table[GameDataId["ConstructionItem"], ConstructionItemDef]:
        """Construction items by ``ConstructionItem``."""
        return self._table("construction_items")

    @cached_property
    def global_effects(self) -> Table[GameDataId["GlobalEffect"], GlobalEffectDef]:
        """Global effects by ``GlobalEffect``."""
        return self._table("global_effects")

    @cached_property
    def general_skills(self) -> Table[GameDataId["GeneralSkill"], GeneralSkillDef]:
        """General skill levels by ``GeneralSkill``."""
        return self._table("general_skills")

    @cached_property
    def legend_skills(self) -> Table[GameDataId["LegendSkill"], LegendSkillDef]:
        """Legend skill levels by ``LegendSkill``."""
        return self._table("legend_skills")

    @cached_property
    def generals(self) -> Table[GameDataId["General"], GeneralDef]:
        """Generals by ``General``."""
        return self._table("generals")

    @cached_property
    def general_abilities(self) -> Table[GameDataId["GeneralAbility"], GeneralAbilityDef]:
        """General ability levels by ``GeneralAbility``."""
        return self._table("general_abilities")

    @cached_property
    def currencies(self) -> Table[GameDataId["CurrencyId"], CurrencyDef]:
        """Currencies by ``CurrencyId``; coins and rubies are not in it."""
        return self._table("currencies")

    @cached_property
    def raid_bosses(self) -> Table[GameDataId["RaidBoss"], RaidBossDef]:
        """Alliance raid bosses by ``RaidBoss``."""
        return self._table("raid_bosses")

    @cached_property
    def buildings(self) -> Table[GameDataId["Building"], BuildingDef]:
        """Buildings, towers, gates, moats and decorations by ``Building``."""
        return self._table("buildings")

    @cached_property
    def researches(self) -> Table[GameDataId["Research"], ResearchDef]:
        """Research levels by ``Research``."""
        return self._table("researches")

    @cached_property
    def events(self) -> Table[GameDataId["Event"], EventDef]:
        """Events by ``Event``."""
        return self._table("events")

    @cached_property
    def loot_boxes(self) -> Table[GameDataId["LootBox"], LootBoxDef]:
        """Loot boxes by ``LootBox``."""
        return self._table("loot_boxes")

    @cached_property
    def loot_box_types(self) -> Table[GameDataId["LootBoxType"], LootBoxTypeDef]:
        """Loot box types by ``LootBoxType``."""
        return self._table("loot_box_types")

    @cached_property
    def equipment_groups(self) -> Table[GameDataId["EquipmentGroup"], EquipmentGroupDef]:
        """Equipment item groups by ``EquipmentGroup``."""
        return self._table("equipment_groups")

    @cached_property
    def difficulty_types(self) -> Table[GameDataId["DifficultyType"], DifficultyTypeDef]:
        """Event difficulty types by ``DifficultyType``."""
        return self._table("difficulty_types")

    @cached_property
    def quests(self) -> Table[GameDataId["QuestId"], QuestDef]:
        """Quests by ``QuestId``."""
        return self._table("quests")

    @cached_property
    def daily_quests(self) -> Table[GameDataId["DailyQuestId"], DailyQuestDef]:
        """Daily quests by ``DailyQuestId``."""
        return self._table("daily_quests")

    @cached_property
    def titles(self) -> Table[GameDataId["Title"], TitleDef]:
        """Titles by ``Title``."""
        return self._table("titles")

    @cached_property
    def gems(self) -> Table[GameDataId["Gem"], GemDef]:
        """Gems by ``Gem``."""
        return self._table("gems")

    @cached_property
    def sceat_skills(self) -> Table[GameDataId["SceatSkill"], SceatSkillDef]:
        """Sceat skill levels by ``SceatSkill``."""
        return self._table("sceat_skills")

    @cached_property
    def horses(self) -> Table[GameDataId["Horse"], HorseStats]:
        """Travel boosters by ``Horse``, the value movements send as ``HBW``."""
        return self._table("horses")

    @cached_property
    def achievements(self) -> Table[GameDataId["Achievement"], AchievementDef]:
        """Achievement series steps by ``Achievement``."""
        return self._table("achievements")

    @cached_property
    def alliance_crest_colors(self) -> Table[GameDataId["AllianceCrestColor"], AllianceCrestColorDef]:
        """Alliance crest colours by ``AllianceCrestColor``."""
        return self._table("alliance_crest_colors")

    @cached_property
    def alliance_crest_layouts(self) -> Table[GameDataId["AllianceCrestLayout"], AllianceCrestLayoutDef]:
        """Alliance crest layouts by ``AllianceCrestLayout``."""
        return self._table("alliance_crest_layouts")

    @cached_property
    def construction_item_recipes(self) -> Table[int, ConstructionItemRecipeDef]:
        """The ``constructionItemRecipes`` rows, by the recipe id a blueprint research unlocks."""
        return self._table("construction_item_recipes")

    @cached_property
    def scaling_camps(self) -> Table[int, ScalingCampDef]:
        """The ``eventAutoScalingCamps`` rows, by the scaling camp id a map row names."""
        return self._table("scaling_camps")

    @cached_property
    def rewards(self) -> Table[RewardId, RewardDef]:
        """
        The rewards by id, each with the collectables it gives.

        Client: ``CastleRewardData.parseXml`` (bundle line 142323)
        """
        currency_ids = {row.name: row.currency_id for row in self.currencies.values()}
        return self._table("rewards", context={"currency_ids": currency_ids})

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def reward_list(self, reward_ids: Iterable[int], *, combine: bool = False) -> tuple[Collectable, ...]:
        """
        What the rewards give, one after the other: a campaign's ``reward_ids``, a title's ``reward_id``.

        An id with no reward (-1, or one the items lack) gives nothing.

        Args:
            reward_ids: The rewards, in order
            combine: Add up the duplicates the client adds up, as some of its dialogs ask for

        Client: ``CastleRewardData.getListByIdArray`` (bundle line 142344)
        """
        found = [
            collectable
            for reward_id in reward_ids
            if (reward := self.rewards.get(RewardId(reward_id))) is not None
            for collectable in reward.collectables
        ]
        return Collectable.merged(found) if combine else tuple(found)

    def get_unit(self, wod_id: int) -> UnitStats | None:
        return self.units.get(wod_id)

    def get_tool(self, wod_id: int) -> ToolStats | None:
        return self.tools.get(wod_id)

    def is_unit(self, wod_id: int) -> bool:
        """Whether the ID is a combat unit rather than a tool or boost item."""
        return wod_id in self.units

    def is_tool(self, wod_id: int) -> bool:
        return wod_id in self.tools

    def units_by_role(self, role: UnitRole) -> list[UnitStats]:
        """Every unit of one role (``SoldierUnitVO.role``, bundle line 12590)."""
        return [unit for unit in self.units.values() if unit.role == role]

    def get_horse(self, wod_id: int) -> HorseStats | None:
        """A travel booster by its ``HBW`` value."""
        return self.horses.get(wod_id)

    def get_default_lord(self, lord_id: int) -> DefaultLordDef | None:
        """A default lord, i.e. one of the negative ``LID`` sentinels."""
        return self.default_lords.get(lord_id)

    def vip_level(self, points: int) -> VipLevelDef | None:
        """
        The VIP level ``points`` VIP points reach: the one whose range holds them, else the
        top one when points are above 0, else None.

        Client: ``CastleVIPData.getVIPLevelInfoVOByPoints`` (bundle line 47531)
        """
        levels = sorted(self.vip_levels.values(), key=lambda level: level.vip_level_id)
        found = next((level for level in levels if level.in_point_range(points)), None)
        if found is None and points > 0 and levels:
            return levels[-1]
        return found

    def get_event_camp(self, table: str, camp_id: int) -> EventCampDef | None:
        """One rank of a daimyo castle (``daimyoCastles``) or township (``daimyoTownships``)."""
        return self.event_camps.get(table, {}).get(camp_id)

    def scaling_camp_level(self, scaling_camp_id: int) -> int | None:
        """
        The level an event's difficulty scaling gives a camp.

        A map row that names a scaling camp overrides every other level source,
        which is how a chosen difficulty raises a camp for one player only.
        """
        camp = self.scaling_camps.get(scaling_camp_id) if scaling_camp_id > 0 else None
        return camp.level if camp is not None else None

    def event_base_camp_level(self, event_id: int, player_level: int, *, sub_type: int = 0) -> int | None:
        """
        Where an invasion event's camps start for a player of this level.

        Each event sorts players into level bands and gives every band its own
        victory range; a camp's base level is the bottom of that range, which is
        why the same camp is harder for a higher-level player.
        """
        for bracket in self.league_brackets:
            if (
                bracket.event_id == event_id
                and bracket.sub_type == sub_type
                and bracket.min_level <= player_level <= bracket.max_level
            ):
                return bracket.victory_min
        return None

    def league_type(self, league_type_id: int, event_id: int = -1, *, sub_type: int = 0) -> LeagueBracketDef | None:
        """
        A league by the ``LID`` a highscore reply names, within its event.

        The same id is a different level band in every event, and within an
        event in every sub type, so both are part of the key; ``event_id=-1``
        finds the rows of no event.

        Client: ``AScoreEventVO.generateLeagueLevelsList`` (bundle line 14971)
        """
        return _single(
            f"league type {league_type_id} of event {event_id} sub type {sub_type}",
            [
                r
                for r in self.league_brackets
                if r.league_type_id == league_type_id and r.event_id == event_id and r.sub_type == sub_type
            ],
            lambda r: league_type_id,
        )

    def resolve_relic_effect(self, relic_effect_id: int) -> EffectDef | None:
        """
        The plain effect a relic bonus id points at.

        Relic bonuses index the relic effect table, which then names a normal
        effect; the two id spaces overlap and disagree.
        """
        relic = self.relic_effects.get(relic_effect_id)
        if relic is None:
            return None
        return self.effects.get(relic.effect_id)

    def effect_type_name(self, effect_id: int) -> str:
        """Resolve an effect ID to its effect type's name."""
        effect = self.effects.get(effect_id)
        if effect is None:
            return ""
        effect_type = self.effect_types.get(effect.effect_type_id)
        return effect_type.name if effect_type else ""

    def dungeon_defense(self, victories: int, kingdom_id: Kingdom = Kingdom.GREEN) -> DungeonDefence | None:
        """The camp defense for a victory count in a kingdom."""
        for row in self.dungeons:
            if row.count_victories == victories and row.kingdom_id == kingdom_id:
                return row
        return None

    def raw(self, table: str) -> list:
        """An unmodeled table, exactly as the payload had it."""
        return self.raw_tables.get(table, [])

    # ------------------------------------------------------------------
    # Named lookups
    # ------------------------------------------------------------------
    # Game-data ids change between client releases, so these find a row by
    # the key that identifies it instead. Names match exactly. A miss returns
    # None; a key that matches more than one row raises AmbiguousLookupError
    # with every matching id. Horses have none: the game tells them apart by
    # their place in the travel dialog, so use get_horse or the Horse enum.

    def general(self, name: str) -> GeneralDef | None:
        """A general by its ``generalName``, e.g. ``"Toril"``."""
        return _single(
            f"general {name!r}", [r for r in self.generals.values() if r.name == name], lambda r: r.general_id
        )

    def general_ability(self, name: str, level: int) -> GeneralAbilityDef | None:
        """A general's ability at one level, e.g. ``("PowerSurge", 1)``."""
        return _single(
            f"general ability {name!r} level {level}",
            [r for r in self.general_abilities.values() if r.name == name and r.level == level],
            lambda r: r.ability_id,
        )

    def general_skill(self, general_id: int, name: str, level: int) -> GeneralSkillDef | None:
        """
        One level of a general's skill; the general's id comes from :meth:`general`.

        Skill names repeat across generals, so the general is part of the key.
        """
        return _single(
            f"general {general_id} skill {name!r} level {level}",
            [
                r
                for r in self.general_skills.values()
                if r.general_id == general_id and r.name == name and r.level == level
            ],
            lambda r: r.skill_id,
        )

    def legend_skill(self, tree_id: int, group_id: int, level: int) -> LegendSkillDef | None:
        """
        A legend skill by its tree, group and level.

        Its ``effectType`` is no key: the same effect sits in more than one tree.
        """
        return _single(
            f"legend skill tree {tree_id} group {group_id} level {level}",
            [
                r
                for r in self.legend_skills.values()
                if r.skill_tree_id == tree_id and r.skill_group_id == group_id and r.level == level
            ],
            lambda r: r.skill_id,
        )

    def currency(self, json_key: str) -> CurrencyDef | None:
        """
        A currency by its ``JSONKey``, e.g. ``"KT"`` for khan tablets.

        C1 and C2 (coins and rubies) are not in this table.

        Client: ``CurrencyData.getXmlCurrencyByKey`` (bundle line 141194)
        """
        return _single(
            f"currency {json_key!r}",
            [r for r in self.currencies.values() if r.json_key == json_key],
            lambda r: r.currency_id,
        )

    def effect_type(self, name: str) -> EffectTypeDef | None:
        """An effect type by name, e.g. ``"fameDefenseBonus"``."""
        return _single(
            f"effect type {name!r}",
            [r for r in self.effect_types.values() if r.name == name],
            lambda r: r.effect_type_id,
        )

    def raid_boss(self, name: str) -> RaidBossDef | None:
        """An alliance raid boss by name, e.g. ``"Necromancer"``."""
        return _single(
            f"raid boss {name!r}", [r for r in self.raid_bosses.values() if r.name == name], lambda r: r.raid_boss_id
        )

    def global_effect(self, name: str) -> GlobalEffectDef | None:
        """
        A global effect by name.

        Names are not quite unique: ``"SpeedBoost"`` is two effects of
        different strength, and asking for it raises with both ids.
        """
        return _single(
            f"global effect {name!r}",
            [r for r in self.global_effects.values() if r.name == name],
            lambda r: r.global_effect_id,
        )

    def unit(self, unit_type: str, level: int | None = None) -> UnitStats | None:
        """
        A unit by its ``type`` and, optionally, level.

        Units have no unique name. A type repeats across levels, and event
        variants of one unit share its type, often with no level to tell them
        apart (``Ogermace`` is both 68 and 7), so a lookup that still matches
        several units raises rather than picking one. A row without a level
        has level -1, as the client reads it, so ``level=-1`` finds those and
        ``level=0`` only a row whose level is 0.
        """
        return _single(
            f"unit {unit_type!r}" + (f" level {level}" if level is not None else ""),
            [r for r in self.units.values() if r.unit_type == unit_type and (level is None or r.level == level)],
            lambda r: r.wod_id,
        )

    def tool(self, tool_type: str, level: int | None = None) -> ToolStats | None:
        """
        A tool by its ``type`` and, optionally, level; see :meth:`unit` for why it can be ambiguous.

        Event copies of a tool share its type (``EliteComboRam`` is both 113 and 564).
        """
        return _single(
            f"tool {tool_type!r}" + (f" level {level}" if level is not None else ""),
            [r for r in self.tools.values() if r.tool_type == tool_type and (level is None or r.level == level)],
            lambda r: r.wod_id,
        )

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def parse(cls, version: str, items_data: dict) -> "GameData":
        """Trim a full items payload down to the combat-relevant tables."""
        equipment_sets: dict[int, list[EquipmentSetDef]] = {}
        for row in _rows(items_data.get("equipment_sets"), EquipmentSetDef):
            equipment_sets.setdefault(row.set_id, []).append(row)

        data = cls(
            version=version,
            schema_fingerprint=_schema_fingerprint(),
            effect_caps={r.cap_id: r for r in _rows(items_data.get("effectCaps"), EffectCapDef)},
            equipment_effects={
                r.equipment_effect_id: r for r in _rows(items_data.get("equipment_effects"), EquipmentEffectDef)
            },
            relic_effects={r.relic_effect_id: r for r in _rows(items_data.get("relicEffects"), RelicEffectDef)},
            equipment_sets=equipment_sets,
            fortifications={
                row.wod_id: row
                for row in _rows(
                    [
                        entry
                        for entry in (items_data.get("buildings") or [])
                        if isinstance(entry, dict)
                        and any(entry.get(key) for key in ("wallBonus", "gateBonus", "moatBonus"))
                    ],
                    FortificationDef,
                )
            },
            alliance_buffs={r.alliance_buff_id: r for r in _rows(items_data.get("alliancebuffs"), AllianceBuffDef)},
            attack_slots={r.slot_id: r for r in _rows(items_data.get("attackSetupSlots"), AttackSlotDef)},
            tool_categories={r.tool_category_id: r for r in _rows(items_data.get("toolCategories"), ToolCategoryDef)},
            default_lords={r.lord_id: r for r in _rows(items_data.get("lords"), DefaultLordDef)},
            vip_levels={r.vip_level_id: r for r in _rows(items_data.get("viplevels"), VipLevelDef)},
            dungeons=_rows(items_data.get("dungeons"), DungeonDefence),
            camps={
                table: _rows(items_data.get(table), NpcCampDefence) for table in CAMP_TABLES if items_data.get(table)
            },
            event_camps={
                table: {r.camp_id: r for r in _rows(items_data.get(table), EventCampDef)}
                for table in EVENT_CAMP_TABLES
                if items_data.get(table)
            },
            league_brackets=_rows(items_data.get("leaguetypes"), LeagueBracketDef),
            raw_tables={table: items_data[table] for table in RAW_TABLES if isinstance(items_data.get(table), list)},
        )
        data._table_rows = _TableRows(
            {name: source.rows(name, items_data.get(source.items_table)) for name, source in _TABLES.items()}
        )
        return data

    @classmethod
    def load(cls, *, refresh: bool = False, cache_dir: str | Path | None = None) -> "GameData":
        """
        The game data for the current items version, downloaded at most once per version.

        The version file is checked on every call, so a game patch invalidates
        the cache on its own. The data is kept for the process and every caller
        gets the same instance while the version holds: it is shared, so treat
        it as read-only and never change its tables or rows. Without a kept copy
        for the version, the disk cache is tried, and only a miss downloads the
        full payload. Concurrent loads, in threads or processes sharing
        ``cache_dir``, make one download between them.

        When the CDN cannot be reached, the data already kept is returned (with
        a warning), even if a newer version could not be fetched. Only a load
        with nothing kept, or with ``refresh=True``, raises. After a failed fetch
        the CDN is not asked again for five minutes.

        Args:
            refresh: Ignore the kept and cached copies and any failure backoff, and re-download
            cache_dir: Where to keep trimmed data (default: XDG cache dir). It is read and
                written only when the kept copy is not current, so a call that finds it
                current returns it whatever ``cache_dir`` it was loaded with.

        Raises:
            NetworkError: Nothing is kept (or ``refresh`` is set) and the CDN could not be
                reached, now or less than five minutes ago
        """
        try:
            return cls._load(refresh, Path(cache_dir) if cache_dir is not None else default_cache_dir())
        except NetworkError as e:
            kept = None if refresh else _loaded
            if kept is None:
                raise
            logger.warning(f"Keeping the loaded game data v{kept.version}: {e}")
            return kept

    @classmethod
    def _load(cls, refresh: bool, directory: Path) -> "GameData":
        global _loaded, _failed_at
        if not refresh and _failed_at is not None and time.monotonic() - _failed_at < cdn.RETRY_AFTER_FAILURE:
            raise NetworkError(
                "The items CDN is unavailable: the last fetch failed less than "
                f"{cdn.RETRY_AFTER_FAILURE:.0f}s ago and is not retried yet"
            )
        try:
            version = cdn.get_items_version()
        except Exception as e:
            with _load_lock:
                _failed_at = time.monotonic()
            raise NetworkError(f"Failed to fetch the items version: {e}") from e

        with _load_lock:
            data = _loaded
            if refresh or data is None or data.version != version:
                cache_file = directory / CACHE_FILENAME_TEMPLATE.format(version=version)
                with cache.locked(cache_file.with_suffix(".lock")):
                    data = None if refresh else cls._read_cache(cache_file, version)
                    if data is None:
                        try:
                            items_data = cdn.fetch_items_data(version)
                        except Exception as e:
                            _failed_at = time.monotonic()
                            raise NetworkError(f"Failed to fetch items data v{version}: {e}") from e
                        data = cls.parse(version, items_data)
                        data._write_cache(cache_file)
                        logger.info(
                            f"Loaded {len(data._table_rows['units'])} units, {len(data._table_rows['tools'])} "
                            f"tools and {len(data.dungeons)} camp defenses (v{version})"
                        )
                _loaded = data
            _failed_at = None
            _check_ids_version(version)
            return data

    @classmethod
    def loaded(cls) -> "GameData | None":
        """
        The data the last :meth:`load` in this process gave, or None; never touches the network.

        It is the instance :meth:`load` hands every caller, so treat it as read-only.
        """
        return _loaded

    @classmethod
    def _read_cache(cls, cache_file: Path, version: str) -> "GameData | None":
        if not cache_file.is_file():
            return None
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            table_rows = payload.pop("table_rows", {})
            table_digest = payload.pop("table_digest", None)
            token = READING_CACHE.set(True)
            try:
                data = cls.model_validate(payload)
            finally:
                READING_CACHE.reset(token)
        except (OSError, ValueError, AttributeError) as e:
            logger.warning(f"Ignoring unreadable game data cache {cache_file}: {e}")
            return None
        if data.version != version:
            return None
        if data.schema_fingerprint != _schema_fingerprint():
            logger.info(f"Game data cache {cache_file} predates the current tables; re-parsing")
            return None
        if not isinstance(table_rows, dict) or not all(isinstance(text, str) for text in table_rows.values()):
            logger.warning(f"Ignoring unreadable game data cache {cache_file}: its tables are not JSON text")
            return None
        if table_digest != _tables_digest(table_rows):
            logger.warning(f"Ignoring unreadable game data cache {cache_file}: its tables changed after it was written")
            return None
        data._table_rows = _TableRows(table_rows)
        logger.debug(f"Loaded game data v{version} from {cache_file}")
        return data

    def _write_cache(self, cache_file: Path) -> None:
        try:
            tables = self._table_rows.as_text()
            payload = {**self.model_dump(mode="json"), "table_rows": tables, "table_digest": _tables_digest(tables)}
            cache.write_atomic(cache_file, json.dumps(payload, separators=(",", ":")))
        except OSError as e:
            # A read-only cache dir must not fail the load.
            logger.warning(f"Could not cache game data to {cache_file}: {e}")


__all__ = ["GameData", "default_cache_dir"]
