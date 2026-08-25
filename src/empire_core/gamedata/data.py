"""
Static game data from the GGE items payload.

The client builds its combat maths from ``items_v{version}.json`` on the GGE
CDN. That file is ~20 MB, so nothing here is fetched implicitly: call
:meth:`GameData.load` (or :meth:`EmpireClient.load_game_data`) when you want it.
What is parsed is trimmed to the combat-relevant tables and cached on disk per
version, so the download happens once per game patch.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

from empire_core.exceptions import NetworkError
from empire_core.utils.troops import fetch_items_data, get_items_version

from .models import (
    AllianceBuffDef,
    AttackSlotDef,
    ConstructionItemDef,
    DefaultLordDef,
    DungeonDefence,
    EffectCapDef,
    EffectDef,
    EffectTypeDef,
    EquipmentEffectDef,
    GeneralDef,
    GeneralSkillDef,
    GlobalEffectDef,
    HorseStats,
    LegendSkillDef,
    NpcCampDefence,
    RelicEffectDef,
    SceatSkillDef,
    ToolCategoryDef,
    ToolStats,
    UnitStats,
)

logger = logging.getLogger(__name__)

CACHE_FILENAME_TEMPLATE = "items_v{version}.trimmed.json"

# Camp tables that share the NpcCampDefence shape.
CAMP_TABLES = (
    "nomadCamps",
    "samuraiCamps",
    "factioninvasioncamps",
    "allianceInvasionCamps",
)

# Kept verbatim: needed later, but their encodings are not established yet, so
# modelling them now would be guesswork.
RAW_TABLES = (
    "bossdungeons",
    "specialcamps",
    "eventAutoScalingCamps",
    "eventAutoScalingUnitPairings",
    "eventAutoScalingToolPairings",
)

R = TypeVar("R", bound=BaseModel)


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


class GameData(BaseModel):
    """
    The combat-relevant tables for one items version.

    Load it explicitly:

        data = GameData.load()
        data.get_unit(211).range_attack
    """

    model_config = ConfigDict(extra="ignore")

    version: str
    units: dict[int, UnitStats] = Field(default_factory=dict)
    tools: dict[int, ToolStats] = Field(default_factory=dict)
    effects: dict[int, EffectDef] = Field(default_factory=dict)
    effect_types: dict[int, EffectTypeDef] = Field(default_factory=dict)
    effect_caps: dict[int, EffectCapDef] = Field(default_factory=dict)
    equipment_effects: dict[int, EquipmentEffectDef] = Field(default_factory=dict)
    relic_effects: dict[int, RelicEffectDef] = Field(default_factory=dict)
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
    dungeons: list[DungeonDefence] = Field(default_factory=list)
    camps: dict[str, list[NpcCampDefence]] = Field(default_factory=dict)
    raw_tables: dict[str, list] = Field(default_factory=dict)

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

    def units_by_role(self, role: str) -> list[UnitStats]:
        return [unit for unit in self.units.values() if unit.role == role]

    def get_horse(self, wod_id: int) -> HorseStats | None:
        """A travel booster by its ``HBW`` value."""
        return self.horses.get(wod_id)

    def get_default_lord(self, lord_id: int) -> DefaultLordDef | None:
        """A default lord, i.e. one of the negative ``LID`` sentinels."""
        return self.default_lords.get(lord_id)

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

    def dungeon_defence(self, victories: int, kingdom_id: int = 0) -> DungeonDefence | None:
        """The camp defence for a victory count in a kingdom."""
        for row in self.dungeons:
            if row.count_victories == victories and row.kingdom_id == kingdom_id:
                return row
        return None

    def raw(self, table: str) -> list:
        """An unmodelled table, exactly as the payload had it."""
        return self.raw_tables.get(table, [])

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

        return cls(
            version=version,
            units=units,
            tools=tools,
            effects={r.effect_id: r for r in _rows(items_data.get("effects"), EffectDef)},
            effect_types={r.effect_type_id: r for r in _rows(items_data.get("effecttypes"), EffectTypeDef)},
            effect_caps={r.cap_id: r for r in _rows(items_data.get("effectCaps"), EffectCapDef)},
            equipment_effects={
                r.equipment_effect_id: r for r in _rows(items_data.get("equipment_effects"), EquipmentEffectDef)
            },
            relic_effects={r.relic_effect_id: r for r in _rows(items_data.get("relicEffects"), RelicEffectDef)},
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
            dungeons=_rows(items_data.get("dungeons"), DungeonDefence),
            camps={
                table: _rows(items_data.get(table), NpcCampDefence) for table in CAMP_TABLES if items_data.get(table)
            },
            raw_tables={table: items_data[table] for table in RAW_TABLES if isinstance(items_data.get(table), list)},
        )

    @classmethod
    def load(cls, *, refresh: bool = False, cache_dir: str | Path | None = None) -> "GameData":
        """
        Fetch the items payload and return the trimmed tables.

        The version file is checked on every call, so a game patch invalidates
        the cache on its own. Only a cache miss downloads the full payload.

        Args:
            refresh: Ignore any cached copy and re-download
            cache_dir: Where to keep trimmed data (default: XDG cache dir)

        Raises:
            NetworkError: The CDN could not be reached
        """
        directory = Path(cache_dir) if cache_dir is not None else default_cache_dir()
        try:
            version = get_items_version()
        except Exception as e:
            raise NetworkError(f"Failed to fetch the items version: {e}") from e

        cache_file = directory / CACHE_FILENAME_TEMPLATE.format(version=version)
        if not refresh:
            cached = cls._read_cache(cache_file, version)
            if cached is not None:
                return cached

        try:
            items_data = fetch_items_data(version)
        except Exception as e:
            raise NetworkError(f"Failed to fetch items data v{version}: {e}") from e

        data = cls.parse(version, items_data)
        data._write_cache(cache_file)
        logger.info(
            f"Loaded {len(data.units)} units, {len(data.tools)} tools and "
            f"{len(data.dungeons)} camp defences (v{version})"
        )
        return data

    @classmethod
    def _read_cache(cls, cache_file: Path, version: str) -> "GameData | None":
        if not cache_file.is_file():
            return None
        try:
            payload = json.loads(cache_file.read_text())
            data = cls.model_validate(payload)
        except (OSError, ValueError) as e:
            logger.warning(f"Ignoring unreadable game data cache {cache_file}: {e}")
            return None
        if data.version != version:
            return None
        logger.debug(f"Loaded game data v{version} from {cache_file}")
        return data

    def _write_cache(self, cache_file: Path) -> None:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(self.model_dump_json())
        except OSError as e:
            # A read-only cache dir must not fail the load.
            logger.warning(f"Could not cache game data to {cache_file}: {e}")


__all__ = ["GameData", "default_cache_dir"]
