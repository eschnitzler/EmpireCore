<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/pydantic-v2-purple.svg" alt="Pydantic v2">
  <img src="https://img.shields.io/badge/tool-uv-orange.svg" alt="UV">
  <img src="https://img.shields.io/badge/status-WIP-red.svg" alt="Work in Progress">
</p>

<h1 align="center">EmpireCore</h1>

<p align="center">
  <strong>Fully typed Python API for Goodgame Empire</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#roadmap">Roadmap</a>
</p>

---

> **Warning: Work in Progress**
> 
> This library is under active development. APIs may change, and some features are incomplete or untested.

---

## Features

| Category | Capabilities |
|----------|-------------|
| **Connection** | WebSocket with threading, auto-reconnect, keepalive, login cooldown handling |
| **State Tracking** | Player, castles, resources, movements |
| **Protocol** | Packet parsing (XML handshake, XT/JSON game data) |
| **Models** | Pydantic models for type-safe game data |

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
git clone https://github.com/eschnitzler/EmpireCore.git
cd EmpireCore
uv sync
```

## Quick Start

```python
from empire_core import EmpireClient

client = EmpireClient(username="your_user", password="your_pass")
client.login()

movements = client.get_movements()
print(f"Found {len(movements)} movements")

for m in client.get_incoming_attacks():
    print(f"Incoming attack! {m.time_remaining}s remaining")

client.close()
```

## Roadmap

### Done

- [x] **Sync Connection** - WebSocket with `websocket-client`, receive thread, keepalive thread
- [x] **Message Routing** - Waiters (request/response) and Subscribers (pub/sub for events)
- [x] **EmpireClient** - Login sequence, basic commands (get_movements, send_alliance_chat)
- [x] **Packet Protocol** - XML and XT packet parsing
- [x] **State Models** - Player, Castle, Movement, MapObject with Pydantic

### In Progress

- [ ] **Alliance Chat Detection** - Identify incoming chat packet command ID
- [ ] **State Manager Sync** - Port GameState from async to sync

### Planned

- [ ] **More Commands** - search_alliance, get_alliance_members, attack, transport, etc.
- [ ] **AccountPool** - Manage multiple accounts for parallel operations
- [ ] **Dreambot Integration** - Use from Discord.py via thread pool

### Archived (for later)

The following async services are archived in `_archive/` for future porting as needed:

- `AllianceService`, `ChatService` - Alliance management and chat
- `MapScanner` - World map scanning
- `ResourceManager`, `BuildingManager`, `UnitManager` - Automation
- `DefenseManager`, `QuestService`, `BattleReportService` - Game automation
- `EventManager` - Async event system

---

<p align="center">
  <sub>For educational purposes only. Use responsibly.</sub>
</p>
