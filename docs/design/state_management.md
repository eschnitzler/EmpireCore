# State Management

`GameState` keeps an in-memory snapshot of the game so bot logic can read the
current player, castles, and troop movements without re-querying the server
for every decision.

## The `GameState` Object

`GameState` (in `empire_core.state.manager`) holds plain dictionaries:

```python
class GameState:
    local_player: Player | None
    players: dict[int, Player]        # player_id -> Player (local player only)
    castles: dict[int, Castle]        # castle_id -> Castle
    movements: dict[int, Movement]    # movement_id -> Movement
    active_event_ids: list[int]
```

It is created and owned by `EmpireClient` as `client.state`.

Despite its type, `players` only ever holds the **local player** — nothing in
the library records other players there. Don't iterate it expecting opponents
or alliance members; use the alliance service (`ain`) or the commander/profile
services for those. The inventory lives on the player itself
(`local_player.inventory`, item id -> count), not on `GameState`.

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
client.state.get_inventory()                 # dict copy: item id -> count
```

* `get_local_player()` returns a `Player` copy taken under the lock, with
  **detached** `inventory` and `castles` containers, so several fields can be
  read consistently while the receive thread is applying an update. It returns
  `None` before login. The `Castle` objects inside the snapshot are the live
  ones, as with `get_castles()`.
* `get_inventory()` returns a `dict[str, int]` copy of the inventory (item id
  -> count; ids are strings). Empty before login, or before the first `sce`.

The public attributes (`state.local_player`, `state.castles`, …) stay readable
directly, but they are live and unlocked. Prefer the accessors when reading
several fields at once or iterating a container.

## Passive Updates

State is never mutated by user code directly — it is updated **only** by
incoming packets. `update_from_packet(cmd, payload)` dispatches tracked
commands to handlers:

| Command      | Handler effect                                    |
|--------------|---------------------------------------------------|
| `gbd`, `lli` | initial login data: player, castles, inventory    |
| `gam`        | full movement list refresh                        |
| `mov`        | real-time single-movement update                  |
| `atv`, `ata` | movement/attack arrived → removed                 |
| `mrm`        | movement recalled → removed                       |
| `dcl`        | detailed castle resources / units                 |
| `sce`        | inventory update                                   |
| `sei`        | active event ids                                   |

### Presence vs. Absence in `gbd`/`lli`

A section that is present but empty is a statement about the world; a section
that is absent says nothing at all and leaves existing state alone:

* `gal` present without a usable `AID` → the player is in no alliance, so a
  stale alliance is **cleared** (left, kicked, disbanded). A packet with no
  `gal` key leaves alliance state untouched.
* `gcl` carrying a castle section (`C`) is authoritative → castles it does not
  list are dropped, **including when it lists none at all** (the player just
  lost their last castle). A packet with no castle section leaves the castle
  list untouched.
* `gcu`, `vip`, and `gxp` are partial updates: a key they omit keeps its
  previous value rather than resetting to zero.

### Object Identity and Container Swaps

On relogin, existing `Player`/`Castle` objects are updated in place (identity
preserved) rather than replaced, so references held by user code stay live. The
`Player` and `Castle` field merges are applied as a **single atomic swap** of
the field mapping, so a reader can never observe a half-merged player (the new
name against the old level) or a castle mid-relocation (the new X against the
old Y).

The *containers* work the other way round — they are rebuilt and swapped, not
mutated. Each update replaces `local_player.inventory` and
`local_player.castles` with new dicts (likewise `castle.resources` and
`castle.units` on `dcl`), so a reference to one of those objects held across an
update goes **stale**: it keeps the contents it had when it was taken. That is
deliberate — it is what stops an unlocked reader iterating the container from
crashing with `dictionary changed size during iteration`. Re-read the attribute
(or call `get_inventory()` / `get_castles()`) on each pass instead of caching
the container.

## Movement Lifecycle

* `created_at` is set once, when a movement is first seen, and preserved
  across updates.
* `time_remaining` and `has_arrived()` are computed against wall-clock time
  (extrapolated from the last packet's `TT - PT`), so they keep counting down
  between updates instead of freezing at the last snapshot.
* Movements are removed on their `atv`/`ata`/`mrm` packet. If that packet is
  missed, the movement is pruned once its estimated arrival is more than
  `STALE_MOVEMENT_GRACE` (300s) in the past, so `movements` can't grow without
  bound in a long-running session.
* Pruning runs on every path that inserts movements — the `gam` full refresh
  *and* pushed `mov` packets — and again inside the list queries
  (`get_all_movements`, `get_incoming_movements`, `get_outgoing_movements`,
  `get_incoming_attacks`). A consumer driven purely by push callbacks may never
  call `gam`, and would otherwise keep being shown attacks that already landed.
  `get_movement_by_id` checks only the movement asked for and drops that one if
  it is stale, so the point lookup stays O(1).
* On the insert paths the prune runs *after* storing, so a movement the packet
  just refreshed is never dropped and immediately re-created — which would
  re-fire `on_incoming_attack` for an attack already alerted on.

## Reactive Callbacks

State changes that matter for automation are surfaced as callbacks, not
per-property observers. Register them on `client.state`:

```python
def alert(movement):                      # incoming attacks receive the Movement
    print(f"Incoming attack {movement.MID} from {movement.source_player_name}")

def arrived(movement_id, movement):       # arrival/recall: id + Movement (or None)
    print(f"Movement {movement_id} arrived: {movement}")

client.state.on_incoming_attack(alert)
client.state.on_movement_arrived(arrived)   # likewise on_movement_recalled
```

The signatures differ per event. `on_incoming_attack` callbacks take the
`Movement`. `on_movement_arrived` / `on_movement_recalled` callbacks take
either just the movement id (`def cb(movement_id): ...`) or the id plus the
`Movement` that was removed from state — prefer the two-argument form: the
movement is already gone from state when the callback runs, so the id alone
cannot be resolved (`movement` is `None` only for movements this state never
tracked, e.g. arrivals during a disconnect window).

`on_incoming_attack` fires **once** per newly seen hostile attack (not on every
`gam` refresh, and not for the local player's own outgoing attacks). Callbacks
are dispatched on a thread pool, so a callback may make blocking calls (e.g.
request more data) without stalling the receive loop. See
[events.md](events.md) for the full event/callback model.

## Persistence (Optional / Experimental)

`empire_core.storage.database` provides an experimental async SQLite store for
persisting discovered map objects and player snapshots across restarts. It is
not yet wired into the client.

Its dependencies (`sqlmodel`, `aiosqlite`) are not installed by default:
importing `empire_core.storage` without the `storage` extra
(`pip install empire-core[storage]`) raises an ImportError explaining this.
