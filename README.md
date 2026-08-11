<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/pydantic-v2-purple.svg" alt="Pydantic v2">
  <img src="https://img.shields.io/badge/tool-uv-orange.svg" alt="UV">
  <img src="https://img.shields.io/badge/status-WIP-red.svg" alt="Work in Progress">
</p>

<h1 align="center">EmpireCore</h1>

<p align="center">
  <strong>Fully typed Python library for Goodgame Empire</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#services">Services</a> •
  <a href="#contributing">Contributing</a>
</p>

---

> **Warning: Work in Progress**
> 
> This library is under active development. APIs may change, and some features are incomplete or untested.

---

## Features

| Category | Description |
|----------|-------------|
| **Connection** | Synchronous WebSocket with a background receive thread and keepalive |
| **Protocol Models** | Pydantic models for all GGE commands with type-safe request/response handling |
| **Services** | High-level APIs for alliance, castle, and more - auto-attached to client |
| **State Tracking** | Player, castles, resources, movements |

## Installation

```bash
# Using uv (recommended)
uv add empire-core

# Or with pip
pip install empire-core
```

For development:

```bash
git clone https://github.com/eschnitzler/EmpireCore.git
cd EmpireCore
uv sync --extra dev
```

(`dev` is an extra, not a default group — a plain `uv sync` removes pytest,
ruff and mypy from the environment.)

The experimental `empire_core.storage` package needs the `storage` extra
(`pip install empire-core[storage]`); the core client does not depend on it.

## Quick Start

```python
from empire_core import EmpireClient

client = EmpireClient(username="your_user", password="your_pass")
client.login()

# Services are auto-attached to the client
client.alliance.send_chat("Hello alliance!")
client.alliance.help_all()

castles = client.castle.get_all()
for c in castles:
    print(f"{c.castle_name} at ({c.x}, {c.y})")

client.close()
```

## Services

Services provide high-level APIs and are automatically attached to the client.

### AllianceService (`client.alliance`)

```python
# Send chat message
client.alliance.send_chat("Hello!")

# Get chat history
history = client.alliance.get_chat_log()
for entry in history:
    print(f"{entry.player_name}: {entry.decoded_text}")

# Help all members
response = client.alliance.help_all()
print(f"Helped {response.helped_count} members")

# Subscribe to incoming messages
def on_message(msg):
    print(f"[{msg.player_name}] {msg.decoded_text}")

client.alliance.on_chat_message(on_message)
```

### CastleService (`client.castle`)

```python
# Get all castles
castles = client.castle.get_all()

# Get detailed info (None when the response omits the castle)
details = client.castle.get_details(castle_id=12345)
if details:
    print(f"Buildings: {len(details.buildings)}")

# Select a castle
client.castle.select(castle_id=12345)

# Get resources (None when unavailable)
resources = client.castle.get_resources(castle_id=12345)
if resources:
    print(f"Wood: {resources.wood}, Stone: {resources.stone}")
```

## Map Scanning

Scan a kingdom for castles, outposts, capitals, etc. A full scan uses BFS
discovery from your castle's position and can take a few minutes:

```python
from empire_core import Kingdom, MapItemType

result = client.scan_kingdom(Kingdom.GREEN, item_types=[MapItemType.CASTLE])
print(f"{len(result.items)} items, {len(result.failed_chunks)} failed chunks")
```

`chunk_delay` (default `0.2`s) paces the requests — the server drops
connections that sustain a high request rate, so don't lower it for
long-running scans unless you know the server tolerates it.

**Re-scanning cheaply**: `result.content_chunks` lists the chunks that
contained items. Feed it back into `scan_chunks()` to re-scan a known
region without paying for BFS discovery of the empty boundary again
(roughly a third fewer requests). Run a full `scan_kingdom()` periodically
to pick up content that appeared in previously-empty chunks:

```python
# Discovery scan (expensive, occasionally)
discovery = client.scan_kingdom(Kingdom.GREEN, item_types=[MapItemType.CASTLE])

# Targeted re-scans (cheap, frequently)
fresh = client.scan_chunks(
    Kingdom.GREEN, list(discovery.content_chunks), item_types=[MapItemType.CASTLE]
)
```

For very frequent scans, split `content_chunks` across multiple logged-in
accounts (e.g. interleaved slices `chunks[i::n]`) and run the
`scan_chunks()` calls concurrently — per-account request rate is what the
server rate-limits.

## Protocol Models

For lower-level access, use protocol models directly:

```python
from empire_core.protocol.models import (
    AllianceChatMessageRequest,
    GetCastlesRequest,
    parse_response,
)

# Build a request
request = AllianceChatMessageRequest.create("Hello 100%!")
packet = request.to_packet()
# -> "%xt%EmpireEx_21%acm%1%{"M": "Hello 100&percnt;!"}%"

# Fire-and-forget (no response awaited)
client.send(request)

# Or wait for and parse the response
response = client.send(GetCastlesRequest(), wait=True)
```

## Error Handling

Calls that wait for a response raise typed exceptions on failure instead of
returning `None` — so a timeout, a dropped connection, and a server-side
rejection are distinguishable. All inherit from `EmpireError`.

```python
from empire_core import CommandError, EmpireTimeoutError, ConnectionClosedError

try:
    castles = client.castle.get_all()
except CommandError as e:
    # Server answered with a non-zero error code
    print(f"rejected: {e.command} code {e.code}")
except EmpireTimeoutError:
    # No response within the timeout
    ...
except ConnectionClosedError:
    # Connection dropped while waiting
    ...
```

`EmpireTimeoutError` also subclasses the builtin `TimeoutError`, so
`except TimeoutError` works too. Action helpers (e.g. `client.castle.select()`)
return `bool` — `False` means the server rejected the action, while transport
failures still raise.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Adding new protocol commands
- Creating new services
- Protocol model conventions
- Testing guidelines

## Architecture

```
empire_core/
├── client/          # EmpireClient - main entry point
├── protocol/
│   └── models/      # Pydantic models for GGE commands
├── services/        # High-level service APIs
├── state/           # Game state models
└── network/         # WebSocket connection
```

---

<p align="center">
  <sub>For educational purposes only. Use responsibly.</sub>
</p>
