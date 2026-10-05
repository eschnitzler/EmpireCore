# State Management

Checked against client release: a4a25ae6

`GameState` keeps an in-memory snapshot of the game so bot logic can read the
current player, castles, and troop movements without re-querying the server
for every decision.

## The `GameState` Object

`GameState` (`empire_core.state.GameState`) holds plain dictionaries:

```python
class GameState:
    local_player: Player | None
    players: dict[int, Player]        # player_id -> Player (local player only)
    castles: dict[CastleKey, Castle]  # (kingdom, castle_id) -> Castle
    permanent_castles: dict[CastleKey, PermanentCastle]  # gpc: unlocked units and horses
    movements: dict[int, Movement]    # movement_id -> Movement
    events: dict[int, SpecialEvent]  # event id -> its model (sei/tei), in start order
```

It is created and owned by `EmpireClient` as `client.state`.

Despite its type, `players` only ever holds the **local player** — nothing in
the library records other players there. Don't iterate it expecting opponents
or alliance members; use the alliance service (`ain`) or the commander/profile
services for those. The special currencies (`sce`) live on the player itself
(`local_player.special_currencies`, currency key -> amount), not on `GameState`.

## Thread Safety

The receive thread writes state (via `update_from_packet`) while user threads
read it. All mutation and every query are guarded by a single `RLock`, and the
query methods return **snapshots** (new lists, dicts, or copies), so iterating
them can't raise `dictionary changed size during iteration`:

```python
for m in client.state.get_all_movements():   # snapshot list
    ...
client.state.get_castles()
client.state.get_incoming_attacks()
client.state.get_local_player()              # Player copy, or None before login
client.state.get_special_currencies()        # dict copy: currency key -> amount
```

* `get_local_player()` returns a `Player` copy taken under the lock, with
  **detached** `special_currencies`, `castles` and `beginner_protection` containers, so several fields can be
  read consistently while the receive thread is applying an update. It returns
  `None` before login. The `Castle` objects inside the snapshot are the live
  ones, as with `get_castles()`.
* `get_special_currencies()` returns a `dict[str, int]` copy of the special
  currencies (`PTT`, `MS1`, ...). Empty before login, or before the first `sce`.

The public attributes (`state.local_player`, `state.castles`, …) stay readable
directly, but they are live and unlocked. Prefer the accessors when reading
several fields at once or iterating a container.

## Passive Updates

State is never mutated by user code directly — it is updated **only** by
incoming packets. `update_from_packet(cmd, payload)` dispatches tracked
commands to handlers:

| Command      | Handler effect                                    |
|--------------|---------------------------------------------------|
| `gbd`        | login data: player, castles, currencies, events   |
| `gam`        | full movement list refresh                        |
| `abr`, `asr` | one movement pushed as it nears its target        |
| `cra`, `cam`, `abgcam` | the reply to an attack you send: its movement (`AAM`) and coins/rubies |
| `cds`, `csm`, `cat`, `crm`, `css`, `tde`, `cdd`, `cpm` | the reply to another send: its movement (`A`) and coins/rubies |
| `thm`, `ldt` | a treasure hunt you send (`TM`), a daimyo taunt attack |
| `mcm`        | your recall: the movement, now heading home       |
| `mrm`        | server removed a movement                         |
| `mfc`        | movement can be force-cancelled                   |
| `dcl`        | detailed castle resources / units                 |
| `gpi`, `gxp`, `gcu`, `vip`, `gal`, `gcl`, `gho`, `uap`, `gpc` | one login section, pushed when it changes |
| `glu`        | level up: its `gcu` and `gxp`                      |
| `mir`, `fjf` | castle list (`gcl`) after taking a castle, or in a faction join reply |
| `sce`        | special currency update                            |
| `sei`, `tei` | running events, read into their models (also the `sei` in `fjf` and `bst` replies) |
| `see`, `tee` | an event ended                                    |
| `pep`        | your points and rank in a running event           |

`lli` is not applied to state: in the client a successful `lli` carries no
game data (`LLICommand.executeCommand`, bundle line 120647, only reads its
payload on a refusal, for the ban time, cooldown, instance id or player id).
The player, castles and the rest come in the `gbd` the server sends right
after it.

### Presence vs. Absence in `gbd` and the Section Pushes

A section that is present but empty is a statement about the world; a section
that is absent says nothing at all and leaves existing state alone:

* `gal` present without a usable `AID` → the player is in no alliance, so a
  stale alliance is **cleared** (left, kicked, disbanded). A packet with no
  `gal` key leaves alliance state untouched.
* `gcl` carrying a castle section (`C`) is authoritative → castles it does not
  list are dropped, **including when it lists none at all** (the player just
  lost their last castle). A packet with no castle section leaves the castle
  list untouched, and so does a section whose entries were all unreadable.
* `gcu`, `vip`, `gxp` and `gho` are partial updates: a key they omit keeps its
  previous value rather than resetting to zero.
* `gpc` replaces the castles it names and keeps the others.

### Object Identity and Container Swaps

When a section push (or another `gbd`) updates the player or a castle already
in state, the existing `Player`/`Castle` object is updated in place (identity
preserved) rather than replaced, so references held by user code stay live.
A lost connection is different: `reset()` forgets the whole session, as the
game client does, and the next login's `gbd` builds new objects. The
`Player` and `Castle` field merges are applied as a **single atomic swap** of
the field mapping, so a reader can never observe a half-merged player (the new
name against the old level) or a castle mid-relocation (the new X against the
old Y).

The *containers* work the other way round — they are rebuilt and swapped, not
mutated. Each update replaces `local_player.special_currencies` and
`local_player.castles` with new dicts (likewise `castle.resources`,
`castle.units` and `castle.details` on `dcl`), so a reference to one of those objects held across an
update goes **stale**: it keeps the contents it had when it was taken. That is
deliberate — it is what stops an unlocked reader iterating the container from
crashing with `dictionary changed size during iteration`. Re-read the attribute
(or call `get_special_currencies()` / `get_castles()`) on each pass instead of caching
the container.

## Movement Lifecycle

* `created_at` is set once, when a movement is first seen, and preserved
  across updates.
* `time_remaining` and `has_arrived()` are computed against wall-clock time
  (extrapolated from the last packet's `TT - PT`), so they keep counting down
  between updates instead of freezing at the last snapshot.
* The server sends no arrival packet. As in the game client, a movement
  arrives once its travel time is up (`estimated_arrival`), and leaves state at
  `estimated_end`: the same moment, except for an army that waits at its
  target (a stationed support, `UM.TWD`), which stays until its wait is over.
  `mrm` removes a movement early.
* The check runs after every packet, handled or not, and inside every movement
  query, so arrivals fire with the first packet or query after the travel time
  is up. `gam` does not remove movements it no longer lists.
* A packet's movements are stored *before* the check runs, so a movement the
  packet just refreshed is never dropped and re-created, which would re-fire
  `on_incoming_attack` for an attack already alerted on.
* A movement first seen after it arrived (a support already stationed at
  login, or an attack reported late) is not an arrival and does not alert.
* An army's way home is a separate movement: a new `MID`, typed TRAVEL, with
  `D == 1` and source and target swapped.

## Reactive Callbacks

State changes that matter for automation are surfaced as callbacks, not
per-property observers. Register them on `client.state`:

```python
def alert(movement):                      # incoming attacks receive the Movement
    print(f"Incoming attack {movement.movement_id} from {movement.source_player_name}")

def arrived(movement_id, movement):       # arrival/recall: id + Movement (or None)
    print(f"Movement {movement_id} arrived: {movement}")

client.state.on_incoming_attack(alert)
client.state.on_movement_arrived(arrived)   # likewise on_movement_recalled / _removed
```

The signatures differ per event. `on_incoming_attack` callbacks take the
`Movement`. `on_movement_arrived` / `on_movement_recalled` /
`on_movement_removed` callbacks take either just the movement id
(`def cb(movement_id): ...`) or the id plus the `Movement`. Prefer the
two-argument form: an arrived or removed movement is usually gone from state
when the callback runs, so the id alone cannot be resolved. `movement` is
`None` only for an `mrm` about a movement this state never tracked.

* `on_movement_arrived`: travel time is up (see above). Fires once.
* `on_movement_recalled`: the `mcm` reply to your own recall, with the
  movement heading home.
* `on_movement_removed`: the server sent `mrm`. It does not say why.
* `on_incoming_attack_updated`: a later packet changed an announced attack's
  army, arrival, target or commander; it takes the old and the new
  `Movement`.
* `on_incoming_attack_withdrawn`: `mrm` removed an attack `on_incoming_attack`
  announced more than two seconds before its estimated arrival. Derived from
  the arrival time; it takes the `Movement`.
* `on_occupation_started`, `on_occupation_updated`: the same for
  occupations (`SIEGE`, `OCCUPY_FACTION`), the forces that hold an area
  after a capture attack won ("Occupying forces" in the game), which the
  attack callbacks do not report. The client raises no attack warning for an
  occupation; these follow its movement list, which shows one that holds an
  area of yours, the daimyo township's or another alliance member's.
* `on_occupation_ended`: an announced occupation left state; it takes the
  `Movement` and `captured`, True when its occupation time ran out (the area
  is captured) and False when `mrm` removed it more than two seconds before
  then (the occupation was broken).

`on_incoming_attack` fires **once** per attack movement id (judged again on
every packet that carries it, so an attacker's record that comes later counts), also
across a reconnect (not on every `gam` refresh). As in the client's
`CastleArmyData.checkAllAttackMovements`, it covers attacks aimed at you (or
your daimyo township) and player attacks aimed at a member of your alliance;
not your own attacks, armies on their way home, or attacks that had already
landed when first seen. Callbacks
run one at a time on a single callback thread, in packet order, never on the
receive thread, so a callback may make blocking calls (e.g. request more data)
without stalling the receive loop; everything queued behind it waits, though.
See [Reacting to movements](../guides/movements.md) for examples.

### One registry for every callback

Every `on_<name>` of the client, its state and its services is a declaration
of `Callbacks` (`src/empire_core/utils/callbacks.py`), not a hand-written method:

```python
on_incoming_attack = Callbacks[Callable[[Movement], None]]()
"""Register a callback for new hostile attack movements. ..."""
remove_incoming_attack_callback = Remover(on_incoming_attack)
"""Unregister an incoming attack callback."""
```

On an instance, `on_incoming_attack` is the registration and
`remove_incoming_attack_callback` its remover. Each owner keeps every
subscription in one `Registry`, its `_registry`, behind one lock: the state's
`RLock` for `GameState`, so registering waits for a packet being applied, and
a lock of its own for the client and each service. The owner fires an event
from a snapshot, `self.on_incoming_attack.calls()`, taken under that lock.
`GameState` queues each callback on the callback thread; a service calls its
callbacks on the receive thread; the client's session queues `on_session_lost`
and `on_session_restored` on the state's callback thread. The client's
`Registry` is also the store its connection keeps its disconnect listeners in,
so the `on_disconnect` callbacks are those listeners: the connection calls them
between its `on_disconnect` and `after_disconnect` slots, in the order
registered through either `client.on_disconnect` or
`connection.add_disconnect_listener`. Two things differ by owner, and the
owner's `Registry` says which: state callbacks fire once per registration and
removing one not registered raises `ValueError`; a service ignores such a
removal; the client (and so the connection) also registers each callback only
once.

`client.listen()` streams whatever is declared: `callback_sources` lists the
declarations of the client, its state and every service, so a new event is
streamed by declaring it. A `Remover` named other than
`remove_<name>_callback` fails when its class is created.
