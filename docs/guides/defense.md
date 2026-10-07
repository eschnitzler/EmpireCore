---
description: Reading and setting a castle's keep, wall and moat defense.
---

# Defense

## Reading a castle's defense

`client.defense.get_own_defense(castle_x, castle_y, castle_id)` reads the
keep, wall and moat setup of one of your castles, with its units, unit
priorities and castellan:

```python
castle = client.state.get_castles()[0]
defense = client.defense.get_own_defense(castle.x, castle.y, castle.id)

print(defense.keep.slots)            # (WodAmount(item=..., amount=...), ...), one per slot
print(defense.wall.left.unit_percent)
print(defense.moat.middle_slots)
print(defense.inventory())           # {Unit or Tool: amount}
```

## Changing it

The setters take the keep, wall and moat the way `get_own_defense` returns
them, so read the setup, change what you want and send it back. Each returns
the setup the server stored:

```python
from empire_core.gamedata import Tool, WodAmount

keep = defense.keep
keep.slots = (WodAmount(Tool.ELITESHIELDS, 20), *keep.slots[1:])   # the first keep slot
client.defense.set_keep(castle.x, castle.y, castle.id, keep)

wall = defense.wall
wall.left.unit_percent, wall.middle.unit_percent, wall.right.unit_percent = 30, 40, 30
client.defense.set_wall(castle.x, castle.y, castle.id, wall)

client.defense.set_moat(castle.x, castle.y, castle.id, defense.moat)
```

Each slot list is a tuple of `WodAmount` pairs in the order the reply sent
them, empty ones too: the game reads a slot by its position. An empty slot is
`WodAmount(None, 0)` (`EMPTY_SLOT`), sent back as `[-1, 0]`; a pair unpacks
as `tool, amount = slot`. The wall's unit percents are
whole numbers, as the game's slider sends them. The library checks neither
the tools against your inventory nor the slots against the castle's level;
that is left to the server.

## A castle you could support

`client.defense.get_support_defense_info(target_x, target_y)` reads the
defense of an alliance member's castle, as the game does before you send
support. The server refuses your own castle with `NO_SELF_DESTRUCTION` (92).

**API:** [`DefenseService`](../reference/defense.md#empire_core.defense.service.DefenseService),
[`GetDefenseResponse`](../reference/defense.md#empire_core.defense.models.GetDefenseResponse)
