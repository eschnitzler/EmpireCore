---
description: The game's own texts, in any language, from its language file.
---

# Game texts

Every string the game shows (error messages, names, descriptions) is in its
language file, about 30k texts per language. `empire_core.texts` reads it the
way the client does.

```python
from empire_core.texts import cached_text, get_texts, text

text("errorCode_120")                         # "This player's level is too low."
text("travelSpeedBonusPerField", 5, 10)       # "+5% for every 10 fields"
text("currency_name_1MinSkip", lang="de")     # in German
text("no_such_key")                           # "no_such_key"
```

- Keys are not case sensitive.
- A key with no text reads as the key itself, as in the game.
- `get_texts(lang)` gives the whole file as a mapping of lower-cased keys.

## Arguments and numbers

`{0}`, `{1}`, ... are filled with the arguments in order, the way the game
fills them:

- A number is written for the language: grouped by thousands, at most two
  fraction digits (a half rounds up), and from 100,000 on abbreviated with
  the language's own `k` and `M`.
- A string that is a text id goes in as that text; any other string as it is.
- `True` and `None` count as the numbers 1 and 0, as in JavaScript.

```python
from empire_core.texts import LocalizedNumber, fill, number, text

text("travelSpeedBonusPerField", 1234.567, 150000)   # "+1,234.57% for every 150k fields"
text("travelSpeedBonusPerField", 1234, 5, grouping=False)  # "+1234% for every 5 fields"
text("travelSpeedBonusPerField", LocalizedNumber(250000), 5)  # "+250,000% ...": not abbreviated

number(1500000, compact=True)                 # "1.5M"
number(1234.5, lang="de")                     # "1.234,5"
fill("{0} of {1}", 1234567, "dialog_ok")      # "1234567 of dialog_ok": plain, as written
```

`LocalizedNumber` sets how one argument is written: abbreviated or not, how
many fraction digits (none unless you say), and `right_to_left` for a space
before the `k`; `number()` takes the same. `fill()` is the plain filling,
without any of this.
Only English and German number symbols are known; other languages write
numbers as English does. Right-to-left languages are not reordered.

## When it downloads

Nothing downloads until you ask for a text. The first `text()` or
`get_texts()` in a language fetches that language's file and keeps it for 24
hours. When the CDN is down, texts read as their keys (or the copy already
fetched) and the CDN is left alone for five minutes. `cached_text()` only
reads what is already loaded and returns `None` otherwise, so it never waits.

## Error messages

A `CommandError` or `LoginError` carries the game's message for its code once
the texts are loaded; raising one never downloads anything.

```python
from empire_core import CommandError
from empire_core.texts import get_texts

get_texts("en")                               # load once, e.g. at start-up

try:
    client.castle.get_all()
except CommandError as e:
    print(e)                                  # ...for command 'gcl': An error has occurred, ...
    e.game_message("de")                      # None until get_texts("de")
```

Event titles come from the same file; see [Events](events.md).

## Display names

The [game-data id enums](game-data-ids.md) whose rows the game names by a
text have `display_name(lang="en")`: units, tools, currencies, researches,
generals, legend and sceat skills, events, gems, achievements, titles,
alliance crest layouts and main quests. Each member's `text_id` is the text
id the game reads for it, so `cached_text(member.text_id)` is the variant
that never downloads. Not every event and general has a text: theirs is
`None` where the language file has none.

```python
from empire_core.enums import AllianceRank, Kingdom
from empire_core.gamedata import Currency, Event, Gem, Research, Unit
from empire_core.texts import cached_text, text

Unit.MEAD_RANGER_L6.display_name()            # "Valkyrie ranger": the type's name, without the level
Currency.SKIP_5_MINUTES.display_name("de")    # in German
Gem.GEM_OF_THE_RESERVES_L6.display_name()     # "Gem of the reserves: 6"
Research.BEEFSTORAGE_G193_L1.display_name()   # "Premium beef storage build item blueprint"
Research.DRAGON_CHARM_G175_L1.display_name()  # None: a crafting recipe research's name holds
                                              # its recipe's output, which is not done here
Event.NOMAD_INVASION.text_id                  # "event_title_5"; display_name() is None, as
                                              # the English file has no such text
cached_text(Unit.MEAD_RANGER_L6.text_id)      # None until the English texts are loaded

text(Kingdom.SANDS.text_id)                   # "The Burning Sands"
text(AllianceRank.COLEADER.text_id)           # "Deputy"
```

`Kingdom` and `AllianceRank` live with the other hand-written enums, which
import nothing, so they carry only their `text_id`: read it with `text()`.

Where the generator names members from the English text (currencies,
researches with a title, gems, sceat skills, achievements, titles, crest
layouts, main quests), it reads the same text id, so the member's name and
its English display name agree. The other enums are named from the items
file's codes, which can differ from what the game shows: `Unit.MEAD_RANGER_L6`
is a "Valkyrie ranger".

## Effect descriptions

`describe_effect()` writes one bonus with its value the way the game's
tooltips do, and `describe_effects()` a list of them. They need a loaded
[`GameData`](game-data.md) to know what the effect is and how its value reads
(one number, a value per unit, a list of unlocked ids, ...).
`describe_construction_item()` writes a construction item's whole tooltip:
the fixed bonuses in columns of its own (`castle_effects`) first, then its
`effects`. `describe_building()` writes a decoration's effects, each with its
cap.

```python
from empire_core.gamedata import (
    EffectTemplate,
    GameData,
    describe_building,
    describe_construction_item,
    describe_effect,
)

game_data = GameData.load()
describe_construction_item(game_data.construction_items[1], game_data)  # "-2% recruitment costs"

gem = game_data.gems[55]
describe_effect(gem.effects[0], game_data, EffectTemplate.EQUIPMENT, trigger_chance=gem.trigger_chance)
# "30% chance of 13% more glory when defending an attack"
```

The template says where the description is shown: `CONSTRUCTION_ITEM`
(`ci_effect_<name>`, the default), `BUILDING` (`effect_name_<name>`, with
the effect's cap where it has one) or
`EQUIPMENT` (`equip_effect_description_<name>`, also for gems; an equipment
item's bonus, an `EquipmentEffectValue`, always reads this way). A gem that
does not always trigger reads its chance first, as in the game.
