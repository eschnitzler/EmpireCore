---
description: Commanders and castellans, their equipment, and renaming them.
---

# Commanders

A **commander** leads an army out of the castle; a **castellan** defends one.
The server knows both as "lords" (command `gli`, field `LID`); the game's
interface and this library call them commanders and castellans.

```python
for commander in client.commanders.get_commanders():
    print(commander.commander_id, commander.name, commander.wins, commander.defeats)
    for item in commander.equipment:
        print("  ", item.equipment_id, item.slot, item.enchantment_level)

castellans = client.commanders.get_castellans()
```

Both lists come back from the same request; `client.commanders.get_all()`
returns the whole reply when you want both at once.

## Rename

```python
client.commanders.rename(castellans[0].commander_id, "farm-1")
```

`rename` takes either kind, and its reply carries the updated list.

## Related

- [Skills and generals](skills.md): a general is assigned *to* a commander.
- [Equipment](equipment.md): putting items on commanders and castellans.
- [Attack](attack.md): every attack is led by a commander.

**API:** [`CommandersService`](../reference/commanders.md#empire_core.commanders.service.CommandersService),
[`Commander`](../reference/commanders.md#empire_core.commanders.models.roster.Commander)
