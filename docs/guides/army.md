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

## Recruitment

```python
from empire_core.army import ProductionListId, SlotType

client.army.produce_units(12345, ProductionListId.SOLDIERS, wod_id=620, amount=50)

production = client.army.get_production_list(12345, ProductionListId.SOLDIERS)
for slot in production.queue:
    print(slot.position, slot.wod_id, slot.amount)

client.army.cancel_production(
    12345, ProductionListId.SOLDIERS, SlotType.QUEUE, position=0
)
```

`double_production_slot` doubles a slot's units, for rubies. A unit with a ruby
price, and paying missing resources with rubies, need `spend_rubies=True`; see
[Spending rubies](index.md#spending-rubies).

## The hospital

```python
hospital = client.army.get_production_list(12345, ProductionListId.HOSPITAL)
for slot in hospital.hospital_slots:
    print(slot.position)

client.army.heal_units(12345, wod_id=620, amount=10)
client.army.cancel_heal(12345, position=hospital.hospital_slots[0].position)
```

`heal_all` and `skip_heal` finish healing for rubies, and `heal_units` heals a
unit that costs rubies to heal, only with `spend_rubies=True`; `dismiss_wounded` and
`dismiss_wounded_units` give wounded units up instead of healing them.

!!! tip "Unit ids"

    Unit and tool ids (`wod_id`) change between client releases. Look them up
    by name with [game data](game-data.md), or use the generated
    [`Unit`](game-data-ids.md) enum.

**API:** [`ArmyService`](../reference/army.md#empire_core.army.service.ArmyService)
