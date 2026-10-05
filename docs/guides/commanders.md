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
returns the whole reply when you want both at once. Both are in the game's
order: commanders by id, castellans by portrait.

The login data already carries the list, and state keeps the last one any
reply brought (a rename, a general assignment, an attack info reply, ...), so
reading it costs no request:

```python
roster = client.state.get_commanders()   # None before the login data
if roster is not None:
    print(len(roster.commanders), len(roster.castellans))
```

## Rename

```python
client.commanders.rename(castellans[0].commander_id, "farm-1")
```

`rename` takes either kind, and its reply carries the updated list.

## The premium commander

`PREMIUM_COMMANDER_ID` (`-14`) is the premium commander, which the game offers
from level 10. Leading with it is free while your VIP level gives free premium
commanders that you have not used today, or while a premium account runs.
Otherwise it costs rubies, and the game asks first.

```python
from empire_core.commanders import PREMIUM_COMMANDER_ID

client.load_game_data()                          # the VIP levels come from the items payload
print(client.commanders.free_premium_commanders())  # None before the login data
if client.commanders.premium_commander_is_free():
    client.castle.send_support(
        source_castle_id, target_x, target_y, units=[[620, 50]],
        commander_id=PREMIUM_COMMANDER_ID, use_premium_commander=True,
    )
```

The count comes from state: your VIP points, VIP time and the premium
commanders used today arrive in the login data's `vip` and in every `vip` the
server pushes. `free_premium_commanders` needs the game data only while VIP
time runs. The server sends no `vip` with a send's reply, so the library
counts its own accepted premium sends (without a premium account) as used
until the next `vip` arrives; that is the library's choice, not something the
game client does.

`send_support`, `send_troops` and `send_attack` never spend rubies on the
premium commander unless you pass `spend_rubies=True`. Led by it
(`use_premium_commander=True` or `commander_id=PREMIUM_COMMANDER_ID`) when it
is not free, or when that is not known yet, they raise
`PremiumCommanderCostError` and send nothing. The check and the send hold one
lock, so two premium sends at once cannot both take the last free one.

One known gap: for a conquer attack (`attack_type=AttackType.CONQUER`) the
game client sends `BPC` 0 without asking for rubies, whichever commander
leads, unless the target is a capital, village, kings tower, resource isle,
monument or laboratory. `send_attack` does not know the target's area type, so
it checks such an attack like any other; pass `use_premium_commander=False`
and `spend_rubies=True` to send what the client sends there.

## Related

- [Skills and generals](skills.md): a general is assigned *to* a commander.
- [Equipment](equipment.md): putting items on commanders and castellans.
- [Attack](attack.md): every attack is led by a commander.

**API:** [`CommandersService`](../reference/commanders.md#empire_core.commanders.service.CommandersService),
[`Commander`](../reference/commanders.md#empire_core.commanders.models.roster.Commander)
