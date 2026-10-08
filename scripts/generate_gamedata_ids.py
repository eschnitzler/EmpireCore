"""
Generate the ``empire_core.gamedata.ids`` enums from the items data.

    uv run python scripts/generate_gamedata_ids.py                  # the versions the game serves now
    uv run python scripts/generate_gamedata_ids.py --items items_v786.03.json --texts scripts/gamedata_ids_texts.json
    uv run python scripts/generate_gamedata_ids.py --check          # exit 1 if out of date, against the live texts
    uv run python scripts/generate_gamedata_ids.py --check --texts scripts/gamedata_ids_texts.json  # texts offline
    uv run python scripts/generate_gamedata_ids.py --diff-names names.md --breaking-footer footer.txt

Each table becomes one module. Member names come from the row's name columns,
UPPER_SNAKE; names that still collide after that all get the row id appended,
so no member keeps a bare name another row also claims. Where a table's names
would be codes (currency keys, the researches' German notes) or it has none
(gems, sceat skills, achievements, titles, crest layouts, main quests), a row
is named from the game's English text instead, by the text id the client
shows for it; a row without its own text keeps the code name, a designer
note, or its id. The texts come from the live
language file (or ``--texts``), and the ones used are kept in
``scripts/gamedata_ids_texts.json``, so ``--items X --texts`` that file
regenerates the same names offline, and a renamed text shows up as a diff. Each member also
carries its row's fixed id and number columns to filter on (a level, a unit's
role, a tool's category), but not the name and type text its name is built
from; an enum with none is plain ``NAME = id``. A table with a text id the
client names its rows by gets ``display_name(lang)``, which reads that text at
run time; the same text id names the members, and a member carries it as
``text_id`` where the id does not follow from its value. Output is sorted
by id and formatted the way ``ruff format`` leaves it, so regenerating from the
same data changes nothing.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import keyword
import re
import sys
import textwrap
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

from empire_core.gamedata import AchievementCondition, CurrencyDef, GameData, QuestCondition
from empire_core.gamedata.tables import row_id
from empire_core.texts import fetch_texts

SCRIPT = "scripts/generate_gamedata_ids.py"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "src" / "empire_core" / "gamedata" / "ids"
DEFAULT_SNAPSHOT = Path(__file__).resolve().parent / "gamedata_ids_texts.json"
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
class DisplayName:
    """The text id the client names a row by, which names the member and its ``display_name`` reads."""

    key: str
    """A format string over ``value`` and the member's attributes, e.g. ``event_title_{value}``."""
    client: str
    arg: str | None = None
    """The attribute that fills the text's ``{0}``."""
    optional: bool = False
    """Some rows have no text id (an empty ``text_id``)."""
    shown: str = ""
    """The text id as the docs show it, when ``key`` is an attribute."""

    def __call__(self, **fields: object) -> str:
        return self.key.format(**fields)

    @property
    def documented(self) -> str:
        return self.shown or re.sub(r"\{(\w+)\}", r"<\1>", self.key)

    @property
    def stored(self) -> bool:
        """Members carry the text id as their ``text_id`` attribute rather than build it from their value."""
        return self.key == "{text_id}"

    @property
    def expression(self) -> str:
        """The key as Python over ``self``."""
        return 'f"' + re.sub(r"\{(\w+)\}", r"{self.\1}", self.key) + '"'


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
    display: DisplayName | None = None


@contextmanager
def enums_not_generated_yet() -> Iterator[set[str]]:
    """
    Read the ids of an enum the package lacks as plain ints, so a new table generates from a clean package.

    A table's rows type their id as the table's enum, which reading them looks up in
    ``empire_core.gamedata.ids``; before its first generation there is none, so an empty one stands in.
    The fields that looked it up keep the stand-in for the process. Yields the names stood in for,
    which the caller checks are all enums of tables being generated.
    """
    namespace = vars(importlib.import_module("empire_core.gamedata.ids"))
    lookup = namespace["__getattr__"]
    stood_in: set[str] = set()

    def stand_in(name: str) -> Any:
        try:
            return lookup(name)
        except AttributeError:
            if name.startswith("_"):
                raise
            stood_in.add(name)
            return IntEnum(name, {})

    namespace["__getattr__"] = stand_in
    try:
        yield stood_in
    finally:
        namespace["__getattr__"] = lookup


class Texts:
    """The English texts members are named from; remembers each one a name used, for the snapshot."""

    def __init__(self, texts: Mapping[str, object]) -> None:
        # The client looks texts up case-insensitively: GlobalizeTextProcessor.setTexts (dll line 22936)
        self._texts = {key.lower(): str(value) for key, value in texts.items() if key != "@metadata"}
        self.used: dict[str, str] = {}

    def get(self, text_id: str) -> str | None:
        found = self._texts.get(text_id.lower())
        if not found:
            return None
        self.used[text_id] = found
        return found

    def snapshot(self) -> str:
        return json.dumps(dict(sorted(self.used.items())), indent=2, ensure_ascii=False) + "\n"


def text_name(text: str) -> str:
    """
    ``Toril's general shard`` -> ``Torils general shard``; a leading number goes last (``generals XP 1000``).

    A ``{0}`` placeholder is left out: the caller names what fills it, such as a level.
    """
    text = re.sub(r"\{\d+\}", "", text)
    text = re.sub(r"(?<=\d),(?=\d{3})", "", re.sub(r"['\u2019]", "", text))
    return re.sub(r"^(\d+)\s+(.+)$", r"\2 \1", text)


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
TEXT_ID = Attr("text_id", "str", "The text id the game names it by, which ``display_name`` reads.")

UNIT_NAME = DisplayName("{text_id}", "``BasicUnitVO.getNameString`` (bundle line 19219)", shown="<type>_name")
CURRENCY_NAME = DisplayName(
    "{text_id}",
    "``CollectableItemGenericCurrencyVO.getNameTextId`` (bundle line 5267)",
    shown="currency_name_<assetName or Name>",
)
GENERAL_NAME = DisplayName("generals_characters_{value}_name", "``GeneralXmlVO.nameTextID`` (bundle line 33105)")
LEGEND_SKILL_NAME = DisplayName(
    "dialog_legendTemple_{skill_group_id}_name", "``CastleLegendSkillVO.nameTextID`` (bundle line 48669)"
)
RESEARCH_TITLE = DisplayName(
    "research_{group_id}_title",
    "``ResearchVO.nameTextId`` (bundle line 61480); a blueprint or recipe research is named from other tables, "
    "which is not done here",
)
EVENT_TITLE = DisplayName("event_title_{value}", "``ASeasonEventVO.seasonNameString`` (bundle line 31389)")
GEM_NAME = DisplayName(
    "{text_id}",
    "``CastleGemVO.nameString`` (bundle line 28321)",
    arg="level",
    shown="gem_unique_<reuseAssetOfGemID> or gem_effect_name_<gem type>",
)
SCEAT_SKILL_NAME = DisplayName(
    "dialog_legendTemple_sceat_{skill_group_id}_name", "``CastleSceatSkillVO.nameTextID`` (bundle line 23110)"
)
ACHIEVEMENT_NAME = DisplayName("achievementName_{series_id}", "``AchievementSerieVO.nameString`` (bundle line 92822)")
TITLE_NAME = DisplayName("playerTitle_{value}", "``TitleVO.textID`` (bundle line 62756)")
CREST_LAYOUT_NAME = DisplayName(
    "allianceCoat_Layout_name_{value}", "``CollectableItemAllianceCrestLayoutVO.getNameTextId`` (bundle line 89359)"
)
MAIN_QUEST_TITLE = DisplayName("mainquest_{value}_title", "the quest book's chapter dialog (bundle line 93386)")


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


# EffectTypeEnum.EFFECT_TYPE_ENABLE_CONSTRUCTIONITEM_RECIPE_ID and EFFECT_TYPE_ENABLE_CRAFTINGRECIPE (bundle line 1322)
RECIPE_EFFECT_TYPES = {116, 170}


def research_rows(data: GameData, texts: Texts | None) -> list[Row]:
    """
    ``<title>_L<level>`` from ``research_<groupID>_title``, else :func:`research_name`.

    Only rows the client builds as a ``ResearchVO`` have that title: ``CastleResearchData.createResearchVO``
    (bundle line 139323) builds a blueprint or crafting-recipe research, named from other tables, when the
    first effect enables recipes, and ``ResearchVO.nameTextId`` (bundle line 61480) is the title. The
    title names a group, so a title two groups share falls back on the research id.
    """
    rows = []
    for row in data.researches.values():
        research_id, group_id, level = int(row.research_id), row.group_id, row.level
        first_effect = row.effects[0].effect_id if row.effects else None
        effect = data.effects.get(first_effect) if first_effect is not None else None
        recipe = effect is not None and effect.effect_type_id in RECIPE_EFFECT_TYPES
        text_id = "" if recipe else RESEARCH_TITLE(group_id=group_id)
        title = texts.get(text_id) if texts is not None and text_id else None
        if title:
            base = text_name(title) + level_suffix(level)
        else:
            base = research_name(row.label, group_id, level)
        rows.append(Row(base, research_id, str(research_id), (group_id, level, text_id)))
    return rows


def currency_names(data: GameData, texts: Texts | None) -> list[tuple[str, CurrencyDef, str]]:
    """
    (name, row, text id) for every currency the server keys: its English name, else its key.

    The client names a currency ``"currency_name_" + (assetName or Name)``
    (``CollectableItemGenericCurrencyVO.getNameTextId`` and ``getNameOrAssetName``, bundle lines 5267
    and 5273). A text id several currencies share (the 80 decoration catalysts) names none of them.
    """
    rows = [row for row in data.currencies.values() if row.json_key]
    text_ids = {row.currency_id: row.name_text_id for row in rows}
    shared = {text_id for text_id, n in Counter(t.lower() for t in text_ids.values()).items() if n > 1}
    named = []
    for row in rows:
        text_id = text_ids[row.currency_id]
        text = None if texts is None or text_id.lower() in shared else texts.get(text_id)
        named.append((text_name(text) if text else row.json_key.upper(), row, text_id))
    return named


def condition_name(conditions: Sequence[QuestCondition] | Sequence[AchievementCondition]) -> str:
    """``collectFame+225000#lootResource+2400`` -> ``COLLECT_FAME``: what the first condition counts."""
    return to_snake(conditions[0].condition_type) if conditions else ""


def named(texts: Texts | None, text_id: str) -> str | None:
    """The English text ``text_id`` names, made a name; None when there is none."""
    text = texts.get(text_id) if texts is not None else None
    return text_name(text) if text else None


def gem_rows(data: GameData, texts: Texts | None) -> list[Row]:
    """
    A unique gem (level 0) by ``gem_unique_<reuseAssetOfGemID, else its id>``; any other by
    ``gem_effect_name_gem<FirstEffect>`` (``_100`` when it always triggers) and its level, which fills its ``{0}``.

    Client: ``CastleGemVO.nameString``, ``isUnique`` and ``reuseAssetOfGemID`` (bundle lines 28321, 28324,
    28372), ``GemBonusVO.gemTypeString`` (bundle line 46814)
    """
    rows = []
    for row in data.gems.values():
        gem_id = int(row.gem_id)
        if row.level == 0:
            asset_id = row.reuse_asset_of_gem_id if row.reuse_asset_of_gem_id > 0 else gem_id
            text_id = f"gem_unique_{asset_id}"
            name = named(texts, text_id)
        else:
            effect = data.effects.get(row.effects[0].effect_id) if row.effects else None
            always = "_100" if row.trigger_chance == 100 else ""
            gem_type = f"gem{effect.name[:1].upper()}{effect.name[1:]}" if effect else ""
            text_id = f"gem_effect_name_{gem_type}{always}" if gem_type else ""
            name = named(texts, text_id) if text_id else None
            name = name + level_suffix(row.level) if name else None
        rows.append(Row(name or f"GEM_{gem_id}", gem_id, str(gem_id), (row.level, row.set_id, text_id)))
    return rows


def sceat_skill_rows(data: GameData, texts: Texts | None) -> list[Row]:
    """
    ``dialog_legendTemple_sceat_<skillGroupID>_name`` and level.

    Client: ``CastleSceatSkillVO.nameTextID`` (bundle line 23110)
    """
    return [
        Row(
            (named(texts, SCEAT_SKILL_NAME(skill_group_id=s.skill_group_id)) or f"SCEAT_G{s.skill_group_id}")
            + level_suffix(s.level),
            int(s.skill_id),
            str(s.skill_id),
            (s.skill_group_id, s.skill_tree_id, s.level),
        )
        for s in data.sceat_skills.values()
    ]


def achievement_rows(data: GameData, texts: Texts | None) -> list[Row]:
    """
    The series' ``achievementName_<achievementSeriesID>`` and the step as its level, else what it counts.

    Client: ``AchievementSerieVO.nameString`` (bundle line 92822) and ``addAchievementVO``, which keys a
    series' steps by ``achievementSeriesNumber`` (bundle line 92818); the main series
    (``CastleAchievementData.MAIN_ACHIEVMENT_SERIESID``, bundle line 29884) has no text of its own.
    """
    return [
        Row(
            (
                named(texts, ACHIEVEMENT_NAME(series_id=a.series_id))
                or condition_name(a.conditions)
                or f"SERIES_{a.series_id}"
            )
            + level_suffix(a.series_number),
            int(a.achievement_id),
            str(a.achievement_id),
            (a.series_id, a.series_number),
        )
        for a in data.achievements.values()
    ]


def horse_rows(data: GameData) -> list[Row]:
    """The ``comment2`` and ``comment1`` notes, e.g. ``WARHORSE_STABLE1``; the client reads neither."""
    return [
        Row(
            "_".join(part for part in (h.label, to_snake(h.building_label)) if part) or f"HORSE_{h.wod_id}",
            int(h.wod_id),
            str(h.wod_id),
        )
        for h in data.horses.values()
    ]


def main_quest_rows(data: GameData, texts: Texts | None) -> list[Row]:
    """
    ``mainquest_<id>_title``, the title ``CastleMainQuestFinishedDialog`` shows (bundle line 93386).

    The client parses no ``mainquests`` rows; the ids are the chapters the quest book lists
    (``CastleQuestBookMainQuestListVO.parseListsFromParamObject``, bundle line 52419).
    """
    rows = []
    for entry in data.raw("mainquests"):
        quest_id = row_id(entry.get("mainQuestID"))
        rows.append(
            Row(named(texts, MAIN_QUEST_TITLE(value=quest_id)) or f"MAIN_QUEST_{quest_id}", quest_id, str(quest_id))
        )
    return rows


def building_rows(data: GameData) -> list[Row]:
    return [
        Row(building_name(b.name, b.building_type, b.level), int(b.building_id), str(b.building_id), (b.group, b.level))
        for b in data.buildings.values()
    ]


def tables(data: GameData, texts: Texts | None = None) -> list[Table]:
    """
    Every table the ids package covers, from ``data`` parsed from the full items file.

    Without ``texts`` every row keeps its code name.
    """
    general_names = {row.general_id: row.name for row in data.generals.values()}

    def general_of(general_id: int) -> str:
        return to_snake(general_names.get(general_id) or f"G{general_id}")

    currencies = currency_names(data, texts)

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
                    (u.level, u.role, u.name_text_id),
                )
                for u in data.units.values()
            ],
            (LEVEL, Attr("role", "str", "melee or ranged."), TEXT_ID),
            display=UNIT_NAME,
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
                    (t.level, t.category, t.name_text_id),
                )
                for t in data.tools.values()
            ],
            (LEVEL, Attr("category", "str", 'Attack or Defence; "0" when the row has none.'), TEXT_ID),
            display=UNIT_NAME,
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
            "Currency keys from the ``currencies`` table, the key the server uses, named from the game's English "
            "name; coins and rubies are not in it.",
            "``CurrencyData.getXmlCurrencyByKey`` (bundle line 141194); names from ``currency_name_<assetName or "
            "Name>`` (``CollectableItemGenericCurrencyVO.getNameTextId``, bundle line 5267)",
            [
                Row(key, row.json_key, str(row.currency_id), (row.currency_id, text_id))
                for key, row, text_id in currencies
            ],
            (Attr("currency_id", "int", "The currency's id, as other tables reference it."), TEXT_ID),
            str_enum=True,
            display=CURRENCY_NAME,
        ),
        Table(
            "currencies",
            "CurrencyId",
            "C",
            "Currency ids from the ``currencies`` table, as other tables reference them; names match ``Currency``.",
            "``XmlCurrencyVO.parseXml`` (bundle line 141282)",
            [
                Row(key, row.currency_id, str(row.currency_id), (row.json_key, text_id))
                for key, row, text_id in currencies
            ],
            (Attr("json_key", "str", "The key the server uses for it, a ``Currency`` value."), TEXT_ID),
            display=CURRENCY_NAME,
        ),
        Table(
            "generals",
            "General",
            "G",
            "General ids from the ``generals`` table.",
            "``GeneralXmlVO.fillFromParamXml`` (bundle line 33102)",
            [Row(to_snake(g.name), g.general_id, str(g.general_id), (g.rarity_id,)) for g in data.generals.values()],
            (Attr("rarity_id", "int", "The ``generalRarityID`` column."),),
            display=GENERAL_NAME,
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
            display=LEGEND_SKILL_NAME,
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
            "Research ids from the ``researches`` table, named from the game's English title and level; a "
            "blueprint or recipe research from the ``comment2`` note, group and level.",
            "``AResearchVO.fillFromParamXML`` (bundle line 61502), which does not read ``comment2``; titles "
            "from ``ResearchVO.nameTextId`` (bundle line 61480)",
            research_rows(data, texts),
            (Attr("group_id", "int", "The group the research's levels share."), LEVEL, TEXT_ID),
            display=DisplayName("{text_id}", RESEARCH_TITLE.client, optional=True, shown="research_<groupID>_title"),
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
                Row(to_snake(e.event_type) or f"E{e.event_id}", int(e.event_id), str(e.event_id))
                for e in data.events.values()
            ],
            display=EVENT_TITLE,
        ),
        Table(
            "loot_boxes",
            "LootBox",
            "L",
            "Loot box ids from the ``lootBoxes`` table, named name and rarity.",
            "``LootBoxVO.parseXML`` (bundle line 112502)",
            [
                Row(f"{to_snake(b.name)}_R{b.rarity}", int(b.loot_box_id), str(b.loot_box_id), (b.rarity,))
                for b in data.loot_boxes.values()
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
                Row(to_snake(t.theme) or f"L{t.loot_box_type_id}", int(t.loot_box_type_id), str(t.loot_box_type_id))
                for t in data.loot_box_types.values()
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
                    condition_name(q.conditions) or "QUEST",
                    int(q.quest_id),
                    str(q.quest_id),
                    (q.series_id, int(q.event_id)),
                )
                for q in data.quests.values()
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
                    condition_name(q.conditions) or "DAILY_QUEST",
                    int(q.quest_id),
                    str(q.quest_id),
                    (int(q.trigger_kingdom),),
                )
                for q in data.daily_quests.values()
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
                Row(to_snake(g.name), int(g.group_id), str(g.group_id), (int(g.wearer_id), int(g.slot_id)))
                for g in data.equipment_groups.values()
            ],
            (
                Attr("wearer_id", "int", "Who wears it, a ``WearerType`` value."),
                Attr("slot_id", "int", "The slot it goes in, an ``EquipmentSlot`` value."),
            ),
        ),
        Table(
            "gems",
            "Gem",
            "G",
            "Gem ids from the ``gems`` table, named from the game's English name and, unless unique, level.",
            "``CastleGemVO.parseXML`` (bundle line 28287); names from ``CastleGemVO.nameString`` (bundle line 28321)",
            gem_rows(data, texts),
            (
                Attr("level", "int", "Gem level; 0 for a unique gem."),
                Attr("set_id", "int", "Its set; -1 for none."),
                TEXT_ID,
            ),
            display=GEM_NAME,
        ),
        Table(
            "sceat_skills",
            "SceatSkill",
            "S",
            "Sceat skill ids from the ``sceatSkills`` table, named from the game's English name and level.",
            "``CastleSceatSkillVO.parseXML`` (bundle line 23074); names from ``nameTextID`` (bundle line 23110)",
            sceat_skill_rows(data, texts),
            (
                Attr("skill_group_id", "int", "The group its levels share."),
                Attr("skill_tree_id", "int", "The tree it sits in."),
                LEVEL,
            ),
            display=SCEAT_SKILL_NAME,
        ),
        Table(
            "achievements",
            "Achievement",
            "A",
            "Achievement ids from the ``achievements`` table, named from the series' English name and the step "
            "as its level; the main series from what it counts.",
            "``AchievementVO.fillFromParamXML`` (bundle line 92882); names from ``AchievementSerieVO.nameString`` "
            "(bundle line 92822)",
            achievement_rows(data, texts),
            (
                Attr("series_id", "int", "The series it is a step of."),
                Attr("series_number", "int", "Its step in the series."),
            ),
            display=ACHIEVEMENT_NAME,
        ),
        Table(
            "horses",
            "Horse",
            "H",
            "Travel booster ``wodID`` values from the ``horses`` table, the ``HBW`` movements send, named from "
            "the ``comment2`` and ``comment1`` notes: the game names a horse only by its button's place in the "
            "travel dialog, the tooltip text ``horse<n>``.",
            "``HorseTravelboosterVO.parseXmlNode`` (bundle line 118814); "
            "``ACastlePostActionDialog.calculateTooltip`` (bundle line 27269)",
            horse_rows(data),
        ),
        Table(
            "titles",
            "Title",
            "T",
            "Title ids from the ``titles`` table, named from the game's English title.",
            "``TitleVO.parseXml`` (bundle line 62705); names from ``TitleVO.textID`` (bundle line 62756)",
            [
                Row(
                    named(texts, TITLE_NAME(value=t.title_id)) or f"TITLE_{t.title_id}",
                    int(t.title_id),
                    str(t.title_id),
                    (str(getattr(t.title_system, "value", t.title_system)),),
                )
                for t in data.titles.values()
            ],
            (Attr("title_system", "str", "Its title system, a ``TitleSystem`` value."),),
            display=TITLE_NAME,
        ),
        Table(
            "alliance_crests",
            "AllianceCrestLayout",
            "L",
            "Alliance crest layout ids from the ``allianceCoatLayouts`` table, named from the game's English "
            "name, else the ``comment1`` note.",
            "``AllianceCrestLayoutVO.parseXML`` (bundle line 111024); names from "
            "``CollectableItemAllianceCrestLayoutVO.getNameTextId`` (bundle line 89359)",
            [
                Row(
                    named(texts, CREST_LAYOUT_NAME(value=c.layout_id)) or c.label or f"LAYOUT_{c.layout_id}",
                    int(c.layout_id),
                    str(c.layout_id),
                    (c.color_count,),
                )
                for c in data.alliance_crest_layouts.values()
            ],
            (Attr("color_count", "int", "Colours it takes."),),
            display=CREST_LAYOUT_NAME,
        ),
        Table(
            "alliance_crests",
            "AllianceCrestColor",
            "C",
            "Alliance crest colour ids from the ``allianceCoatColors`` table. The game names no colour, so each "
            "is named by its id and carries its hex colour.",
            "``AllianceCrestColorVO.parseXML`` (bundle line 111012)",
            [
                Row(f"COLOR_{c.color_id}", int(c.color_id), str(c.color_id), (c.color,))
                for c in data.alliance_crest_colors.values()
            ],
            (Attr("color", "str", "The colour as hex text, e.g. 0xDBDACA."),),
        ),
        Table(
            "main_quests",
            "MainQuest",
            "M",
            "Main quest ids from the ``mainquests`` table, the quest book's chapters, named from the game's "
            "English title.",
            "``CastleQuestBookMainQuestListVO.parseListsFromParamObject`` (bundle line 52419); names from "
            "``mainquest_<id>_title`` (bundle line 93386)",
            main_quest_rows(data, texts),
            display=MAIN_QUEST_TITLE,
        ),
        Table(
            "difficulty_types",
            "DifficultyType",
            "D",
            "Event difficulty type ids from the ``eventAutoScalingDifficultyTypes`` table.",
            "``EventAutoScalingDifficultyTypeVO.parseXML`` (bundle line 38258)",
            [
                Row(to_snake(t.name), int(t.difficulty_type_id), str(t.difficulty_type_id))
                for t in data.difficulty_types.values()
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


def display_name_lines(display: DisplayName) -> list[str]:
    """
    The ``display_name`` method, the member's text in a language through ``empire_core.texts.text``, and
    a ``text_id`` property where members do not carry it.

    Client: ``Localize.text`` (dll line 3278), with the text id the client class reads.
    """
    key = display.documented
    text_id: list[str] = []
    if not display.stored:
        text_id = [
            "    @property",
            "    def text_id(self) -> str:",
            f'        """The text id of its name, ``{key}``."""',
            f"        return {display.expression}",
            "",
        ]
    args = ", ".join(["self.text_id", *([f"self.{display.arg}"] if display.arg else []), "lang=lang"])
    returns = "str | None" if display.optional else "str"
    doc = [
        f"The game's name for it in ``lang``, the text ``{key}``"
        + (f", its ``{{0}}`` filled with the {display.arg}" if display.arg else "")
        + ("; None for a row without one" if display.optional else "")
        + ".",
        "",
        "Fetches the language file on first use and caches it (:func:`empire_core.texts.text`); a text "
        "the file lacks, or a failed fetch, gives the text id.",
        "",
        f"Client: {display.client}",
    ]
    body = f"text({args})"
    if display.optional:
        body = f"{body} if self.text_id else None"
    out = [*text_id, f'    def display_name(self, lang: str = "en") -> {returns}:', '        """']
    indent = " " * 8
    for paragraph in doc:
        out += textwrap.wrap(paragraph, LINE_LENGTH, initial_indent=indent, subsequent_indent=indent) or [""]
    return [*out, '        """', f"        return {body}"]


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
    if table.display:
        out += ["", *display_name_lines(table.display)]
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
    if any(t.display for t, _ in enums):
        out += ["", "from empire_core.texts import text"]
    for table, named in enums:
        out += ["", "", *class_lines(table, named)]
    return "\n".join(out) + "\n"


INIT_DOC = """\
Game-data ids as enums, so they autocomplete.

One enum per items table, each member named from the row in UPPER_SNAKE;
where two rows would share a name, both carry their id (``SPEED_BOOST_2``).
Currencies and researches are named from the game's English text
(``Currency.SKIP_5_MINUTES`` is ``"MS2"``), where the row has its own.
Members are plain ints (``Currency`` members plain strs), so they go on the
wire and into models as their value.

Most members also carry their row's fixed id and number columns, e.g.
``Unit.MEAD_RANGER_L6.role`` and ``.level`` or ``Tool.X.category``, so
``[t for t in Tool if t.category == "Defence"]`` works without game data.
Anything a balance patch can change is not baked in: for the full row, load a
:class:`GameData` (nothing here downloads it) and index its table with the
member, e.g. ``game_data.units[Unit.MEAD_RANGER_L6]``.

Enums whose rows the game names by a text (units, tools, currencies,
researches, generals, legend and sceat skills, events, gems, achievements,
titles, crest layouts, main quests) have ``display_name(lang="en")``, the
name the game shows: ``Unit.MEAD_RANGER_L6.display_name("de")``. It reads the
language file, fetched on first use and cached (:mod:`empire_core.texts`).

``ITEMS_VERSION`` is the items version they were generated from, and
:func:`is_current` says whether a loaded :class:`GameData` is that version. For
anything newer, use the named lookups on :class:`GameData`.

Equipment, relic effects and alliance buffs have no enum, as the game names
none of their rows; look them up by id on :class:`GameData`
(``equipment_effects``, ``relic_effects``, ``alliance_buffs``). Nor do the
27,000 rewards: the game shows no text for one, and the notes some rows carry
name where it is given, not the reward.

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


def render(data: GameData, texts: Texts | None = None) -> dict[str, str]:
    """File name -> contents for the whole package."""
    table_list = tables(data, texts)
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
    parser.add_argument(
        "--texts", type=Path, help="the English language file, or a snapshot of it (default: download the current one)"
    )
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT, help="where to keep the texts names used")
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

    texts = Texts(json.loads(args.texts.read_text()) if args.texts else fetch_texts("en"))
    with enums_not_generated_yet() as stood_in:
        table_list = tables(data, texts)
        unknown = stood_in - {t.enum for t in table_list}
        if unknown:
            raise SystemExit(f"no table generates {', '.join(sorted(unknown))}, which the items tables name")
        empty = [t.enum for t in table_list if not t.rows]
        if empty:
            raise SystemExit(f"no rows for {', '.join(empty)}; is this the full items file?")
        files = render(data, texts)
    snapshot = texts.snapshot()
    snapshot_stale = not args.snapshot.is_file() or args.snapshot.read_text() != snapshot
    changes = name_changes(files, args.out)
    if args.diff_names:
        args.diff_names.write_text(names_report(changes))
    if args.breaking_footer:
        args.breaking_footer.write_text(breaking_footer(changes))
    if args.check:
        changed = [args.out / name for name in stale(files, args.out)] + ([args.snapshot] if snapshot_stale else [])
        for path in changed:
            print(f"out of date: {path}", file=sys.stderr)
        if changed:
            print(names_report(changes), file=sys.stderr)
            print(f"Regenerate for items {data.version}: uv run python {SCRIPT}", file=sys.stderr)
            return 1
        print(f"{args.out} is up to date with items {data.version}", file=sys.stderr)
        return 0
    write(files, args.out)
    if snapshot_stale:
        args.snapshot.write_text(snapshot)
    for t in table_list:
        print(f"{t.enum}: {len(t.rows)} members, {collided(t)} with an id suffix", file=sys.stderr)
    print(f"Wrote {len(files)} files for items {data.version} to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
