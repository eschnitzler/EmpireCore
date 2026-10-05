---
description: What client.state holds, how to read it safely, and how to tell how old it is.
---

# State and freshness

`client.state` is an in-memory picture of your account: the player, castles,
the castle you joined with its mines and resource carts, movements, special
currencies, your spy count, active events, your commanders and skills, your
alliance and its chat, and your progress: research, boosters, might, titles,
achievements, relocation and plague monks. A background thread applies the
server's packets to it while your code reads it.

## Read through the accessors

Each accessor takes the state lock and returns a snapshot, so nothing changes
underneath you mid-iteration:

```python
player = client.state.get_local_player()    # None until the login data arrives
castles = client.state.get_castles()
unlocks = client.state.get_permanent_castle(castle_id)    # unlocked units, horses
horse_ids = client.state.get_castle_horse_ids(castle_id)  # the horses' wod ids
movements = client.state.get_all_movements()
attacks = client.state.get_incoming_attacks()
currencies = client.state.get_special_currencies()
spies = client.state.get_max_spies()        # spies owned, before boosts
events = client.state.get_events()          # the running events, by id
roster = client.state.get_commanders()      # commanders and castellans
skills = client.state.get_skills()          # legend and sceat skills
alliance = client.state.get_own_alliance()  # your alliance's details and members
chat = client.state.get_alliance_chat()     # the alliance chat history, oldest first
research = client.state.get_research()      # finished and running research
boosts = client.state.get_boosts()          # boosters, premium account, slots, festival
might = client.state.get_might()
glory = client.state.get_glory_points()
berimond = client.state.get_faction_points()
ranks = client.state.get_title_ranks()      # top-X ranks, Storm Islands title
achievements = client.state.get_achievements()
relocation = client.state.get_relocation()
monks = client.state.get_plague_monks()
area = client.state.get_joined_area()       # None until a castle is joined
mines = client.state.get_mines()            # the joined castle's mines, by object id
carts = client.state.get_resource_carts()   # its wood, stone and food carts
```

The commanders, skills and alliance accessors return copies, and the chat
messages and progress models are read-only, so changing what you hold changes
nothing in state, and a newer packet does not change it either. The progress
models count their times from when they were read (`received_at`, in
`time.monotonic()` seconds), so `research.remaining_research_seconds()` or
`booster.is_active()` stay right between packets.

The attributes behind them (`client.state.local_player`,
`client.state.castles`, ...) stay readable, but they are live and unlocked.
Prefer the accessors whenever you read several fields at once or iterate a
container. `client.state.castles` is keyed by `(kingdom, castle_id)`, as the
game keeps a castle list per kingdom.

## Where state comes from

Nothing in state polls the server. It is updated only by incoming packets, and
every value is as old as the last packet that carried it:

| State | Refreshed by | To refresh it now |
|---|---|---|
| Castle names, positions, the castle list | `gcl`, `mir` (pushed) | log in again |
| Castle resources, units and details | `dcl` | `client.castle.get_details(castle_id)` |
| Castle units, as new ones arrive | `rue` (pushed) | `client.castle.get_details(castle_id)` |
| Castle open-gate counter | `gcl`, `kik` (pushed, resets it on Mondays) | log in again |
| Joined castle, slum level, builder discount | `jaa` (the join reply), `csl`, `gab` (pushed) | `client.castle.join(castle_id)` |
| Joined castle's mines | `gsm` (pushed), the `jaa` and `cmr` replies | `client.castle.join(castle_id)` |
| Joined castle's resource carts | `rci` (pushed), the `jaa` and `rcc` replies | `client.castle.join(castle_id)` |
| Player identity, level and XP | `gpi`, `gxp`, `glu` | log in again |
| Coins, rubies, VIP, alliance | `gcu`, `vip`, `gal` | log in again |
| Honor, beginner protection | `gho`, `uap` | log in again |
| Special currencies | `sce` (pushed) | none |
| Spies owned, before boosts | `gms` (pushed) | log in again |
| Commanders and castellans | `gli`, and the replies that carry it (`arl`, `gla`, `seq`, `sdi`, `sti`, the attack and conquer info replies) | `client.commanders.get_all()` |
| Legend and sceat skills | `skl`, `ego` (pushed) | `client.skills.get_skills()` |
| Your alliance's details and members | `ain`, `acn`, `cal`, `acd`, `ado`, `akm`, `arm`; an `acm` marks its sender online | `client.alliance.get_alliance_info(alliance_id)` |
| Alliance chat history | `acl`, `acm` (pushed) | none |
| Research | `rei` (pushed), the `res` and `msr` replies | log in again |
| Boosters, premium account, production slots | `boi` (pushed), the booster replies (`ovs`, `bds`, ...); a `boi` updates only the boosters it lists | log in again |
| Festival | `boi`, the `bfs` reply | log in again |
| Might points | `gmu` (pushed) | log in again |
| Glory points | `ufa` (pushed) | log in again |
| Berimond points | `ufp` (pushed; the login data's copy is ignored, as the game ignores it) | none |
| Top-X ranks, Storm Islands title | `uar` (pushed) | log in again |
| Achievements | `vli` (pushed); finished ones add up, progress per achievement | log in again |
| Relocation | `gri` (pushed) | log in again |
| Plague monks | `cpi` (pushed), the `cpm` and `sbp` replies | log in again |
| Running events, their scores and ends | `sei`, `tei` (pushed), `see`, `tee`, `pep`, the `fjf` and `bst` replies | `client.events.refresh()` |
| Movements | `gam`, `abr`/`asr`, your sends' replies | `client.movements.get_movements()` |

Every player section is sent inside the login data (`gbd`) and again as a push
of its own when it changes. A section a reply carries is applied only when the
reply succeeded, as the game applies it.

Only your own alliance is kept: `get_alliance_info` for another alliance
leaves it alone. The chat history grows with every `acl` and `acm`, as the
game's does, and starts over when you leave the alliance or a `gal` says you
are in none. Each message's `sent_at` is the wall-clock time it was sent,
taken from its age when it arrived.

## Knowing whether state is fresh

Castle resources and units are often filled once, at login, and never again
unless you ask. State can be stale without being wrong, so check before you
trust it:

```python
if client.state.get_castle_last_updated(castle_id) is None:
    # Never refreshed: resources and units are defaults, not measurements.
    client.castle.get_details(castle_id)
```

The freshness accessors are `get_castle_last_updated` and `get_castle_age`,
`get_player_last_updated`, and `get_last_packet_time` or `get_packet_times`
for each command. They return wall-clock `time.time()` seconds, and `None`
means never seen, which is different from seen and empty.

## The joined castle

Logging in joins no castle; `client.castle.join(castle_id)` does, and its reply
fills `get_joined_area()` (the castle's kingdom and id, slum level and builder
discount) and, when the server sends them, the mines and resource carts. Their
pushes keep them current while you stay. A map read (`gaa`, as every
[scan](map-scanning.md) sends) drops the mines, as the game drops them on the
world map; `get_joined_area()` and the resource carts stay, as the game keeps
them, even though the session is no longer in the castle. Mines and carts are
read-only. A mine's `next_collect_seconds` and a
cart's `remaining_seconds` count down from when they arrived, as in the game:

```python
import time

client.castle.join(castle_id)
sent_at = client.state.get_last_packet_time("gsm")
for object_id, mine in client.state.get_mines().items():
    if mine.next_collect_seconds >= 0 and mine.next_collect_seconds <= time.time() - sent_at:
        client.castle.collect_mine(object_id)
```

The joined castle's buildings are not kept in state. `on_building_finished`
(`fbe`), `on_building_xp` (`cbx`) and `on_buildings_changed` (`gdb` damaged
buildings, `gcb` changed efficiency), with their `remove_*` counterparts, call
you back on the callback thread instead.

## Running events

`client.state.get_events()` maps each running event's id to a model of its kind
(the ones in `empire_core.events.EVENT_CLASSES`, such as `InvasionEvent` or
`KingdomsLeagueEvent`), or a plain `SpecialEvent` for the rest. Each keeps the
fields its game dialog reads, the entries the server sent in `raw`, and when it
ends (`end_time`, in `time.monotonic()` seconds; `remaining_seconds()` and
`is_active()` read it):

```python
from empire_core.gamedata.ids import Event

for event_id, event in client.state.get_events().items():
    print(event_id, type(event).__name__, round(event.remaining_seconds()))

samurai = client.state.get_event(Event.SAMURAI_INVASION)
if samurai is not None:
    print(samurai.parts["A"].league_id, samurai.parts["A"].own_points)
```

An event starts with the `sei` (or, for the kingdoms league and the global
effects, `tei`) entry that names it, and later entries are read over it the way
the game reads them: a field the entry leaves out mostly keeps its value. It
ends with a `see` or `tee`, or when its time runs out. Your points come with
the `pep` pushes. The models never change; a later packet replaces them, so a
snapshot stays as it was.

`on_event_added`, `on_event_removed` and `on_events_updated` (and their
`remove_*` counterparts) call you back on the callback thread when an event
starts, ends, or a packet updates the events; `get_events_last_updated()` says
when one last did. The [events guide](events.md) lists the models.

## Disconnects

When the connection drops, state is emptied, as the game client empties its
own. The next login's `gbd` refills the player, castles, commanders, skills,
alliance and chat, and the movement
list the server pushes shortly after refills the movements.
`client.on_disconnect(callback)` tells you when a session drops; `close()`
does not fire it.

```python
client.on_disconnect(lambda: print("connection lost"))
```

The callback runs on the receive thread as it shuts down. Keep it short and
start a new login from another thread.

## From an asyncio program

The client is threaded, and its callbacks run on its own threads. On an event
loop, `client.listen()` streams them instead: every `on_*` registration of the
client, its state and its services, or only the ones you pass. Each event is a
`ClientEvent` whose `name` is the registration without `on_` and whose `args`
are what a callback there is called with: `(old, new)` for
`incoming_attack_updated`, `(movement_id, movement)` for the movement
callbacks, one model for the others, none for `disconnect`:

```python
import asyncio

from empire_core import ClientEvent

async def watch(client):
    await asyncio.to_thread(client.login)
    async with client.listen(
        client.state.on_incoming_attack,
        client.state.on_movement_arrived,
        client.alliance.on_chat_message,
        client.on_disconnect,
    ) as events:
        async for event in events:
            match event:
                case ClientEvent(name="incoming_attack", args=(movement,)):
                    print("attack from", movement.source_player_name)
                case ClientEvent(name="movement_arrived", args=(movement_id, movement)):
                    print("arrived", movement_id)
                case ClientEvent(name="chat_message", args=(message,)):
                    print(message.player_name, message.decoded_text)
                case ClientEvent(name="disconnect"):
                    print("connection lost")
```

The events come on the loop in the order their packets came, across every
registration, through the one callback thread: no thread is started per event.
Service and disconnect events (chat, help, skill lists, new messages,
`disconnect`) are queued there behind the state callbacks, so a slow state
callback delays them too.

A stream outlives sessions, as callbacks do: a dropped session is a
`disconnect` event, and after `client.close()` and a new `client.login()` the
same stream delivers the new session's events. While the client is closed,
nothing arrives.

A stream of one registration is typed: its events' `args` are that
registration's callback parameters, so a type checker sees the `Movement`
pair of `on_incoming_attack_updated`. Streams of several registrations, and of
the movement callbacks (which take one or two parameters), have untyped `args`.

```python
async with client.listen(client.state.on_incoming_attack_updated) as updates:
    async for update in updates:
        old, new = update.args  # Movement, Movement
        print(old.estimated_arrival, "->", new.estimated_arrival)
```

A stream listens for exactly its `async with` block: entering subscribes,
leaving (or `events.close()`) stops listening, and iterating a stream you did
not enter raises `RuntimeError`. A stream is entered once; call
`client.listen()` again for another. `client.close_streams()` ends every open
stream after the events already on their way; `client.close()` does not. A
pool calls `close_streams()` when it releases a client, so your streams never
run into the next lease.

Nothing is dropped while your loop keeps up. `client.listen(maxsize=n)` caps
the events waiting unread instead: one more stops the stream, which raises
`EventStreamOverflowError` after the events it holds. Read the state you need
again and listen anew.

Blocking calls stay blocking; run them off the loop with `asyncio.to_thread`,
as above, so a request that waits for its reply does not stall the loop:

```python
movements = await asyncio.to_thread(client.movements.get_movements)
```

!!! tip "Going deeper"

    [State management](../design/state_management.md) documents the
    object-identity and container-swap rules in full.

**API:** [`GameState`](../reference/state.md#empire_core.state.manager.GameState)
