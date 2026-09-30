---
description: The equipment inventory, and putting items on and off commanders and castellans.
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

client.equipment.equip(equipment_id=item.equipment_id, commander_id=commander.commander_id)
client.equipment.unequip(equipment_id=item.equipment_id, commander_id=commander.commander_id)
```

Both return `False` when the server refuses the move. Their replies carry no
data, so read `client.commanders.get_all()` again to see the change. To move an
item from one wearer to another, do as the game client does: take it off the
first, then put it on the second.

What a commander already wears is on `Commander.equipment`; see
[Commanders](commanders.md).

**API:** [`EquipmentService`](../reference/commanders.md#empire_core.commanders.service.EquipmentService),
[`Equipment`](../reference/commanders.md#empire_core.commanders.models.equipment.Equipment)
