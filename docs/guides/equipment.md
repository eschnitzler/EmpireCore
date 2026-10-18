---
description: The equipment inventory, putting items on and off commanders and castellans, selling, gems and auto-sell.
---

# Equipment

`client.equipment.get_inventory()` lists the items no commander or castellan is
wearing:

```python
inventory = client.equipment.get_inventory()
for item in inventory:
    print(item.equipment_id, item.slot, item.rarity_id)
```

## Equip and unequip

```python
commander = client.commanders.get_commanders()[0]
item = inventory[0]

client.equipment.equip(item.equipment_id, commander.commander_id)
client.equipment.unequip(item.equipment_id, commander.commander_id)
```

Both raise `CommandError` when the server refuses the move. Their replies carry no
data, so read `client.commanders.get_all()` again to see the change. To move an
item from one wearer to another, do as the game client does: take it off the
first, then put it on the second.

What a commander already wears is on `Commander.equipment`; see
[Commanders](commanders.md).

## Sell items and gems

```python
client.equipment.sell_equipment(item.equipment_id)
gems = client.equipment.gems
if gems is not None and gems.gems:
    client.equipment.sell_gem(gems.gems[0])
```

Selling is free and pays coins; the reply's coins and inventory space reach
`client.state`. `bind_gem(gem, equipment_id, commander_id)` sets a gem in an
item a commander wears, for coins; a gem already set there is not taken back.

## Auto-sell

With the auto-sell subscription, the server sells new equipment and gems as they
drop, by the rules `get_auto_sell()` reads and `set_auto_sell()` replaces:

```python
from empire_core.commanders import AutoSellEquipment, AutoSellRules
from empire_core.enums import EquipmentSlot, GemColor, Rareness

client.equipment.set_auto_sell(
    AutoSellRules(
        equipment=(AutoSellEquipment(slot=EquipmentSlot.HELMET, rareness=Rareness.COMMON),),
        gems={GemColor.RED: 3},
    )
)
```

A gem rule sells that colour's gems up to the level given, 0 none.

**API:** [`EquipmentService`](../reference/commanders.md#empire_core.commanders.service.EquipmentService),
[`Equipment`](../reference/commanders.md#empire_core.commanders.models.equipment.Equipment)
