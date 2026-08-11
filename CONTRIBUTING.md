# Contributing to EmpireCore

This guide covers how to add new protocol commands and services to EmpireCore.

## Architecture Overview

```
src/empire_core/
├── client/
│   └── client.py          # Main EmpireClient - auto-attaches services
├── protocol/
│   ├── models/            # Pydantic models for all GGE commands
│   │   ├── base.py        # BaseRequest, BaseResponse, registry
│   │   ├── chat.py        # Chat commands (acm, acl)
│   │   ├── alliance.py    # Alliance commands (ahc, aha, ahr)
│   │   ├── castle.py      # Castle commands (gcl, dcl, jca, etc.)
│   │   └── ...
│   └── packet.py          # Low-level packet parsing
├── services/              # High-level service APIs
│   ├── base.py            # BaseService, @register_service
│   ├── alliance.py        # AllianceService
│   └── castle.py          # CastleService
├── network/               # WebSocket connection, receive loop, redaction
├── state/                 # Thread-safe game state and world models
├── storage/               # Experimental persistence (optional extra)
└── utils/                 # Enums, CDN-backed event and troop data
```

Design notes for the trickier layers live in [`docs/design/`](docs/design/) —
read [`state_management.md`](docs/design/state_management.md) before touching
`state/`.

## Adding a New Protocol Command

Protocol models define the request/response structure for GGE commands. Each command has:
- A **request model** (what you send)
- A **response model** (what you receive)

### Step 1: Add the Command Code

Add the command code to `GGECommand` in `protocol/models/base.py`:

```python
class GGECommand:
    # ... existing commands ...
    
    # Your new command
    XYZ = "xyz"  # Description of what it does
```

### Step 2: Create Request Model

Request models inherit from `BaseRequest` and define:
- `command` class variable (the command code)
- Fields with `Field(alias="X")` for wire format

```python
# protocol/models/your_domain.py

from pydantic import Field
from .base import BaseRequest

class YourRequest(BaseRequest):
    """
    Description of what this request does.
    
    Command: xyz
    Payload: {"FID": field_id, "V": value}
    """
    
    command = "xyz"
    
    field_id: int = Field(alias="FID")
    value: str = Field(alias="V")
```

**Key points:**
- Use `Field(alias="X")` to map Python names to wire format
- Add `@classmethod` factory methods for common patterns
- Document the command and payload format

### Step 3: Create Response Model

Response models inherit from `BaseResponse`:

```python
from pydantic import Field
from .base import BaseResponse

class YourResponse(BaseResponse):
    """
    Response from xyz command.
    
    Command: xyz
    Payload: {"R": result, "S": success}
    """
    
    command = "xyz"  # Auto-registers in response registry
    
    result: str = Field(alias="R")
    finished: bool = Field(alias="S", default=True)
```

**Key points:**
- Setting `command = "xyz"` auto-registers the response model — registering a
  command twice raises at class-definition time, so pick one that is not
  already in the registry
- Never name a field `success`: `BaseResponse.success` is a property derived
  from the packet's status code, and a same-named field is silently shadowed
  (pydantic warns, and your field becomes unreachable)
- Use `parse_response("xyz", payload)` to parse responses

### Step 4: Export Models

Add exports to `protocol/models/__init__.py`:

```python
from .your_domain import (
    YourRequest,
    YourResponse,
)

__all__ = [
    # ... existing exports ...
    "YourRequest",
    "YourResponse",
]
```

### Complete Example: Adding a New Command

Here's a complete example adding a hypothetical "get bookmarks" command:

```python
# protocol/models/bookmarks.py

from __future__ import annotations

from pydantic import ConfigDict, Field

from .base import BaseRequest, BaseResponse, Position


class GetBookmarksRequest(BaseRequest):
    """
    Get player's map bookmarks (illustrative command id 'zzb' — 'gbl' itself is already registered by the library).
    
    Command: zzb
    Payload: {} (empty)
    """
    
    command = "zzb"


class Bookmark(BaseResponse):
    """A single bookmark entry."""
    
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    
    bookmark_id: int = Field(alias="BID")
    name: str = Field(alias="N")
    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    kingdom_id: int = Field(alias="KID", default=0)
    
    @property
    def position(self) -> Position:
        return Position(X=self.x, Y=self.y, KID=self.kingdom_id)


class GetBookmarksResponse(BaseResponse):
    """
    Response containing player's bookmarks.
    
    Command: zzb
    Payload: {"BL": [bookmark, ...]}
    """
    
    command = "zzb"
    
    bookmarks: list[Bookmark] = Field(alias="BL", default_factory=list)


__all__ = [
    "GetBookmarksRequest",
    "GetBookmarksResponse",
    "Bookmark",
]
```

## Adding a New Service

Services provide high-level APIs that use protocol models. They are auto-attached to the client.

### Step 1: Create Service Class

```python
# services/bookmarks.py

from __future__ import annotations

import logging
import threading
from typing import Callable

from empire_core.protocol.models import (
    Bookmark,
    GetBookmarksRequest,
    GetBookmarksResponse,
)

from .base import BaseService, register_service

logger = logging.getLogger(__name__)


@register_service("bookmarks")
class BookmarksService(BaseService):
    """
    Service for bookmark operations.
    
    Accessible via client.bookmarks after auto-registration.
    
    Usage:
        client = EmpireClient(...)
        client.login()
        
        bookmarks = client.bookmarks.get_all()
        for b in bookmarks:
            print(f"{b.name} at ({b.x}, {b.y})")
    """
    
    def get_all(self, timeout: float = 5.0) -> list[Bookmark]:
        """
        Get all bookmarks.
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            List of Bookmark objects
        """
        request = GetBookmarksRequest()
        response = self.send(request, wait=True, timeout=timeout)
        
        if isinstance(response, GetBookmarksResponse):
            return response.bookmarks
        
        return []
```

### Step 2: Register Service

Add the import to `services/__init__.py`:

```python
from .base import BaseService, register_service, get_registered_services

# Import services to trigger registration
from .alliance import AllianceService
from .castle import CastleService
from .bookmarks import BookmarksService  # Add this

__all__ = [
    "BaseService",
    "register_service",
    "get_registered_services",
    # Services
    "AllianceService",
    "CastleService",
    "BookmarksService",  # Add this
]
```

### Service Patterns

#### Fire-and-forget (no response needed)

```python
def send_chat(self, message: str) -> None:
    request = AllianceChatMessageRequest.create(message)
    self.send(request)  # No wait
```

#### Wait for response

```python
def get_resources(self, castle_id: int) -> ResourceAmount | None:
    request = GetResourcesRequest(CID=castle_id)
    response = self.send(request, wait=True, timeout=5.0)
    
    if isinstance(response, GetResourcesResponse):
        return response.resources
    return None
```

#### Subscribe to incoming messages

Three things this pattern must get right, all of them learned the hard way:
register **and** unregister, guard the list with a lock, and never swallow a
callback's exception.

```python
def __init__(self, client) -> None:
    super().__init__(client)
    self._callbacks: list[Callable] = []
    # Callbacks are registered from user threads and dispatched from the
    # receive thread. CPython's per-op atomicity is not a guarantee to build
    # on and does not hold on free-threaded builds, so take the lock.
    self._callback_lock = threading.Lock()

    self.on_response("acm", self._handle_message)

def on_message(self, callback: Callable) -> None:
    """Register a callback for incoming messages."""
    with self._callback_lock:
        self._callbacks.append(callback)

def remove_message_callback(self, callback: Callable) -> None:
    """Detach a callback registered with :meth:`on_message`.

    Always ship the unregister half: a consumer that re-wires its callbacks
    after each reconnect otherwise accumulates duplicates with no way out.
    """
    with self._callback_lock:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

def _handle_message(self, response) -> None:
    """Internal handler; dispatches to callbacks outside the lock."""
    if not isinstance(response, AllianceChatMessageResponse):
        return

    with self._callback_lock:
        callbacks = list(self._callbacks)   # snapshot: a callback may unregister

    for callback in callbacks:
        try:
            callback(response)
        except Exception:
            # One bad consumer callback must not kill the receive thread or
            # stop the others -- but it must never vanish either.
            logger.exception("Error in message callback")
```

## BaseService API Reference

```python
class BaseService:
    def __init__(self, client: EmpireClient) -> None:
        self.client = client
    
    @property
    def zone(self) -> str:
        """Get the game zone from client config."""
        return self.client.config.default_zone
    
    def send(
        self, 
        request: BaseRequest, 
        wait: bool = False, 
        timeout: float = 5.0
    ) -> BaseResponse | None:
        """
        Send a request to the server.
        
        Args:
            request: The request model to send
            wait: Whether to wait for a response
            timeout: Timeout in seconds when waiting
            
        Returns:
            The parsed response if wait=True, otherwise None
        """
    
    def on_response(self, command: str, handler: Callable) -> None:
        """
        Register a handler for a specific response type.
        
        Args:
            command: The command code to handle (e.g., "acm")
            handler: Callback that receives the parsed response
        """
```

## Protocol Model Conventions

### Field Naming

Use descriptive Python names with short aliases:

```python
# Good
player_id: int = Field(alias="PID")
castle_name: str = Field(alias="CN")

# Bad - don't use the wire names directly
PID: int
CN: str
```

### Optional Fields

Use `| None` with `default=None`:

```python
error_message: str | None = Field(alias="EM", default=None)
```

### Lists

Use `default_factory=list`:

```python
castles: list[CastleInfo] = Field(alias="C", default_factory=list)
```

### Nested Models

Create separate model classes for nested structures:

```python
class ChatMessageData(BaseModel):
    player_name: str = Field(alias="PN")
    message_text: str = Field(alias="MT")

class AllianceChatMessageResponse(BaseResponse):
    command = "acm"
    chat_message: ChatMessageData = Field(alias="CM")
```

### Factory Methods

Add `@classmethod` factory methods for common patterns:

```python
class HelpMemberRequest(BaseRequest):
    command = "ahc"
    
    player_id: int = Field(alias="PID")
    castle_id: int = Field(alias="CID")
    help_type: int = Field(alias="HT")
    
    @classmethod
    def heal(cls, player_id: int, castle_id: int) -> "HelpMemberRequest":
        """Create a heal help request."""
        return cls(PID=player_id, CID=castle_id, HT=HelpType.HEAL)
    
    @classmethod
    def repair(cls, player_id: int, castle_id: int) -> "HelpMemberRequest":
        """Create a repair help request."""
        return cls(PID=player_id, CID=castle_id, HT=HelpType.REPAIR)
```

## Development Setup

```bash
uv sync --extra dev     # `dev` is an extra, not a default group: a plain
                        # `uv sync` leaves you without pytest/ruff/mypy
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
```

The commit-msg hook matters: commits must follow
[Conventional Commits](https://www.conventionalcommits.org/), because the
release version and changelog are derived from them.

> [!IMPORTANT]
> A breaking change needs a **`BREAKING CHANGE:`** footer (or
> `BREAKING-CHANGE:`). `BREAKING:` alone looks right, passes review, and is
> silently ignored by the release tooling — the change then ships with nothing
> in the changelog telling users why their code stopped working.
>
> ```
> fix(pool): raise instead of returning None when every candidate fails
>
> BREAKING CHANGE: lease() raises LoginError when all candidates fail; None
> now means only "no candidates".
> ```

If you change dependencies, run `uv lock` and commit `uv.lock` with the
change; CI installs with `--locked` and will reject a stale lockfile.

## Testing

```bash
uv run pytest                       # the suite
uv run pre-commit run --all-files   # exactly what CI's lint job runs
```

> [!TIP]
> `uv run mypy src` is **not** enough — the hook type-checks `tests/` and
> `examples/` too, so run pre-commit before pushing.

Verify the service registry still wires up:

```bash
uv run python -c "from empire_core.services import get_registered_services; print(get_registered_services())"
```

### What to test

This library parses bytes from a server we do not control, so a fix is not
finished until a test pins it. **Watch the test fail first** — a test that was
green before your change proves nothing about your change.

- **Drift.** For every accessor a caller is told to use, add a case where the
  server sends the wrong shape or type (a string where an int is documented, a
  dict where a list is). It must skip or degrade with a log, never raise a raw
  `pydantic.ValidationError` or `AttributeError` past the library's API.
- **Silence.** If your code skips or degrades bad input, assert on the log
  record (`caplog`). A silent skip turns a server-side schema change into
  quietly incomplete results, which is far harder to diagnose than a crash.
- **Concurrency.** State is written by the receive thread and read by user
  threads. If you touch it, test it under a concurrent writer — several real
  bugs here only appeared that way.
- **Failure, not just success.** Cover the timeout, the non-zero error code and
  the dropped connection, and assert the exception *type* callers are told to
  catch.

## Guidelines

1. **Log to a named logger** — Use `logging.getLogger(__name__)`; never print. Never swallow an exception without at least logging it
2. **Use type hints** — All public methods should have complete type hints
3. **Document wire format** — Include the command code and payload format in docstrings
4. **Fail loudly and precisely** — Raise the typed exceptions from `empire_core.exceptions` (`CommandError`, `EmpireTimeoutError`, ...) instead of collapsing failures into `None`. Action methods may return `False` for server-rejected actions, but transport failures must raise
5. **Never return an empty collection to mean "it failed"** — `[]` must mean "there is nothing", so a caller can trust it. If the answer is unknown, raise
6. **Degrade loudly** — When you skip a malformed entry, count the skips and log one warning per response. Silently dropping drifted data turns a schema change into a "successful" empty result
7. **Never leak another library's exceptions** — `pydantic.ValidationError`, `socket.error` and friends must not escape the public API; wrap them in an `EmpireError` subclass. Callers are told `except EmpireError` is enough
8. **Swap, don't mutate** — Readers hold references to state containers without a lock. Build the replacement and swap it in rather than editing in place, so nobody observes a half-updated object
9. **Redact credentials before logging** — Frames can carry passwords. Anything that logs raw wire data must go through the redaction helpers, at any log level
10. **Use descriptive names** — Python names should be readable, aliases handle the wire format
11. **Anything public is forever-ish** — Re-export it from `empire_core/__init__.py` and treat deep-module paths as internal. Removing or renaming an exported name is a breaking change and needs the footer above
