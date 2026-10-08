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
