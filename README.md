<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/asyncio-powered-green.svg" alt="Asyncio">
  <img src="https://img.shields.io/badge/pydantic-v2-purple.svg" alt="Pydantic v2">
  <img src="https://img.shields.io/badge/status-WIP-red.svg" alt="Work in Progress">
</p>

<h1 align="center">EmpireCore</h1>

<p align="center">
  <strong>Modern async Python library for Goodgame Empire automation</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#examples">Examples</a> •
  <a href="#documentation">Documentation</a>
</p>

---

> **⚠️ Work in Progress**
> 
> This library is under active development. APIs may change, and some features are incomplete or untested. Use at your own risk.

---

## Features

| Category | Capabilities |
|----------|-------------|
| **Connection** | WebSocket, auto-reconnect, login cooldown handling |
| **State Tracking** | Player, castles, resources, buildings, units, movements |
| **Actions** | Attacks, transports, recruiting, building, with response validation |
| **Automation** | Farming bots, task scheduler, multi-account, target finder |
| **Analysis** | Battle simulation, travel time calc, resource forecasting |

## Installation

```bash
git clone https://github.com/eschnitzler/EmpireCore.git
cd EmpireCore
pip install -r requirements.txt
```

## Configuration

To use the test scripts or manage multiple accounts, create a `accounts.json` file in the root directory. You can use the provided template:

```bash
cp accounts.json.template accounts.json
```

Then edit `accounts.json` with your credentials:

```json
[
    {
        "username": "YourUsername",
        "password": "YourPassword"
    }
]
```

This file is git-ignored to keep your credentials safe.

## Quick Start

```python
import asyncio
from empire_core import EmpireClient, EmpireConfig

async def main():
    client = EmpireClient(EmpireConfig(
        username="YourUsername",
        password="YourPassword"
    ))
    
    await client.login()
    await client.get_detailed_castle_info()
    
    player = client.state.local_player
    print(f"{player.name} | Level {player.level} | {player.gold} gold")
    
    for cid, castle in player.castles.items():
        r = castle.resources
        print(f"  {castle.name}: {r.wood}/{r.wood_cap} wood (+{r.wood_rate}/h)")
    
    await client.close()

asyncio.run(main())
```

## Movement Tracking

```python
# Refresh and monitor army movements
await client.refresh_movements()

# Query movements
incoming = client.get_incoming_attacks()      # Attacks against you
outgoing = client.get_outgoing_movements()    # Your attacks/transports
returning = client.get_returning_movements()  # Armies coming home

# Get details
for attack in incoming:
    print(f"Incoming attack! Arrives in {attack.format_time_remaining()}")
    print(f"  From: {attack.source_area_id} -> {attack.target_area_id}")

# Event-driven alerts
@client.event
async def on_incoming_attack(event):
    print(f"ALERT: Attack detected! {event.movement.format_time_remaining()}")
```

## Automation

```python
from empire_core.automation import FarmingBot, TaskScheduler

async def main():
    client = EmpireClient(config)
    await client.login()
    
    # Configure farming
    bot = FarmingBot(client)
    bot.max_distance = 30.0
    bot.farm_interval = 300
    
    # Schedule tasks
    scheduler = TaskScheduler()
    scheduler.add_task("farm", bot._farm_cycle, interval=300)
    scheduler.add_task("refresh", client.get_detailed_castle_info, interval=600)
    
    await scheduler.start()
```

## Examples

| Script | Description |
|--------|-------------|
| [`demo.py`](examples/demo.py) | Basic connection and state access |
| [`movement_tracker.py`](examples/movement_tracker.py) | Real-time movement monitoring |
| [`simple_farm_bot.py`](examples/simple_farm_bot.py) | Automated barbarian farming |
| [`resource_monitor_bot.py`](examples/resource_monitor_bot.py) | Resource level monitoring |

## Project Structure

```
src/empire_core/
├── client/       # EmpireClient, actions, commands
├── network/      # WebSocket connection handling
├── protocol/     # Packet encoding/decoding
├── state/        # Game state models (Pydantic)
├── events/       # Event emitter system
├── utils/        # Calculations, helpers, battle sim
├── automation/   # Bots, scheduler, multi-account
└── storage/      # SQLite database integration
```

## Documentation

- [`docs/protocol.md`](docs/design/protocol.md) - Protocol specification
- [`docs/architecture.md`](docs/design/architecture.md) - System architecture
- [`docs/events.md`](docs/design/events.md) - Event system guide
- [`STATUS.md`](STATUS.md) - Feature status and roadmap

## Testing

```bash
# Run all tests
python -m pytest tests/

# Run specific test
python -m pytest tests/test_events.py -v
```

---

<p align="center">
  <sub>For educational purposes only. Use responsibly.</sub>
</p>
