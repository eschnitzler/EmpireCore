---
description: Castles, resources, buildings, the construction queue, research and the mercenary camp.
---

# Castle

## Your castles

```python
castles = client.castle.get_all()    # list[CastleInfo]

details = client.castle.get_details(castle_id=12345)  # UnknownCastleError when it is not yours
print(f"Wood: {details.wood}, units: {details.units}")   # {Unit or Tool: amount}

resources = client.castle.get_resources(castle_id=12345)
print(f"Wood: {resources.wood}, Stone: {resources.stone}")
```

`CastleInfo.castle_id` is the id every other castle call takes, and
`CastleInfo.kingdom_id` the kingdom it sits in. `get_details` also refreshes the
castle's resources and units in [state](game-state.md).

### The kingdom comes from your castle list

Methods that act on one of your castles take its id alone and send its
kingdom from the castle list the server sent at login
(`client.castle.castles`), as the game client does. There is no
`kingdom_id` argument to get wrong, and an id that is not one of your castles
raises `UnknownCastleError`.

That covers `select`, `join`, `get_resources`, `get_details`, `rename`,
`abandon_castle`, `cancel_abandon`,
`send_resources`, `transfer_units_to_kingdom`, `transfer_goods_to_kingdom`, the `client.army` methods and
`client.alliance.donate`.

### Abandoning a castle

```python
reply = client.castle.abandon_castle(castle_id=12345)  # free; ValueError for a kingdom's main castle
print(reply.abandon_seconds, reply.cancel_seconds)     # until it goes (a day), left to cancel (3 hours)
client.castle.cancel_abandon(castle_id=12345)           # keeps it while cancel time is left
```

The castle list's `CastleInfo.abandon_outpost_seconds`, `cancel_abandon_seconds`
and `no_abandon_seconds` show a running abandon and how long until a castle has
been held long enough to abandon. Opening the gate and peace mode cost rubies
and are not in the library.

## Construction items

Request the items in storage with `get_construction_items()`. The result contains
one `ConstructionItemStack` per inventory row, with `construction_item_id` and
`amount`. Unknown item ids remain integers. An empty inventory has `items == ()`.
`client.castle.construction_items` reads the last inventory received and is `None`
before the first reply.

```python
inventory = client.castle.get_construction_items()
for stack in inventory.items:
    print(stack.construction_item_id, stack.amount)
```

Equip and remove take your castle id, a building's `BuildingRow.object_id`, the
construction item id, and a slot index within the item's slot type. They join the
castle themselves and use its kingdom from your castle list. The examples below
use synthetic ids:

```python
from empire_core.castle import ConstructionItemMode

placement = client.castle.equip_construction_item(
    12345, 77, 99999999, 0, mode=ConstructionItemMode.ADD
)
removed = client.castle.remove_construction_item(12345, 77, 99999999, 0)
```

`ADD` fills an empty slot. `REPLACE` returns the old item to storage and pays its
coin removal cost. `OVERWRITE` discards the old item. Removal also pays the item's
coin removal cost. The server checks slot compatibility, inventory capacity and
available coins; a refusal raises `CommandError`. These modes have no ruby payment
option.

Both actions return the server's complete placement: `result.items` contains
`BuildingConstructionItems`, each with an `object_id` and `PlacedConstructionItem`
entries. These retain temporary items' `remaining_seconds` and unknown item ids.
`client.castle.placed_construction_items` gives a snapshot of the joined castle's
placement, updated by joins, successful service actions and expiry pushes. A map
read clears this snapshot. A reply arriving after the session changes castle or
leaves and rejoins the same castle raises `ReplyMismatchError` and cannot replace
another area's placement. Bare `client.request()` calls for equip/remove do not
update this cache because their replies carry no castle identity. Placement updates
follow receive order: an expiry push received after an action reply wins, even
when the requesting thread resumes later.

Disassembly consumes items in storage, or a lost and found entry when its id is
supplied:

```python
result = client.castle.disassemble_construction_item(12345, 99999999, amount=2)
print(result.amount, result.rewards)
```

`DisassembleConstructionItemResponse` exposes the server's `amount`, typed
`reward_ids` and the collectables resolved from those rewards using game data.
Unknown reward ids are retained. Permanent items' material yield is calculated
from static item definitions by the game client and is not included in this
server reply; `rewards` describes the drawn rewards only. Game data is loaded
before sending disassembly so a loading error cannot occur after items are
consumed.

Each successful action refreshes the inventory with `gii`. If that refresh fails,
the accepted action's result is returned, a warning is logged, and
`construction_items` stays `None` until a successful refresh. Retry
`get_construction_items()` to restore the snapshot. Refusals and transport failures
of the action itself propagate as typed errors. An accepted action whose body
cannot be parsed raises `PacketError` and invalidates the inventory too. An unreadable
equip/remove placement becomes unknown unless a newer expiry or join snapshot
already replaced it. Request
`get_construction_items()` explicitly to recover its snapshot.

## The joined castle

The game acts on one castle at a time, the one the session has joined. Joining
returns the castle's buildings, resources and production area, and building
and production commands then act on it:

```python
castle = client.castle.join(castle_id=12345)

area = client.castle.get_production()    # production, storage, population
queue = client.castle.get_build_queue()

if castle.buildings:
    building = castle.buildings.buildings[0]
    client.castle.upgrade_building(12345, building.object_id)
```

`client.castle.select(castle_id)` joins without returning the state, and
`join_area(x, y)` joins an outpost, capital, metropolis or faction camp by its
position, as the client does for the areas it may visit that are not castles.

!!! note "Scans and other castles move the session"

    A [map scan](map-scanning.md) leaves the castle the session had joined, and
    so does joining another one. `client.army` joins its castle itself; for
    anything else castle-scoped, join again first.

The joined-castle commands are `build`, `move_building`, `sell_decoration`,
`destroy_building`, `skip_construction_time`, `repair_building`, `repair_all`,
`buy_expansion`, `open_treasure_chest`, `collect_mine` and
`collect_resource_cart`. `upgrade_building`, `upgrade_defense` and
`finish_construction` take the castle id and join it themselves, as
`client.army` does, pricing the building from the join's reply. Each returns
`True` when the server accepts it. A building with a ruby price, finishing a
construction with over 240 seconds left (or a time left that cannot be worked
out), `repair_all`, a premium expansion and a castle rename spend rubies and
need `spend_rubies=True`, which also pays missing resources with rubies; see
[Spending rubies](index.md#spending-rubies).
`skip_construction_time` raises `ValueError` for a currency that is no minute
skip and, once the special currencies are known, for one you hold none of.

The join also fills [state](game-state.md#the-joined-castle) with the castle's
mines and resource carts, and their pushes keep them current, so you can see
what is ready before you collect it:

```python
from empire_core.enums import ResourceCartType

client.castle.join(castle_id)
mines = client.castle.mines        # object id -> MineStatus
wood = client.castle.resource_cart(ResourceCartType.WOOD)
if wood is not None and wood.amount > 0:
    client.castle.collect_resource_cart(ResourceCartType.WOOD)
```

Units that finish arrive as `rue` pushes, which update that castle's `units`
in state.

`rename(castle_id, new_name)` renames a castle. A rename costs 2500 rubies unless
a premium account runs, so without one it needs `spend_rubies=True`;
`is_initial_name=True` names a new castle, for free.

## Tax

The tax collector brings coins from your population. Read where it stands,
start a collection of one tax type, and collect it:

```python
tax = client.castle.get_tax_info()
print(tax.status, tax.remaining_seconds, tax.expected_income)

client.castle.start_tax(0)
reply = client.castle.collect_tax()
print(reply.collected)
```

`tax.status` is a `TaxStatus`: `NONE`, `COLLECTING` or `WAIT_FOR_COLLECT`, as
of the reply. Like the game, it counts a collection with `remaining_seconds` 0
as still collecting; the game shows it ready once that time has passed, so
count down from the reply to tell. Collecting while the collection runs brings the share of its
income earned so far.

| Tax type | Duration | Cost |
| --- | --- | --- |
| 0 | 10 minutes | free |
| 1 to 4 | 30 minutes to 6 hours | a tenth of the income, in coins |
| 5 | 12 hours | 125 rubies |
| 6 | 24 hours | 300 rubies |

A premium account, a VIP level or the tax research can waive the rubies of
types 5 and 6; without a premium account, a waived collection costs a tenth
of its income in coins instead. `start_tax`
refuses types 5 and 6 with `ValueError` unless you pass `spend_rubies=True`;
it does not check for a waiver, so the flag may spend rubies.
`TAX_DURATIONS` and `TAX_RUBY_COSTS` hold the numbers by tax type.

## Research

Research runs on `client.castle`. Start one, or shorten the running one with a
minute skip from your inventory:

```python
from empire_core.gamedata import Currency, Research

client.castle.start_research(Research.MANEUVER_L1)
client.castle.skip_research(Currency.SKIP_10_MINUTES)

research = client.castle.research
print(research.current_research_id, research.remaining_research_seconds())
```

Both raise `CommandError` when the server refuses. `start_research` looks the research
up in the game data (loaded on first use): some
researches cost rubies themselves (`ResearchDef.cost_rubies`, `costs`), and
it raises `ValueError` for those unless you pass `spend_rubies=True`. Their
other costs, legendary tokens included, are paid as the game charges them. It
never pays missing resources with rubies, and finishing a research at once for
rubies is left out. `skip_research` raises `ValueError` for a currency that is
no minute skip, or one you hold none of. Each reply's research reaches
`client.castle.research`.

## Mercenary camp

The mercenary camp's missions are on `client.castle` too. One request, `mpe`,
lists them, starts one and collects one:

```python
missions = client.castle.list_missions()
for mission in missions.missions:
    print(mission.mission_id, mission.quality, mission.current_state(), mission.price, mission.rewards)

client.castle.start_mission(mission_id=3)    # an open mission, paid in coins
client.castle.collect_mission(mission_id=3)  # once its time has run out
```

Each mission's `rewards` are `Collectable`s, `quality` a `MercenaryMissionRarity`
and `state` a `MercenaryMissionState` as of the reply; `current_state()` counts a
started mission whose time has run out as `COLLECTABLE`, as the game does.

Sending a running mission's id finishes it at once for rubies, so both calls
list the missions first and decide from that list: `start_mission` raises
`ValueError` unless the mission is open and no other mission runs or waits to
be collected, and `collect_mission` unless the server lists the mission as
collectable, as started with no remaining time sent (finished for the game),
or as started with its time run out at least two seconds before (the remaining
time it sends is rounded); a started mission still counting down is refused. Another session of the same account
can still change a mission between the list and the send; nothing closes that
window. Finishing a mission for rubies and swapping one for another (240
rubies) are left out.

**API:** [`CastleService`](../reference/castle.md#empire_core.castle.service.CastleService)

## Horses

`client.castle.horses(castle_id)` lists the horses a castle can send
movements with, read from the login data's `gpc` section and its pushes, so
nothing is sent. It reads the horses' stats from the game data, raises
`UnknownCastleError` for a castle that is not yours, and returns `None` while
no `gpc` has named the castle yet:

```python
for horse in client.castle.horses(castle_id=12345) or []:
    print(horse.wod_id, horse.unit_boost, horse.market_boost, horse.spy_boost)
```

Each row is a `HorseStats`: the speed bonus percent for troops
(`unit_boost`), traders (`market_boost`) and spies (`spy_boost`), the coin and
ruby cost multipliers (`cost_factor_c1`, `cost_factor_c2`), and
`is_instant_spy_horse`, a horse that can be paid with rubies or, sent with
`feathers=True`, with feathers. Pass a horse's `wod_id` as `horse_booster_id`
to `send_resources`, `send_support`, `send_troops`, `client.attack.send_attack`
or the spy missions. A horse whose `cost_factor_c2` is above 0, unless paid with
feathers, and any slowdown cost rubies and need `spend_rubies=True`.

On a live account, main and kingdom castles offered horses 1007 to 1009, the
Storm castle 1030 to 1032, and outposts none. Without game data,
`client.castle.unlocks(castle_id).horse_ids` gives the `Horse` members
(`Horse.HORSE_STABLE3` is 1007).

**API:** [`CastleService`](../reference/castle.md#empire_core.castle.service.CastleService)
