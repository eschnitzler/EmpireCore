<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/pydantic-v2-purple.svg" alt="Pydantic v2">
  <img src="https://img.shields.io/badge/typed-py.typed-brightgreen.svg" alt="PEP 561 typed">
  <img src="https://img.shields.io/badge/tool-uv-orange.svg" alt="UV">
  <img src="https://img.shields.io/badge/status-WIP-red.svg" alt="Work in Progress">
</p>

<h1 align="center">EmpireCore</h1>

<p align="center">
  <strong>A fully typed Python client for Goodgame Empire</strong>
</p>

<p align="center">
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#services">Services</a> •
  <a href="#game-state">Game State</a> •
  <a href="#map-scanning">Map Scanning</a> •
  <a href="#error-handling">Errors</a> •
  <a href="#contributing">Contributing</a>
</p>

---

> [!WARNING]
> **Work in progress.** This is a `0.x` library: every **minor** release may
> break API, and breaking changes are called out in
> [CHANGELOG.md](CHANGELOG.md). Pin a minor line (`empire-core>=0.30,<0.31`).

---

## What you get

| | |
|---|---|
| **Typed end to end** | Pydantic v2 models for every command, and a `py.typed` marker so your type checker actually sees them |
| **Honest failures** | Typed exceptions from a single `EmpireError` base — no leaked pydantic or socket errors, and no empty list that secretly means "the request failed" |
| **Thread-safe state** | A background thread applies server pushes while your code reads consistent snapshots |
| **High-level services** | `client.alliance`, `client.attack`, `client.castle`, `client.army`, `client.commanders`, `client.ranking`, `client.spy` |
| **Map scanning** | BFS kingdom discovery with cheap, targeted re-scans |
| **Multi-account** | A pool that leases one logged-in client per account |

## Installation

```bash
uv add empire-core        # or: pip install empire-core
```

The experimental persistence layer needs an extra:

```bash
pip install "empire-core[storage]"
```

<details>
<summary><strong>Developing on the library itself</strong></summary>

```bash
git clone https://github.com/eschnitzler/EmpireCore.git
cd EmpireCore
uv sync --extra dev     # `dev` is an extra, not a default group:
                        # a plain `uv sync` leaves you without pytest/ruff/mypy
uv run pytest
```

</details>

## Quick Start

```python
from empire_core import EmpireClient

# The context manager disconnects and shuts the state worker down on any exit.
with EmpireClient(username="your_user", password="your_pass") as client:
    client.login()

    client.alliance.send_chat("Hello alliance!")

    for castle in client.castle.get_all():
        print(f"{castle.castle_name} at ({castle.x}, {castle.y})")
```

Without the `with` block, call `client.close()` yourself — skipping it leaks the
receive thread and the state executor for the life of the process.

## Services

Services are attached to the client automatically; there is nothing to wire up.

### `client.alliance`

```python
client.alliance.send_chat("Hello!")
client.alliance.help_all()

for entry in client.alliance.get_chat_log():
    print(f"{entry.player_name}: {entry.decoded_text}")

# Typed push subscription (detach again with remove_chat_message_callback)
client.alliance.on_chat_message(lambda msg: print(msg.decoded_text))
```

### `client.castle`

```python
castles = client.castle.get_all()

details = client.castle.get_details(castle_id=12345)
if details:                       # None when the response omits the castle
    print(f"Buildings: {len(details.buildings)}")

resources = client.castle.get_resources(castle_id=12345)
if resources:
    print(f"Wood: {resources.wood}, Stone: {resources.stone}")
```

Also available: `client.army`, `client.ranking` and `client.spy`.

### `client.commanders`

```python
for commander in client.commanders.get_commanders():
    print(commander.commander_id, commander.name, commander.wins, commander.defeats)
    for item in commander.equipment():
        print("  ", item.equipment_id, item.slot, item.enchantment_level, item.is_permanent)

# The defensive counterparts come back from the same command.
castellans = client.commanders.get_castellans()
```

The server calls both kinds "lords" (command `gli`, field `LID`); the game UI
calls them commanders and castellans, and so does this library.

### `client.attack`

```python
from empire_core import AttackWave, WaveFlank

commanders = client.commanders.get_commanders()

client.attack.send_attack(
    source_x=500,
    source_y=510,
    target_x=700,
    target_y=710,
    waves=[AttackWave(L=WaveFlank(U=[[487, 100]], T=[[301, 5]]))],
    commander_id=commanders[0].commander_id,
)
```

`commander_id` is required: every id `get_commanders()` returns leads an
attack, `0` included, so there is no value that means "no commander". The
server echoes the chosen one back, so `CreateAttackResponse.leader` says which
commander it actually flew with.

Waves without units are dropped before sending, as the game client does, and
passing `feathers=True` forces the horse field to -1 exactly as the client
does. See [`examples/commanders_and_attack.py`](examples/commanders_and_attack.py)
for a runnable version that dry-runs by default.

### Filling waves

```python
client.load_game_data()          # explicit: the items payload is a large download

commander = client.commanders.get_commanders()[1]
attack = client.attack.fill_attack(
    castle_id,
    target_x=624, target_y=247,  # a target is all it needs
    commander=commander,
)

client.attack.send_attack(
    source_x=castle.x, source_y=castle.y,
    target_x=624, target_y=247,
    waves=attack.waves, yard_wave=attack.yard,
    commander_id=commander.commander_id,
)
```

Coordinates are enough. From them it reads the target's area type and
structures, the defenders each flank holds and the castellan holding it, the
area effects that widen your flanks, your general's skills and your own legend
and Hall of Legends skills. A camp's level comes from the victory count in its
map row; a player's from the owner records beside it. Every one of those can be
passed instead, and passing one skips the request that would have found it.

Each wave is sized the way the game sizes it, which is by the *target owner's*
level rather than the attacker's: a level 13 castle holds far fewer troops than
a level 70 one, whatever the attacker's level. Some targets defend at a level of
their own - a monument is built for level 70 however low its owner is. On top
come the commander's own equipment, its general's unit-limit skills, the Hall of
Legends skills, and the legend skills when both sides are at the level cap.

Each flank takes tools first and then units, because a placed tool reduces the
defence the units are then chosen against. Units are picked to counter whichever
of the target's defences is proportionally weaker; tools are picked to cancel
the target's wall, gate, moat and defender bonuses in as few units as possible,
and are skipped entirely where the commander's own reductions already erase
them. A flank that ends up with tools but no units gives the tools back.

Fortification is per flank, not per castle: a defending tool raises only the
flank it stands on, and only the middle flank meets the gate at all. Tools are
also filtered by the target - many may only be carried against particular
kingdoms and area types, or not against camps.

See [`examples/fill_waves.py`](examples/fill_waves.py) for the whole path.

Alongside the waves comes the courtyard wave, the final assault that rides in
the same request. It holds units only, is sized from both levels rather than the
target's alone, and is filled against the defenders of the keep.

## Game State

A background thread applies server pushes to `client.state` while your code
reads it. Read through the accessors rather than touching the containers: each
one takes the state lock and returns a snapshot, so nothing changes underneath
you mid-iteration.

```python
player = client.state.get_local_player()      # None until login completes
castles = client.state.get_castles()
attacks = client.state.get_incoming_attacks()
inventory = client.state.get_inventory()
```

### Knowing whether state is fresh

Not every field is refreshed by every packet. Castle resources and units are
often populated once at login and never again unless you ask — so state can be
stale without being wrong. Check before trusting it:

```python
if client.state.get_castle_last_updated(castle_id) is None:
    # Never refreshed: resources and units are defaults, not measurements.
    client.castle.get_details(castle_id)
```

### Reacting to movements

```python
def on_attack(movement):
    print(f"{movement.troop_count} troops from {movement.source_player_name}, "
          f"{movement.time_remaining}s out")

def on_arrived(movement_id, movement):
    print(f"{movement_id} arrived: {movement}")

client.state.on_incoming_attack(on_attack)
client.state.on_movement_arrived(on_arrived)
```

Arrival and recall callbacks also accept a single-argument `(movement_id)`
form, but the movement is removed from state before they run, so the id alone
can no longer be resolved — prefer the two-argument form above.

> [!TIP]
> [`docs/design/state_management.md`](docs/design/state_management.md) documents
> the object-identity and freshness rules in full.

## Map Scanning

Scan a kingdom for castles, outposts and capitals. A full scan uses BFS
discovery from your castle's position and can take a few minutes:

```python
from empire_core import Kingdom, MapItemType

result = client.scan_kingdom(Kingdom.GREEN, item_types=[MapItemType.CASTLE])
print(f"{len(result.items)} items, {len(result.failed_chunks)} failed chunks")
```

`chunk_delay` (default `0.2`s) paces the requests — the server drops
connections that sustain a high request rate, so don't lower it for
long-running scans unless you know the server tolerates it.

> [!IMPORTANT]
> Always check `failed_chunks`. A partial scan is not an empty kingdom, and
> only this field tells them apart.

**Re-scanning cheaply.** `result.content_chunks` lists the chunks that held
items. Feed it back into `scan_chunks()` to re-scan a known region without
paying for BFS discovery again (roughly a third fewer requests), and run a full
`scan_kingdom()` periodically to pick up content in previously-empty chunks:

```python
discovery = client.scan_kingdom(Kingdom.GREEN, item_types=[MapItemType.CASTLE])

fresh = client.scan_chunks(
    Kingdom.GREEN, list(discovery.content_chunks), item_types=[MapItemType.CASTLE]
)
```

For very frequent scans, split `content_chunks` across several logged-in
accounts (interleaved slices `chunks[i::n]`) and run the `scan_chunks()` calls
concurrently — per-account request rate is what the server limits.

## Multiple Accounts

`AccountPool` hands out one logged-in client per account and refuses to lease
the same account twice. Prefer `leased()`: it releases the account and closes
the client even if your code raises.

```python
from empire_core import AccountPool, PoolExhaustedError

pool = AccountPool()
try:
    with pool.leased(tag="scanning") as client:
        result = client.scan_kingdom()
except PoolExhaustedError:
    ...   # no candidate account was free
```

Accounts come from `accounts.json` plus every `EMPIRE_ACCOUNT_*` environment
variable. A `.env` file is read only if you opt in with
`accounts.load(load_env_file=True)` — importing the library never mutates your
environment. See [`examples/account_pool.py`](examples/account_pool.py).

> [!CAUTION]
> `accounts.json` holds passwords in plain text. Keep it out of version control
> and `chmod 600` it; the library warns when it is group- or world-readable.

## Protocol Models

For lower-level access, use the protocol models directly:

```python
from empire_core.protocol.models import (
    AllianceChatMessageRequest,
    GetCastlesRequest,
)

request = AllianceChatMessageRequest.create("Hello 100%!")
packet = request.to_packet()
# -> "%xt%EmpireEx_21%acm%1%{"M": "Hello 100&percnt;!"}%"

client.send(request)                        # fire and forget
response = client.send(GetCastlesRequest(), wait=True)   # or await the reply
```

## Error Handling

Calls that wait for a response raise typed exceptions instead of returning
`None`, so a timeout, a dropped connection and a server-side rejection are
distinguishable. All inherit from `EmpireError`.

```python
from empire_core import CommandError, ConnectionClosedError, EmpireTimeoutError

try:
    castles = client.castle.get_all()
except CommandError as e:
    print(f"rejected: {e.command} code {e.code}")   # non-zero server error code
except EmpireTimeoutError:
    ...                                             # no response in time
except ConnectionClosedError:
    ...                                             # dropped while waiting
```

`EmpireTimeoutError` also subclasses the builtin `TimeoutError`. Action helpers
(e.g. `client.castle.select()`) return `bool` — `False` means the server
rejected the action, while transport failures still raise.

Two more you will meet: **`NetworkError`** from `connect()` and the CDN-backed
helpers, and **`PacketError`** when a response cannot be parsed. Catching
`EmpireError` covers every one of them — the library does not leak
`pydantic.ValidationError` or raw socket exceptions past its own API.

An empty collection therefore always means "nothing there", never "the lookup
failed": `get_active_events()` and `get_troop_ids()` raise on a CDN outage
rather than return empty. Where an exact answer depends on data that may be
missing, ask first:

```python
from empire_core import troop_data_available

if not troop_data_available():
    ...   # troop counts would include equipment; treat them as approximate
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for adding protocol commands and
services, model conventions, and testing guidelines.

## Architecture

```
empire_core/
├── client/          # EmpireClient — main entry point, map scanner
├── network/         # WebSocket connection, receive loop, redaction
├── protocol/
│   ├── models/      # Pydantic request/response models per command
│   └── packet.py    # Low-level frame parsing
├── services/        # High-level APIs attached to the client
├── state/           # Thread-safe game state and world models
├── storage/         # Experimental persistence (optional extra)
└── utils/           # Enums, CDN-backed event and troop data
```

Design notes live in [`docs/design/`](docs/design/).

---

<p align="center">
  <sub>For educational purposes only. Use responsibly.</sub>
</p>
