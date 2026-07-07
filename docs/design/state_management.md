# State Management

`GameState` keeps an in-memory snapshot of the game so bot logic can read the
current player, castles, and troop movements without re-querying the server
for every decision.

## The `GameState` Object

`GameState` (in `empire_core.state.manager`) holds plain dictionaries:

```python
class GameState:
    local_player: Player | None
    players: dict[int, Player]        # player_id -> Player
    castles: dict[int, Castle]        # castle_id -> Castle
    movements: dict[int, Movement]    # movement_id -> Movement
    active_event_ids: list[int]
```

It is created and owned by `EmpireClient` as `client.state`.

## Thread Safety

The receive thread writes state (via `update_from_packet`) while user threads
read it. All mutation and every query are guarded by a single `RLock`, and the
query methods return **snapshots** (new lists), so iterating them can't raise
`dictionary changed size during iteration`:

```python
for m in client.state.get_all_movements():   # snapshot list
    ...
client.state.get_castles()
client.state.get_incoming_attacks()
```

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

On relogin, existing `Player`/`Castle` objects are updated in place (identity
preserved) rather than replaced, so references held by user code stay live.

## Movement Lifecycle

* `created_at` is set once, when a movement is first seen, and preserved
  across updates.
* `time_remaining` and `has_arrived()` are computed against wall-clock time
  (extrapolated from the last packet's `TT - PT`), so they keep counting down
  between updates instead of freezing at the last snapshot.
* Movements are removed on their `atv`/`ata`/`mrm` packet. If that packet is
  missed, the movement is pruned once its estimated arrival is well in the
  past, so `movements` can't grow without bound in a long-running session.

## Reactive Callbacks

State changes that matter for automation are surfaced as callbacks, not
per-property observers. Register them on `client.state`:

```python
def alert(movement):
    print(f"Incoming attack {movement.MID} from {movement.source_player_name}")

client.state.on_incoming_attack(alert)   # also: on_movement_arrived, on_movement_recalled
```

`on_incoming_attack` fires **once** per newly seen hostile attack (not on every
`gam` refresh, and not for the local player's own outgoing attacks). Callbacks
are dispatched on a thread pool, so a callback may make blocking calls (e.g.
request more data) without stalling the receive loop. See
[events.md](events.md) for the full event/callback model.

## Persistence (Optional / Experimental)

`empire_core.storage.database` provides an experimental async SQLite store for
persisting discovered map objects and player snapshots across restarts. It is
not yet wired into the client.
