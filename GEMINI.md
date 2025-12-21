# EmpireCore - AI Context File

## Project Overview
**EmpireCore** is a modern, async Python library for automating the browser game *Goodgame Empire*.
It provides a high-level, type-safe API for interacting with the game server via WebSocket (SmartFoxServer protocol).

**Goal:** Provide a robust "High Level API" for developers to build bots, tools, and analyzers without dealing with raw packets.

---

## Core Architecture

### 1. Account System (`empire_core.accounts`)
The entry point for all automation.
*   **`AccountRegistry` (`accounts`)**: Singleton that loads credentials from `accounts.json` and environment variables.
*   **`Account`**: Represents a game account. Has methods to create a client.
*   **Usage:**
    ```python
    from empire_core import accounts
    account = accounts.get_default()
    client = account.get_client()
    ```

### 2. The Client (`empire_core.client`)
*   **`EmpireClient`**: The central coordinator. It manages the connection and state.
*   **Composition over Inheritance**: Features are exposed via composed services, not mixins.
    *   `client.quests` -> `QuestService`
    *   `client.reports` -> `BattleReportService`
    *   `client.alliance` -> `AllianceService`
    *   `client.chat` -> `ChatService`
    *   `client.defense` -> `DefenseService`
    *   `client.scanner` -> `MapScanner`
    *   `client.resources` -> `ResourceManager`

### 3. State Management (`empire_core.state`)
*   **`GameState`**: The source of truth. Updated automatically by incoming packets.
*   **Models**: Pydantic models in `empire_core.state.models` (Player, Castle, Building) and `world_models` (MapObject, Movement).
*   **Access:** `client.state.local_player`, `client.state.castles`, etc.

### 4. Automation & Tasks (`empire_core.automation`)
*   **`tasks.loop`**: A decorator (similar to `discord.ext.tasks`) for running background loops.
*   **Tools**:
    *   `TargetFinder`: Scans map objects.
    *   `MapScanner`: Handles spiral scanning logic.
    *   `MultiAccountManager`: Manages a pool of clients.

### 5. Network & Protocol
*   **`SFSConnection`**: Handles WebSocket I/O and SFS handshake.
*   **`Packet`**: Represents a parsed game packet (JSON or XML payload).
*   **Events**: The client emits typed events (e.g., `PacketEvent`) that can be listened to via `@client.event`.

---

## Usage Patterns

### Initialization
```python
from empire_core import accounts
from empire_core.client.client import EmpireClient

async def main():
    # 1. Get Account
    account = accounts.get_default()
    
    # 2. Get Client
    client = account.get_client()
    
    # 3. Login
    await client.login()
    
    # 4. Initial Data
    await client.get_detailed_castle_info()
```

### Automation Loop
```python
from empire_core.automation import tasks

@tasks.loop(minutes=5)
async def farm_loop():
    # Logic using client...
    pass

farm_loop.start()
```

### Service Usage
```python
# Quests
await client.quests.refresh_quests()
summary = client.quests.get_daily_quest_summary()

# Reports
reports = await client.reports.fetch_recent_reports()

# Alliance
members = await client.alliance.get_online_members()
```

---

## Development Guidelines

1.  **Type Hints**: Strict usage of Python type hints is mandatory.
2.  **Async/Await**: The library is fully async. Do not use blocking calls.
3.  **Clean API**: Avoid "God Objects". Use Services/Managers for new features.
4.  **Accounts**: Always use `empire_core.accounts`. Never hardcode credentials.
5.  **Logging**: Use the `logging` module, not `print`.

## Key File Locations
*   `src/empire_core/client/client.py`: Main client class.
*   `src/empire_core/accounts.py`: Account management.
*   `src/empire_core/state/manager.py`: State update logic.
*   `src/empire_core/protocol/packet.py`: Packet parsing.
*   `examples/`: Reference implementations.
