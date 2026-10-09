---
description: Castles, resources, buildings, the construction queue, moving goods and troops, research and the mercenary camp.
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
(`client.state.get_castles()`), as the game client does. There is no
`kingdom_id` argument to get wrong:

- an id that is not one of your castles raises `UnknownCastleError`;
- an id listed in several of your kingdoms raises `AmbiguousCastleError`,
  since the library then cannot tell which castle is meant.

That covers `select`, `join`, `get_resources`, `get_details`, `rename`,
`send_resources`, `transfer_units_to_kingdom`, `transfer_goods_to_kingdom`, the `client.army` methods and
`client.alliance.donate`.

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
mines = client.state.get_mines()        # object id -> MineStatus
wood = client.state.get_resource_cart(ResourceCartType.WOOD)
if wood is not None and wood.amount > 0:
    client.castle.collect_resource_cart(ResourceCartType.WOOD)
```

Units that finish arrive as `rue` pushes, which update that castle's `units`
in state.

## Moving goods and troops

```python
from empire_core import Resource

goods = {Resource.WOOD: 1000, Resource.STONE: 500}
client.castle.send_resources(source_castle_id, target_x, target_y, goods)

from empire_core.gamedata import Unit

commander = client.commanders.get_commanders()[0]
client.castle.send_support(
    source_castle_id, target_x, target_y,
    units={Unit.SWORDMAN: 50}, commander_id=commander.commander_id,
)
client.castle.send_troops(
    source_x, source_y, target_x, target_y,
    units={Unit.SWORDMAN: 50}, commander_id=commander.commander_id,
)
```

Led by the premium commander, a support or troop send that may cost rubies
raises `PremiumCommanderCostError` unless you pass `spend_rubies=True`; see
[the premium commander](commanders.md#the-premium-commander).

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
with `send_troops`. Before sending, `get_travel_info` asks for what the game's
send dialog asks for:

```python
info = client.castle.get_travel_info(source_x, source_y, target_x, target_y)
print(info.units.units)                 # {Unit or Tool: amount} at the source
print(info.target_area.owner)           # the target's owner record
print(info.area_effects)                # CommanderEffect rows on the movement
```

Your commanders in the reply update [state](game-state.md). The reply has no
travel time, which the game works out from the units it sends. A source that
is not yours raises `CommandError` with `NOT_IN_OWNED_CASTLE`.

`get_market_info()` lists each castle's free carriages.

### Other kingdoms

`transfer_units_to_kingdom` sends units to another kingdom and
`transfer_goods_to_kingdom` goods to your castle there:

```python
from empire_core.enums import Kingdom, KingdomTransferType
from empire_core.gamedata import Currency

client.castle.transfer_goods_to_kingdom(castle_id, Kingdom.ICE, {Resource.WOOD: 1000})
kingdoms = client.state.get_kingdoms()
for transfer in kingdoms.goods_transfers if kingdoms else ():
    print(transfer.kingdom_id, transfer.remaining_seconds())

client.castle.skip_kingdom_transfer_time(Kingdom.ICE, KingdomTransferType.GOODS, Currency.SKIP_1_HOUR)
```

The goods pass the same checks as `send_resources` (one tab per send, classic
goods only below legend level). Like the game, `transfer_goods_to_kingdom`
raises `ValueError` for a source castle in the target kingdom or in Berimond,
and for a kingdom with no castle of yours to receive them. The travel tax and
the target's storage are left to the server.

`skip_kingdom_transfer_time` spends one minute skip item on the units or goods
on their way to a kingdom. As the game lists only the minute skips you hold, it
raises `ValueError` for a currency that is no minute skip and, once the special
currencies (`client.state.get_special_currencies()`) are known, for one you
hold none of. The full skip the game also offers costs rubies and is not in the
library.

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

Research runs on `client.player`. Start one, or shorten the running one with a
minute skip from your inventory:

```python
from empire_core.gamedata import Currency, Research

client.player.start_research(Research.MANEUVER_L1)
client.player.skip_research(Currency.SKIP_10_MINUTES)

research = client.state.get_research()  # None until the login data arrives
if research is not None:
    print(research.current_research_id, research.remaining_research_seconds())
```

Both return False when the server refuses. `start_research` needs the game
data (`client.load_game_data()`) and looks the research up in it: some
researches cost rubies themselves (`ResearchDef.cost_rubies`, `costs`), and
it raises `ValueError` for those unless you pass `spend_rubies=True`. Their
other costs, legendary tokens included, are paid as the game charges them. It
never pays missing resources with rubies, and finishing a research at once for
rubies is left out. `skip_research` raises `ValueError` for a currency that is
no minute skip, or one you hold none of. Each reply's research reaches
`client.state.get_research()`.

## Mercenary camp

The mercenary camp's missions are on `client.player` too. One request, `mpe`,
lists them, starts one and collects one:

```python
missions = client.player.list_missions()
for mission in missions.missions:
    print(mission.mission_id, mission.quality, mission.current_state(), mission.price, mission.rewards)

client.player.start_mission(mission_id=3)    # an open mission, paid in coins
client.player.collect_mission(mission_id=3)  # once its time has run out
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

**API:** [`PlayerService`](../reference/player.md#empire_core.player.service.PlayerService)

## Horses

`client.castle.get_horses(castle_id)` lists the horses a castle can send
movements with, read from the login data's `gpc` section and its pushes, so
nothing is sent. It needs `client.load_game_data()`, raises
`UnknownCastleError` for a castle that is not yours, and returns `None` while
no `gpc` has named the castle yet:

```python
client.load_game_data()

for horse in client.castle.get_horses(castle_id=12345) or []:
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
`client.state.get_castle_horse_ids(castle_id)` gives the `Horse` members
(`Horse.HORSE_STABLE3` is 1007).

**API:** [`CastleService`](../reference/castle.md#empire_core.castle.service.CastleService)
