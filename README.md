# EmpireCore

**The definitive Python library for Goodgame Empire automation.**

Modern, type-safe, async/await Python library for building bots and automation tools for Goodgame Empire.

## ✨ Features

- 🚀 **Modern Python** - Async/await, type hints, Pydantic models
- 🎯 **100% Feature Parity** - Everything pygge does, plus 10 bonus features
- 🛡️ **Type Safe** - Full type hints and Pydantic validation
- 📦 **60+ Features** - Comprehensive state tracking, actions, automation
- 🤖 **Automation Ready** - Built-in farming bots, schedulers, multi-account
- 📊 **Battle Simulation** - Calculate attack outcomes
- 💾 **Database Storage** - Track historical data
- 🔧 **Easy to Use** - Clean API with helper functions

## 📦 Installation

```bash
# Clone the repository
git clone <repo-url>
cd EmpireCore

# Install dependencies
pip install -r requirements.txt

# Or use poetry
poetry install
```

## 🚀 Quick Start

```python
import asyncio
from empire_core import EmpireClient, EmpireConfig

async def main():
    # Create client
    config = EmpireConfig(username="YourUsername", password="YourPassword")
    client = EmpireClient(config)
    
    # Login
    await client.login()
    
    # Get player state
    await client.get_detailed_castle_info()
    player = client.state.local_player
    
    print(f"Logged in as {player.name}, Level {player.level}")
    print(f"Gold: {player.gold}, Rubies: {player.rubies}")
    
    # Send an attack
    await client.send_attack(
        origin_castle_id=12345,
        target_area_id=67890,
        units={620: 100}  # 100 militia
    )
    
    # Close connection
    await client.close()

asyncio.run(main())
```

## 📚 Core Features

### State Tracking
- Player info (level, XP, alliance, resources)
- Castle state (resources, buildings, population, production rates)
- Movement tracking (attacks, transports, progress)
- Quest tracking
- Battle reports
- Army composition

### Actions
- Send attacks
- Transport resources
- Build/upgrade buildings
- Recruit units
- Cancel operations
- Speed up with rubies
- Response validation (optional)

### Utilities
- Distance & travel time calculations
- Resource production estimates
- Helper classes (Castle, Movement, Resource, Player)
- Time formatting
- Battle simulation
- Keep level calculator

### Automation
- Target finder (find nearby targets)
- World scanner (map exploration)
- Farming bots
- Resource collectors
- Building queue management
- Task scheduler
- Multi-account support

## 🤖 Automation Example

```python
from empire_core import EmpireClient, EmpireConfig
from empire_core.automation import FarmingBot, TaskScheduler

async def main():
    client = EmpireClient(EmpireConfig(username="...", password="..."))
    await client.login()
    
    # Setup farming bot
    farm_bot = FarmingBot(client)
    farm_bot.farm_interval = 300  # 5 minutes
    farm_bot.max_distance = 30.0
    
    # Setup scheduler
    scheduler = TaskScheduler()
    scheduler.add_task("farm", farm_bot._farm_cycle, interval=300)
    scheduler.add_task("refresh", client.get_detailed_castle_info, interval=600)
    
    # Run forever
    await scheduler.start()

asyncio.run(main())
```

## 📖 Documentation

- [Feature Comparison](docs/PYGGE_COMPARISON.md) - Compare with pygge
- [Feature Parity](docs/FEATURE_PARITY.md) - Complete feature checklist
- [API Documentation](docs/API.md) - Full API reference
- [Examples](examples/) - Working examples

## 🏗️ Project Structure

```
EmpireCore/
├── src/empire_core/
│   ├── client/          # Client and game actions
│   ├── network/         # WebSocket connection
│   ├── protocol/        # Packet handling
│   ├── state/           # Game state models
│   ├── events/          # Event system
│   ├── utils/           # Utilities and helpers
│   ├── automation/      # Automation bots
│   └── storage/         # Database storage
├── examples/            # Example scripts
├── tests/               # Test suite
└── docs/                # Documentation
```

## 🎯 Comparison with pygge

| Feature | EmpireCore | pygge |
|---------|-----------|-------|
| **Total Features** | **60** | 50 |
| Type Hints | ✅ 100% | ❌ 10% |
| Async/Await | ✅ Modern | ⚠️ Twisted |
| Data Models | ✅ Pydantic | ⚠️ Dicts |
| Response Validation | ✅ Yes | ❌ No |
| Task Scheduler | ✅ Yes | ❌ No |
| Helper Classes | ✅ Yes | ❌ No |

**EmpireCore exceeds pygge in features (60 vs 50) and code quality!**

## 🧪 Testing

```bash
# Run tests
python -m pytest tests/

# Run specific test
python tests/test_response_awaiter.py
```

## 📝 License

MIT License - See LICENSE file

## 🤝 Contributing

Contributions welcome! Please read CONTRIBUTING.md first.

## ⚠️ Disclaimer

This library is for educational purposes only. Use at your own risk. The authors are not responsible for any consequences of using this library.

## 🌟 Star History

If you find this library useful, please consider giving it a star! ⭐
