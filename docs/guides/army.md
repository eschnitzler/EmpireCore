---
description: Units, recruitment, production lists and the hospital.
---

# Army

Every `client.army` call joins its castle first, so you never need to select
one yourself; production and hospital commands then act on that castle. The
castle's kingdom comes from your castle list, so a castle that is not yours
raises `UnknownCastleError`.

## Units

```python
from empire_core.gamedata import Unit

units = client.army.get_units(castle_id=12345)     # {Unit or Tool: amount}
for unit, amount in units.items():
    print(unit, amount)
print(units.get(Unit.PEASANT, 0))
```

`get_units` covers the soldiers and tools at home. Units in production, in the
stronghold or in the hospital are reported separately by
`get_units_response(castle_id)`, as `in_production`, `stronghold` and
`hospital`, each the same `{Unit or Tool: amount}` mapping. `dismiss_units` dismisses units of the castle
or of its stronghold.

`store_in_stronghold(castle_id, unit, amount)` hides soldiers in the stronghold and
`take_from_stronghold` brings them back; both return the castle's inventories after the move.

## Recruitment

```python
from empire_core.army import ProductionListId, SlotType, Unit

client.army.produce_units(12345, ProductionListId.SOLDIERS, wod_id=Unit.SWORDMAN, amount=50)

production = client.army.get_production_list(12345, ProductionListId.SOLDIERS)
for slot in production.queue:
    print(slot.position, slot.wod_id, slot.amount)

client.army.cancel_production(
    12345, ProductionListId.SOLDIERS, SlotType.QUEUE, position=0
)
```

`move_production_slot(castle_id, list_id, old_position, new_position)` reorders the queue by
`ProductionSlot.position`, and `set_recruitment_mode` picks whether a list finishes its first
stack first or all stacks equally (`RecruitmentMode`).

`double_production_slot` doubles a slot's units, for rubies. A unit with a ruby
price, and paying missing resources with rubies, need `spend_rubies=True`; see
[Spending rubies](index.md#spending-rubies). `skip_production_slot` finishes a slot now, also for
rubies; the client keeps that button for an A/B test group, so the server may refuse it.

### Loops and copies

```python
targets = client.army.get_recruitment_copy_targets(12345, ProductionListId.SOLDIERS)
picked = [target for target in targets if target.can_copy]
client.army.copy_recruitment(12345, ProductionListId.SOLDIERS, picked, spend_rubies=True)
```

`get_recruitment_copy_targets` lists your other castles with what a copy of the queue costs
there; `copy_recruitment` copies it, and needs `spend_rubies=True` when a target's
`doubling_ruby_cost` is above 0. `start_recruitment_loop(castle_id, list_id, loops,
spend_rubies=True)` repeats the queue, always for rubies. Both raise
`ProductionSlotsNeededError`, with `missing_slots`, when the list needs more unlocked slots.

`get_camp_unit_capacity(camp_id)` gives how many more soldiers a faction kingdom camp takes,
yours or one you send support to.

## The hospital

```python
hospital = client.army.get_production_list(12345, ProductionListId.HOSPITAL)
for slot in hospital.hospital_slots:
    print(slot.position)

client.army.heal_units(12345, wod_id=Unit.SWORDMAN, amount=10)
client.army.cancel_heal(12345, position=hospital.hospital_slots[0].position)
```

`heal_all` and `skip_heal` finish healing for rubies, and `heal_units` heals a
unit that costs rubies to heal, only with `spend_rubies=True`; `dismiss_wounded` and
`dismiss_wounded_units` give wounded units up instead of healing them.
`get_hospital_flags` and `set_hospital_flags(castle_id, admit_ruby_units=...)` read and set
whether the hospital admits wounded ruby units.

!!! tip "Unit ids"

    Unit and tool ids (`wod_id`) change between client releases. Look them up
    by name with [game data](game-data.md), or use the generated
    [`Unit`](game-data-ids.md) enum.

**API:** [`ArmyService`](../reference/army.md#empire_core.army.service.ArmyService)
