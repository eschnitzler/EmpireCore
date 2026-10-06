"""
Generate the ``empire_core.gamedata.ids`` enums from the items data.

    uv run python scripts/generate_gamedata_ids.py                  # the version GameData.load() fetches
    uv run python scripts/generate_gamedata_ids.py --items items_v786.03.json
    uv run python scripts/generate_gamedata_ids.py --check          # exit 1 if the package is out of date
    uv run python scripts/generate_gamedata_ids.py --diff-names names.md --breaking-footer footer.txt

Each table becomes one module. Member names come from the row's name columns,
UPPER_SNAKE; names that still collide after that all get the row id appended,
so no member keeps a bare name another row also claims. Each member also
carries its row's fixed id and number columns to filter on (a level, a unit's
role, a tool's category), but not the name and type text its name is built
from; an enum with none is plain ``NAME = id``. Output is sorted
by id and formatted the way ``ruff format`` leaves it, so regenerating from the
same data changes nothing.
"""

from __future__ import annotations

import argparse
import ast
import json
import keyword
import re
import sys
import textwrap
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from empire_core.gamedata import GameData
from empire_core.protocol.js import js_falsy, js_parse_int

SCRIPT = "scripts/generate_gamedata_ids.py"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "src" / "empire_core" / "gamedata" / "ids"
LINE_LENGTH = 120
VERSION = re.compile(r"\d+(\.\d+)*")

Value = int | str


@dataclass(frozen=True)
class Attr:
    """A fixed column every member of an enum carries."""

    name: str
    type: str
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


def research_name(label: str, group_id: int, level: int) -> str:
    """
    ``<label>_G<group>_L<level>``; group and level make it unique, the label only makes it readable.

    The label is the ``comment2`` note, which the client does not read; a row without one is ``RESEARCH``.
    """
    stem = identifier(label, "R") if re.search(r"[A-Za-z]", label) else "RESEARCH"
    return f"{stem}_G{group_id}{level_suffix(level)}"


def condition_name(conditions: str) -> str:
    """``collectFame+225000#lootResource+2400`` -> ``COLLECT_FAME``: what the first condition counts."""
    return to_snake(conditions.split("#")[0].split("+")[0])


def building_rows(data: GameData) -> list[Row]:
    rows = []
    for wod_id, row in data.buildings.items():
        building_type = str_column(row, "type")
        if building_type == "-":
            building_type = ""
        level = int_column(row, "level", -1)
        name = building_name(str_column(row, "name"), building_type, level)
        rows.append(Row(name, wod_id, str(wod_id), (str_column(row, "group"), level)))
    return rows


def tables(data: GameData) -> list[Table]:
    """Every table the ids package covers, from ``data`` parsed from the full items file."""
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
                Row(to_snake(u.unit_type) + level_suffix(u.level), u.wod_id, str(u.wod_id), (u.level, u.role))
                for u in data.units.values()
            ],
            (LEVEL, Attr("role", "str", "melee or ranged.")),
        ),
        Table(
            "tools",
            "Tool",
            "T",
            "Tool ``wodID`` values from the ``units`` table (rows with ``slotTypes``).",
            "``ToolUnitVO.parseXmlNode`` (bundle line 6538)",
            [
                Row(to_snake(t.tool_type) + level_suffix(t.level), t.wod_id, str(t.wod_id), (t.level, t.category))
                for t in data.tools.values()
            ],
            (LEVEL, Attr("category", "str", 'Attack or Defence; "0" when the row has none.')),
        ),
        Table(
            "effects",
            "Effect",
            "E",
            "Effect ids from the ``effects`` table.",
            "``EffectVO.parseXML`` (bundle line 41702)",
            [Row(to_snake(e.name), e.effect_id, str(e.effect_id), (e.effect_type_id,)) for e in data.effects.values()],
            (Attr("effect_type_id", "int", "The effect type it modifies, an ``EffectType`` value."),),
        ),
        Table(
            "effect_types",
            "EffectType",
            "E",
            "Effect type ids from the ``effecttypes`` table.",
            "``CastleEffectTypeVO`` (bundle line 111835)",
            [Row(to_snake(t.name), t.effect_type_id, str(t.effect_type_id)) for t in data.effect_types.values()],
        ),
        Table(
            "currencies",
            "Currency",
            "C",
            "Currency keys from the ``currencies`` table, the key the server uses; coins and rubies are not in it.",
            "``CurrencyData.getXmlCurrencyByKey`` (bundle line 141194)",
            [Row(key, row.json_key, str(row.currency_id), (row.currency_id,)) for key, row in currencies],
            (Attr("currency_id", "int", "The currency's id, as other tables reference it."),),
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
        ),
        Table(
            "generals",
            "General",
            "G",
            "General ids from the ``generals`` table.",
            "``GeneralXmlVO.fillFromParamXml`` (bundle line 33102)",
            [Row(to_snake(g.name), g.general_id, str(g.general_id), (g.rarity_id,)) for g in data.generals.values()],
            (Attr("rarity_id", "int", "The ``generalRarityID`` column."),),
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
                    (a.ability_group_id, a.level),
                )
                for a in data.general_abilities.values()
            ],
            (Attr("ability_group_id", "int", "The group the ability's levels share."), LEVEL),
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
                    (s.general_id, s.level),
                )
                for s in data.general_skills.values()
            ],
            (Attr("general_id", "int", "The general it belongs to, a ``General`` value."), LEVEL),
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
                    (s.skill_tree_id, s.skill_group_id, s.level),
                )
                for s in data.legend_skills.values()
            ],
            (
                Attr("skill_tree_id", "int", "The tree it sits in."),
                Attr("skill_group_id", "int", "The group its levels share."),
                LEVEL,
            ),
        ),
        Table(
            "raid_bosses",
            "RaidBoss",
            "R",
            "Alliance raid boss ids from the ``raidBosses`` table.",
            "``AllianceRaidbossVO.parseXML`` (bundle line 113835)",
            [Row(to_snake(b.name), b.raid_boss_id, str(b.raid_boss_id)) for b in data.raid_bosses.values()],
        ),
        Table(
            "global_effects",
            "GlobalEffect",
            "G",
            "Global effect ids from the ``globalEffects`` table.",
            "``GlobalEffectVO.parseXml`` (bundle line 143690)",
            [Row(to_snake(g.name), g.global_effect_id, str(g.global_effect_id)) for g in data.global_effects.values()],
        ),
        Table(
            "buildings",
            "Building",
            "B",
            "Building ``wodID`` values from the ``buildings`` table, named name, type (for decorations) and level.",
            "``AVisualVO.parseXmlNode`` (bundle line 17800) reads name, group and type, ``AShopVO.parseXmlNode`` "
            "(bundle line 31713) the level",
            building_rows(data),
            (Attr("group", "str", "The ``group`` column, e.g. Building or Tower."), LEVEL),
        ),
        Table(
            "researches",
            "Research",
            "R",
            "Research ids from the ``researches`` table, named from the ``comment2`` note, group and level.",
            "``AResearchVO.fillFromParamXML`` (bundle line 61502), which does not read ``comment2``",
            [
                Row(
                    research_name(
                        str_column(row, "comment2"), int_column(row, "groupID", -1), int_column(row, "level", -1)
                    ),
                    research_id,
                    str(research_id),
                    (int_column(row, "groupID", -1), int_column(row, "level", -1)),
                )
                for research_id, row in data.researches.items()
            ],
            (Attr("group_id", "int", "The group the research's levels share."), LEVEL),
        ),
        Table(
            "construction_items",
            "ConstructionItem",
            "C",
            "Construction item ids from the ``constructionItems`` table, named name, group and level.",
            "``ConstructionItemVO.parseBasicValues`` (bundle line 47719)",
            [
                Row(
                    f"{to_snake(c.name)}_G{c.group_id}{level_suffix(c.level)}",
                    c.construction_item_id,
                    str(c.construction_item_id),
                    (c.group_id, c.level, c.rareness_id),
                )
                for c in data.construction_items.values()
            ],
            (
                Attr("group_id", "int", "The ``constructionItemGroupID`` column."),
                LEVEL,
                Attr("rareness_id", "int", "The ``rarenessID`` column."),
            ),
        ),
        Table(
            "events",
            "Event",
            "E",
            "Event ids from the ``events`` table, named from ``eventType``.",
            "``CastleSpecialEventData.storeXmlEvents`` (bundle line 139777) keys rows by ``eventID``, "
            "``ASpecialEventVO.parseBasicsFromXmlNode`` (bundle line 2959) reads ``eventType``",
            [
                Row(to_snake(str_column(row, "eventType")) or f"E{event_id}", event_id, str(event_id))
                for event_id, row in data.events.items()
            ],
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
                    (int_column(row, "rarity", 0),),
                )
                for loot_box_id, row in data.loot_boxes.items()
            ],
            (Attr("rarity", "int", "The ``rarity`` column."),),
        ),
        Table(
            "loot_box_types",
            "LootBoxType",
            "L",
            "Loot box type ids from the ``lootBoxTypes`` table, named from ``lootBoxTheme``; keys count per type.",
            "``LootBoxTypeVO.parseXML`` (bundle line 58900)",
            [
                Row(to_snake(str_column(row, "lootBoxTheme")) or f"L{type_id}", type_id, str(type_id))
                for type_id, row in data.loot_box_types.items()
            ],
        ),
        Table(
            "quests",
            "QuestId",
            "Q",
            "Quest ids from the ``quests`` table, named from what the first condition counts; most names "
            "carry their id, as many quests count the same thing. Named QuestId, as ``empire_core.quests.Quest`` "
            "is your running quest.",
            "``CastleQuestData.generateQuestXMLList`` (bundle line 20192), ``CastleQuestVO.fillFromParamXML`` "
            "(bundle line 52452)",
            [
                Row(
                    condition_name(str_column(row, "conditions")) or "QUEST",
                    quest_id,
                    str(quest_id),
                    (int_column(row, "questSeriesID", -1), int_column(row, "eventID", 0)),
                )
                for quest_id, row in data.quests.items()
            ],
            (
                Attr("series_id", "int", "The quest series it belongs to; -1 for none."),
                Attr("event_id", "int", "The event it belongs to, an ``Event`` value; 0 for none."),
            ),
        ),
        Table(
            "daily_quests",
            "DailyQuestId",
            "D",
            "Daily quest ids from the ``dailyactivities`` table, named from what the first condition counts. "
            "Named DailyQuestId, as ``empire_core.quests.DailyQuest`` is today's quest.",
            "``CastleDailyQuestData.createXmlQuestDic`` (bundle line 134082), ``DailyQuestVO.fillFromParamXML`` "
            "(bundle line 134124)",
            [
                Row(
                    condition_name(str_column(row, "conditions")) or "DAILY_QUEST",
                    quest_id,
                    str(quest_id),
                    (int_column(row, "triggerKingdomID", 0),),
                )
                for quest_id, row in data.daily_quests.items()
            ],
            (Attr("trigger_kingdom_id", "int", "The kingdom the quest counts in, a ``Kingdom`` value; -1 for any."),),
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
                    (int_column(row, "wearerID", -1), int_column(row, "slotID", -1)),
                )
                for group_id, row in data.equipment_groups.items()
            ],
            (
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
                Row(to_snake(str_column(row, "name")), type_id, str(type_id))
                for type_id, row in data.difficulty_types.items()
            ],
        ),
    ]


def header(version: str) -> str:
    return f"# Generated by {SCRIPT} from items {version}; do not edit.\n"


def literal(value: Value) -> str:
    """The literal ``ruff format`` keeps: double quotes, unless the text holds more of them than single ones."""
    text = json.dumps(value, ensure_ascii=False)
    if isinstance(value, str) and value.count('"') > value.count("'"):
        return "'" + text[1:-1].replace('\\"', '"').replace("'", "\\'") + "'"
    return text


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


def wrapped(text: str) -> list[str]:
    """Docstring lines, indented, within the line length."""
    return textwrap.wrap(text, LINE_LENGTH, initial_indent="    ", subsequent_indent="    ", break_on_hyphens=False)


def class_lines(table: Table, named: list[tuple[str, Value]]) -> list[str]:
    base = "str" if table.str_enum else "int"
    out = [f"class {table.enum}({'str, Enum' if table.str_enum else 'IntEnum'}):"]
    out += ['    """', *wrapped(table.doc), "", *wrapped(f"Client: {table.client}"), '    """']
    if table.attrs:
        out += ["", f"    _value_: {base}"]
        for attr in table.attrs:
            out += [f"    {attr.name}: {attr.type}", f'    """{attr.doc}"""']
        out += ["", *signature_lines(table)]
        out += [f"        member = {base}.__new__(cls, value)", "        member._value_ = value"]
        out += [f"        member.{a.name} = {a.name}" for a in table.attrs]
        out.append("        return member")
    by_value = {row.value: row.attrs for row in table.rows}
    if named:
        out.append("")
    for name, value in named:
        out += member_lines(name, value, by_value[value])
    return out


def render_module(version: str, enums: Iterable[tuple[Table, list[tuple[str, Value]]]]) -> str:
    enums = list(enums)
    bases = sorted({"Enum" if t.str_enum else "IntEnum" for t, _ in enums})
    out = [header(version)]
    if any(t.attrs for t, _ in enums):
        out += ["from __future__ import annotations", ""]
    out.append(f"from enum import {', '.join(bases)}")
    for table, named in enums:
        out += ["", "", *class_lines(table, named)]
    return "\n".join(out) + "\n"


INIT_DOC = """\
Game-data ids as enums, so they autocomplete.

One enum per items table, each member named from the row in UPPER_SNAKE;
where two rows would share a name, both carry their id (``SPEED_BOOST_2``).
Members are plain ints (``Currency`` members plain strs), so they go on the
wire and into models as their value.

Most members also carry their row's fixed id and number columns, e.g.
``Unit.MEAD_RANGER_L6.role`` and ``.level`` or ``Tool.X.category``, so
``[t for t in Tool if t.category == "Defence"]`` works without game data.
Anything a balance patch can change is not baked in: for the full row, load a
:class:`GameData` (nothing here downloads it) and ask
``game_data.record(member)``, or ``game_data.records(members)`` for several.

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
    module_of = {t.enum: t.module for t in table_list}
    out = [header(version), '"""', INIT_DOC, '"""', "", "from __future__ import annotations", ""]
    out += ["import importlib", "from typing import TYPE_CHECKING, Any", ""]
    by_module: dict[str, list[str]] = defaultdict(list)
    for t in table_list:
        by_module[t.module].append(t.enum)
    out += ["if TYPE_CHECKING:", "    from empire_core.gamedata.data import GameData", ""]
    for module in sorted(by_module):
        out.append(f"    from .{module} import {', '.join(sorted(by_module[module]))}")
    out += ["", f"ITEMS_VERSION = {literal(version)}", '"""The items version these enums were generated from."""', ""]
    out += ["# Each enum's module, imported on first use: together they hold thousands of members", "_MODULES = {"]
    out += [f'    "{name}": "{module_of[name]}",' for name in sorted(names)]
    out += [
        "}",
        "",
        "",
        "def is_current(game_data: GameData) -> bool:",
        '    """Whether ``game_data`` is the items version these enums were generated from."""',
        "    return game_data.version == ITEMS_VERSION",
        "",
        "",
        "if not TYPE_CHECKING:",
        "    # Hidden from type checkers, so they still flag a name the package lacks",
        "    def __getattr__(name: str) -> Any:",
        "        module = _MODULES.get(name)",
        "        if module is None:",
        '            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")',
        '        value = getattr(importlib.import_module(f".{module}", __name__), name)',
        "        globals()[name] = value",
        "        return value",
        "",
        "    def __dir__() -> list[str]:",
        "        return sorted({*globals(), *__all__})",
        "",
        "",
        "__all__ = [",
    ]
    out += [f'    "{name}",' for name in sorted(names + ["ITEMS_VERSION", "is_current"])]
    out.append("]")
    return "\n".join(out) + "\n"


def render(data: GameData) -> dict[str, str]:
    """File name -> contents for the whole package."""
    table_list = tables(data)
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


def member_values(files: dict[str, str]) -> dict[str, Value]:
    """``Enum.MEMBER`` -> value for every member in a rendered or committed package."""
    found: dict[str, Value] = {}
    for text in files.values():
        for node in ast.parse(text).body:
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
                    value = item.value.elts[0] if isinstance(item.value, ast.Tuple) else item.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, (int, str)):
                        found[f"{node.name}.{item.targets[0].id}"] = value.value
    return found


@dataclass(frozen=True)
class NameChanges:
    renamed: list[tuple[str, str]]
    """(old, new) for a value whose member name changed."""
    removed: list[str]
    changed: list[str]
    """Names kept but now naming another value."""
    added: list[str]

    @property
    def breaking(self) -> bool:
        return bool(self.renamed or self.removed or self.changed)


def name_changes(files: dict[str, str], out: Path) -> NameChanges:
    """How the members in ``files`` differ from the package committed in ``out``."""
    on_disk = {path.name: path.read_text() for path in out.glob("*.py")} if out.is_dir() else {}
    old, new = member_values(on_disk), member_values(files)

    new_by_value = {(name.split(".")[0], value): name for name, value in new.items()}
    renamed, removed, changed = [], [], []
    for name, value in old.items():
        if name in new:
            if new[name] != value:
                changed.append(name)
            continue
        successor = new_by_value.get((name.split(".")[0], value))
        if successor is not None and successor not in old:
            renamed.append((name, successor))
        else:
            removed.append(name)
    moved = {new_name for _, new_name in renamed}
    added = [name for name in new if name not in old and name not in moved]
    return NameChanges(sorted(renamed), sorted(removed), sorted(changed), sorted(added))


def names_report(changes: NameChanges) -> str:
    """Markdown listing every renamed, removed, changed and added member."""
    if not (changes.breaking or changes.added):
        return "No member was added, renamed or removed.\n"
    out = []
    sections = [
        ("Renamed", [f"`{old}` -> `{new}`" for old, new in changes.renamed]),
        ("Removed", [f"`{name}`" for name in changes.removed]),
        ("Now another id", [f"`{name}`" for name in changes.changed]),
        ("Added", [f"`{name}`" for name in changes.added]),
    ]
    for title, lines in sections:
        if lines:
            out += [f"### {title} ({len(lines)})", "", *(f"- {line}" for line in lines), ""]
    return "\n".join(out)


def breaking_footer(changes: NameChanges) -> str:
    """A ``BREAKING CHANGE:`` footer naming what callers lose, or "" when nothing breaks."""
    if not changes.breaking:
        return ""
    parts = [f"{old} is now {new}" for old, new in changes.renamed]
    parts += [f"{name} is removed" for name in changes.removed]
    parts += [f"{name} now names another id" for name in changes.changed]
    return "BREAKING CHANGE: " + "; ".join(parts) + ".\n"


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
    parser.add_argument(
        "--diff-names", type=Path, help="write a Markdown list of renamed, removed and added members here"
    )
    parser.add_argument(
        "--breaking-footer", type=Path, help='write a "BREAKING CHANGE:" footer here, empty when nothing breaks'
    )
    args = parser.parse_args(argv)

    if args.items:
        payload = json.loads(args.items.read_text())
        version = items_version(args.items, payload)
        if not VERSION.fullmatch(version):
            raise SystemExit(f"items version {version!r} is not dotted digits")
        data = GameData.parse(version, payload)
    else:
        data = GameData.load()
        if not VERSION.fullmatch(data.version):
            raise SystemExit(f"items version {data.version!r} is not dotted digits")

    table_list = tables(data)
    empty = [t.enum for t in table_list if not t.rows]
    if empty:
        raise SystemExit(f"no rows for {', '.join(empty)}; is this the full items file?")
    files = render(data)
    changes = name_changes(files, args.out)
    if args.diff_names:
        args.diff_names.write_text(names_report(changes))
    if args.breaking_footer:
        args.breaking_footer.write_text(breaking_footer(changes))
    if args.check:
        changed = stale(files, args.out)
        for name in changed:
            print(f"out of date: {args.out / name}", file=sys.stderr)
        if changed:
            print(names_report(changes), file=sys.stderr)
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
