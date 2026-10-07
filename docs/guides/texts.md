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

- Keys are not case sensitive, and `{0}`, `{1}`, ... are filled with the
  arguments in order, as plain strings.
- A key with no text reads as the key itself, as in the game.
- `get_texts(lang)` gives the whole file as a mapping of lower-cased keys.

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
    print(e)                                  # ...for command 'gaa': This player's level is too low.
    e.game_message("de")                      # None until get_texts("de")
```

Event titles come from the same file; see [Events](events.md).
