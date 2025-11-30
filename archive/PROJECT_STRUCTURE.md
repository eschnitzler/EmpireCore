# EmpireCore - Project Structure

```
EmpireCore/
│
├── 📁 src/empire_core/           # Main library code
│   ├── 📁 client/                # High-level API
│   │   ├── __init__.py
│   │   └── client.py             # EmpireClient class (222 lines)
│   │
│   ├── 📁 network/               # WebSocket layer
│   │   ├── __init__.py
│   │   └── connection.py         # SFSConnection (async I/O)
│   │
│   ├── 📁 protocol/              # Packet parsing
│   │   ├── __init__.py
│   │   └── packet.py             # Packet model (XML + %xt%)
│   │
│   ├── 📁 state/                 # Game state management
│   │   ├── __init__.py
│   │   ├── manager.py            # GameState (packet handlers)
│   │   ├── models.py             # Player, Castle, Resources
│   │   └── world_models.py       # MapObject, Movement
│   │
│   ├── 📁 events/                # Event system
│   │   ├── __init__.py
│   │   ├── base.py               # PacketEvent
│   │   └── manager.py            # EventManager
│   │
│   ├── 📁 utils/                 # Utilities
│   │   ├── __init__.py
│   │   ├── crypto.py             # Password hashing
│   │   ├── decorators.py         # Error handling
│   │   └── enums.py              # GGEServer enum
│   │
│   ├── __init__.py               # Package exports
│   ├── config.py                 # EmpireConfig (Pydantic)
│   └── exceptions.py             # Custom exceptions
│
├── 📁 tests/                     # Test files
│   ├── real_network_test.py      # ✅ Live server test
│   ├── manual_network_test.py    # ✅ Mock server test
│   ├── test_events.py
│   ├── test_handshake.py
│   └── test_state_population.py
│
├── 📁 examples/                  # Example bots
│   └── resource_monitor_bot.py   # ✅ Working bot
│
├── 📁 docs/                      # Documentation
│   └── 📁 design/
│       ├── architecture.md       # System architecture
│       ├── protocol.md           # Protocol specification
│       ├── state_management.md   # State layer design
│       ├── events.md             # Event system
│       ├── dreambot_analysis.md  # Reference code analysis
│       └── game_bundle_analysis.md
│
├── 📄 demo.py                    # ✅ Full feature demo
├── 📄 pyproject.toml             # Poetry configuration
├── 📄 README.md                  # Project overview
├── 📄 DEV_CONTEXT.md             # Developer instructions
├── 📄 STATUS.md                  # ✅ Development status
├── �� QUICKSTART.md              # ✅ Quick reference
├── 📄 HANDOFF.md                 # ✅ Session summary
└── 📄 PROJECT_STRUCTURE.md       # This file

```

## 📊 Code Statistics

| Component | Lines | Status |
|-----------|-------|--------|
| Client Layer | ~222 | ✅ Complete |
| Network Layer | ~150 | ✅ Complete |
| Protocol Layer | ~120 | ✅ Complete |
| State Layer | ~250 | ✅ Core Complete |
| Event System | ~80 | ✅ Complete |
| Utils | ~100 | ✅ Complete |
| Config | ~50 | ✅ Complete |
| **Total** | **~1,065** | **Phase 1 Complete** |

## 🎯 Key Files to Know

### For Adding Features
- `src/empire_core/client/client.py` - Add new API methods here
- `src/empire_core/state/manager.py` - Add packet handlers here
- `src/empire_core/state/models.py` - Add new data models here

### For Understanding Code
- `demo.py` - See working example
- `STATUS.md` - Check what's done
- `QUICKSTART.md` - API reference

### For Development
- `DEV_CONTEXT.md` - Architecture rules
- `docs/design/architecture.md` - System design
- `docs/design/protocol.md` - Protocol details

## 🔧 Development Workflow

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Run tests
python tests/real_network_test.py

# 3. Run demo
python demo.py

# 4. Make changes
# Edit src/empire_core/...

# 5. Test changes
python demo.py
```

## 📦 Dependencies

```toml
[tool.poetry.dependencies]
python = "^3.10"
aiohttp = "^3.9"      # WebSocket client
pydantic = "^2.5"     # Data validation

[tool.poetry.dev-dependencies]
pytest = "^7.0"
pytest-asyncio = "^0.23"
black = "^24.0"
isort = "^5.13"
mypy = "^1.8"
```

## 🎓 Layer Responsibilities

```
┌─────────────────────────────────────┐
│ CLIENT: High-level API              │
│ - login(), get_map_chunk()          │
│ - User-facing methods               │
└─────────────────────────────────────┘
              ↓ uses
┌─────────────────────────────────────┐
│ STATE: Game world representation    │
│ - Player, Castle, MapObject         │
│ - update_from_packet()              │
└─────────────────────────────────────┘
              ↓ reads
┌─────────────────────────────────────┐
│ PROTOCOL: Packet parsing            │
│ - XML, %xt% format                  │
│ - JSON extraction                   │
└─────────────────────────────────────┘
              ↓ uses
┌─────────────────────────────────────┐
│ NETWORK: WebSocket I/O              │
│ - connect(), send(), receive()      │
│ - Raw bytes                         │
└─────────────────────────────────────┘
```

## 🧩 Module Dependencies

```
client.py
  ├── network.connection
  ├── protocol.packet
  ├── state.manager
  ├── events.manager
  └── config

state/manager.py
  ├── state.models
  └── state.world_models

network/connection.py
  ├── aiohttp (external)
  └── protocol.packet
```

## 📝 Naming Conventions

- **Files:** `snake_case.py`
- **Classes:** `PascalCase`
- **Functions:** `snake_case()`
- **Constants:** `UPPER_CASE`
- **Private:** `_leading_underscore`

## 🎨 Code Style

- **Line Length:** 88 characters (Black default)
- **Type Hints:** Required on all public APIs
- **Docstrings:** Google style
- **Imports:** Sorted with isort

## 🔍 Finding Things

**To find command handlers:**
```bash
grep -r "_handle_" src/empire_core/state/
```

**To find event usage:**
```bash
grep -r "@client.event" .
```

**To find packet formats:**
```bash
grep -r "%xt%" src/empire_core/
```

## 🚀 Quick Commands

```bash
# Find all TODO items
grep -r "TODO\|FIXME" src/

# Count lines by module
find src -name "*.py" -exec wc -l {} +

# List all models
grep "^class" src/empire_core/state/*.py

# List all client methods
grep "async def" src/empire_core/client/client.py
```

---

**Last Updated:** 2025-11-30  
**Status:** ✅ Foundation Complete, Ready for Feature Development
