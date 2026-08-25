"""
Static game data from the GGE items payload.

The client builds its combat maths from ``items_v{version}.json`` on the GGE
CDN. That file is ~20 MB, so nothing here is fetched implicitly: call
:meth:`GameData.load` (or :meth:`EmpireClient.load_game_data`) when you want it.
Parsed data is trimmed to the unit and tool tables and cached on disk per
version, so the download happens once per game patch.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from empire_core.exceptions import NetworkError
from empire_core.utils.troops import fetch_items_data, get_items_version

logger = logging.getLogger(__name__)

CACHE_FILENAME_TEMPLATE = "items_v{version}.trimmed.json"


def default_cache_dir() -> Path:
    """Where trimmed game data is cached (honours XDG_CACHE_HOME)."""
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "empire_core"


class UnitStats(BaseModel):
    """
    A combat unit from the items payload.

    Units are the entries without ``slotTypes``; everything else is a tool.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    wod_id: int = Field(alias="wodID")
    source: str = Field(alias="name", default="")
    unit_type: str = Field(alias="type", default="")
    role: str = ""
    level: int = 0
    speed: int = 0
    melee_attack: int = Field(alias="meleeAttack", default=0)
    range_attack: int = Field(alias="rangeAttack", default=0)
    melee_defence: int = Field(alias="meleeDefence", default=0)
    range_defence: int = Field(alias="rangeDefence", default=0)
    loot_value: float = Field(alias="lootValue", default=0)
    might_value: float = Field(alias="mightValue", default=0)
    mead_supply: int = Field(alias="meadSupply", default=0)
    beef_supply: int = Field(alias="beefSupply", default=0)
    food_supply: int = Field(alias="foodSupply", default=0)
    healing_cost_c1: int = Field(alias="healingCostC1", default=0)
    healing_cost_c2: int = Field(alias="healingCostC2", default=0)
    hybrid: bool = False
    fight_type: int = Field(alias="fightType", default=0)

    @property
    def is_melee(self) -> bool:
        return self.role == "melee"

    @property
    def is_ranged(self) -> bool:
        return self.role == "ranged"

    @property
    def is_allround(self) -> bool:
        """A hybrid unit, which the client treats as fitting either flank."""
        return self.hybrid

    @property
    def attack_value(self) -> int:
        """Raw offence, before any commander or equipment effects."""
        return max(self.melee_attack, self.range_attack)

    @property
    def is_offensive(self) -> bool:
        return self.attack_value > 0


class ToolStats(BaseModel):
    """
    A siege or defence tool from the items payload.

    ``effects`` is kept raw: resolving it needs the payload's effect tables,
    which the wave solver reads separately.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    wod_id: int = Field(alias="wodID")
    source: str = Field(alias="name", default="")
    tool_type: str = Field(alias="type", default="")
    category: str = Field(alias="typ", default="")
    raw_slot_types: str = Field(alias="slotTypes", default="")
    tool_category: str = Field(alias="toolCategory", default="")
    speed: int = 0
    amount_per_wave: int = Field(alias="amountPerWave", default=0)
    # 0/absent, 1 and 2 all occur; the client distinguishes them, so keep the value.
    delete_after_battle: int = Field(alias="deleteToolAfterBattle", default=0)
    can_attack_npc: bool = Field(alias="canBeUsedToAttackNPC", default=False)
    fight_type: int = Field(alias="fightType", default=0)
    effects: Any = None

    @property
    def slot_types(self) -> tuple[int, ...]:
        """Attack-screen slot types this tool fits."""
        return tuple(int(part) for part in self.raw_slot_types.split(",") if part.strip())

    @property
    def is_attack_tool(self) -> bool:
        return self.category == "Attack"

    @property
    def is_defence_tool(self) -> bool:
        return self.category == "Defence"

    @property
    def is_consumed_in_battle(self) -> bool:
        return self.delete_after_battle > 0

    def fits_slot(self, slot_type: int) -> bool:
        """Whether this tool may go in the given slot type."""
        return slot_type in self.slot_types


class GameData(BaseModel):
    """
    The unit and tool tables for one items version.

    Load it explicitly:

        data = GameData.load()
        data.get_unit(211).range_attack
    """

    model_config = ConfigDict(extra="ignore")

    version: str
    units: dict[int, UnitStats] = Field(default_factory=dict)
    tools: dict[int, ToolStats] = Field(default_factory=dict)

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

    @classmethod
    def parse(cls, version: str, items_data: dict) -> "GameData":
        """Trim a full items payload down to the unit and tool tables."""
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
        return cls(version=version, units=units, tools=tools)

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
        logger.info(f"Loaded {len(data.units)} units and {len(data.tools)} tools (v{version})")
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


__all__ = ["GameData", "UnitStats", "ToolStats", "default_cache_dir"]
