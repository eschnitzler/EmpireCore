---
description: Castles, resources, buildings, the construction queue and moving goods and troops.
---

# Castle

## Your castles

```python
castles = client.castle.get_all()                  # list[CastleInfo]

details = client.castle.get_details(castle_id=12345)
if details:                                        # None when the reply leaves the castle out
    print(f"Wood: {details.wood}, units: {details.units}")

resources = client.castle.get_resources(castle_id=12345)
print(f"Wood: {resources.wood}, Stone: {resources.stone}")
```

`CastleInfo.castle_id` is the id every other castle call takes, and
`CastleInfo.kingdom_id` the kingdom it sits in. `get_details` also refreshes the
castle's resources and units in [state](game-state.md).

### The kingdom comes from your castle list

Methods that act on one of your castles take its id alone and send its
kingdom from the castle list the server sent at login
(`client.state.get_castles()`), as the game client does. There is no
`kingdom_id` argument to get wrong:

- an id that is not one of your castles raises `UnknownCastleError`;
- an id listed in several of your kingdoms raises `AmbiguousCastleError`,
  since the library then cannot tell which castle is meant.

That covers `select`, `join`, `get_resources`, `get_details`, `rename`,
`send_resources`, `transfer_units_to_kingdom`, the `client.army` methods and
`client.alliance.donate`.

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
from empire_core import Resource

client.castle.send_resources(source_castle_id, target_x, target_y, {Resource.WOOD: 1000, Resource.STONE: 500})

commander = client.commanders.get_commanders()[0]
client.castle.send_support(
    source_castle_id, target_x, target_y, units=[[620, 50]], commander_id=commander.commander_id
)
client.castle.send_troops(
    source_x, source_y, target_x, target_y, units=[[620, 50]], commander_id=commander.commander_id
)
```

### Goods, one tab per send

The game's send dialog offers goods on three tabs, and the server refuses a
send that mixes them (`INVALID_PARAMETER_VALUE`, seen live), so each send
carries goods from one tab only:

| Tab | `Resource` members |
|---|---|
| Classic | `WOOD`, `STONE`, `FOOD` |
| Kingdom | `COAL`, `OIL`, `GLASS`, `IRON` |
| Mead | `HONEY`, `MEAD`, `BEEF` |

A player without a legend level gets only the classic tab. `send_resources`
raises `UnsendableGoodsError`, without sending anything, for goods from more
than one tab, anything but classic goods for such a player, or an amount that
is not a positive int. The target owner's level, the carriage capacity and the
castle's stock are left to the server.

### Troops

`send_support` sends troops to someone else's area; the server refuses one to
your own with `NO_SELF_DESTRUCTION` (92). Move troops between your own areas
with `send_troops`. `get_market_info()` lists each castle's free carriages, and
`transfer_units_to_kingdom` sends units to another kingdom.

`rename(castle_id, new_name)` renames a castle.

## Horses

`client.castle.get_horses(castle_id)` lists the horses a castle can send
movements with, read from the login data's `gpc` section and its pushes, so
nothing is sent. It needs `client.load_game_data()`, and returns `None` for a
castle that is not yours or that no `gpc` named:

```python
client.load_game_data()

for horse in client.castle.get_horses(castle_id=12345) or []:
    print(horse.wod_id, horse.unit_boost, horse.market_boost, horse.spy_boost, horse.is_instant_spy_horse)
```

Each row is a `HorseStats`: the speed bonus percent for troops
(`unit_boost`), traders (`market_boost`) and spies (`spy_boost`), the coin and
ruby cost multipliers (`cost_factor_c1`, `cost_factor_c2`), and
`is_instant_spy_horse`, a horse that can be paid with rubies or, sent with
`feathers=True`, with feathers. Pass a horse's `wod_id` as `horse_booster_id`
to `send_resources`, `send_support`, `send_troops`, `client.attack.send_attack`
or the spy missions.

On a live account, main and kingdom castles offered horses 1007 to 1009, the
Storm castle 1030 to 1032, and outposts none. Without game data,
`client.state.get_castle_horse_ids(castle_id)` gives the bare wod ids.

**API:** [`CastleService`](../reference/castle.md#empire_core.castle.service.CastleService)
