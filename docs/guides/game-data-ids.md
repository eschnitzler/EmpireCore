---
description: Game-data ids as generated enums, for autocomplete, and how they are kept current.
---

# Generated ids

For autocomplete, the ids of one items version are also generated as enums:

```python
from empire_core.gamedata import Currency, General, GeneralSkill, Unit

General.TORIL                        # 101
Currency.SKIP_5_MINUTES              # "MS2", the key the server uses
Unit.MEAD_RANGER_L6                  # 211: type plus level
GeneralSkill.TORIL_ASPECTOFTHE_DRAGON_L1
```

Units, tools, effects, effect types, currencies (`Currency` by key,
`CurrencyId` by id), generals, general abilities and skills, legend skills,
raid bosses, global effects, buildings, researches, construction items,
events, loot boxes and their types, equipment groups, event difficulty types,
quests (`QuestId`), daily quests (`DailyQuestId`), main quests (`MainQuest`),
gems, sceat skills, achievements, horses, titles and alliance crest layouts and
colours each have one. The 27,000 rewards have none: the game shows no text
for a reward, and the notes some rows carry name where it is given, not the
reward. Reward ids stay ints; the game reads each as the collectables it holds.

## Names

Member names come from the row, in `UPPER_SNAKE`. Where the row only has a
code, the name is the game's English text for it, the one the game shows:
currencies are named from their name (`Currency.SKIP_5_MINUTES` for `MS2`,
`Currency.FAST_TRAVEL_FEATHERS` for `PTT`), researches from their title and level
(`Research.STRENGTH_TRAINING_L1`). A row the game has no text of its own for
keeps its code (`Currency.DC1` to `DC80`, the decoration catalysts, share one
name), and a blueprint or recipe research keeps the items file's note, group
and level (`Research.BEEFSTORAGE_G193_L1`). Where two rows
would get the same name, both carry their id (`GlobalEffect.SPEED_BOOST_2`,
`GlobalEffect.SPEED_BOOST_11`). Quests are named after what their first
condition counts, so most carry their id (`QuestId.BUILDINGS_44`).

Tables whose rows have no name column are named from the text the game shows
for them: gems (`Gem.GEM_OF_THE_GLORIOUS_DEFENDER_L6`, a unique one by its own
name), sceat skills, achievements (the series' name, the step as its level),
titles (`Title.KNIGHT`), crest layouts and main quests. Where the game has no
text, a designer note names the row (`Horse.WARHORSE_STABLE1`, as the game
names a horse only by its place in the travel dialog;
`AllianceCrestLayout.FREE_1`), and a crest colour, which has neither, is named
by its id and carries its hex colour (`AllianceCrestColor.COLOR_1.color`).

Enums the game names by a text give that name at run time, in any language:
`Currency.SKIP_5_MINUTES.display_name("de")`, with its text id as `.text_id`.
A member named from the English text has the same name in English; one named
from the items file's code may not (`Unit.MEAD_RANGER_L6` is a "Valkyrie
ranger"). See [Game texts](texts.md#display-names).

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
here downloads the game data. For the full row, index a loaded `GameData`
table with the member; see [Game data](game-data.md).

## Ids in models

Models type the ids they read with these enums, leniently: a field typed
`EnumOrInt[Kingdom]` holds the member for an id the enum has, and the plain int
for one it lacks (a client release newer than the enums), with a warning logged
once per id, so a packet never fails over it. `EnumOrStr[Currency]` does the
same for keys. Name a generated enum by its name in quotes
(`EnumOrInt["QuestId"]`) to load its module only when a value arrives.

Rewards, costs and goods are `Collectable`s: the `kind` (a `CollectableKind`),
the `amount`, and the `item` the entry names, typed for the kinds that name one
(a `Unit` or `Tool` for units, a `Currency`, a `BoosterId`, a `LootBox`, ...):

```python
from empire_core.gamedata import Collectable

rewards = Collectable.from_object({"U": [[664, 5]], "MS2": [1], "C1": [2000]})
[(reward.kind, reward.item, reward.amount) for reward in rewards]
# [(CollectableKind.UNITS, Unit.KINGSCROSSBOWMAN, 5),
#  (CollectableKind.CURRENCY, Currency.SKIP_5_MINUTES, 1), (CollectableKind.COINS, None, 2000)]
```

An entry under a key the client has no type for is kept as
`CollectableKind.OTHER`, with its `key` and the entry as sent in `value`.

Packets read into the same type: a movement's `goods` and a travel
movement's loot, a battle report participant's `loot`, a spy report's
`resources`, the time skip a battle found and what an auto-skip cost
(`auto_skip_paid`) or refunded (`auto_skip_refunded`). So do the items'
rewards, through `GameData.reward_list`.

## Keeping them current

`ITEMS_VERSION` is the items version the enums came from, and
`is_current(game_data)` says whether loaded data matches it; `GameData.load()`
logs a warning when it does not. Ids added since are not in the enums, but the
[lookups by name](game-data.md#lookups-by-name) cover them.

To regenerate from a checkout after a client update:

```bash
# downloads the current items and English texts
uv run python scripts/generate_gamedata_ids.py
# offline, with the texts the committed names came from
uv run python scripts/generate_gamedata_ids.py --items items_v786.03.json --texts scripts/gamedata_ids_texts.json
# exits 1 if the ids are out of date with the live texts (downloads them)
uv run python scripts/generate_gamedata_ids.py --check
# the same against the committed texts, offline for the texts
uv run python scripts/generate_gamedata_ids.py --check --texts scripts/gamedata_ids_texts.json
```

The names come from the game's [texts](texts.md), but the generator keeps only
the texts it used, in `scripts/gamedata_ids_texts.json`, next to it. A weekly
workflow regenerates the ids from the live items and texts and, when the ids
or those texts changed, opens a pull request with them, listing every member
renamed, removed or added. `--diff-names names.md` writes the same list
locally.

**API:** [Generated ids](../reference/gamedata.md#generated-ids)
