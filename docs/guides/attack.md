---
description: Sending an attack with waves you build yourself, and attack presets.
---

# Attack

`client.attack.send_attack` sends an attack from a castle to a map position.
This page builds the waves by hand; [Filling waves](filling-waves.md) has the
library fill them the way the game's own button does.

```python
from empire_core import AttackWave, WaveFlank

commanders = client.commanders.get_commanders()

accepted = client.attack.send_attack(
    source_x=500,
    source_y=510,
    target_x=700,
    target_y=710,
    waves=[AttackWave(left=WaveFlank(units=[[487, 100]], tools=[[301, 5]]))],
    commander_id=commanders[0].commander_id,
)
```

An `AttackWave` has a `left`, `middle` and `right` flank, and each
`WaveFlank` holds `units` and `tools` as `[wod_id, amount]` pairs. The wire
keys (`L`, `M`, `R`, `U`, `T`) are accepted as well. Waves go front to back.

The attack is sent in the kingdom of your area at the source position, looked
up in your castle list; pass `kingdom_id` to name it yourself. With no area of
yours there it raises `UnknownCastleError`, and with areas of yours at that
position in several kingdoms, `AmbiguousCastleError`.

## The commander

`commander_id` is required. Every id `get_commanders()` returns leads an
attack, `0` included, so there is no value that means "no commander". The
server echoes the chosen one back in its reply (`CreateAttackResponse.leader`).
`-14` with `use_premium_commander=True` leads with the premium commander, which
uses one of your premium commanders or costs rubies.

## What the client checks, and so does the library

- Waves without units are dropped before sending, as the game client does.
  If no wave carries any, `send_attack` raises `ValueError`.
- `feathers=True` forces the horse field to -1, exactly as the client does.
- With one of your attacks already on its way to the same target,
  `send_attack` raises `AttackInProgressError`, carrying that attack's arrival
  time and size. Pass `send_anyway=True` to send regardless, as the client's
  confirmation dialog does.
- Given `min_soldiers` or a `capacity`, it raises `AttackBelowMinimumError`
  before sending an attack below the minimum the client requires; see
  [the minimum](filling-waves.md#the-minimum).

`send_attack` returns `True` when the server accepts the attack and `False`
when it refuses it, for example with `MOVEMENT_HAS_NO_UNITS` (100).

## Before you attack

`client.attack.get_attack_info(target_x, target_y, source_x, source_y)` asks
for the pre-calculation the game's attack dialog asks for: the target's map
row, your inventory and commanders, and your effects scoped to this target.
Pass the target's `area_type` so the right command is asked, as the client
picks it.

## Presets

The game's attack presets are saved armies, one per slot. `get_presets()`
lists your unlocked slots; `save_preset` stores a wave in one and
`rename_preset` names it:

```python
for preset in client.attack.get_presets():
    army = preset.army()               # PresetArmy, or None for an empty slot
    print(preset.index, preset.name, army.to_wave() if army else None)

client.attack.save_preset(0, AttackWave(left=WaveFlank(units=[[487, 100]])))
client.attack.rename_preset(0, "Farm")
```

A wave is saved the way the game saves one: its filled slots, without support
tools. A preset name is at most 15 characters and none of the characters the
game refuses in names (`SMARTFOX_INVALID_CHARS`); `rename_preset` raises
`ValueError` for any other, as the game's rename dialog refuses it. Both
return `True` when the server accepts and `False` when it refuses. The game
saves only into unlocked slots.

Unlocking a slot is left out: every slot after the first costs rubies, from
2,200 for the second to 72,000 for the thirtieth.

## Runnable example

This script lists your commanders and prints the attack it would send; it
only sends with `--send`:

```python title="examples/commanders_and_attack.py"
--8<-- "examples/commanders_and_attack.py"
```

**API:** [`AttackService`](../reference/attack.md#empire_core.attack.service.AttackService)
