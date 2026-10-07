"""
Static game data from the GGE items payload.

The client builds its combat maths from ``items_v{version}.json`` on the GGE
CDN. That file is ~20 MB, so nothing here is fetched implicitly: call
:meth:`GameData.load` (or :meth:`EmpireClient.load_game_data`) when you want it.
What is parsed is trimmed to the combat-relevant tables and the tables the
id enums name, and cached on disk per version, so the download happens once
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
from collections.abc import Callable, Mapping
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from empire_core.enums import Kingdom, UnitRole
from empire_core.exceptions import AmbiguousLookupError, NetworkError

from . import cache, cdn
from .lenient import GameDataId
from .models import (
    READING_CACHE,
    AllianceBuffDef,
    AttackSlotDef,
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
)
from .table import Table
from .tables import (
    BuildingDef,
    DailyQuestDef,
    DifficultyTypeDef,
    EquipmentGroupDef,
    EventDef,
    LootBoxDef,
    LootBoxTypeDef,
    QuestCondition,
    QuestDef,
    ResearchDef,
    ScalingCampDef,
    TitleDef,
    row_id,
)

if TYPE_CHECKING:
    from .ids import (
        Building,
        DailyQuestId,
        DifficultyType,
        EquipmentGroup,
        Event,
        LootBox,
        LootBoxType,
        QuestId,
        Research,
    )

logger = logging.getLogger(__name__)

CACHE_FILENAME_TEMPLATE = "items_v{version}.trimmed.json"


_CACHED_MODELS = (
    UnitStats,
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
    ScalingCampDef,
    EffectValue,
    EquipmentEffectValue,
)
"""Every row model the cache stores; the fingerprint covers each one's fields."""


def _schema_fingerprint() -> str:
    """
    A short hash of every field the cache stores.

    The cache holds parsed models keyed by field name, so a model that gains a
    column reads back the old file with that column at its default - silently,
    and wrongly, and a changed default leaves the old default in the file.
    Fingerprinting the field names, aliases and defaults, and GameData's own
    tables, means any such change invalidates the cache instead. The aliases
    count because the lazily read tables keep only the columns they name.
    """
    tables = [f"GameData:{','.join(sorted(GameData.model_fields))}", f"tables:{sorted(TABLES.items())}"]
    for model in _CACHED_MODELS:
        fields = ",".join(
            f"{name}={field.alias}={field.default!r}" for name, field in sorted(model.model_fields.items())
        )
        tables.append(f"{model.__name__}:{fields}")
    return hashlib.sha256(";".join(tables).encode()).hexdigest()[:12]


class TableSource(NamedTuple):
    """Where a lazily read table's rows come from."""

    items_table: str
    model: type[BaseModel]
    id_field: str

    def __repr__(self) -> str:
        return f"{self.items_table}:{self.model.__name__}.{self.id_field}"

    def rows(self, entries: object) -> dict[int, dict[str, Any]]:
        """
        The table's rows by id, each trimmed to the columns the model reads.

        A row whose id is missing or not a number is left out; of two rows with one id, the last is kept.
        """
        fields = self.model.model_fields
        columns = {field.alias or name for name, field in fields.items()}
        id_column = fields[self.id_field].alias or self.id_field
        rows: dict[int, dict[str, Any]] = {}
        for entry in entries if isinstance(entries, list) else ():
            if not isinstance(entry, dict):
                continue
            try:
                key = row_id(entry.get(id_column))
            except ValueError:
                continue
            rows[key] = {column: value for column, value in entry.items() if column in columns}
        return rows


TABLES: dict[str, TableSource] = {
    "buildings": TableSource("buildings", BuildingDef, "building_id"),
    "researches": TableSource("researches", ResearchDef, "research_id"),
    "events": TableSource("events", EventDef, "event_id"),
    "loot_boxes": TableSource("lootBoxes", LootBoxDef, "loot_box_id"),
    "loot_box_types": TableSource("lootBoxTypes", LootBoxTypeDef, "loot_box_type_id"),
    "equipment_groups": TableSource("equipment_groups", EquipmentGroupDef, "group_id"),
    "difficulty_types": TableSource("eventAutoScalingDifficultyTypes", DifficultyTypeDef, "difficulty_type_id"),
    "quests": TableSource("quests", QuestDef, "quest_id"),
    "daily_quests": TableSource("dailyactivities", DailyQuestDef, "quest_id"),
    "titles": TableSource("titles", TitleDef, "title_id"),
    "scaling_camps": TableSource("eventAutoScalingCamps", ScalingCampDef, "scaling_camp_id"),
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
)
"""
Tables kept verbatim. The client parses no ``bossdungeons`` or pairing rows, so their meaning is the
server's; it reads ``specialcamps`` into two value objects by row type (``FactionEventVO.parseAdditionalXmlFromRoot``,
bundle line 7400), which are not modeled yet.
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

    The tables in :data:`TABLES` are read-only :class:`Table` mappings that
    validate a row the first time it is read, so loading costs no validation
    for them.
    """

    model_config = ConfigDict(extra="ignore")

    version: str
    schema_fingerprint: str = ""
    """Hash of the table fields, so a cache from older tables is not reused."""

    units: dict[int, UnitStats] = Field(default_factory=dict)
    tools: dict[int, ToolStats] = Field(default_factory=dict)
    effects: dict[int, EffectDef] = Field(default_factory=dict)
    effect_types: dict[int, EffectTypeDef] = Field(default_factory=dict)
    effect_caps: dict[int, EffectCapDef] = Field(default_factory=dict)
    equipment_effects: dict[int, EquipmentEffectDef] = Field(default_factory=dict)
    relic_effects: dict[int, RelicEffectDef] = Field(default_factory=dict)
    gems: dict[int, GemDef] = Field(default_factory=dict)
    equipment_sets: dict[int, list[EquipmentSetDef]] = Field(default_factory=dict)
    """Each equipment set's threshold rows by set id, in the order listed."""
    fortifications: dict[int, FortificationDef] = Field(default_factory=dict)
    construction_items: dict[int, ConstructionItemDef] = Field(default_factory=dict)
    alliance_buffs: dict[int, AllianceBuffDef] = Field(default_factory=dict)
    global_effects: dict[int, GlobalEffectDef] = Field(default_factory=dict)
    sceat_skills: dict[int, SceatSkillDef] = Field(default_factory=dict)
    general_skills: dict[int, GeneralSkillDef] = Field(default_factory=dict)
    legend_skills: dict[int, LegendSkillDef] = Field(default_factory=dict)
    attack_slots: dict[int, AttackSlotDef] = Field(default_factory=dict)
    tool_categories: dict[int, ToolCategoryDef] = Field(default_factory=dict)
    horses: dict[int, HorseStats] = Field(default_factory=dict)
    default_lords: dict[int, DefaultLordDef] = Field(default_factory=dict)
    generals: dict[int, GeneralDef] = Field(default_factory=dict)
    general_abilities: dict[int, GeneralAbilityDef] = Field(default_factory=dict)
    currencies: dict[int, CurrencyDef] = Field(default_factory=dict)
    raid_bosses: dict[int, RaidBossDef] = Field(default_factory=dict)
    vip_levels: dict[int, VipLevelDef] = Field(default_factory=dict)
    dungeons: list[DungeonDefence] = Field(default_factory=list)
    camps: dict[str, list[NpcCampDefence]] = Field(default_factory=dict)
    event_camps: dict[str, dict[int, EventCampDef]] = Field(default_factory=dict)
    league_brackets: list[LeagueBracketDef] = Field(default_factory=list)
    raw_tables: dict[str, list] = Field(default_factory=dict)
    _table_rows: dict[str, Mapping[int, dict[str, Any]]] = PrivateAttr(default_factory=dict)

    def _table(self, name: str) -> Table[Any, Any]:
        source = TABLES[name]
        return Table(source.model, source.id_field, self._table_rows.get(name, {}))

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
    def titles(self) -> Table[int, TitleDef]:
        """Titles by ``titleID``; they have no enum, as their rows have no name."""
        return self._table("titles")

    @cached_property
    def scaling_camps(self) -> Table[int, ScalingCampDef]:
        """The ``eventAutoScalingCamps`` rows, by the scaling camp id a map row names."""
        return self._table("scaling_camps")

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

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
    # with every matching id. Horses have none yet: what separates their
    # variants is not traced, so use get_horse by id.

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
        units: dict[int, UnitStats] = {}
        tools: dict[int, ToolStats] = {}
        skipped = 0
        for entry in items_data.get("units", []):
            if not isinstance(entry, dict) or entry.get("wodID") is None:
                skipped += 1
                continue
            try:
                if entry.get("slotTypes"):
                    tool = ToolStats.model_validate(entry)
                    tools[tool.wod_id] = tool
                else:
                    unit = UnitStats.model_validate(entry)
                    units[unit.wod_id] = unit
            except ValueError:
                # One malformed entry must not cost the whole table.
                skipped += 1
        if skipped:
            logger.warning(f"Skipped {skipped} unparseable items entries (v{version})")
        equipment_sets: dict[int, list[EquipmentSetDef]] = {}
        for row in _rows(items_data.get("equipment_sets"), EquipmentSetDef):
            equipment_sets.setdefault(row.set_id, []).append(row)

        data = cls(
            version=version,
            schema_fingerprint=_schema_fingerprint(),
            units=units,
            tools=tools,
            effects={r.effect_id: r for r in _rows(items_data.get("effects"), EffectDef)},
            effect_types={r.effect_type_id: r for r in _rows(items_data.get("effecttypes"), EffectTypeDef)},
            effect_caps={r.cap_id: r for r in _rows(items_data.get("effectCaps"), EffectCapDef)},
            equipment_effects={
                r.equipment_effect_id: r for r in _rows(items_data.get("equipment_effects"), EquipmentEffectDef)
            },
            relic_effects={r.relic_effect_id: r for r in _rows(items_data.get("relicEffects"), RelicEffectDef)},
            gems={r.gem_id: r for r in _rows(items_data.get("gems"), GemDef)},
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
            construction_items={
                r.construction_item_id: r for r in _rows(items_data.get("constructionItems"), ConstructionItemDef)
            },
            alliance_buffs={r.alliance_buff_id: r for r in _rows(items_data.get("alliancebuffs"), AllianceBuffDef)},
            global_effects={r.global_effect_id: r for r in _rows(items_data.get("globalEffects"), GlobalEffectDef)},
            sceat_skills={r.skill_id: r for r in _rows(items_data.get("sceatSkills"), SceatSkillDef)},
            general_skills={r.skill_id: r for r in _rows(items_data.get("generalSkills"), GeneralSkillDef)},
            legend_skills={r.skill_id: r for r in _rows(items_data.get("legendskills"), LegendSkillDef)},
            attack_slots={r.slot_id: r for r in _rows(items_data.get("attackSetupSlots"), AttackSlotDef)},
            tool_categories={r.tool_category_id: r for r in _rows(items_data.get("toolCategories"), ToolCategoryDef)},
            horses={r.wod_id: r for r in _rows(items_data.get("horses"), HorseStats)},
            default_lords={r.lord_id: r for r in _rows(items_data.get("lords"), DefaultLordDef)},
            generals={r.general_id: r for r in _rows(items_data.get("generals"), GeneralDef)},
            general_abilities={r.ability_id: r for r in _rows(items_data.get("generalAbilities"), GeneralAbilityDef)},
            currencies={r.currency_id: r for r in _rows(items_data.get("currencies"), CurrencyDef)},
            raid_bosses={r.raid_boss_id: r for r in _rows(items_data.get("raidBosses"), RaidBossDef)},
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
        data._table_rows = {name: source.rows(items_data.get(source.items_table)) for name, source in TABLES.items()}
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
                            f"Loaded {len(data.units)} units, {len(data.tools)} tools and "
                            f"{len(data.dungeons)} camp defenses (v{version})"
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
            token = READING_CACHE.set(True)
            try:
                data = cls.model_validate(payload)
            finally:
                READING_CACHE.reset(token)
            data._table_rows = {name: {int(key): row for key, row in rows.items()} for name, rows in table_rows.items()}
        except (OSError, ValueError, AttributeError) as e:
            logger.warning(f"Ignoring unreadable game data cache {cache_file}: {e}")
            return None
        if data.version != version:
            return None
        if data.schema_fingerprint != _schema_fingerprint():
            logger.info(f"Game data cache {cache_file} predates the current tables; re-parsing")
            return None
        logger.debug(f"Loaded game data v{version} from {cache_file}")
        return data

    def _write_cache(self, cache_file: Path) -> None:
        try:
            payload = {**self.model_dump(mode="json"), "table_rows": self._table_rows}
            cache.write_atomic(cache_file, json.dumps(payload, separators=(",", ":")))
        except OSError as e:
            # A read-only cache dir must not fail the load.
            logger.warning(f"Could not cache game data to {cache_file}: {e}")


__all__ = ["GameData", "TABLES", "TableSource", "default_cache_dir"]
