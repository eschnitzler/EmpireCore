# EmpireCore Refactor Plan

## Problem Statement

EmpireCore is currently async-first, which causes issues when integrated with Discord.py:
- Both libraries fight for the event loop
- Long-running operations (map scanning) block Discord's interaction responses
- Results in random 404 "Unknown interaction" errors on slash commands

## Goals

1. **Sync + Threading architecture** - Each client runs in its own thread with a sync websocket
2. **Clean API** - High-level methods like `client.search_alliance(name)` instead of raw packet building
3. **Sane logging** - WARNING by default, not flooding with DEBUG
4. **Proper message routing** - One RecvThread routes responses to waiters and broadcasts events
5. **AccountPool** - Proper worker pool for parallel operations

---

## Phase 1: Sync Connection Layer

### 1.1 Replace `SFSConnection`
Replace async `SFSConnection` with a sync version using `websocket-client`:

```python
class Connection:
    def __init__(self, url: str):
        self.url = url
        self.ws: Optional[WebSocket] = None
        self._recv_thread: Optional[Thread] = None
        self._running = False
        
        # Response waiters: cmd_id -> Event + result slot
        self._waiters: Dict[str, ResponseWaiter] = {}
        
        # Event subscribers (pub/sub, not consumed)
        self._subscribers: Dict[str, List[Callable]] = {}
    
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def send(self, data: str) -> None: ...
    def wait_for(self, cmd_id: str, timeout: float = 5.0) -> Packet: ...
    def subscribe(self, cmd_id: str, callback: Callable[[Packet], None]) -> None: ...
```

### 1.2 Message Routing
The RecvThread should:
1. Parse incoming packet
2. Check if any waiter matches (request/response pattern) → resolve waiter
3. Broadcast to all subscribers for that cmd_id (pub/sub pattern)

Key difference from current: **Waiters consume the message, subscribers get a copy**

### 1.3 Keepalive
- Separate thread or timer that sends keepalive every 30s
- Detects dead connections

---

## Phase 2: Sync Client

### 2.1 Replace `EmpireClient`
Replace the async `EmpireClient` with a sync version:

```python
class EmpireClient:
    def __init__(self, username: str, password: str, server: str = "EmpireEx_23"):
        self.connection = Connection(url)
        self.state = GameState()  # Can keep this, just make updates sync
        
    def login(self) -> None: ...
    def close(self) -> None: ...
    
    # High-level API
    def search_alliance(self, name: str) -> Optional[Alliance]: ...
    def get_alliance_members(self, alliance_id: int) -> List[Member]: ...
    def get_player_info(self, player_id: int) -> PlayerInfo: ...
    def send_attack(self, from_castle: int, to_coords: Tuple[int, int], troops: Dict) -> Movement: ...
```

### 2.2 Thread Safety
- Each client instance = one connection = one thread
- For parallel operations, use multiple client instances (AccountPool)
- State updates should be thread-safe (use locks if needed)

---

## Phase 3: AccountPool

### 3.1 Worker Pool
```python
class AccountPool:
    def __init__(self, accounts: List[Account], max_workers: int = 5):
        self._accounts = accounts
        self._available: Queue[EmpireClient] = Queue()
        self._lock = Lock()
    
    def initialize(self) -> None:
        """Connect all accounts."""
        
    def get_client(self, timeout: float = 30.0) -> EmpireClient:
        """Get an available client (blocks until one is free)."""
        
    def release_client(self, client: EmpireClient) -> None:
        """Return client to pool."""
        
    @contextmanager
    def client(self) -> Generator[EmpireClient, None, None]:
        """Context manager for borrowing a client."""
        client = self.get_client()
        try:
            yield client
        finally:
            self.release_client(client)
```

### 3.2 Usage Pattern
```python
pool = AccountPool(accounts, max_workers=5)
pool.initialize()

# For quick operations
with pool.client() as client:
    alliance = client.search_alliance("Dynamis")

# For parallel scanning
def scan_chunk(pool: AccountPool, kingdom: int, x: int, y: int):
    with pool.client() as client:
        return client.get_map_chunk(kingdom, x, y)

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(scan_chunk, pool, 0, x, y) for x, y in chunks]
```

---

## Phase 4: Clean API Surface

### 4.1 High-Level Methods
Replace raw packet building with clean methods:

| Current (raw) | New (clean) |
|---------------|-------------|
| `Packet.build_xt("EmpireEx_23", "gpi", {"PID": 123})` | `client.get_player_info(123)` |
| `Packet.build_xt(..., "gia", {"AID": 456})` | `client.get_alliance_info(456)` |
| `Packet.build_xt(..., "saa", {...})` | `client.search_alliance("name")` |
| Manual gaa + wait + parse | `client.get_map_chunk(kingdom, x, y)` |

### 4.2 Return Types
Methods should return parsed models, not raw dicts:
```python
def search_alliance(self, name: str) -> Optional[Alliance]:
    """Search for alliance by name. Returns None if not found."""
    
def get_alliance_members(self, alliance_id: int) -> List[AllianceMember]:
    """Get all members of an alliance."""
```

---

## Phase 5: Logging Cleanup

### 5.1 Default to WARNING
```python
# In __init__.py or config
logging.getLogger("empire_core").setLevel(logging.WARNING)
```

### 5.2 Structured Logging
- Connection events: INFO
- Packet send/recv: DEBUG
- Errors: ERROR/WARNING
- State updates: DEBUG

Users can enable verbose logging:
```python
logging.getLogger("empire_core").setLevel(logging.DEBUG)
```

---

## Phase 6: Cleanup

### 6.1 Remove Async Code
- Delete all async/await code
- Remove aiohttp dependency
- Update imports and exports

---

## File Structure (After Refactor)

```
src/empire_core/
  __init__.py
  config.py
  exceptions.py
  
  client/
    client.py          # EmpireClient (sync)
    connection.py      # Connection (sync websocket + recv thread)
    commands.py        # High-level command methods
    actions.py         # Game actions (attack, support, etc.)
  
  accounts/
    account.py         # Account dataclass
    pool.py            # AccountPool
  
  state/
    manager.py         # GameState
    models.py          # Castle, Player, Alliance, etc.
    world_models.py    # Movement, MapTile, etc.
  
  protocol/
    packet.py          # Packet parsing/building
```

---

## Implementation Order

1. [x] **Phase 1.1**: Replace `SFSConnection` with sync `Connection`
2. [x] **Phase 1.2**: Implement message routing (waiters + subscribers)
3. [x] **Phase 1.3**: Add keepalive thread
4. [x] **Phase 2.1**: Replace `EmpireClient` with sync version
5. [ ] **Phase 2.2**: Port essential commands (search_alliance, get_alliance_members, etc.)
6. [ ] **Phase 3**: Implement AccountPool
7. [ ] **Phase 4**: Add high-level API methods
8. [ ] **Phase 5**: Fix logging levels
9. [ ] **Phase 6**: Remove async code, test with Dreambot

---

## Testing Strategy

1. **Unit tests**: Mock websocket, test packet parsing
2. **Integration tests**: Real connection to test server (if available)
3. **Dreambot integration test**: Run bot with refactored EmpireCore, verify no interaction errors

---

## Notes

- The original sync GGE socket from `Dreambot.py/scripts/gge.py` is a good reference
- websocket-client library: `pip install websocket-client`
- Keep the existing Packet class - it works fine for parsing/building
- GameState can remain mostly unchanged, just make updates sync
