---
description: Sending an attack with waves you build yourself, and attack presets.
---

# Attack

`client.attack.send_attack` sends an attack from a castle to a map position.
This page builds the waves by hand; [Filling waves](filling-waves.md) has the
library fill them the way the game's own button does.

```python
from empire_core import AttackWave, WaveFlank
from empire_core.gamedata import Tool, Unit

commanders = client.commanders.get_commanders()

accepted = client.attack.send_attack(
    source_x=500,
    source_y=510,
    target_x=700,
    target_y=710,
    waves=[
        AttackWave(
            left=WaveFlank(units={Unit.SWORDMAN: 100}, tools={Tool.RAM: 5})
        )
    ],
    commander_id=commanders[0].commander_id,
)
```

An `AttackWave` has a `left`, `middle` and `right` flank, and each
`WaveFlank` holds its `units` and `tools` slots as `WodAmount` pairs, one per
slot in order. Pass a mapping (`units={Unit.SWORDMAN: 100}`) and each entry
becomes a slot; an empty slot is `EMPTY_SLOT` (`[-1, 0]` on the wire). To
assign slots to an existing flank, `WodAmount.slots({...})` builds them. Waves
go front to back.

The courtyard wave, the support tools and collector boosters read the same
way: `yard_wave={Unit.SWORDMAN: 300}`, `support_tools=(Tool.X, None, None)`
with None for an empty slot, `collector_booster={CurrencyId.SAMURAI_MEDAL_BOOSTER: 5}`.

The attack is sent in the kingdom of your area at the source position, looked
up in your castle list; pass `kingdom_id` to name it yourself. With no area of
yours there it raises `UnknownCastleError`, and with areas of yours at that
position in several kingdoms, `AmbiguousCastleError`.

## The commander

`commander_id` is required. Every id `get_commanders()` returns leads an
attack, `0` included, so there is no value that means "no commander". The
server echoes the chosen one back in its reply (`CreateAttackResponse.leader`).
`-14` with `use_premium_commander=True` leads with the premium commander, which
uses one of your free premium commanders or costs rubies. Where it may cost
rubies `send_attack` raises `PremiumCommanderCostError` unless you pass
`spend_rubies=True`; see [the premium commander](commanders.md#the-premium-commander).
A conquer attack is checked the same way, although the game client sends most
of them without the premium commander's rubies: the guide there has the gap.

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

With a spy report on the target, `info.spy_army` holds its defenders by
position, None without a report. Each position is a tuple of `WodAmount`
stacks in the order the report lists them. `SpyArmySection` names the
positions and iterates in wire order:

```python
from empire_core.army import SpyArmySection

army = info.spy_army
if army is not None:
    for unit, amount in army.section(SpyArmySection.KEEP):
        print(unit, amount)
    print(army.wall_total(), [section.value for section in SpyArmySection if section.is_wall])
```

## Presets

The game's attack presets are saved armies, one per slot. `get_presets()`
lists your unlocked slots; `save_preset` stores a wave in one and
`rename_preset` names it:

```python
for preset in client.attack.get_presets():
    army = preset.army()               # PresetArmy, or None for an empty slot
    print(preset.index, preset.name, army.to_wave() if army else None)

client.attack.save_preset(0, AttackWave(left=WaveFlank(units={Unit.SWORDMAN: 100})))
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
