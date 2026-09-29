"""
Generate the ``empire_core.gamedata.ids`` enums from the items data.

    uv run python scripts/generate_gamedata_ids.py                  # the version GameData.load() fetches
    uv run python scripts/generate_gamedata_ids.py --items items_v786.03.json

Each table becomes one module. Member names come from the row's name columns,
UPPER_SNAKE; names that still collide after that all get the row id appended,
so no member keeps a bare name another row also claims. Output is sorted by id
and formatted the way ``ruff format`` leaves it, so regenerating from the same
data changes nothing.
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

SCRIPT = "scripts/generate_gamedata_ids.py"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "src" / "empire_core" / "gamedata" / "ids"


@dataclass(frozen=True)
class Table:
    """One generated enum."""

    module: str
    enum: str
    prefix: str
    """Put in front of a name that would start with a digit."""
    doc: str
    client: str
    rows: list[tuple[str, int | str, str]]
    """(base name, value, id suffix used on collision)."""
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


def members(table: Table) -> list[tuple[str, int | str]]:
    """Name every row, suffixing each member of a colliding group with its id."""
    groups: dict[str, list[tuple[int | str, str]]] = defaultdict(list)
    for base, value, suffix in table.rows:
        groups[identifier(base, table.prefix)].append((value, suffix))
    named: dict[str, int | str] = {}
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
    for base, _, _ in table.rows:
        counts[identifier(base, table.prefix)] += 1
    return sum(n for n in counts.values() if n > 1)


def level_suffix(level: int) -> str:
    return f"_L{level}" if level >= 0 else ""


def tables(data: GameData) -> list[Table]:
    """Every table the ids package covers, named from ``data``."""
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
            [(to_snake(u.unit_type) + level_suffix(u.level), u.wod_id, str(u.wod_id)) for u in data.units.values()],
        ),
        Table(
            "tools",
            "Tool",
            "T",
            "Tool ``wodID`` values from the ``units`` table (rows with ``slotTypes``).",
            "``ToolUnitVO.parseXmlNode`` (bundle line 6538)",
            [(to_snake(t.tool_type) + level_suffix(t.level), t.wod_id, str(t.wod_id)) for t in data.tools.values()],
        ),
        Table(
            "effects",
            "Effect",
            "E",
            "Effect ids from the ``effects`` table.",
            "``EffectVO.parseXML`` (bundle line 41702)",
            [(to_snake(e.name), e.effect_id, str(e.effect_id)) for e in data.effects.values()],
        ),
        Table(
            "effect_types",
            "EffectType",
            "E",
            "Effect type ids from the ``effecttypes`` table.",
            "``CastleEffectTypeVO`` (bundle line 111835)",
            [(to_snake(t.name), t.effect_type_id, str(t.effect_type_id)) for t in data.effect_types.values()],
        ),
        Table(
            "currencies",
            "Currency",
            "C",
            "Currency keys from the ``currencies`` table, the key the server uses; coins and rubies are not in it.",
            "``CurrencyData.getXmlCurrencyByKey`` (bundle line 141194)",
            [(key, row.json_key, str(row.currency_id)) for key, row in currencies],
            str_enum=True,
        ),
        Table(
            "currencies",
            "CurrencyId",
            "C",
            "Currency ids from the ``currencies`` table, as other tables reference them; names match ``Currency``.",
            "``XmlCurrencyVO.parseXml`` (bundle line 141282)",
            [(key, row.currency_id, str(row.currency_id)) for key, row in currencies],
        ),
        Table(
            "generals",
            "General",
            "G",
            "General ids from the ``generals`` table.",
            "``GeneralXmlVO.fillFromParamXml`` (bundle line 33102)",
            [(to_snake(g.name), g.general_id, str(g.general_id)) for g in data.generals.values()],
        ),
        Table(
            "general_abilities",
            "GeneralAbility",
            "A",
            "General ability ids from the ``generalAbilities`` table, one per level.",
            "``GeneralAbilityXmlVO.fillFromParamXml`` (bundle line 113203)",
            [
                (to_snake(a.name) + level_suffix(a.level), a.ability_id, str(a.ability_id))
                for a in data.general_abilities.values()
            ],
        ),
        Table(
            "general_skills",
            "GeneralSkill",
            "S",
            "General skill ids from the ``generalSkills`` table, named general, skill and level.",
            "``GeneralSkillVO.parseXML`` (bundle line 113363)",
            [
                (f"{general_of(s.general_id)}_{to_snake(s.name)}{level_suffix(s.level)}", s.skill_id, str(s.skill_id))
                for s in data.general_skills.values()
            ],
        ),
        Table(
            "legend_skills",
            "LegendSkill",
            "L",
            "Legend skill ids from the ``legendskills`` table, named effect type, tree, group and level.",
            "``CastleLegendSkillVO.parseXML`` (bundle line 48652)",
            [
                (
                    f"{to_snake(s.effect_type)}_T{s.skill_tree_id}_G{s.skill_group_id}{level_suffix(s.level)}",
                    s.skill_id,
                    str(s.skill_id),
                )
                for s in data.legend_skills.values()
            ],
        ),
        Table(
            "raid_bosses",
            "RaidBoss",
            "R",
            "Alliance raid boss ids from the ``raidBosses`` table.",
            "``AllianceRaidbossVO.parseXML`` (bundle line 113835)",
            [(to_snake(b.name), b.raid_boss_id, str(b.raid_boss_id)) for b in data.raid_bosses.values()],
        ),
        Table(
            "global_effects",
            "GlobalEffect",
            "G",
            "Global effect ids from the ``globalEffects`` table.",
            "``GlobalEffectVO.parseXml`` (bundle line 143690)",
            [(to_snake(g.name), g.global_effect_id, str(g.global_effect_id)) for g in data.global_effects.values()],
        ),
    ]


def header(version: str) -> str:
    return f"# Generated by {SCRIPT} from items {version}; do not edit.\n"


def docstring(table: Table) -> list[str]:
    return ['    """', f"    {table.doc}", "", f"    Client: {table.client}", '    """']


def render_module(version: str, enums: Iterable[tuple[Table, list[tuple[str, int | str]]]]) -> str:
    enums = list(enums)
    bases = {"Enum" if t.str_enum else "IntEnum" for t, _ in enums}
    out = [header(version), f"from enum import {', '.join(sorted(bases))}"]
    for table, named in enums:
        base = "str, Enum" if table.str_enum else "IntEnum"
        out += ["", "", f"class {table.enum}({base}):"]
        out += docstring(table)
        if named:
            out.append("")
        for name, value in named:
            out.append(f"    {name} = {json.dumps(value)}")
    return "\n".join(out) + "\n"


INIT_DOC = """\
Game-data ids as enums, so they autocomplete.

One enum per items table, each member named from the row in UPPER_SNAKE;
where two rows would share a name, both carry their id (``SPEED_BOOST_2``).
``ITEMS_VERSION`` is the items version they were generated from, and
:func:`is_current` says whether a loaded :class:`GameData` is that version. For
anything newer, use the named lookups on :class:`GameData`.

Gems, equipment and horses have no enum, as their rows have no name; look them
up by id with ``GameData.gems``, ``GameData.equipment_effects`` and
``GameData.get_horse``.

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
    args = parser.parse_args(argv)

    if args.items:
        payload = json.loads(args.items.read_text())
        data = GameData.parse(items_version(args.items, payload), payload)
    else:
        data = GameData.load(refresh=True)

    empty = [t.enum for t in tables(data) if not t.rows]
    if empty:
        raise SystemExit(f"no rows for {', '.join(empty)}; is this the full items file?")
    files = render(data)
    write(files, args.out)
    for t in tables(data):
        print(f"{t.enum}: {len(t.rows)} members, {collided(t)} with an id suffix", file=sys.stderr)
    print(f"Wrote {len(files)} files for items {data.version} to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
