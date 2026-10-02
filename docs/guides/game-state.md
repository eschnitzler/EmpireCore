---
description: What client.state holds, how to read it safely, and how to tell how old it is.
---

# State and freshness

`client.state` is an in-memory picture of your account: the player, castles,
movements, special currencies, your spy count, active events, your commanders and
skills, and your alliance and its chat. A background thread applies
the server's packets to it while your code reads it.

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
```

The commanders, skills and alliance accessors return copies, and the chat
messages are read-only, so changing what you hold changes nothing in state, and
a newer packet does not change it either.

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
| Player identity, level and XP | `gpi`, `gxp`, `glu` | log in again |
| Coins, rubies, VIP, alliance | `gcu`, `vip`, `gal` | log in again |
| Honor, beginner protection | `gho`, `uap` | log in again |
| Special currencies | `sce` (pushed) | none |
| Spies owned, before boosts | `gms` (pushed) | log in again |
| Commanders and castellans | `gli`, and the replies that carry it (`arl`, `gla`, `seq`, `sdi`, `sti`, the attack and conquer info replies) | `client.commanders.get_all()` |
| Legend and sceat skills | `skl`, `ego` (pushed) | `client.skills.get_skills()` |
| Your alliance's details and members | `ain`, `acn`, `cal`, `acd`, `ado`, `akm`, `arm`; an `acm` marks its sender online | `client.alliance.get_alliance_info(alliance_id)` |
| Alliance chat history | `acl`, `acm` (pushed) | none |
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

!!! tip "Going deeper"

    [State management](../design/state_management.md) documents the
    object-identity and container-swap rules in full.

**API:** [`GameState`](../reference/state.md#empire_core.state.manager.GameState)
