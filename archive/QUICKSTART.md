# EmpireCore Quick Reference

## Installation

```bash
# Clone repository
git clone <repo-url>
cd EmpireCore

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install aiohttp pydantic
```

## Basic Usage

### 1. Simple Login

```python
import asyncio
from empire_core import EmpireClient
from empire_core.config import EmpireConfig

async def main():
    config = EmpireConfig(username="your_username", password="your_password")
    client = EmpireClient(config)
    
    await client.login()
    print(f"Logged in as {client.state.local_player.name}")
    
    await client.close()

asyncio.run(main())
```

### 2. Event Handlers

```python
@client.event
async def on_gbd(event):
    """Fires when big data packet arrives (player info, castles, etc.)"""
    player = client.state.local_player
    print(f"Level {player.level} | Gold: {player.gold}")

@client.event
async def on_packet(event):
    """Fires for EVERY packet"""
    print(f"Packet: {event.command_id}")

@client.event
async def on_gam(event):
    """Fires when movement data arrives"""
    print(f"Movements: {len(client.state.movements)}")
```

### 3. Query Game State

```python
await client.login()
await asyncio.sleep(2)  # Wait for initial data

# Access player data
player = client.state.local_player
print(f"Name: {player.name}")
print(f"Level: {player.level}")
print(f"Gold: {player.gold}")
print(f"Rubies: {player.rubies}")

# Access castles
for castle_id, castle in player.castles.items():
    print(f"Castle: {castle.name} in K{castle.KID}")

# Access map data
for obj_id, obj in client.state.map_objects.items():
    print(f"Map Object at ({obj.X}, {obj.Y}): Type {obj.T}")
```

### 4. Request Data

```python
# Get detailed castle info (resources, units, buildings)
await client.get_detailed_castle_info()
await asyncio.sleep(1)  # Wait for response

# Get army movements
await client.get_movements()
await asyncio.sleep(1)

# Get map chunk
await client.get_map_chunk(kingdom=0, x=100, y=100)
await asyncio.sleep(1)
```

## Configuration Options

```python
from empire_core.config import EmpireConfig, GGEServer

config = EmpireConfig(
    username="player",
    password="pass123",
    server=GGEServer.US1,  # or EU1, EU2, etc.
    game_version="166",
    default_zone="EmpireEx_21",
    request_timeout=5.0,
    login_timeout=10.0
)
```

## Common Patterns

### Monitor Incoming Attacks

```python
@client.event
async def on_gam(event):
    """Check for incoming attacks"""
    for movement_id, movement in client.state.movements.items():
        if movement.is_incoming:
            print(f"⚠️ Attack incoming! ETA: {movement.arrival_time}s")
```

### Track Resource Production

```python
import time

async def monitor_resources():
    while True:
        player = client.state.local_player
        print(f"Gold: {player.gold:,}")
        await asyncio.sleep(60)  # Check every minute

# Run in background
asyncio.create_task(monitor_resources())
```

### Keep Connection Alive

```python
async def main():
    await client.login()
    
    try:
        while True:
            await asyncio.sleep(30)  # Heartbeat every 30s
            # Server sends updates automatically
    except KeyboardInterrupt:
        pass
    finally:
        await client.close()
```

## Data Models

### Player

```python
player = client.state.local_player

player.id           # int - Player ID
player.name         # str - Player name
player.level        # int - Current level
player.legendary_level  # int - Legendary level
player.xp           # int - Experience points
player.gold         # int - Gold amount
player.rubies       # int - Rubies amount
player.castles      # Dict[int, Castle] - Player's castles
```

### Castle

```python
castle = player.castles[castle_id]

castle.OID          # int - Castle/Area ID
castle.N            # str - Castle name
castle.KID          # int - Kingdom ID (0=Green, 1=Desert, 2=Ice, 3=Fire)
castle.resources    # Resources - Food, wood, stone, etc.
```

### MapObject

```python
obj = client.state.map_objects[area_id]

obj.AID             # int - Area ID
obj.OID             # int - Owner ID
obj.T               # int - Type (castle, robber, etc.)
obj.X               # int - X coordinate
obj.Y               # int - Y coordinate
obj.KID             # int - Kingdom ID
```

## Error Handling

```python
from empire_core.exceptions import LoginError, LoginCooldownError, TimeoutError

try:
    await client.login()
except LoginCooldownError as e:
    print(f"Login cooldown active. Wait {e.cooldown}s")
except TimeoutError:
    print("Connection timeout")
except LoginError as e:
    print(f"Login failed: {e}")
```

## Debugging

### Enable Debug Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

### Inspect Packets

```python
@client.event
async def on_packet(event):
    if event.command_id == "lli":  # Login response
        print(f"Login packet payload: {event.payload}")
```

### View Raw Connection Data

```python
# In connection.py, the read loop logs all raw packets at DEBUG level
# Set logging level to DEBUG to see them
```

## Architecture

```
EmpireCore/
├── src/empire_core/
│   ├── network/        # WebSocket connection
│   ├── protocol/       # SFS packet parsing
│   ├── state/          # Game state management
│   ├── client/         # High-level API
│   ├── events/         # Event system
│   ├── utils/          # Helpers (crypto, decorators)
│   └── config.py       # Configuration
├── tests/              # Test files
├── docs/               # Documentation
├── demo.py            # Working example
└── STATUS.md          # Development status
```

## Layer Boundaries

**DO NOT:**
- Use network operations in state layer
- Parse packets in client layer
- Include game logic in network layer

**DO:**
- Keep layers separate
- Use events for cross-layer communication
- Add new handlers in appropriate layer

## Next Steps for Developers

1. **Add more packet handlers** in `state/manager.py`
2. **Implement actions** (attack, transport) in `client/client.py`
3. **Create utilities** (calculators, helpers) in `utils/`
4. **Build bots** using the client API

## Resources

- **Protocol docs:** `docs/design/protocol.md`
- **Architecture:** `docs/design/architecture.md`
- **Game bundle:** Search for command strings (e.g., "lli", "att") to find payload formats
- **Status:** `STATUS.md` for current development state
