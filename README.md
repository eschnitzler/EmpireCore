# EmpireCore

Modern async Python library for Goodgame Empire automation.

## Features

- **Async/Await** - Built on asyncio and aiohttp
- **Type Safe** - Full type hints with Pydantic models
- **State Tracking** - Player, castles, resources, movements, quests
- **Game Actions** - Attacks, transports, building, recruiting
- **Automation** - Farming bots, schedulers, multi-account support
- **Battle Simulation** - Calculate attack outcomes before sending

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
import asyncio
from empire_core import EmpireClient, EmpireConfig

async def main():
    config = EmpireConfig(username="YourUsername", password="YourPassword")
    client = EmpireClient(config)
    
    await client.login()
    await client.get_detailed_castle_info()
    
    player = client.state.local_player
    print(f"Logged in as {player.name}, Level {player.level}")
    
    for castle_id, castle in player.castles.items():
        r = castle.resources
        print(f"{castle.name}: {r.wood}/{r.wood_cap} wood (+{r.wood_rate}/h)")
    
    # Track movements
    await client.refresh_movements()
    for attack in client.get_incoming_attacks():
        print(f"Incoming attack! Arrives in {attack.format_time_remaining()}")
    
    await client.close()

asyncio.run(main())
```

## Core Features

### State Tracking
- Player info (level, XP, alliance, gold, rubies)
- Castle state (resources, buildings, population, production rates)
- Movement tracking (attacks, transports, returns)
- Quest and battle report tracking

### Actions
- Send attacks and transports
- Build/upgrade buildings
- Recruit units
- Response validation with timeouts

### Utilities
- Distance and travel time calculations
- Battle simulation with loss prediction
- Movement and resource helpers
- Time formatting

### Automation
- Target finder with filters
- Task scheduler with priorities
- Multi-account manager
- Farming bot framework

## Project Structure

```
EmpireCore/
├── src/empire_core/
│   ├── client/       # Client, actions, commands
│   ├── network/      # WebSocket connection
│   ├── protocol/     # Packet encoding/decoding
│   ├── state/        # Game state models
│   ├── events/       # Event system
│   ├── utils/        # Calculations, helpers
│   ├── automation/   # Bots, scheduling
│   └── storage/      # Database integration
├── examples/         # Example scripts
├── tests/            # Test suite
└── docs/             # Documentation
```

## Examples

See the `examples/` directory:
- `demo.py` - Basic usage
- `movement_tracker.py` - Track army movements
- `simple_farm_bot.py` - Automated farming
- `resource_monitor_bot.py` - Resource monitoring

## Testing

```bash
python -m pytest tests/
```

## Disclaimer

For educational purposes only. Use at your own risk.
