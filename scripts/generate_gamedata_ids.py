"""
Generate the ``empire_core.gamedata.ids`` enums from the items data.

    uv run python scripts/generate_gamedata_ids.py                  # the version GameData.load() fetches
    uv run python scripts/generate_gamedata_ids.py --items items_v786.03.json
    uv run python scripts/generate_gamedata_ids.py --check          # exit 1 if the package is out of date

Each table becomes one module. Member names come from the row's name columns,
UPPER_SNAKE; names that still collide after that all get the row id appended,
so no member keeps a bare name another row also claims. Each member also
carries the columns that identify its row, which a balance patch leaves alone.
Output is sorted by id and formatted the way ``ruff format`` leaves it, so
regenerating from the same data changes nothing.
"""

from __future__ import annotations

import argparse
import json
import keyword
import re
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from empire_core.gamedata import GameData
from empire_core.protocol.js import js_falsy, js_parse_int
from empire_core.utils.troops import fetch_items_data, get_items_version

SCRIPT = "scripts/generate_gamedata_ids.py"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "src" / "empire_core" / "gamedata" / "ids"
LINE_LENGTH = 120

Value = int | str


@dataclass(frozen=True)
class Attr:
    """A fixed column every member of an enum carries."""

    name: str
    type: str
    doc: str


@dataclass(frozen=True)
class Link:
    """A property returning the member's full row from the loaded GameData."""

    name: str
    model: str
    lookup: str
    """Called on the GameData with the member, e.g. ``units.get``."""
    doc: str


@dataclass(frozen=True)
class Row:
    base: str
    value: Value
    suffix: str
    """Appended to the name when another row shares it."""
    attrs: tuple[Value, ...] = ()


@dataclass(frozen=True)
class Table:
    """One generated enum."""

    module: str
    enum: str
    prefix: str
    """Put in front of a name that would start with a digit."""
    doc: str
    client: str
    rows: list[Row]
    attrs: tuple[Attr, ...] = ()
    links: tuple[Link, ...] = ()
    str_enum: bool = False


def to_snake(text: str) -> str:
    """``MeadRanger`` -> ``MEAD_RANGER``, ``CooldownReductionRBC`` -> ``COOLDOWN_REDUCTION_RBC``."""
    text = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    return text.upper()


def identifier(text: str, prefix: str) -> str:
    """A valid, public, non-keyword member name."""
    name = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_").upper()
    name = re.sub(r"_+", "_", name)
    if not name or name[0].isdigit():
        name = f"{prefix}_{name}".rstrip("_")
    if keyword.iskeyword(name):
        name += "_"
    return name


def members(table: Table) -> list[tuple[str, Value]]:
    """Name every row, suffixing each member of a colliding group with its id."""
    groups: dict[str, list[tuple[Value, str]]] = defaultdict(list)
    for row in table.rows:
        groups[identifier(row.base, table.prefix)].append((row.value, row.suffix))
    named: dict[str, Value] = {}
    for name, rows in groups.items():
        if len(rows) == 1:
            named[name] = rows[0][0]
            continue
        for value, suffix in rows:
            named[identifier(f"{name}_{suffix}", table.prefix)] = value
    if len(named) != len(table.rows):
        raise SystemExit(f"{table.enum}: names still collide after the id suffix")
    values = list(named.values())
    if len(set(values)) != len(values):
        raise SystemExit(f"{table.enum}: duplicate values would alias")
    return sorted(named.items(), key=lambda item: (0, item[1], "") if isinstance(item[1], int) else (1, 0, item[1]))


def collided(table: Table) -> int:
    """How many rows needed the id suffix."""
    counts: dict[str, int] = defaultdict(int)
    for row in table.rows:
        counts[identifier(row.base, table.prefix)] += 1
    return sum(n for n in counts.values() if n > 1)


def level_suffix(level: int) -> str:
    return f"_L{level}" if level >= 0 else ""


LEVEL = Attr("level", "int", "Upgrade level; -1 when the row has none.")
ROW_NAME = Attr("row_name", "str", "The row's name column.")


def info(model: str, lookup: str, what: str) -> Link:
    return Link("info", model, lookup, f"This {what}'s row in the loaded game data, or None if it has none.")


def raw_rows(payload: dict, table: str, id_key: str) -> list[tuple[int, dict]]:
    """
    A table GameData does not model, as ``(id, row)``.

    The id is ``parseInt`` of the column, as every parser below reads it; a
    row whose id is not a number is skipped.
    """
    rows = []
    for row in payload.get(table) or []:
        if not isinstance(row, dict):
            continue
        value = row.get(id_key)
        parsed = None if js_falsy(value) else js_parse_int(value)
        if parsed is not None:
            rows.append((parsed, row))
    return rows


def int_column(row: dict, key: str, default: int) -> int:
    """``parseInt(getValueOrDefault(key, row, default))``, NaN read as the default."""
    value = row.get(key)
    parsed = None if js_falsy(value) else js_parse_int(value)
    return default if parsed is None else parsed


def str_column(row: dict, key: str) -> str:
    """``getStringAttribute(key, row)``: a missing or empty value reads as ""."""
    value = row.get(key)
    return "" if js_falsy(value) else str(value)


def building_name(name: str, building_type: str, level: int) -> str:
    """Name plus level; a type other than ``Level<n>`` names the building too (``Deco`` rows)."""
    base = to_snake(name)
    if building_type and building_type != "Placeholder" and not re.fullmatch(r"Level\d+", building_type):
        base += "_" + to_snake(building_type)
    return base + level_suffix(level)


def building_rows(payload: dict) -> list[Row]:
    rows = []
    for wod_id, row in raw_rows(payload, "buildings", "wodID"):
        name, group = str_column(row, "name"), str_column(row, "group")
        building_type = str_column(row, "type")
        if building_type == "-":
            building_type = ""
        level = int_column(row, "level", -1)
        rows.append(
            Row(building_name(name, building_type, level), wod_id, str(wod_id), (name, group, building_type, level))
        )
    return rows


def tables(data: GameData, payload: dict) -> list[Table]:
    """Every table the ids package covers: ``data`` parsed from ``payload``, the items file."""
    general_names = {row.general_id: row.name for row in data.generals.values()}

    def general_of(general_id: int) -> str:
        return to_snake(general_names.get(general_id) or f"G{general_id}")

    currencies = [(row.json_key.upper(), row) for row in data.currencies.values() if row.json_key]

    return [
        Table(
            "units",
            "Unit",
            "U",
            "Unit ``wodID`` values from the ``units`` table (rows without ``slotTypes``).",
            "``SoldierUnitVO.parseXmlNode`` (bundle line 12531)",
            [
                Row(
                    to_snake(u.unit_type) + level_suffix(u.level),
                    u.wod_id,
                    str(u.wod_id),
                    (u.unit_type, u.level, u.role),
                )
                for u in data.units.values()
            ],
            (
                Attr("unit_type", "str", "The ``type`` column, e.g. MeadRanger; shared across levels."),
                LEVEL,
                Attr("role", "str", "melee or ranged."),
            ),
            (Link("stats", "UnitStats", "get_unit", "This unit's stats in the loaded game data, or None."),),
        ),
        Table(
            "tools",
            "Tool",
            "T",
            "Tool ``wodID`` values from the ``units`` table (rows with ``slotTypes``).",
            "``ToolUnitVO.parseXmlNode`` (bundle line 6538)",
            [
                Row(
                    to_snake(t.tool_type) + level_suffix(t.level),
                    t.wod_id,
                    str(t.wod_id),
                    (t.tool_type, t.level, t.category),
                )
                for t in data.tools.values()
            ],
            (
                Attr("tool_type", "str", "The ``type`` column, e.g. Ladder; shared across levels."),
                LEVEL,
                Attr("category", "str", 'Attack or Defence; "0" when the row has none.'),
            ),
            (Link("stats", "ToolStats", "get_tool", "This tool's stats in the loaded game data, or None."),),
        ),
        Table(
            "effects",
            "Effect",
            "E",
            "Effect ids from the ``effects`` table.",
            "``EffectVO.parseXML`` (bundle line 41702)",
            [
                Row(to_snake(e.name), e.effect_id, str(e.effect_id), (e.name, e.effect_type_id))
                for e in data.effects.values()
            ],
            (ROW_NAME, Attr("effect_type_id", "int", "The effect type it modifies, an ``EffectType`` value.")),
            (info("EffectDef", "effects.get", "effect"),),
        ),
        Table(
            "effect_types",
            "EffectType",
            "E",
            "Effect type ids from the ``effecttypes`` table.",
            "``CastleEffectTypeVO`` (bundle line 111835)",
            [
                Row(to_snake(t.name), t.effect_type_id, str(t.effect_type_id), (t.name,))
                for t in data.effect_types.values()
            ],
            (ROW_NAME,),
            (info("EffectTypeDef", "effect_types.get", "effect type"),),
        ),
        Table(
            "currencies",
            "Currency",
            "C",
            "Currency keys from the ``currencies`` table, the key the server uses; coins and rubies are not in it.",
            "``CurrencyData.getXmlCurrencyByKey`` (bundle line 141194)",
            [Row(key, row.json_key, str(row.currency_id), (row.currency_id,)) for key, row in currencies],
            (Attr("currency_id", "int", "The currency's id, as other tables reference it."),),
            (info("CurrencyDef", "currency", "currency"),),
            str_enum=True,
        ),
        Table(
            "currencies",
            "CurrencyId",
            "C",
            "Currency ids from the ``currencies`` table, as other tables reference them; names match ``Currency``.",
            "``XmlCurrencyVO.parseXml`` (bundle line 141282)",
            [Row(key, row.currency_id, str(row.currency_id), (row.json_key,)) for key, row in currencies],
            (Attr("json_key", "str", "The key the server uses for it, a ``Currency`` value."),),
            (info("CurrencyDef", "currencies.get", "currency"),),
        ),
        Table(
            "generals",
            "General",
            "G",
            "General ids from the ``generals`` table.",
            "``GeneralXmlVO.fillFromParamXml`` (bundle line 33102)",
            [
                Row(to_snake(g.name), g.general_id, str(g.general_id), (g.name, g.rarity_id))
                for g in data.generals.values()
            ],
            (ROW_NAME, Attr("rarity_id", "int", "The ``generalRarityID`` column.")),
            (info("GeneralDef", "generals.get", "general"),),
        ),
        Table(
            "general_abilities",
            "GeneralAbility",
            "A",
            "General ability ids from the ``generalAbilities`` table, one per level.",
            "``GeneralAbilityXmlVO.fillFromParamXml`` (bundle line 113203)",
            [
                Row(
                    to_snake(a.name) + level_suffix(a.level),
                    a.ability_id,
                    str(a.ability_id),
                    (a.name, a.ability_group_id, a.level),
                )
                for a in data.general_abilities.values()
            ],
            (ROW_NAME, Attr("ability_group_id", "int", "The group the ability's levels share."), LEVEL),
            (info("GeneralAbilityDef", "general_abilities.get", "ability"),),
        ),
        Table(
            "general_skills",
            "GeneralSkill",
            "S",
            "General skill ids from the ``generalSkills`` table, named general, skill and level.",
            "``GeneralSkillVO.parseXML`` (bundle line 113363)",
            [
                Row(
                    f"{general_of(s.general_id)}_{to_snake(s.name)}{level_suffix(s.level)}",
                    s.skill_id,
                    str(s.skill_id),
                    (s.name, s.general_id, s.level),
                )
                for s in data.general_skills.values()
            ],
            (ROW_NAME, Attr("general_id", "int", "The general it belongs to, a ``General`` value."), LEVEL),
            (info("GeneralSkillDef", "general_skills.get", "skill"),),
        ),
        Table(
            "legend_skills",
            "LegendSkill",
            "L",
            "Legend skill ids from the ``legendskills`` table, named effect type, tree, group and level.",
            "``CastleLegendSkillVO.parseXML`` (bundle line 48652)",
            [
                Row(
                    f"{to_snake(s.effect_type)}_T{s.skill_tree_id}_G{s.skill_group_id}{level_suffix(s.level)}",
                    s.skill_id,
                    str(s.skill_id),
                    (s.effect_type, s.skill_tree_id, s.skill_group_id, s.level),
                )
                for s in data.legend_skills.values()
            ],
            (
                Attr("effect_type", "str", "The ``effectType`` column."),
                Attr("skill_tree_id", "int", "The tree it sits in."),
                Attr("skill_group_id", "int", "The group its levels share."),
                LEVEL,
            ),
            (info("LegendSkillDef", "legend_skills.get", "skill"),),
        ),
        Table(
            "raid_bosses",
            "RaidBoss",
            "R",
            "Alliance raid boss ids from the ``raidBosses`` table.",
            "``AllianceRaidbossVO.parseXML`` (bundle line 113835)",
            [Row(to_snake(b.name), b.raid_boss_id, str(b.raid_boss_id), (b.name,)) for b in data.raid_bosses.values()],
            (ROW_NAME,),
            (info("RaidBossDef", "raid_bosses.get", "raid boss"),),
        ),
        Table(
            "global_effects",
            "GlobalEffect",
            "G",
            "Global effect ids from the ``globalEffects`` table.",
            "``GlobalEffectVO.parseXml`` (bundle line 143690)",
            [
                Row(to_snake(g.name), g.global_effect_id, str(g.global_effect_id), (g.name,))
                for g in data.global_effects.values()
            ],
            (ROW_NAME,),
            (info("GlobalEffectDef", "global_effects.get", "global effect"),),
        ),
        Table(
            "buildings",
            "Building",
            "B",
            "Building ``wodID`` values from the ``buildings`` table, named name, type (for decorations) and level.",
            "``AVisualVO.parseXmlNode`` (bundle line 17800), ``AShopVO.parseXmlNode`` (bundle line 31713)",
            building_rows(payload),
            (
                ROW_NAME,
                Attr("group", "str", "The ``group`` column, e.g. Building or Tower."),
                Attr("building_type", "str", "The ``type`` column, e.g. Level3 or a decoration's own name."),
                LEVEL,
            ),
            (
                Link(
                    "fortification",
                    "FortificationDef",
                    "fortifications.get",
                    "The wall, gate or moat protection this building gives, or None if it gives none.",
                ),
            ),
        ),
        Table(
            "researches",
            "Research",
            "R",
            "Research ids from the ``researches`` table, named from the ``comment2`` note and level.",
            "``AResearchVO.fillFromParamXML`` (bundle line 61502), which does not read ``comment2``",
            [
                Row(
                    str_column(row, "comment2") + level_suffix(int_column(row, "level", -1)),
                    research_id,
                    str(research_id),
                    (int_column(row, "groupID", -1), int_column(row, "level", -1)),
                )
                for research_id, row in raw_rows(payload, "researches", "researchID")
            ],
            (Attr("group_id", "int", "The group the research's levels share."), LEVEL),
        ),
        Table(
            "construction_items",
            "ConstructionItem",
            "C",
            "Construction item ids from the ``constructionItems`` table, named name and level.",
            "``ConstructionItemVO.parseBasicValues`` (bundle line 47719)",
            [
                Row(
                    to_snake(c.name) + level_suffix(c.level),
                    c.construction_item_id,
                    str(c.construction_item_id),
                    (c.name, c.group_id, c.level, c.rareness_id),
                )
                for c in data.construction_items.values()
            ],
            (
                ROW_NAME,
                Attr("group_id", "int", "The ``constructionItemGroupID`` column."),
                LEVEL,
                Attr("rareness_id", "int", "The ``rarenessID`` column."),
            ),
            (info("ConstructionItemDef", "construction_items.get", "construction item"),),
        ),
        Table(
            "events",
            "Event",
            "E",
            "Event ids from the ``events`` table, named from ``eventType``.",
            "``ASpecialEventVO.parseBasicsFromXmlNode`` (bundle line 2959)",
            [
                Row(
                    to_snake(str_column(row, "eventType")) or f"E{event_id}",
                    event_id,
                    str(event_id),
                    (str_column(row, "eventType"),),
                )
                for event_id, row in raw_rows(payload, "events", "eventID")
            ],
            (Attr("event_type", "str", "The ``eventType`` column, e.g. Nomad."),),
        ),
        Table(
            "loot_boxes",
            "LootBox",
            "L",
            "Loot box ids from the ``lootBoxes`` table, named name and rarity.",
            "``LootBoxVO.parseXML`` (bundle line 112502)",
            [
                Row(
                    f"{to_snake(str_column(row, 'name'))}_R{int_column(row, 'rarity', 0)}",
                    loot_box_id,
                    str(loot_box_id),
                    (str_column(row, "name"), int_column(row, "rarity", 0)),
                )
                for loot_box_id, row in raw_rows(payload, "lootBoxes", "lootBoxID")
            ],
            (ROW_NAME, Attr("rarity", "int", "The ``rarity`` column.")),
        ),
        Table(
            "equipment_groups",
            "EquipmentGroup",
            "G",
            "Equipment item group ids from the ``equipment_groups`` table, as equipment effects name them.",
            "``XmlEquipmentGroupVO.parseXml`` (bundle line 144187)",
            [
                Row(
                    to_snake(str_column(row, "name")),
                    group_id,
                    str(group_id),
                    (str_column(row, "name"), int_column(row, "wearerID", -1), int_column(row, "slotID", -1)),
                )
                for group_id, row in raw_rows(payload, "equipment_groups", "itemGroupID")
            ],
            (
                ROW_NAME,
                Attr("wearer_id", "int", "Who wears it, a ``WearerType`` value."),
                Attr("slot_id", "int", "The slot it goes in, an ``EquipmentSlot`` value."),
            ),
        ),
        Table(
            "difficulty_types",
            "DifficultyType",
            "D",
            "Event difficulty type ids from the ``eventAutoScalingDifficultyTypes`` table.",
            "``EventAutoScalingDifficultyTypeVO.parseXML`` (bundle line 38258)",
            [
                Row(to_snake(str_column(row, "name")), type_id, str(type_id), (str_column(row, "name"),))
                for type_id, row in raw_rows(payload, "eventAutoScalingDifficultyTypes", "difficultyTypeID")
            ],
            (ROW_NAME,),
        ),
    ]


def header(version: str) -> str:
    return f"# Generated by {SCRIPT} from items {version}; do not edit.\n"


def literal(value: Value) -> str:
    return json.dumps(value, ensure_ascii=False)


def member_lines(name: str, value: Value, attrs: tuple[Value, ...]) -> list[str]:
    """``NAME = value, attr, ...`` on one line, or one element per line as ruff splits it."""
    items = [literal(value), *map(literal, attrs)]
    line = f"    {name} = {', '.join(items)}"
    if len(line) <= LINE_LENGTH:
        return [line]
    return [f"    {name} = (", *(f"        {item}," for item in items), "    )"]


def signature_lines(table: Table) -> list[str]:
    base = "str" if table.str_enum else "int"
    # Defaults only so that a type checker accepts Unit(211), which looks the member up
    empty = {"int": "0", "str": '""'}
    params = ["cls", f"value: {base}", *(f"{a.name}: {a.type} = {empty[a.type]}" for a in table.attrs)]
    line = f"    def __new__({', '.join(params)}) -> {table.enum}:"
    if len(line) <= LINE_LENGTH:
        return [line]
    return ["    def __new__(", *(f"        {p}," for p in params), f"    ) -> {table.enum}:"]


def class_lines(table: Table, named: list[tuple[str, Value]]) -> list[str]:
    base = "str" if table.str_enum else "int"
    out = [f"class {table.enum}({'str, Enum' if table.str_enum else 'IntEnum'}):"]
    out += ['    """', f"    {table.doc}", "", f"    Client: {table.client}", '    """', ""]
    out.append(f"    _value_: {base}")
    for attr in table.attrs:
        out += [f"    {attr.name}: {attr.type}", f'    """{attr.doc}"""']
    out += ["", *signature_lines(table)]
    out += [f"        member = {base}.__new__(cls, value)", "        member._value_ = value"]
    out += [f"        member.{a.name} = {a.name}" for a in table.attrs]
    out.append("        return member")
    for link in table.links:
        out += ["", "    @property", f"    def {link.name}(self) -> {link.model} | None:", f'        """{link.doc}"""']
        out.append(f"        return default_game_data().{link.lookup}(self)")
    by_value = {row.value: row.attrs for row in table.rows}
    if named:
        out.append("")
    for name, value in named:
        out += member_lines(name, value, by_value[value])
    return out


def render_module(version: str, enums: Iterable[tuple[Table, list[tuple[str, Value]]]]) -> str:
    enums = list(enums)
    bases = sorted({"Enum" if t.str_enum else "IntEnum" for t, _ in enums})
    models = sorted({link.model for t, _ in enums for link in t.links})
    out = [header(version), "from __future__ import annotations", "", f"from enum import {', '.join(bases)}"]
    if models:
        out += ["", "from empire_core.gamedata.data import default_game_data"]
        out.append(f"from empire_core.gamedata.models import {', '.join(models)}")
    for table, named in enums:
        out += ["", "", *class_lines(table, named)]
    return "\n".join(out) + "\n"


INIT_DOC = """\
Game-data ids as enums, so they autocomplete.

One enum per items table, each member named from the row in UPPER_SNAKE;
where two rows would share a name, both carry their id (``SPEED_BOOST_2``).
Members are plain ints (``Currency`` members plain strs), so they go on the
wire and into models as their value.

Each member also carries the columns that identify its row and do not change
between patches, e.g. ``Unit.MEAD_RANGER_L6.unit_type``. Anything a balance
patch can change is not baked in: ``Unit.X.stats``, ``Tool.X.stats`` and the
other enums' ``info`` return the full row from
:func:`~empire_core.gamedata.default_game_data`, the GameData loaded last
(loading it on first use if none was).

``ITEMS_VERSION`` is the items version they were generated from, and
:func:`is_current` says whether a loaded :class:`GameData` is that version. For
anything newer, use the named lookups on :class:`GameData`.

Gems, equipment, horses, relic effects, alliance buffs and sceat skills have
no enum, as their rows have no name; look them up by id on :class:`GameData`
(``gems``, ``equipment_effects``, ``get_horse``, ``relic_effects``,
``alliance_buffs``, ``sceat_skills``).

Regenerate with ``uv run python scripts/generate_gamedata_ids.py``."""


def render_init(version: str, table_list: list[Table]) -> str:
    names = [t.enum for t in table_list]
    out = [header(version), '"""', INIT_DOC, '"""', "", "from __future__ import annotations", ""]
    out += ["from typing import TYPE_CHECKING", ""]
    by_module: dict[str, list[str]] = defaultdict(list)
    for t in table_list:
        by_module[t.module].append(t.enum)
    for module in sorted(by_module):
        out.append(f"from .{module} import {', '.join(sorted(by_module[module]))}")
    out += ["", "if TYPE_CHECKING:", "    from empire_core.gamedata.data import GameData", ""]
    out += [f'ITEMS_VERSION = "{version}"', '"""The items version these enums were generated from."""', "", ""]
    out += [
        "def is_current(game_data: GameData) -> bool:",
        '    """Whether ``game_data`` is the items version these enums were generated from."""',
        "    return game_data.version == ITEMS_VERSION",
        "",
        "",
        "__all__ = [",
    ]
    out += [f'    "{name}",' for name in sorted(names + ["ITEMS_VERSION", "is_current"])]
    out.append("]")
    return "\n".join(out) + "\n"


def render(data: GameData, payload: dict) -> dict[str, str]:
    """File name -> contents for the whole package."""
    table_list = tables(data, payload)
    by_module: dict[str, list[Table]] = defaultdict(list)
    for t in table_list:
        by_module[t.module].append(t)
    files = {
        f"{module}.py": render_module(data.version, ((t, members(t)) for t in group))
        for module, group in by_module.items()
    }
    files["__init__.py"] = render_init(data.version, table_list)
    return files


def items_version(path: Path, payload: dict) -> str:
    """The version the file declares, else the one in an ``items_v<version>.json`` name."""
    info = payload.get("versionInfo")
    if isinstance(info, dict):
        value = (info.get("version") or {}).get("@value")
        if value:
            return str(value)
    if path.name.endswith(".trimmed.json"):
        raise SystemExit(f"{path} is GameData's parsed cache, not an items file; pass the items JSON itself")
    match = re.fullmatch(r"items_v(.+?)\.json", path.name)
    if match:
        return match.group(1)
    raise SystemExit(f"cannot tell the items version of {path}; name it items_v<version>.json")


def stale(files: dict[str, str], out: Path) -> list[str]:
    """The files in ``out`` that writing ``files`` would change, add or remove."""
    on_disk = {path.name: path.read_text() for path in out.glob("*.py")} if out.is_dir() else {}
    return sorted(name for name in files.keys() | on_disk.keys() if files.get(name) != on_disk.get(name))


def write(files: dict[str, str], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.py"):
        if stale.name not in files:
            stale.unlink()
    for name, text in sorted(files.items()):
        path = out / name
        if not path.is_file() or path.read_text() != text:
            path.write_text(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--items", type=Path, help="a full items_v<version>.json (default: download the current one)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="package directory to write")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if the package would change")
    args = parser.parse_args(argv)

    if args.items:
        payload = json.loads(args.items.read_text())
        version = items_version(args.items, payload)
    else:
        version = get_items_version()
        payload = fetch_items_data(version)
    data = GameData.parse(version, payload)

    table_list = tables(data, payload)
    empty = [t.enum for t in table_list if not t.rows]
    if empty:
        raise SystemExit(f"no rows for {', '.join(empty)}; is this the full items file?")
    files = render(data, payload)
    if args.check:
        changed = stale(files, args.out)
        for name in changed:
            print(f"out of date: {args.out / name}", file=sys.stderr)
        if changed:
            print(f"Regenerate for items {data.version}: uv run python {SCRIPT}", file=sys.stderr)
            return 1
        print(f"{args.out} is up to date with items {data.version}", file=sys.stderr)
        return 0
    write(files, args.out)
    for t in table_list:
        print(f"{t.enum}: {len(t.rows)} members, {collided(t)} with an id suffix", file=sys.stderr)
    print(f"Wrote {len(files)} files for items {data.version} to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
