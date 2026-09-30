---
description: Game-data ids as generated enums, for autocomplete, and how they are kept current.
---

# Generated ids

For autocomplete, the ids of one items version are also generated as enums:

```python
from empire_core.gamedata import Currency, General, GeneralSkill, Unit

General.TORIL                        # 101
Currency.GXP1                        # "GXP1", the key the server uses
Unit.MEAD_RANGER_L6                  # 211: type plus level
GeneralSkill.TORIL_ASPECTOFTHE_DRAGON_L1
```

Units, tools, effects, effect types, currencies (`Currency` by key,
`CurrencyId` by id), generals, general abilities and skills, legend skills,
raid bosses, global effects, buildings, researches, construction items,
events, loot boxes, equipment groups and event difficulty types each have one.

## Names

Member names come from the row, in `UPPER_SNAKE`. Research names start with the
items file's own note, which is partly German, and end in group and level
(`Research.RECRUITMENT_SPEED_G41_L1`), which keep them unique. Where two rows
would get the same name, both carry their id (`GlobalEffect.SPEED_BOOST_2`,
`GlobalEffect.SPEED_BOOST_11`).

## Members are plain values

Members are plain ints (`Currency` members plain strs), so they go straight
into requests. Most also carry their row's fixed id and number columns, to
filter on without loading any game data:

```python
from empire_core.gamedata import General, Tool, Unit

Unit.MEAD_RANGER_L6.role             # "ranged"; also .level
General.TORIL.rarity_id              # 4
[t for t in Tool if t.category == "Defence"]
```

Stats and costs are not baked in, as balance patches change them, and nothing
here downloads the game data. For the full row, ask a loaded `GameData`; see
[Full rows for generated ids](game-data.md#full-rows-for-generated-ids).

## Keeping them current

`ITEMS_VERSION` is the items version the enums came from, and
`is_current(game_data)` says whether loaded data matches it; `GameData.load()`
logs a warning when it does not. Ids added since are not in the enums, but the
[lookups by name](game-data.md) cover them.

To regenerate from a checkout after a client update:

```bash
# downloads the current items
uv run python scripts/generate_gamedata_ids.py
uv run python scripts/generate_gamedata_ids.py --items items_v786.03.json
# exits 1 if the ids are out of date
uv run python scripts/generate_gamedata_ids.py --check
```

A weekly workflow compares the live items version with `ITEMS_VERSION` and,
when they differ, opens a pull request with the regenerated ids, listing every
member renamed, removed or added. `--diff-names names.md` writes the same list
locally.

**API:** [Generated ids](../reference/gamedata.md#generated-ids)
