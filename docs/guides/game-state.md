---
description: What client.state holds, how to read it safely, and how to tell how old it is.
---

# State and freshness

`client.state` is an in-memory picture of your account: the player, castles,
the castle you joined with its mines and resource carts, movements, special
currencies, your spy count, active events, your commanders and skills, your
alliance and its chat, and your progress: research, boosters, might, titles,
achievements, relocation and plague monks; account details such as the
daily reset, the attack counter and the wishing well; and your inventory and
economy: gems, loot boxes, kingdoms, mercenary missions and tax. A background thread
applies the server's packets to it while your code reads it.

## Read through the accessors

Each accessor takes the state lock and returns a snapshot, so nothing changes
underneath you mid-iteration:

```python
player = client.state.get_local_player()    # None until the login data arrives
castles = client.state.get_castles()
unlocks = client.state.get_permanent_castle(castle_id)    # unlocked units, horses
horse_ids = client.state.get_castle_horse_ids(castle_id)  # the castle's horses, Horse members
movements = client.state.get_all_movements()
attacks = client.state.get_incoming_attacks()
announced = client.state.get_announced_attacks()  # what on_incoming_attack reported
currencies = client.state.get_special_currencies()  # by Currency; a newer key stays a str
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
quests = client.state.get_quests()          # your active quests, by id
book = client.state.get_quest_book()        # the quest book's main quests
daily = client.state.get_daily_quests()     # daily quest level, today's quests
reset = client.state.get_daily_reset()      # reset.remaining_seconds()
counter = client.state.get_attack_counter() # attacks counted, the threshold
training = client.state.get_officer_training()  # None when no program runs; .bonus is its effect
boosted = client.state.get_boosted_global_effects()  # the GlobalEffect members boosted
gifts = client.state.get_player_gifts()     # gift packages to send
well = client.state.get_wishing_well()
relics = client.state.get_new_relics()
gems = client.state.get_gems()              # gems and relic gems held
boxes = client.state.get_loot_boxes()       # loot boxes and key progress
space = client.state.get_inventory_space()  # equipment and gem inventory space
kingdoms = client.state.get_kingdoms()      # unlocks, transfers between kingdoms
missions = client.state.get_mercenary_missions()  # each mission's rewards are Collectables
tax = client.state.get_tax()                # a copy; remaining_seconds as of its packet
expiry = client.state.get_construction_item_expiry()
pool = client.state.get_resource_pool()     # the goods the citizen in your castle carries
area = client.state.get_joined_area()       # None until a castle is joined
mines = client.state.get_mines()            # the joined castle's mines, by object id
carts = client.state.get_resource_carts()   # its wood, stone and food carts
```

The commanders, skills and alliance accessors return copies, and the chat
messages, progress and account models are read-only, so changing what you hold
changes nothing in state, and a newer packet does not change it either. The
timed ones count their times from when they were read (`received_at`, in
`time.monotonic()` seconds), so `research.remaining_research_seconds()`,
`booster.is_active()` or `reset.remaining_seconds()` stay right between packets.

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
| Castle resources, after an action that spends or brings them | `grc` and the replies that carry one (building, recruiting, research, ...) | `client.castle.get_resources(castle_id)` |
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
| Daily reset | `drt` (login data only) | log in again |
| Attack counter | `gai` (pushed) | log in again |
| Officers' school training | `gatp` (any `gatp` without a running program clears it), `gtp` (its running program; none clears it) | log in again |
| Boosted global effects | `bie` (pushed) | log in again |
| Gift packages | `pgl` | log in again |
| Ruby wishing well | `rww` | log in again |
| New relics flag | `nrf` (pushed) | log in again |
| Gems and relic gems | `ggm`, `gec` (pushed; adds or takes gems away) | log in again |
| Loot boxes, key progress | `gls` (pushed, also before the login data); a `gls` updates only the key progress it lists | log in again |
| Equipment and gem inventory space | `esl` (pushed), the `bgm`, `ceq`, `cge`, `frc` and `seq` replies | log in again |
| Kingdoms, transfers between them | `kpi`, the `kgt`, `kst`, `kut`, `msk` and `fjf` replies; a `kpi` updates only the kingdoms it lists | log in again |
| Mercenary missions | `mpe` | log in again |
| Tax collection | `txi`, the `txs`, `txc` and `btx` replies | `client.castle.get_tax_info()` |
| Construction item expiry | `nec` (pushed) | log in again |
| Resource citizen | `irc` (pushed every 30 seconds or so); joining a castle (`jaa`) clears it | none |
| Running events, their scores and ends | `sei`, `tei` (pushed), `see`, `tee`, `pep`, the `fjf` and `bst` replies, `cqs` for the campaign | `client.events.refresh()` |
| Active quests, the quest book | `qli` (pushed after login, not in the login data), `qst`, `qfi`, the quest popups of `msp` | none |
| Daily quests | `dql` (pushed) | log in again |
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
means never seen, which is different from seen and empty. Only a `dcl` stamps
`get_castle_last_updated`: a `grc` refreshes a castle's resources but not its
units, so `get_last_packet_time("grc")` dates it.

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
sent_at = client.state.get_last_packet_time("gsm")  # None until a gsm arrived
for object_id, mine in client.state.get_mines().items():
    if sent_at is not None and 0 <= mine.next_collect_seconds <= time.time() - sent_at:
        client.castle.collect_mine(object_id)
```

The joined castle's buildings are not kept in state. `on_building_finished`
(`fbe`), `on_building_xp` (`cbx`) and `on_buildings_changed` (`gdb` damaged
buildings, `gcb` changed efficiency) call you back on the callback thread
instead; each one's `.remove(callback)` unregisters.

## Running events

`client.state.get_events()` maps each running event's id to a model of its kind
(the ones in `empire_core.events.EVENT_CLASSES`, such as `InvasionEvent` or
`KingdomsLeagueEvent`), or a plain `SpecialEvent` for the rest. Each keeps the
fields its game dialog reads, the entries the server sent in `raw`, and when it
ends (`end_time`, in `time.monotonic()` seconds; `remaining_seconds()` and
`is_active()` read it):

```python
from empire_core.gamedata import Event

for event_id, event in client.state.get_events().items():
    print(event_id, type(event).__name__, round(event.remaining_seconds()))

samurai = client.state.get_event(Event.SAMURAI_INVASION)
if samurai is not None:
    print(samurai.parts["A"].league_id, samurai.parts["A"].own_points)
```

`get_event` is typed by the event you pass: `get_event(Event.SAMURAI_INVASION)`
is a `SamuraiInvasionEvent | None` to mypy and pyright, so its fields complete
in the editor. An event without a model of its own, or a bare id, is a
`SpecialEvent | None`.

An event starts with the `sei` (or, for the kingdoms league and the global
effects, `tei`) entry that names it, and later entries are read over it the way
the game reads them: a field the entry leaves out mostly keeps its value. It
ends with a `see` or `tee`, or when its time runs out. Your points come with
the `pep` pushes. The models never change; a later packet replaces them, so a
snapshot stays as it was.

`on_event_added`, `on_event_removed` and `on_events_updated` (each with its
`.remove(callback)`) call you back on the callback thread when an event
starts, ends, or a packet updates the events; `get_events_last_updated()` says
when one last did. The [events guide](events.md) lists the models.

## Quests

`client.state.get_quests()` maps each active quest's id to a `Quest`: its
`progress` (one counter per condition, in the order the game data lists the
conditions), `completed`, `failed`, `locked`, and its `end_time` for a quest
with a time limit. The game data holds the quests' conditions and rewards; the
state keeps only what the server sends. `get_daily_quests()` gives your daily
quest level, today's daily quests and each reward threshold's rewards (each a
`Collectable`). Quest ids are `QuestId` and `DailyQuestId` members, or plain ints
for quests newer than the generated enums; the quest book's main quest ids stay
ints, as their game-data rows have no name.

`on_quests_updated` fires for every quest list, `on_quest_started` for each
quest a `qst` starts, `on_quest_progress` when a `qpg` names an active quest
(it changes nothing: the counters come with the next quest list),
`on_quest_finished` when a `qfi` or a quest popup finishes one, and
`on_daily_quests_updated` for every `dql`.

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
start a new login from another thread, or let the client do it.

### Keeping the session

Made with `keep_session=True` (or with `client.keep_session = True` set
later), the client logs a dropped session in again by itself, on a thread of
its own. It is the same client, so callbacks and `listen()` streams carry on.
`client.on_session_restored(callback)` fires once the session is back and its
login data and movement list have reached state, on the callback thread after
the events they caused. `client.on_session_lost(callback)` fires, with the
error, when the attempts end without one:

```python
client = EmpireClient(username="user", password="pass", keep_session=True)
client.on_disconnect(lambda: print("connection lost"))
client.on_session_restored(lambda: print("logged in again"))
client.on_session_lost(lambda error: print("gave up:", error))
client.login()
```

The game client does not log in again by itself: after a drop it shows a
reconnect dialog and waits for a click. So the timing is the library's, set on
the config: the first attempt comes `relogin_first_delay` seconds after the
drop (5 by default), and a failed one is retried after twice the last wait, up
to `relogin_max_delay` (300). A drop is often a kick: the same account logged
in elsewhere, by a person in the browser. A re-login 5 seconds later kicks that
person out again, so give them time:

```python
config = EmpireConfig(relogin_first_delay=600, relogin_max_delay=1800)
client = EmpireClient(username="user", password="pass", config=config, keep_session=True)
```

Both delays must be above 0 and the first no longer than the cap; the config
refuses anything else with a `ValidationError`, also on assignment.

A refusal with a login cooldown counts
as a failed attempt too, and is retried no sooner than the seconds the server
named: after the longer of that cooldown and the doubled wait. The cooldown is
what `client.remaining_login_cooldown()` reports, counting down. Live, a kick
was followed by a refusal with a 55 second cooldown; the client waited it out
to the second and the next attempt restored the session. A refusal that
waiting does not cure (a ban, the wrong server, the client version, the
credentials) ends the attempts with an error in the log and in
`on_session_lost`, and the client stays logged out.

`close()` ends the attempts, also while one is waiting, and never starts one;
the next `login()` turns them back on. Live, a `close()` during the cooldown
wait returned at once, with the re-login thread gone and no login after it.
`close()` may also be called from an `on_disconnect` callback. A `login()` of
your own ends attempts still going before it logs in, so only one login runs;
if it fails it raises, and `on_session_lost` does not fire. Only a session
that was logged in is restored.

`client.is_restoring_session` tells a session being restored from one given
up: it is True from just after the `on_disconnect` callbacks until the session
is back, the attempts give up, or `close()` or a `login()` of your own ends
them; it is already False when `on_session_restored` or `on_session_lost`
runs, and still False inside an `on_disconnect` callback, as the re-login
starts after those. To follow a restore, register the callbacks below.
`client.on_session_retry(callback)` fires for each failed attempt with
the attempts so far, the seconds until the next and the failure, so a long
restore can raise an alert without a timer of your own. An attempt ended by
`close()` or a `login()` of your own does not fire it; the log says
`re-login attempt` for a restore and `login attempt` for `login(retry=True)`:

```python
def retrying(attempt: int, wait: float, error: Exception) -> None:
    if attempt == 5:
        print(f"still logged out after {attempt} attempts: {error}")

client.on_session_retry(retrying)
```

The first login can be retried the same way: `client.login(retry=True)` waits
and logs in again after a timeout, a network error or a login cooldown, on the
same delays, until a login holds. Each failed attempt fires `on_session_retry`.
A refusal that waiting does not cure raises at once, and a `close()` or a
newer `login()` from another thread ends the attempts and makes `login()`
raise the last failure.

An attack or occupation announced before the drop is not announced again when
the restored session lists it: `on_incoming_attack` and `on_occupation_started`
fire for the ones that are new. `client.state.reannounce(movement_id)` fires them
again on purpose; with `when_listed=True` it waits until the restored session
lists the movement, from `on_session_restored` too, which may come before the
movement list did. The same holds across `close()` and `login()`; see
[what was announced](movements.md#what-was-announced-and-announcing-again).

## From an asyncio program

The client is threaded, and its callbacks run on its own threads. On an event
loop, `client.listen()` streams them instead: every `on_*` registration of the
client, its state and its services, or only the ones you pass. Each event is a
`ClientEvent` whose `name` is the registration without `on_` and whose `args`
are what a callback there is called with: `(old, new)` for
`incoming_attack_updated` and `occupation_updated`, `(movement, captured)` for
`occupation_ended`, `(movement_id, movement)` for the movement
callbacks, one model for the others, the error for `session_lost`, none for
`disconnect` and `session_restored`:

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
`disconnect` event, a session `keep_session` restores is a `session_restored`
event, one it gives up on a `session_lost` event, and after `client.close()` and a new `client.login()` the
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

Subscriptions kept as data can name the registrations instead, by the event
names: `client.listen(names={"incoming_attack", "chat_message"})`. A name no
registration has raises `ValueError` when `listen` is called, so a typo does
not go unnoticed; `names` takes a collection, never a single string. A stream
by name has untyped `args`. Registration methods and `names` can be given
together, and the stream then has both. Only `client.listen()` with neither
streams every registration; an empty `names` streams none.

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
