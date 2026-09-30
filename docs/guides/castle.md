---
description: Castles, resources, buildings, the construction queue and moving goods and troops.
---

# Castle

## Your castles

```python
from empire_core import Kingdom

castles = client.castle.get_all()                  # list[CastleInfo]

details = client.castle.get_details(castle_id=12345)
if details:                                        # None when the reply leaves the castle out
    print(f"Wood: {details.wood}, units: {details.units}")

resources = client.castle.get_resources(castle_id=12345, kingdom_id=Kingdom.GREEN)
print(f"Wood: {resources.wood}, Stone: {resources.stone}")
```

`CastleInfo.castle_id` is the id every other castle call takes, and
`CastleInfo.kingdom_id` the kingdom it sits in. `get_details` also refreshes the
castle's resources and units in [state](game-state.md).

## The joined castle

The game acts on one castle at a time, the one the session has joined. Joining
returns the castle's buildings, resources and production area, and building
and production commands then act on it:

```python
castle = client.castle.join(castle_id=12345)

area = client.castle.get_production()              # production, storage, population
queue = client.castle.get_build_queue()

if castle.buildings:
    building = castle.buildings.buildings[0]
    client.castle.upgrade_building(building.object_id)
```

`client.castle.select(castle_id)` joins without returning the state, and
`join_area(x, y)` joins an outpost, capital, metropolis or faction camp by its
position, as the client does for the areas it may visit that are not castles.

!!! note "Scans and other castles move the session"

    A [map scan](map-scanning.md) leaves the castle the session had joined, and
    so does joining another one. `client.army` joins its castle itself; for
    anything else castle-scoped, join again first.

The joined-castle commands are `build`, `upgrade_building`, `move_building`,
`sell_decoration`, `destroy_building`, `finish_construction`,
`skip_construction_time`, `upgrade_defense`, `repair_building`, `repair_all`,
`buy_expansion`, `open_treasure_chest`, `collect_mine` and
`collect_resource_cart`. Each returns `True` when the server accepts it.

## Moving goods and troops

```python
client.castle.send_resources(source_castle_id, target_x, target_y, {"W": 1000, "S": 500})

commander = client.commanders.get_commanders()[0]
client.castle.send_support(
    source_castle_id, target_x, target_y, units=[[620, 50]], commander_id=commander.commander_id
)
client.castle.send_troops(
    source_x, source_y, target_x, target_y, units=[[620, 50]], commander_id=commander.commander_id
)
```

`send_support` sends troops to someone else's area; the server refuses one to
your own with `NO_SELF_DESTRUCTION` (92). Move troops between your own areas
with `send_troops`. `get_market_info()` lists each castle's free carriages, and
`transfer_units_to_kingdom` sends units to another kingdom.

`rename(castle_id, new_name)` renames a castle.

**API:** [`CastleService`](../reference/castle.md#empire_core.castle.service.CastleService)
